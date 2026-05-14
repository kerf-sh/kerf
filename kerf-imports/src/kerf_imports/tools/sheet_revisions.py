"""
sheet_revisions.py — LLM tools for sheet revision tracking and title-block fields.

Extends the .sheet.json kind with a `revisions` array and utilities for
managing revision letters (A→B→…→Z→AA→…), setting the active revision,
and updating title-block metadata fields.
"""

import json
from datetime import date as _date

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ---------------------------------------------------------------------------
# Pure helpers (mirrors src/lib/sheetRevisions.js logic)
# ---------------------------------------------------------------------------

_MAX_CHAR = ord("Z")
_A_CHAR = ord("A")


def _next_letter(existing: str) -> str:
    """Return the next alphabetic revision code after `existing`."""
    if not existing:
        return "A"
    chars = list(existing.upper())
    for i in range(len(chars) - 1, -1, -1):
        code = ord(chars[i])
        if code < _MAX_CHAR:
            chars[i] = chr(code + 1)
            return "".join(chars)
        chars[i] = "A"
    return "A" * (len(chars) + 1)


def _next_revision_letter_for_sheet(sheet: dict) -> str:
    revs = sheet.get("revisions") or []
    letters = sorted([r["letter"] for r in revs if r.get("letter")], key=lambda x: x.upper())
    if not letters:
        return "A"
    return _next_letter(letters[-1])


# ---------------------------------------------------------------------------
# Internal: load a sheet file, return (sheet dict, path)
# ---------------------------------------------------------------------------

def _load_sheet(ctx: ProjectCtx, file_id: str) -> tuple[dict, str]:
    path = ctx.resolve_file_id(file_id)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh), path


def _save_sheet(path: str, sheet: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sheet, fh, indent=2)


# ---------------------------------------------------------------------------
# Tool: add_sheet_revision
# ---------------------------------------------------------------------------

@register(ToolSpec(
    name="add_sheet_revision",
    description="Append a new revision entry to a sheet's revisions list and "
                "optionally set it as the active revision.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "description": {"type": "string"},
            "by": {"type": "string"},
            "date": {"type": "string"},
            "set_active": {"type": "boolean"},
        },
        "required": ["file_id", "description"],
    },
))
def add_sheet_revision(ctx: ProjectCtx, *, file_id: str, description: str,
                        by: str | None = None, date: str | None = None,
                        set_active: bool = True) -> str:
    try:
        sheet, path = _load_sheet(ctx, file_id)
    except Exception as e:
        return err_payload(f"Could not load sheet {file_id}: {e}", "NOT_FOUND")

    if "revisions" not in sheet:
        sheet["revisions"] = []

    letter = _next_revision_letter_for_sheet(sheet)
    entry = {
        "letter": letter.upper(),
        "date": (date or str(_date.today())),
        "description": description or "",
        "by": (by or ""),
    }
    sheet["revisions"].append(entry)

    if set_active:
        if "titleblock" not in sheet:
            sheet["titleblock"] = {}
        sheet["titleblock"]["revision"] = letter.upper()

    _save_sheet(path, sheet)
    return ok_payload({"letter": letter.upper(), "revision": entry})


# ---------------------------------------------------------------------------
# Tool: set_active_sheet_revision
# ---------------------------------------------------------------------------

@register(ToolSpec(
    name="set_active_sheet_revision",
    description="Set the active revision letter in the sheet's titleblock.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "letter": {"type": "string"},
        },
        "required": ["file_id", "letter"],
    },
))
def set_active_sheet_revision(ctx: ProjectCtx, *, file_id: str, letter: str) -> str:
    try:
        sheet, path = _load_sheet(ctx, file_id)
    except Exception as e:
        return err_payload(f"Could not load sheet {file_id}: {e}", "NOT_FOUND")

    letter = letter.upper()
    revs = sheet.get("revisions") or []
    if not any(r.get("letter", "").upper() == letter for r in revs):
        return err_payload(f"Revision letter '{letter}' not found in sheet revisions list.", "NOT_FOUND")

    if "titleblock" not in sheet:
        sheet["titleblock"] = {}
    sheet["titleblock"]["revision"] = letter

    _save_sheet(path, sheet)
    return ok_payload({"revision": letter})


# ---------------------------------------------------------------------------
# Tool: list_sheet_revisions
# ---------------------------------------------------------------------------

@register(ToolSpec(
    name="list_sheet_revisions",
    description="Return the sorted revision history for a sheet.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
        },
        "required": ["file_id"],
    },
))
def list_sheet_revisions(ctx: ProjectCtx, *, file_id: str) -> str:
    try:
        sheet, _ = _load_sheet(ctx, file_id)
    except Exception as e:
        return err_payload(f"Could not load sheet {file_id}: {e}", "NOT_FOUND")

    revs = sheet.get("revisions") or []
    sorted_revs = sorted(revs, key=lambda r: r.get("letter", "").upper())
    active = sheet.get("titleblock", {}).get("revision", "").upper()

    return ok_payload({
        "revisions": sorted_revs,
        "active_revision": active,
    })


# ---------------------------------------------------------------------------
# Tool: update_title_block_field
# ---------------------------------------------------------------------------

_VALID_TITLEBLOCK_FIELDS = frozenset([
    "project_name", "issue_date", "drawn_by", "checked_by", "scale",
])

@register(ToolSpec(
    name="update_title_block_field",
    description="Update a single titleblock field on a sheet. "
                "Valid fields: project_name, issue_date, drawn_by, checked_by, scale.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "field": {"type": "string"},
            "value": {"type": "string"},
        },
        "required": ["file_id", "field", "value"],
    },
))
def update_title_block_field(ctx: ProjectCtx, *, file_id: str,
                               field: str, value: str) -> str:
    if field not in _VALID_TITLEBLOCK_FIELDS:
        return err_payload(
            f"Invalid field '{field}'. "
            f"Valid fields: {', '.join(sorted(_VALID_TITLEBLOCK_FIELDS))}",
            "BAD_ARGS"
        )

    try:
        sheet, path = _load_sheet(ctx, file_id)
    except Exception as e:
        return err_payload(f"Could not load sheet {file_id}: {e}", "NOT_FOUND")

    if "titleblock" not in sheet:
        sheet["titleblock"] = {}
    sheet["titleblock"][field] = value

    _save_sheet(path, sheet)
    return ok_payload({"field": field, "value": value})
