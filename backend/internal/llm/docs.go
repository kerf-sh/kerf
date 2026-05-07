package llm

// Embedded LLM authoring corpus.
//
// The markdown corpus under ./docs/ teaches the assistant the canonical
// shape of every non-`.jscad` file kind (sketch / assembly / drawing / part
// / feature / circuit) plus a short JSCAD overview. The `tools` package
// reads them out of `Docs` to power search_kerf_docs and the special
// /docs/llm/<page> read_file route.
//
// Embedding lives in this package (not `tools`) because go:embed patterns
// can't escape the source-file's package directory — and the markdown
// happens to live alongside this file.

import "embed"

// Docs is the embedded authoring corpus; the consumer reads files via
// Docs.ReadDir("docs") and Docs.ReadFile("docs/<name>.md").
//
//go:embed all:docs
var Docs embed.FS

// DocsRoot is the directory inside Docs that holds the markdown.
const DocsRoot = "docs"
