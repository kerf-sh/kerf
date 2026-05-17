# kerf-imports · parasolid_reader.py

Parasolid X_T ASCII text format parser — topology and geometry extraction
without a Parasolid kernel license.

## Entrypoint

### `parse_xt(text: str) -> dict`

```python
from kerf_imports.parasolid_reader import parse_xt

result = parse_xt(xt_text)
# result keys: ok, header, body_count, face_count, edge_count, vertex_count,
#              bodies, inventory, skipped_types, warnings, _model
```

On success:
- `ok` — `True`
- `header` — dict of `SCH_*` key-value pairs extracted from the header section
- `body_count`, `face_count`, `edge_count`, `vertex_count` — topology counts
- `bodies` — list of body dicts with nested topology tree
- `inventory` — flat dict `{index: entity_info}` for all parsed records
- `skipped_types` — set of record type names not yet parsed
- `warnings` — non-fatal parse issues

## File format

### Header section

Lines beginning with `SCH_` are header metadata (e.g. `SCH_CHAR_SIZE=1`).
The header ends at the `END_OF_HEADER` marker or the first line that begins
with a numeric index.

### Record format

```
<int_index> <TYPE> <field1> <field2> ...
    <continuation_field> ...
```

Integer index uniquely identifies each entity. Continuation lines (indented
or blank-prefixed) extend the previous record.

### Topology chain

```
body → shell_ref → face_ref → next_face
face → loop_ref → fin_ref → next_fin → edge_ref
```

- `body` references one or more `shell` entities.
- `shell` references a linked list of `face` entities via `next_face`.
- `face` references a `loop` → `fin` → `edge` chain.
- `fin` is a directed half-edge; `next_fin` forms the loop.

### Supported geometry types

**Surfaces:** `plane`, `cylinder`, `cone`, `sphere`, `torus`, `b_surface`

**Curves:** `line`, `circle`, `ellipse`, `b_curve`

### `_build_inventory(records) -> dict`

Constructs a flat `{index: {type, fields, surface_type?, curve_type?}}`
dict that maps every numeric record to its parsed fields. Used by the
topology builder to resolve cross-references.

## LLM tool: `import_xt`

```json
{"file_blob_id": "uuid", "project_id": "uuid"}
```

Returns: `{ok, body_count, face_count, edge_count, vertex_count,
skipped_types, warnings}`.

## Standards reference

- Siemens Parasolid X_T Schema Reference (available with Parasolid SDK)
- ISO 10303-42: Geometric and topological representation (STEP geometric model)
