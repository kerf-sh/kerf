package tools

import (
	"context"
	"encoding/json"
	"testing"
)

func TestDocsCorpusLoaded(t *testing.T) {
	if len(docCorpus) == 0 {
		t.Fatal("docCorpus is empty — embed failed")
	}
	for _, name := range []string{"index", "assembly", "sketch", "feature", "drawing", "part", "circuit", "jscad"} {
		key := "/docs/llm/" + name + ".md"
		if _, ok := docCorpus[key]; !ok {
			t.Errorf("missing doc: %s", key)
		}
	}
}

func TestSearchKerfDocsFinds(t *testing.T) {
	args, _ := json.Marshal(map[string]any{"query": "fillet feature edge", "limit": 3})
	out, err := runSearchKerfDocs(context.Background(), ProjectCtx{}, args)
	if err != nil {
		t.Fatal(err)
	}
	var res struct {
		Hits []struct {
			Path  string `json:"path"`
			Score int    `json:"score"`
		} `json:"hits"`
	}
	if err := json.Unmarshal([]byte(out), &res); err != nil {
		t.Fatal(err)
	}
	if len(res.Hits) == 0 {
		t.Fatal("expected hits for 'fillet feature edge'")
	}
	if res.Hits[0].Path != "/docs/llm/feature.md" {
		t.Errorf("expected feature.md as top hit, got %s", res.Hits[0].Path)
	}
}

func TestDocCorpusReadFile(t *testing.T) {
	body, ok := docCorpusReadFile("/docs/llm/index.md")
	if !ok {
		t.Fatal("index.md not found")
	}
	if len(body) == 0 {
		t.Fatal("index.md empty")
	}
	_, ok = docCorpusReadFile("/docs/llm/nonexistent.md")
	if ok {
		t.Fatal("nonexistent should miss")
	}
}
