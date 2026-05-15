package configurations_test

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

func TestList(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":[{"id":"cfg_1","label":"Default","params":{}}]}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	cfgs, err := c.Configurations.List(context.Background(), "proj_1", "f1")
	if err != nil {
		t.Fatal(err)
	}
	if len(cfgs) == 0 || cfgs[0].Label != "Default" {
		t.Fatalf("unexpected result: %+v", cfgs)
	}
}

func TestActivate(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":null}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	if err := c.Configurations.Activate(context.Background(), "proj_1", "f1", "cfg_1"); err != nil {
		t.Fatal(err)
	}
}
