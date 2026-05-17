# kerf-imports · jt_reader.py

JT (Jupiter Tessellation) binary format parser — v8 and v10 LSG assembly trees
with tristrip tessellation.

## Entrypoint

### `parse_jt(data: bytes) -> dict`

```python
from kerf_imports.jt_reader import parse_jt

result = parse_jt(jt_bytes)
# result keys: ok, version, toc_entry_count, assembly, meshes, properties, warnings
```

On success:
- `ok` — `True`
- `version` — version string (e.g. `"Version 10.0"`)
- `toc_entry_count` — number of segments in the Table of Contents
- `assembly` — nested dict representing the LSG (Logical Scene Graph) tree
- `meshes` — list of triangle mesh dicts `{vertices, triangles, normals}`
- `properties` — flat dict of document-level metadata
- `warnings` — list of non-fatal parse warnings

## File format

**Magic bytes:** `b"Version "` (8 bytes) at offset 0.

**Byte order:** byte at offset 18. Value `0` = big-endian; any other value
= little-endian.

**TOC offset:** 64-bit integer at bytes 19–30 (little-endian).

### Segment type GUIDs (lower 4 bytes)

| Segment | GUID suffix |
|---|---|
| LSG (scene graph) | `0x10DD1035` |
| Tristrip tessellation | `0x10DD1046` |
| Shape | `0x10DD1038` |
| Meta-data | `0x10DD103A` |
| XT B-rep | `0x10DD1056` |

Segments with zlib-compressed payloads are decompressed automatically.

### LSG node types

`assembly`, `part`, `instance`, `shape`, `range_lod`, `switch`, `meta`

### Tristrip conversion

`_tristrip_to_triangles(indices)`: A negative index signals a degenerate
restart — the current strip is ended and a new strip begun. Even-indexed
triangles within a strip are emitted with vertices in winding order;
odd-indexed triangles are flipped to maintain consistent orientation.

## `_Reader` class

Thin positional byte reader. Methods: `u8`, `u16`, `u32`, `u64`, `i8`,
`i16`, `i32`, `i64`, `f32`, `f64`, `guid()`, `counted_string()`,
`matrix4x4()`.

All reads advance the internal cursor. `matrix4x4()` returns a 16-float
row-major transform.

## Test fixture

`make_minimal_jt() -> bytes` builds a minimal synthetic JT file suitable for
round-trip unit tests. The returned bytes pass `parse_jt` without warnings.

## LLM tool: `import_jt`

```json
{"file_blob_id": "uuid", "project_id": "uuid"}
```

Returns: `{ok, version, toc_entry_count, assembly_node_count, mesh_count,
triangle_count, warnings}`.

## Standards reference

- Siemens JT File Format Reference v10.x (publicly available)
- ISO 14306:2017: JT file format specification
