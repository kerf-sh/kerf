package files_test

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
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":[{"id":"f1","name":"bracket.ks","kind":"file"}]}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	fs, err := c.Files.List(context.Background(), "proj_1")
	if err != nil {
		t.Fatal(err)
	}
	if len(fs) == 0 || fs[0].ID != "f1" {
		t.Fatalf("unexpected result: %+v", fs)
	}
}

func TestRead(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":{"id":"f1","name":"bracket.ks","kind":"file","content":"solid {...}"}}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	fc, err := c.Files.Read(context.Background(), "proj_1", "f1")
	if err != nil {
		t.Fatal(err)
	}
	if fc.Content == "" {
		t.Fatal("expected non-empty content")
	}
}

func TestWrite(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":{"ok":true,"revision_id":"rev_1"}}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	wr, err := c.Files.Write(context.Background(), "proj_1", "f1", "new content")
	if err != nil {
		t.Fatal(err)
	}
	if !wr.OK {
		t.Fatal("expected ok:true")
	}
}

func TestCreate(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":{"id":"f2","name":"new.ks","kind":"file"}}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	fi, err := c.Files.Create(context.Background(), "proj_1", "new.ks", nil)
	if err != nil {
		t.Fatal(err)
	}
	if fi.ID == "" {
		t.Fatal("expected non-empty id")
	}
}

func TestDelete(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":null}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	if err := c.Files.Delete(context.Background(), "proj_1", "f1"); err != nil {
		t.Fatal(err)
	}
}
