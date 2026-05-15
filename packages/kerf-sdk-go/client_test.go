package kerf_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	kerf "github.com/kerf-sh/kerf-sdk-go"
	"github.com/kerf-sh/kerf-sdk-go/files"
)

// rpcHandler returns an http.HandlerFunc that always responds with a fixed JSON body.
func rpcHandler(body string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}
}

// rpcErrorBody builds a JSON-RPC error response body.
func rpcErrorBody(id string, code int, message string) string {
	return `{"jsonrpc":"2.0","id":"` + id + `","error":{"code":` +
		jsonInt(code) + `,"message":"` + message + `"}}`
}

func jsonInt(n int) string {
	b, _ := json.Marshal(n)
	return string(b)
}

// captureHandler records the last request for inspection.
type captureHandler struct {
	AuthHeader string
	Body       string
}

func (h *captureHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	h.AuthHeader = r.Header.Get("Authorization")
	var buf strings.Builder
	_ = json.NewDecoder(r.Body).Decode(new(any)) // drain
	h.Body = buf.String()
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"jsonrpc":"2.0","id":"x","result":[]}`))
}

// ---- Tests ----------------------------------------------------------------

func TestAuthHeaderSent(t *testing.T) {
	capture := &captureHandler{}
	srv := httptest.NewServer(capture)
	defer srv.Close()

	c := kerf.New(srv.URL, "kerf_sk_test")
	_, _ = c.Files.List(context.Background(), "proj_1")

	if capture.AuthHeader != "Bearer kerf_sk_test" {
		t.Fatalf("expected Authorization: Bearer kerf_sk_test, got %q", capture.AuthHeader)
	}
}

func TestJSONRPCError_Unauthorized(t *testing.T) {
	srv := httptest.NewServer(rpcHandler(rpcErrorBody("x", -32001, "unauthorized")))
	defer srv.Close()

	c := kerf.New(srv.URL, "tok")
	_, err := c.Files.List(context.Background(), "proj_1")

	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !errors.Is(err, kerf.ErrUnauthorized) {
		t.Fatalf("expected ErrUnauthorized, got %v", err)
	}
}

func TestJSONRPCError_NotFound(t *testing.T) {
	srv := httptest.NewServer(rpcHandler(rpcErrorBody("x", -32004, "not found")))
	defer srv.Close()

	c := kerf.New(srv.URL, "tok")
	_, err := c.Files.Read(context.Background(), "proj_1", "file_1")

	if !errors.Is(err, kerf.ErrNotFound) {
		t.Fatalf("expected ErrNotFound, got %v", err)
	}
}

func TestJSONRPCError_RateLimited(t *testing.T) {
	srv := httptest.NewServer(rpcHandler(rpcErrorBody("x", -32429, "rate limited")))
	defer srv.Close()

	c := kerf.New(srv.URL, "tok")
	_, err := c.Files.List(context.Background(), "proj_1")

	if !errors.Is(err, kerf.ErrRateLimited) {
		t.Fatalf("expected ErrRateLimited, got %v", err)
	}
}

func TestNetworkFailure(t *testing.T) {
	// Point at a server that immediately closes.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := srv.URL
	srv.Close() // close before the request reaches it

	c := kerf.New(url, "tok")
	_, err := c.Files.List(context.Background(), "proj_1")
	if err == nil {
		t.Fatal("expected network error, got nil")
	}
	var kErr *kerf.Error
	if !errors.As(err, &kErr) {
		t.Fatalf("expected *kerf.Error wrapping network failure, got %T: %v", err, err)
	}
}

func TestFromEnv_MissingToken(t *testing.T) {
	os.Unsetenv("KERF_API_TOKEN")
	os.Unsetenv("KERF_API_URL")

	_, err := kerf.FromEnv()
	if err == nil {
		t.Fatal("expected error when KERF_API_TOKEN is unset")
	}
	if !errors.Is(err, kerf.ErrMissingEnv) {
		t.Fatalf("expected ErrMissingEnv, got %v", err)
	}
}

func TestFromEnv_WithToken(t *testing.T) {
	srv := httptest.NewServer(rpcHandler(`{"jsonrpc":"2.0","id":"x","result":[]}`))
	defer srv.Close()

	t.Setenv("KERF_API_TOKEN", "kerf_sk_env")
	t.Setenv("KERF_API_URL", srv.URL)

	c, err := kerf.FromEnv()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	_, err = c.Files.List(context.Background(), "proj_1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestFilesList_HappyPath(t *testing.T) {
	body := `{"jsonrpc":"2.0","id":"x","result":[{"id":"f1","name":"part.ks","kind":"file"}]}`
	srv := httptest.NewServer(rpcHandler(body))
	defer srv.Close()

	c := kerf.New(srv.URL, "tok")
	fs, err := c.Files.List(context.Background(), "proj_1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(fs) != 1 || fs[0].Name != "part.ks" {
		t.Fatalf("unexpected result: %+v", fs)
	}
}

func TestErrorIs_MultipleInstances(t *testing.T) {
	// Two separate *Error values with the same code must satisfy errors.Is.
	a := &kerf.Error{Code: -32001, Message: "unauthorized from server"}
	if !errors.Is(a, kerf.ErrUnauthorized) {
		t.Fatal("errors.Is should match on Code")
	}
}

// compile-time: files.Client uses files.Caller not *kerf.Client
var _ files.Caller = (interface {
	Call(ctx context.Context, method string, params any, dst any) error
})(nil)
