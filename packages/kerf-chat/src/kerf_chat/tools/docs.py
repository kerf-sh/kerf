import json
import re
from pathlib import Path
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx

# llm_docs corpus has moved into the kerf-chat plugin package.  Try the new
# location first; fall back to the legacy ``backend/llm_docs`` for any tests
# still asserting old paths.
try:
    import kerf_chat as _kerf_chat
    _DOCS_DIR = Path(_kerf_chat.__file__).resolve().parent.parent.parent / "llm_docs"
    if not _DOCS_DIR.exists():
        raise ImportError("llm_docs not found alongside kerf-chat")
except ImportError:
    _DOCS_DIR = Path(__file__).resolve().parent.parent / "llm_docs"
_HEADER_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


search_kerf_docs_spec = ToolSpec(
    name="search_kerf_docs",
    description="Search the embedded Kerf authoring corpus by keyword. Returns the top hits as {path, title, excerpt, score}.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    },
)


@register(search_kerf_docs_spec)
async def run_search_kerf_docs(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    query = a.get("query", "").strip()
    if not query:
        return err_payload("query is required", "BAD_ARGS")

    limit = a.get("limit", 5)
    if limit <= 0:
        limit = 5
    if limit > 10:
        limit = 10

    tokens = query.lower().split()
    hits = []

    corpus = doc_corpus()
    for key, page in corpus.items():
        score = 0
        for tok in tokens:
            score += 5 * page["title_lower"].count(tok)
            score += 2 * page["header_lower"].count(tok)
            score += page["body_lower"].count(tok)
        if score > 0:
            excerpt = page["body"][:300] + "..." if len(page["body"]) > 300 else page["body"]
            hits.append({"path": key, "title": page["title"], "excerpt": excerpt, "score": score})

    hits.sort(key=lambda h: (-h["score"], h["path"]))
    hits = hits[:limit]

    return ok_payload({"query": query, "hits": hits, "total": len(hits)})


_doc_corpus_cache = None


def doc_corpus() -> dict:
    global _doc_corpus_cache
    if _doc_corpus_cache is not None:
        return _doc_corpus_cache

    out = {}
    if _DOCS_DIR.is_dir():
        for path in sorted(_DOCS_DIR.glob("*.md")):
            body = path.read_text(encoding="utf-8")
            h1 = _H1_RE.search(body)
            title = h1.group(1).strip() if h1 else path.stem
            headers = " ".join(m.group(1) for m in _HEADER_RE.finditer(body))
            key = f"/docs/llm/{path.name}"
            out[key] = {
                "title": title,
                "body": body,
                "title_lower": title.lower(),
                "header_lower": headers.lower(),
                "body_lower": body.lower(),
            }
    _doc_corpus_cache = out
    return _doc_corpus_cache


def doc_corpus_read_file(path: str) -> str:
    corpus = doc_corpus()
    page = corpus.get(path)
    if page:
        return page["body"]
    if not path.endswith(".md"):
        page = corpus.get(path + ".md")
        if page:
            return page["body"]
    return None
