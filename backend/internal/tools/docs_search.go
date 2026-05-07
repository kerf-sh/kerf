package tools

// search_kerf_docs + the embedded LLM authoring corpus.
//
// The corpus is a small set of markdown pages (see ../llm/docs/) covering
// every non-`.jscad` file kind plus a JSCAD authoring overview. The LLM uses
// search_kerf_docs to find relevant pages, then read_file('/docs/llm/<page>')
// to load full content (read_file recognises the special /docs/llm/ prefix
// and routes to this in-memory corpus instead of the project file tree).
//
// Indexing is keyword-based: lowercase substring match scored by hit
// location (title × 5, headers × 2, body × 1). Ranks the top N hits and
// returns excerpts. No FTS, no embeddings — at this corpus size, plain
// substring search is precise enough and adds zero deps.

import (
	"context"
	"encoding/json"
	"path"
	"sort"
	"strings"

	"github.com/imranp/kerf/backend/internal/llm"
)

// The corpus is embedded into the binary via internal/llm/docs.go (embed
// patterns cannot escape their source-file's directory, so the markdown
// lives next to its embed declaration, not next to this file).

// docPage is a parsed corpus page. titleLine is the H1 (without the leading
// "# "); headers is the lowercased concatenation of every H1/H2/H3 heading
// for fast title/header scoring.
type docPage struct {
	path        string // canonical "/docs/llm/<file>" path the LLM uses
	title       string // first H1 line, sans markdown
	body        string // raw markdown content
	bodyLower   string // lowercased body for substring matches
	titleLower  string
	headerLower string // lowercased concatenation of every # / ## / ### line
}

// docCorpus is the loaded index. Built once at package init.
var docCorpus = func() map[string]*docPage {
	out := map[string]*docPage{}
	entries, err := llm.Docs.ReadDir(llm.DocsRoot)
	if err != nil {
		// At binary build time the embed must have succeeded; a runtime read
		// error here means the embedded FS is empty/corrupt. Return an empty
		// map so search returns no hits and read_file falls through cleanly.
		return out
	}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		if !strings.HasSuffix(strings.ToLower(name), ".md") {
			continue
		}
		raw, err := llm.Docs.ReadFile(path.Join(llm.DocsRoot, name))
		if err != nil {
			continue
		}
		body := string(raw)
		title, headerLines := extractDocTitleAndHeaders(body)
		key := "/docs/llm/" + name
		out[key] = &docPage{
			path:        key,
			title:       title,
			body:        body,
			bodyLower:   strings.ToLower(body),
			titleLower:  strings.ToLower(title),
			headerLower: strings.ToLower(strings.Join(headerLines, "\n")),
		}
	}
	return out
}()

// extractDocTitleAndHeaders walks the doc top-down for the first H1 (becomes
// the title), and collects every H1/H2/H3 line for header scoring.
func extractDocTitleAndHeaders(body string) (string, []string) {
	var title string
	var headers []string
	for _, line := range strings.Split(body, "\n") {
		trim := strings.TrimSpace(line)
		if strings.HasPrefix(trim, "# ") {
			h := strings.TrimSpace(strings.TrimPrefix(trim, "#"))
			if title == "" {
				title = h
			}
			headers = append(headers, h)
			continue
		}
		if strings.HasPrefix(trim, "## ") || strings.HasPrefix(trim, "### ") {
			h := strings.TrimSpace(strings.TrimLeft(trim, "#"))
			headers = append(headers, h)
		}
	}
	return title, headers
}

// docCorpusLookup returns the embedded page at /docs/llm/<file>, or nil if
// no such page exists. Exported via docCorpusReadFile so file_tools' read_file
// can route /docs/llm/ paths here.
func docCorpusLookup(p string) *docPage {
	if d, ok := docCorpus[p]; ok {
		return d
	}
	// Tolerate trailing/leading whitespace and missing .md.
	clean := strings.TrimSpace(p)
	if !strings.HasSuffix(strings.ToLower(clean), ".md") {
		clean = clean + ".md"
	}
	if d, ok := docCorpus[clean]; ok {
		return d
	}
	return nil
}

// docCorpusReadFile returns the page body if `p` matches an embedded page.
// Returns ("", false) otherwise so callers can fall back to the project tree.
func docCorpusReadFile(p string) (string, bool) {
	d := docCorpusLookup(p)
	if d == nil {
		return "", false
	}
	return d.body, true
}

// ----------------------- search_kerf_docs ------------------------------

