package equations_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	kerf "github.com/kerf-sh/kerf-sdk-go"
)

func serve(body string) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(body))
	}))
}

func TestRead(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":[{"name":"width","expression":"50","value":50}]}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	eqs, err := c.Equations.Read(context.Background(), "proj_1", "f1")
	if err != nil {
		t.Fatal(err)
	}
	if len(eqs) == 0 || eqs[0].Name != "width" {
		t.Fatalf("unexpected result: %+v", eqs)
	}
}

func TestSet(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":null}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	if err := c.Equations.Set(context.Background(), "proj_1", "f1", "height", "100"); err != nil {
		t.Fatal(err)
	}
}
