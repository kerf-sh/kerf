package kerf

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// rpcRequest is the JSON-RPC 2.0 request envelope.
type rpcRequest struct {
	JSONRPC string `json:"jsonrpc"`
	ID      string `json:"id"`
	Method  string `json:"method"`
	Params  any    `json:"params"`
}

// rpcResponse is the JSON-RPC 2.0 response envelope.
type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      string          `json:"id"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

// rpcError is the error object within a JSON-RPC 2.0 response.
type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    any    `json:"data,omitempty"`
}

// newRequestID returns a random UUID v4 string (no external dependency).
func newRequestID() string {
	b := make([]byte, 16)
	_, _ = io.ReadFull(rand.Reader, b)
	b[6] = (b[6] & 0x0f) | 0x40 // version 4
	b[8] = (b[8] & 0x3f) | 0x80 // variant 10
	dst := make([]byte, 36)
	hex.Encode(dst[0:8], b[0:4])
	dst[8] = '-'
	hex.Encode(dst[9:13], b[4:6])
	dst[13] = '-'
	hex.Encode(dst[14:18], b[6:8])
	dst[18] = '-'
	hex.Encode(dst[19:23], b[8:10])
	dst[23] = '-'
	hex.Encode(dst[24:36], b[10:16])
	return string(dst)
}

// httpClient is the shared transport used by all sub-package clients.
type httpClient struct {
	client   *http.Client
	apiURL   string
	apiToken string
}

// Call executes a single JSON-RPC 2.0 request and decodes the result into dst.
//
// On a JSON-RPC error response, it returns *Error. HTTP-level errors are also
// wrapped as *Error with code -32603 (internal error).
// Call satisfies the Caller interface in each sub-package.
func (h *httpClient) Call(ctx context.Context, method string, params any, dst any) error {
	req := rpcRequest{
		JSONRPC: "2.0",
		ID:      newRequestID(),
		Method:  method,
		Params:  params,
	}

	body, err := json.Marshal(req)
	if err != nil {
		return &Error{Code: -32700, Message: fmt.Sprintf("kerf: marshal request: %s", err)}
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, h.apiURL+"/v1/rpc", bytes.NewReader(body))
	if err != nil {
		return &Error{Code: -32603, Message: fmt.Sprintf("kerf: build request: %s", err)}
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Authorization", "Bearer "+h.apiToken)

	resp, err := h.client.Do(httpReq)
	if err != nil {
		return &Error{Code: -32603, Message: fmt.Sprintf("kerf: http: %s", err)}
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &Error{Code: -32603, Message: fmt.Sprintf("kerf: http %d", resp.StatusCode)}
	}

	var rpcResp rpcResponse
	if err := json.NewDecoder(resp.Body).Decode(&rpcResp); err != nil {
		return &Error{Code: -32603, Message: fmt.Sprintf("kerf: decode response: %s", err)}
	}

	if rpcResp.Error != nil {
		e := &Error{
			Code:    rpcResp.Error.Code,
			Message: rpcResp.Error.Message,
			Data:    rpcResp.Error.Data,
		}
		return rpcErrorToSentinel(e)
	}

	if dst != nil && rpcResp.Result != nil {
		if err := json.Unmarshal(rpcResp.Result, dst); err != nil {
			return &Error{Code: -32603, Message: fmt.Sprintf("kerf: decode result: %s", err)}
		}
	}
	return nil
}