var searchKerfDocsSpec = llm.ToolSpec{
	Name: "search_kerf_docs",
	Description: "Search the embedded Kerf authoring corpus by keyword. Returns the top hits as {path, title, excerpt, score}. Use this BEFORE editing a non-.jscad file kind (sketch / assembly / drawing / part / feature / circuit) so you have the JSON shape and conventions in context. Then read the matching page via read_file('/docs/llm/<file>').",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"query": map[string]any{
				"type":        "string",
				"description": "Free-text query. Lowercase substring match against page title, headers, and body.",
			},
			"limit": map[string]any{
				"type":        "integer",
				"description": "Maximum number of hits to return. Default 5; max 10.",
			},
		},
		"required": []string{"query"},
	},
}

type searchKerfDocsArgs struct {
	Query string `json:"query"`
	Limit int    `json:"limit"`
}

type docHit struct {
	Path    string `json:"path"`
	Title   string `json:"title"`
	Excerpt string `json:"excerpt"`
	Score   int    `json:"score"`
}

func runSearchKerfDocs(_ context.Context, _ ProjectCtx, args json.RawMessage) (string, error) {
	var a searchKerfDocsArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	q := strings.TrimSpace(a.Query)
	if q == "" {
		return errPayload("query is required", "BAD_ARGS"), nil
	}
	limit := a.Limit
	if limit <= 0 {
		limit = 5
	}
	if limit > 10 {
		limit = 10
	}

	// Tokenise the query on whitespace so multi-word queries score by hit
	// across all tokens. We treat each token independently and sum.
	tokens := splitDocQuery(q)
	if len(tokens) == 0 {
		return errPayload("query is required", "BAD_ARGS"), nil
	}

	// Stable iteration order so equal-scoring pages return in a consistent
	// order across requests (alphabetical by path).
	keys := make([]string, 0, len(docCorpus))
	for k := range docCorpus {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	hits := make([]docHit, 0, len(docCorpus))
	for _, k := range keys {
		d := docCorpus[k]
		if d == nil {
			continue
		}
		score := 0
		for _, tok := range tokens {
			score += 5 * strings.Count(d.titleLower, tok)
			score += 2 * strings.Count(d.headerLower, tok)
			score += strings.Count(d.bodyLower, tok)
		}
		if score == 0 {
			continue
		}
		excerpt := docExcerptAround(d.body, d.bodyLower, tokens)
		hits = append(hits, docHit{
			Path:    d.path,
			Title:   d.title,
			Excerpt: excerpt,
			Score:   score,
		})
	}

	sort.SliceStable(hits, func(i, j int) bool {
		if hits[i].Score != hits[j].Score {
			return hits[i].Score > hits[j].Score
		}
		return hits[i].Path < hits[j].Path
	})
	if len(hits) > limit {
		hits = hits[:limit]
	}

	return okPayload(map[string]any{
		"query": a.Query,
		"hits":  hits,
		"total": len(hits),
	}), nil
}

// splitDocQuery returns the lowercased whitespace-split tokens of q, dropping
// empties and single-character noise.
func splitDocQuery(q string) []string {
	q = strings.ToLower(q)
	rough := strings.FieldsFunc(q, func(r rune) bool {
		switch r {
		case ' ', '\t', '\n', '\r', ',', ';', ':', '?', '!':
			return true
		}
		return false
	})
	out := make([]string, 0, len(rough))
	for _, t := range rough {
		t = strings.TrimSpace(t)
		if len(t) == 0 {
			continue
		}
		out = append(out, t)
	}
	return out
}

// docExcerptAround returns ~300 chars of the body centred on the first hit
// of any token. Falls back to the leading 300 chars when no token hits.
func docExcerptAround(body, bodyLower string, tokens []string) string {
	const window = 300
	idx := -1
	for _, tok := range tokens {
		i := strings.Index(bodyLower, tok)
		if i < 0 {
			continue
		}
		if idx < 0 || i < idx {
			idx = i
		}
	}
	if idx < 0 {
		// Fall back to the first 300 chars.
		if len(body) <= window {
			return body
		}
		return body[:window] + "…"
	}
	start := idx - window/2
	if start < 0 {
		start = 0
	}
	end := start + window
	if end > len(body) {
		end = len(body)
	}
	prefix := ""
	if start > 0 {
		prefix = "…"
	}
	suffix := ""
	if end < len(body) {
		suffix = "…"
	}
	return prefix + strings.TrimSpace(body[start:end]) + suffix
}
