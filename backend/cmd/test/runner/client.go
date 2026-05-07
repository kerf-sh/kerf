package runner

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client is a thin HTTP wrapper used by scenarios. It targets one base URL
// and lets callers thread a bearer token through optional second-arg.
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

// NewClient builds a client targeted at the given base URL (typically
// httptest.Server.URL).
func NewClient(baseURL string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTP:    &http.Client{Timeout: 30 * time.Second},
	}
}

// Do issues a request and returns (status, body, error). When body is non-nil,
// it's JSON-encoded; pass a *bytes.Buffer to send raw bytes.
func (c *Client) Do(method, path string, body any, token string) (int, []byte, error) {
	var rdr io.Reader
	contentType := ""
	if body != nil {
		switch v := body.(type) {
		case []byte:
			rdr = bytes.NewReader(v)
			contentType = "application/octet-stream"
		case io.Reader:
			rdr = v
		case string:
			rdr = strings.NewReader(v)
			contentType = "application/octet-stream"
		default:
			b, err := json.Marshal(v)
			if err != nil {
				return 0, nil, fmt.Errorf("marshal body: %w", err)
			}
			rdr = bytes.NewReader(b)
			contentType = "application/json"
		}
	}
	req, err := http.NewRequest(method, c.BaseURL+path, rdr)
	if err != nil {
		return 0, nil, err
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return resp.StatusCode, nil, err
	}
	return resp.StatusCode, respBody, nil
}

// DoJSON is a convenience that decodes the response body into out (when
// non-nil) on 2xx. On non-2xx it returns the raw body so the caller can
// surface the server's error.
func (c *Client) DoJSON(method, path string, body any, token string, out any) (int, []byte, error) {
	status, raw, err := c.Do(method, path, body, token)
	if err != nil {
		return status, raw, err
	}
	if out != nil && status >= 200 && status < 300 && len(raw) > 0 {
		if err := json.Unmarshal(raw, out); err != nil {
			return status, raw, fmt.Errorf("decode response: %w (body=%s)", err, truncate(string(raw), 200))
		}
	}
	return status, raw, nil
}

// DoRaw is for scenarios that need full control: it returns the *http.Response.
// Caller MUST close resp.Body.
func (c *Client) DoRaw(req *http.Request) (*http.Response, error) {
	return c.HTTP.Do(req)
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
