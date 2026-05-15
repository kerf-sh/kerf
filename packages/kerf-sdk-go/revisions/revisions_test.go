package revisions_test

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
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":[{"id":"rev_1","file_id":"f1","created_at":"2026-01-01T00:00:00Z"}]}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	revs, err := c.Revisions.List(context.Background(), "proj_1", "f1", nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(revs) == 0 || revs[0].ID != "rev_1" {
		t.Fatalf("unexpected result: %+v", revs)
	}
}

func TestRead(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":{"id":"rev_1","file_id":"f1","created_at":"2026-01-01T00:00:00Z"}}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	rev, err := c.Revisions.Read(context.Background(), "proj_1", "f1", "rev_1")
	if err != nil {
		t.Fatal(err)
	}
	if rev.ID != "rev_1" {
		t.Fatalf("unexpected revision: %+v", rev)
	}
}

func TestRestore(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":null}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	if err := c.Revisions.Restore(context.Background(), "proj_1", "f1", "rev_1"); err != nil {
		t.Fatal(err)
	}
}
