# BIM Categories and Hosted-Element Relationships

This document covers the `category` and `host_ref` fields added to BIM elements,
the category enum, host rules, cascade behaviour, and the LLM validation tools.

See also: `bim.md` for the overall `.bim` file shape, levels, walls, slabs, and IFC4 mapping.

---

## CATEGORIES enum

Every element inside a `.bim` doc may carry a `category` field.  Valid values:

```
Wall  Floor  Roof  Door  Window  Room
Column  Beam  Stair  Railing  Casework  Site
Generic  MEP_Duct  MEP_Pipe  MEP_Conduit
```

Validated by `validate_bim_categories` tool.  Unknown categories are errors.

---

## HOST_RULES

Some categories may only be hosted on specific parent categories:

| Hosted category | Allowed host categories |
|-----------------|------------------------|
| Door            | Wall                   |
| Window          | Wall                   |
| Casework        | Floor, Wall            |
| MEP_Duct        | *(none — cannot be hosted)* |
| MEP_Pipe        | *(none)*               |
| MEP_Conduit     | *(none)*               |
| *all others*    | *(unconstrained — any host)* |

---

## `host_ref` field

`host_ref` is an optional string field on an element that holds the `id` of
another element in the same `.bim` doc.

```json
{
  "id": "door_01",
  "category": "Door",
  "host_ref": "wall_north",
  "position": [1200, 0, 0]
}
```

Rules:
- The referenced `host_ref` id must exist within the same document.
- The `category` / `host_category` combination must satisfy HOST_RULES.
- An element may not be its own host.

---

## Cascade behaviour

When a host element is moved (`move_element`), **all transitively hosted descendants**
move by the same delta.  The chain is depth-first: host → direct children → grandchildren.

Example: moving `wall_north` by `[500, 0, 0]` also translates every Door and
Window whose `host_ref` (directly or indirectly) resolves to `wall_north`.

Translation is applied to whichever coordinate fields are present on each element:
- `position: [x, y, z]`
- `from: [x, y]` / `to: [x, y]`  (wall endpoints)
- 3-D `from: [x, y, z]` / `to: [x, y, z]`  (beams etc.)

---

## LLM tools

| Tool | Description |
|------|-------------|
| `set_element_category` | Set `category` on one element. Rejects unknown categories. |
| `set_element_host` | Set `host_ref` on one element. Validates HOST_RULES; rejects invalid pairs. |
| `unset_element_host` | Remove `host_ref` (detach from host). |
| `move_element` | Translate element + all hosted descendants by `delta=[dx,dy,dz]`. |
| `find_hosted` | Return ids of elements directly hosted on a given host. |
| `validate_bim_categories` | Full-doc audit: returns `{ok, errors, warnings}`. |

---

## `validate_bim_categories` output shape

```json
{
  "ok": false,
  "errors": [
    "openings[0] id=door_01: unknown category 'Spaceship'",
    "openings[1] id=win_01: host_ref 'wall_deleted' does not exist in document",
    "openings[2] id=door_02: 'Door' cannot be hosted on 'Floor' (host_ref=slab_01)"
  ],
  "warnings": []
}
```

`ok` is `true` only when `errors` is empty.  `warnings` is reserved for
advisory issues (e.g. missing category on older elements).

---

## Examples

### 1 — Tag existing walls and add a hosted door

```json
// After create_bim, the doc has walls with ids set:
// { "id": "w1", "from": [0,0], "to": [5000,0], "height": 3000, "thickness": 200 }

// set_element_category
{ "file_id": "<id>", "element_id": "w1", "category": "Wall" }

// Add a door element (via write_file / edit_file) and then bind it:
{ "id": "d1", "category": "Door", "position": [1200, 0, 0], "width": 900, "height": 2100 }

// set_element_host
{ "file_id": "<id>", "element_id": "d1", "host_ref": "w1" }
```

### 2 — Move a wall and cascade to its hosted door

```json
// move_element
{
  "file_id": "<id>",
  "element_id": "w1",
  "delta": [500, 0, 0]
}
// Response: { "element_id": "w1", "delta": [500,0,0], "also_moved": ["d1"] }
```

### 3 — Validate the whole document

```json
// validate_bim_categories
{ "file_id": "<id>" }
// Clean doc response:
{ "ok": true, "errors": [], "warnings": [] }
```
