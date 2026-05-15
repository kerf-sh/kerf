package docs_test

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

func TestSearch(t *testing.T) {
	srv := serve(`{"jsonrpc":"2.0","id":"x","result":[{"id":"doc_1","title":"Equations","excerpt":"Use equations to...","score":0.95}]}`)
	defer srv.Close()
	c := kerf.New(srv.URL, "tok")
	results, err := c.Docs.Search(context.Background(), "equations", nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) == 0 || results[0].Title != "Equations" {
		t.Fatalf("unexpected result: %+v", results)
	}
}
