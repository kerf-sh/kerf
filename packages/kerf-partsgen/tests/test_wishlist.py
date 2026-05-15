"""Hermetic tests for the wishlist markdown parser. No kernel, no network."""

import os

from kerf_partsgen.wishlist import (
    parse_wishlist_file,
    parse_wishlist_text,
    slugify,
)

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

SAMPLE = """\
# Mechanical wishlist

Some prose that is not a row.

## Fasteners

- [x] ISO 4017 hex head bolt — sizes M3–M24 — ref ISO 4017
- [ ] ISO 4762 socket-head cap screw — sizes M3–M24
-  [X]  Spaced Box  -  ref NONE
- [ ] explicit slug here id:custom_slug — ref X
not a list item
- [ ] bare family with no dashes
"""


def test_parses_marks_and_ids():
    rows = parse_wishlist_text(SAMPLE)
    by_id = {r.family_id: r for r in rows}

    assert len(rows) == 5  # prose / "not a list item" ignored

    assert by_id["iso_4017_hex_head_bolt"].approved is True
    assert by_id["iso_4017_hex_head_bolt"].name == "ISO 4017 hex head bolt"

    assert by_id["iso_4762_socket_head_cap_screw"].approved is False

    # uppercase [X] counts as approved; spacing tolerated
    assert by_id["spaced_box"].approved is True

    # explicit id:<slug> token wins over the name slug
    assert "custom_slug" in by_id
    assert by_id["custom_slug"].approved is False

    # a row with no dash → whole body is the family (underscore slug)
    assert "bare_family_with_no_dashes" in by_id


def test_slugify():
    assert slugify("ISO 7089 flat washer") == "iso_7089_flat_washer"
    assert slugify("  M3/M4 (set)  ") == "m3_m4_set"


def test_real_committed_wishlist_parses_and_has_two_real_rows():
    path = os.path.join(
        _REPO_ROOT, "docs", "parts", "wishlist", "mechanical.md"
    )
    rows = parse_wishlist_file(path)
    # ~25–35 family rows expected.
    assert 25 <= len(rows) <= 40

    approved = [r for r in rows if r.approved]
    ids = {r.family_id for r in approved}
    # exactly the two committed reference generators are pre-approved
    assert ids == {"iso_7089_flat_washer", "iso_4017_hex_head_bolt"}
