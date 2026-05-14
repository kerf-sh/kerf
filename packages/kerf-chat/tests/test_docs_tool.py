"""
Tests for kerf_chat.tools.docs — doc corpus search tool.

No DB required; exercises pure search logic and the corpus loader against
the llm_docs bundled with the kerf-chat package.
"""
import asyncio
import json
import sys
import types

import pytest

# ── Stub tools.context so the @register decorator doesn't choke ──────────────
# (backend/ is on sys.path via conftest.py, so tools.context is real; but just
# in case it isn't available in a minimal install we set a fallback stub)
if "tools.context" not in sys.modules:
    _ctx_stub = types.ModuleType("tools.context")
    _ctx_stub.ProjectCtx = type("ProjectCtx", (), {})
    sys.modules["tools.context"] = _ctx_stub

# ── Import module under test ──────────────────────────────────────────────────
from kerf_chat.tools.docs import (
    doc_corpus,
    doc_corpus_read_file,
    run_search_kerf_docs,
    search_kerf_docs_spec,
    _DOCS_DIR,
)


# ── Corpus loader ─────────────────────────────────────────────────────────────

def test_docs_dir_exists():
    """llm_docs directory must be present alongside the package."""
    assert _DOCS_DIR.is_dir(), f"llm_docs not found at {_DOCS_DIR}"


def test_corpus_non_empty():
    corpus = doc_corpus()
    assert len(corpus) > 0, "doc corpus should have at least one page"


def test_corpus_keys_use_docs_llm_prefix():
    corpus = doc_corpus()
    for key in corpus:
        assert key.startswith("/docs/llm/"), f"unexpected key format: {key}"


def test_corpus_page_has_required_fields():
    corpus = doc_corpus()
    for key, page in corpus.items():
        assert "title" in page, f"missing 'title' in {key}"
        assert "body" in page, f"missing 'body' in {key}"
        assert "title_lower" in page
        assert "header_lower" in page
        assert "body_lower" in page


def test_doc_corpus_read_file_hit():
    corpus = doc_corpus()
    if not corpus:
        pytest.skip("corpus is empty")
    first_key = next(iter(corpus))
    result = doc_corpus_read_file(first_key)
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


def test_doc_corpus_read_file_miss():
    result = doc_corpus_read_file("/docs/llm/nonexistent_page_xyz.md")
    assert result is None


# ── Tool spec ─────────────────────────────────────────────────────────────────

def test_search_kerf_docs_spec_name():
    assert search_kerf_docs_spec.name == "search_kerf_docs"


def test_search_kerf_docs_spec_has_schema():
    schema = search_kerf_docs_spec.input_schema
    assert "properties" in schema
    assert "query" in schema["properties"]


# ── Async search logic ────────────────────────────────────────────────────────

class _FakeCtx:
    role = "editor"


@pytest.mark.asyncio
async def test_search_returns_hits():
    ctx = _FakeCtx()
    # Use a generic term likely to appear in the corpus
    corpus = doc_corpus()
    if not corpus:
        pytest.skip("corpus is empty")
    # pick a word from the first doc title
    first_page = next(iter(corpus.values()))
    word = first_page["title"].split()[0].lower()
    result = await run_search_kerf_docs(ctx, json.dumps({"query": word}).encode())
    data = json.loads(result)
    assert "hits" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_search_no_match_returns_empty():
    ctx = _FakeCtx()
    result = await run_search_kerf_docs(
        ctx, json.dumps({"query": "xyzzy_no_match_zqk"}).encode()
    )
    data = json.loads(result)
    assert data["hits"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_search_missing_query_returns_error():
    ctx = _FakeCtx()
    result = await run_search_kerf_docs(ctx, json.dumps({}).encode())
    data = json.loads(result)
    assert "error" in data
    assert data["code"] == "BAD_ARGS"


@pytest.mark.asyncio
async def test_search_invalid_json_returns_error():
    ctx = _FakeCtx()
    result = await run_search_kerf_docs(ctx, b"not-json")
    data = json.loads(result)
    assert "error" in data
    assert data["code"] == "BAD_ARGS"


@pytest.mark.asyncio
async def test_search_respects_limit():
    ctx = _FakeCtx()
    corpus = doc_corpus()
    if len(corpus) < 3:
        pytest.skip("corpus too small to test limit")
    # Query something generic that hits many docs
    result = await run_search_kerf_docs(
        ctx, json.dumps({"query": "the", "limit": 2}).encode()
    )
    data = json.loads(result)
    assert len(data["hits"]) <= 2


# ── Registry: search_kerf_docs is registered ─────────────────────────────────

def test_search_kerf_docs_in_registry():
    from kerf_chat.tools.registry import Registry
    names = [t.spec.name for t in Registry]
    assert "search_kerf_docs" in names, (
        f"search_kerf_docs not found in Registry; registered: {names}"
    )
