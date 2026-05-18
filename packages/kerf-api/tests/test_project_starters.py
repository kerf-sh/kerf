"""Create-project starter catalog — cross-language contract.

The create-project dialog (src/lib/projectTags.js) and the backend
seeder (kerf_api.routes.STARTER_SEEDS) MUST agree: every starter the UI
offers has to be seedable by the API, every project-domain preset must
nudge to a real starter, and every seeded file kind must be in the
FILE_KINDS allow-list (or create_project 400s / silently no-ops — the
exact "restore full starter set" regression this guards).
"""
from __future__ import annotations

import pathlib
import re

from kerf_api.routes import STARTER_SEEDS, DEFAULT_STARTER, FILE_KINDS

_PROJECT_TAGS_JS = (
    pathlib.Path(__file__).resolve().parents[3] / "src/lib/projectTags.js"
)


def _js() -> str:
    return _PROJECT_TAGS_JS.read_text()


def _starter_option_ids() -> set[str]:
    src = _js()
    m = re.search(r"STARTER_OPTIONS\s*=\s*\[(.*?)\n\]", src, re.S)
    assert m, "could not locate STARTER_OPTIONS array in projectTags.js"
    return set(re.findall(r"id:\s*'([a-z_]+)'", m.group(1)))


def _suggest_starter_values() -> set[str]:
    # Only TAG_PRESETS entries use `suggestStarter:`.
    return set(re.findall(r"suggestStarter:\s*'([a-z_]+)'", _js()))


def test_frontend_starter_options_match_backend_catalog():
    ui = _starter_option_ids()
    be = set(STARTER_SEEDS)
    assert ui == be, (
        "create-project starter dropdown drifted from backend STARTER_SEEDS.\n"
        f"  only in UI : {sorted(ui - be)}\n"
        f"  only in API: {sorted(be - ui)}"
    )


def test_default_starter_is_seedable():
    assert DEFAULT_STARTER in STARTER_SEEDS


def test_every_domain_preset_suggests_a_real_starter():
    missing = _suggest_starter_values() - set(STARTER_SEEDS)
    assert not missing, (
        f"TAG_PRESETS nudge to starters the API can't seed: {sorted(missing)}"
    )


def test_seeded_kinds_are_in_file_kinds_allowlist():
    bad = {
        sid: kind
        for sid, (_name, kind, _content) in STARTER_SEEDS.items()
        if kind not in FILE_KINDS
    }
    assert not bad, f"starter kinds not in FILE_KINDS (create_file 400): {bad}"


def test_non_blank_starters_seed_a_named_file_with_content():
    for sid, (name, kind, content) in STARTER_SEEDS.items():
        if sid == "blank":
            assert name == "" and content == "", "blank must seed nothing"
            continue
        assert name and content, f"starter {sid!r} must seed a non-empty file"
        # filename bug regression: must be a real filename, not the id.
        assert name != sid, (
            f"starter {sid!r} seeds a file literally named {sid!r} "
            f"(should be e.g. main.<ext>)"
        )
