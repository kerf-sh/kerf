"""Parser for the human-owned wishlist markdown.

Format (``docs/parts/wishlist/<domain>.md``) — one task-list row per family::

    - [ ] ISO 4762 socket-head cap screw — sizes M3–M24 — ref ISO 4762
    - [x] ISO 4032 hex nut — sizes M3–M24 — ref ISO 4032

``[ ]``  → family wants (re)generating; ``enumerate`` processes it.
``[x]``  → human reviewed & approved; ``enumerate`` skips it, ``seed``
            promotes it.

The markdown is the single human-owned source of truth.  Nothing in this
package ever writes to it — the contributor flips ``[ ]``→``[x]`` by hand
*after* eyeballing ``.parts-out/``; that one-line commit IS the review record.

Each row maps to a generator module ``kerf_partsgen/generators/<family_id>.py``
where ``family_id`` is the slug of the leading family name (text before the
first em/en dash), unless the row carries an explicit ``id:<slug>`` token.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_ROW_RE = re.compile(r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<body>.+?)\s*$")
_ID_RE = re.compile(r"\bid:(?P<id>[a-z0-9][a-z0-9_\-]*)\b")
# Family name = text up to the first em-dash (—), en-dash (–) or " - ".
_NAME_SPLIT_RE = re.compile(r"\s+[—–]\s+|\s+-\s+")


@dataclass
class WishlistRow:
    approved: bool          # True when ticked [x]
    name: str               # full family label as written
    family_id: str          # slug → generators/<family_id>.py
    raw: str                # original line (for diagnostics)
    line_no: int


def slugify(text: str) -> str:
    """Slug used for family_id + generator filename + PartDoc slug.

    Underscores (not hyphens) so it is a valid Python module stem —
    ``generators/<family_id>.py`` is imported by name.
    """
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _family_id(body: str) -> str:
    explicit = _ID_RE.search(body)
    if explicit:
        return explicit.group("id")
    head = _NAME_SPLIT_RE.split(body, maxsplit=1)[0]
    return slugify(head)


def _family_name(body: str) -> str:
    head = _NAME_SPLIT_RE.split(body, maxsplit=1)[0]
    return head.strip()


def parse_wishlist_text(text: str) -> list[WishlistRow]:
    """Parse wishlist markdown into rows. Pure; no filesystem access."""
    rows: list[WishlistRow] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _ROW_RE.match(line)
        if not m:
            continue
        body = m.group("body").strip()
        if not body:
            continue
        rows.append(
            WishlistRow(
                approved=m.group("mark").lower() == "x",
                name=_family_name(body),
                family_id=_family_id(body),
                raw=line.rstrip("\n"),
                line_no=i,
            )
        )
    return rows


def parse_wishlist_file(path: str) -> list[WishlistRow]:
    with open(path, "r", encoding="utf-8") as fh:
        return parse_wishlist_text(fh.read())


def default_wishlist_path(repo_root: str, domain: str = "mechanical") -> str:
    return os.path.join(repo_root, "docs", "parts", "wishlist", f"{domain}.md")
