# Authoring configurations / variants

A **configuration** is a per-file set of parameter overrides that lets one
file describe several flavors of the same thing — M3 / M4 / M5 sizes of
one fastener, engraved vs blank lid, "long" vs "short" bracket. The active
configuration's `params` are merged OVER the equations scope before the
runner evaluates the file, so a single source can produce many BOM rows
without duplicating geometry.

> **Tooling note:** Use `add_configuration` to splice a configuration row
> into a Part / Feature / Sketch file, and `set_active_config` to pin a
> specific configuration on an assembly's component. Both tools record a
> revision so Cmd-Z works.

## File shape

Configurations live alongside the regular file content as two top-level
keys:

```json
{
  "version": 1,
  "name": "Cap screw (M-series)",
  "default_config": "M3",
  "configurations": [
    { "id": "M3", "label": "M3", "params": { "d": 3, "head_d": 5.5 } },
    { "id": "M4", "label": "M4", "params": { "d": 4, "head_d": 7   } },
    { "id": "M5", "label": "M5", "params": { "d": 5, "head_d": 8.5 } }
  ]
}
```

Fields:

- `id` — a stable token used by assembly references and the editor
  dropdown. Must be non-empty. Renaming an `id` is a breaking change
  (assembly components that pinned the old id become unpinned and fall
  back to `default_config`).
- `label` — the human-readable string shown in the editor's config
  dropdown and in the BOM table next to the part name. Defaults to `id`
  when missing.
- `params` — an object of param-name → value overrides. The runner
  merges these OVER the equations scope at evaluation time, so a config
  always wins on key collision.
- `default_config` — the id used when nothing pins a specific
  configuration (assembly component without `config_id`, editor on
  first open). When omitted, the first declared configuration wins.

## Where configurations apply

| File kind  | Where the active params land                                                |
|------------|-----------------------------------------------------------------------------|
| `.part`    | Available to assemblies (BOM grouping by `(file, config)`); 3D model fixed by `model_storage_key` regardless of config. |
| `.feature` | Substituted into `${name}` placeholders inside feature node fields before OCCT evaluation. |
| `.sketch`  | Substituted into `${name}` placeholders inside dimensional constraint values. |
| `.jscad`   | (deferred — JSCAD source is JS, not JSON; configurations land in v2)        |

## Assembly references

An assembly component pins a specific configuration via the `config_id`
field on the component entry:

```json
{
  "components": [
    { "id": "c1", "file_id": "<screw-uuid>", "object_id": "*", "config_id": "M4", "transform": [/*...*/] },
    { "id": "c2", "file_id": "<screw-uuid>", "object_id": "*", "config_id": "M5", "transform": [/*...*/] }
  ]
}
```

When `config_id` is omitted the file's `default_config` is used. When the
referenced file has no configurations the field is ignored.

## BOM grouping

The BOM aggregator groups by `(file_id, config_id)` so M3 and M4
instances of the same screw show as separate rows:

```
| Part name             | Qty | Unit | Total |
|-----------------------|-----|------|-------|
| Cap screw (M-series) [M3] | 4   | $0.10 | $0.40 |
| Cap screw (M-series) [M4] | 2   | $0.12 | $0.24 |
| Cap screw (M-series) [M5] | 8   | $0.15 | $1.20 |
```

The frontend renders the configuration label as a small chip after the
part name.

## Worked example: M3/M4/M5 cap screw

1. Author the Part file (`/library/cap-screw.part`):

   ```json
   {
     "version": 1,
     "name": "Cap screw",
     "manufacturer": "McMaster-Carr",
     "mpn": "92290A115",
     "default_config": "M3",
     "configurations": [
       { "id": "M3", "label": "M3 x 8mm",  "params": { "d": 3, "L": 8  } },
       { "id": "M4", "label": "M4 x 10mm", "params": { "d": 4, "L": 10 } },
       { "id": "M5", "label": "M5 x 12mm", "params": { "d": 5, "L": 12 } }
     ],
     "distributors": [
       { "name": "mcmaster", "url": "https://mcmaster.com/92290A115/", "price_usd": 0.42 }
     ]
   }
   ```

2. From an assembly, place the same Part three times — once per config:

   ```json
   {
     "components": [
       { "id": "screw-a", "file_id": "<screw-uuid>", "object_id": "*", "config_id": "M3", "transform": [/*...*/] },
       { "id": "screw-b", "file_id": "<screw-uuid>", "object_id": "*", "config_id": "M4", "transform": [/*...*/] },
       { "id": "screw-c", "file_id": "<screw-uuid>", "object_id": "*", "config_id": "M5", "transform": [/*...*/] }
     ]
   }
   ```

3. `GET /api/projects/:id/bom` returns three rows with `config_id` =
   `"M3"`, `"M4"`, `"M5"` and `config_label` populated for each.

## Tool quick reference

```jsonc
// Add (or update) a configuration row.
add_configuration({
  "file_id":  "<uuid of .part / .feature / .sketch>",
  "id":       "M4",
  "label":    "M4 x 10mm",
  "params":   { "d": 4, "L": 10 }
})

// Pin a specific configuration on an assembly component.
set_active_config({
  "assembly_file_id": "<assembly uuid>",
  "component_id":     "screw-b",
  "config_id":        "M4"   // empty string clears the pin
})
```

## Gotchas

- **Configurations layer over equations** — a project-wide `wall = 2`
  set in `.equations` is overridden by a config that supplies its own
  `wall`. This is intentional: configurations are the per-file local
  override.
- **Re-using ids across files is fine** — `M3` in screw.part and `M3`
  in nut.part are separate; resolution is always within one file.
- **Renaming an `id`** breaks every assembly component that pinned the
  old id. Editing a `label` is safe (assembly references store the id,
  not the label).
- **An empty `configurations` array** has the same effect as no field —
  the file behaves like an unconfigured Part / Feature / Sketch.
