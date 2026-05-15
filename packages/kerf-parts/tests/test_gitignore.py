"""MIT-hygiene guard: the clone cache + generated output MUST be gitignored
so no third-party parts data can ever be committed. Reads the repo-root
.gitignore (no git invocation, hermetic).
"""
from pathlib import Path

# tests/ -> kerf-parts/ -> packages/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_parts_cache_is_gitignored():
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/.parts-cache/" in gi, (
        ".parts-cache/ must be gitignored — third-party parts data is never "
        "committed (MIT hygiene)"
    )


def test_generated_output_lives_under_cache():
    # The generated NOTICE / converted output dir is a subdir of the
    # gitignored cache, so the single .gitignore line covers it.
    from kerf_parts.fetch import DEFAULT_CACHE_DIR
    from kerf_parts.seed import GENERATED_DIRNAME

    generated = DEFAULT_CACHE_DIR / GENERATED_DIRNAME
    assert DEFAULT_CACHE_DIR.name == ".parts-cache"
    assert generated.parent == DEFAULT_CACHE_DIR
    # And the cache dir resolves inside the repo root.
    assert str(DEFAULT_CACHE_DIR).startswith(str(REPO_ROOT))


def test_default_cache_dir_is_repo_root_parts_cache():
    from kerf_parts.fetch import DEFAULT_CACHE_DIR, REPO_ROOT as FETCH_REPO_ROOT

    assert FETCH_REPO_ROOT == REPO_ROOT
    assert DEFAULT_CACHE_DIR == REPO_ROOT / ".parts-cache"
