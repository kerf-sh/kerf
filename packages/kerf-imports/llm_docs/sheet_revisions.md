# Sheet Revisions — Workflow & Examples

A sheet's `.sheet.json` file may carry a `revisions` array alongside `titleblock`.
Each revision entry tracks a letter, date, description, and author. The active
revision is stored as `titleblock.revision`.

---

## Schema extension

```jsonc
{
  "version": 1,
  "titleblock": {
    "revision": "B",          // currently active revision letter
    "project_name": "Office Tower",
    "issue_date": "2026-05-14",
    "drawn_by": "Jane Smith",
    "checked_by": "Bob Jones",
    "scale": ""
  },
  "revisions": [
    { "letter": "A", "date": "2026-05-01", "description": "Initial issue",     "by": "Jane Smith" },
    { "letter": "B", "date": "2026-05-14", "description": "Structural revisions", "by": "Bob Jones"   }
  ]
}
```

---

## Tools

| Tool | Description |
|------|-------------|
| `add_sheet_revision` | Append a new revision (auto-increments letter, sets active) |
| `set_active_sheet_revision` | Change `titleblock.revision` to an existing letter |
| `list_sheet_revisions` | Return sorted revision history and active revision |
| `update_title_block_field` | Write a single titleblock field (project_name, issue_date, drawn_by, checked_by, scale) |

---

## Workflow

1. **Create a sheet** (existing `create_sheet` tool) with no revisions.
2. **Issue a revision** — call `add_sheet_revision` each time you want to record
   a new design change. The tool auto-assigns the next letter and date, and
   sets `titleblock.revision` to the new letter.
3. **Track multiple issues** — call `add_sheet_revision` repeatedly; letters
   advance A→B→…→Z→AA→AB→…
4. **Switch the active revision** — use `set_active_sheet_revision` to point
   `titleblock.revision` at any previously recorded letter.
5. **Update title-block metadata** — use `update_title_block_field` to write
   fields such as `project_name`, `drawn_by`, `checked_by`, `issue_date`, or
   `scale`.
6. **Audit history** — call `list_sheet_revisions` to retrieve the full sorted
   list at any time.

---

## Examples

### 1 — Issue and activate a new revision

```json
{
  "tool": "add_sheet_revision",
  "args": {
    "file_id": "sheet-uuid-abc123",
    "description": "Relocated structural column at Grid E-4",
    "by": "Bob Jones"
  }
}
```

Response:
```json
{
  "ok": true,
  "result": {
    "letter": "B",
    "revision": {
      "letter": "B",
      "date": "2026-05-14",
      "description": "Relocated structural column at Grid E-4",
      "by": "Bob Jones"
    }
  }
}
```

### 2 — Update title-block fields after revision B is issued

```json
{
  "tool": "update_title_block_field",
  "args": {
    "file_id": "sheet-uuid-abc123",
    "field": "checked_by",
    "value": "Alice Chen"
  }
}
```

```json
{
  "tool": "update_title_block_field",
  "args": {
    "file_id": "sheet-uuid-abc123",
    "field": "issue_date",
    "value": "2026-05-14"
  }
}
```
