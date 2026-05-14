"""Forwarding shim: docs.py has moved to kerf_chat.tools.docs.

This file exists so that ``from tools.docs import ...`` and the re-import in
backend/tools/__init__.py continues to resolve correctly.
"""
from kerf_chat.tools.docs import (  # noqa: F401
    search_kerf_docs_spec,
    run_search_kerf_docs,
    doc_corpus,
    doc_corpus_read_file,
    _DOCS_DIR,
    _HEADER_RE,
    _H1_RE,
)

__all__ = [
    "search_kerf_docs_spec",
    "run_search_kerf_docs",
    "doc_corpus",
    "doc_corpus_read_file",
]
