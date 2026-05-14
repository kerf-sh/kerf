# Family (.family.json) — Parametric component templates

A **family** is a reusable parametric component template (Revit-style).
It lives as a file with `kind = 'family'` in the project tree.
Instances live inside `.bim` files and reference a family by its file id.

---

## Schema

```jsonc
{
  "version": 1,
  "name": "Standard Window",
  "category": "Window",       // Wall | Floor | Roof | Door | Window | Column | Beam
                               // Stair | Railing | Ceiling | Furniture | Generic
  "params": [
    {"name": "width",        "type": "number", "unit": "mm", "default": 900,  "min": 300, "max": 3000},
    {"name": "height",       "type": "number", "unit": "mm", "default": 1200, "min": 300, "max": 3000},
    {"name": "glazing",      "type": "enum",   "options": ["single","double","triple"], "default": "double"},
    {"name": "sill_height",  "type": "number", "unit": "mm", "default": 900}
  ],
  "types": [
    // Named presets — resolved between defaults and per-instance overrides
    {"id": "type-600x900",   "name": "600×900",  "params": {"width": 600,  "height": 900}},
    {"id": "type-1200x1500", "name": "1200×1500","params": {"width": 1200, "height": 1500}}
  ],
  "host_rules": {
    "allowed_hosts": ["Wall"],
    "host_alignment": "centered_on_face"
  },
  "representation": {
    "kind": "geometry_ref",    // or "feature_tree" | "circuit_ref"
    "file_id": "geo-uuid",
    "param_bindings": {
      "width":  "<param.width>",
      "height": "<param.height>"
    }
  }
}
```

### Param types

| type    | required fields              | optional               |
|---------|------------------------------|------------------------|
| number  | name, type                   | unit, default, min, max|
| enum    | name, type, options (array)  | default                |
| string  | name, type                   | default                |
| boolean | name, type                   | default                |

### Precedence (lowest → highest)

```
param.default  →  type.params  →  instance.params
```

### Instance record (inside a .bim file)

```jsonc
{
  "id": "inst-uuid",
  "type": "instance",
  "family_id": "family-file-uuid",
  "type_id": "type-600x900",    // optional named preset
  "params": {"sill_height": 850},  // per-instance overrides
  "host_ref": "wall-e1",
  "transform": [...]
}
```

---

## Tools

| Tool | Description |
|------|-------------|
| `create_family` | Create a new `.family.json` file |
| `add_family_param` | Append a param definition to a family |
| `add_family_type` | Add a named param preset to a family |
| `instantiate_family` | Append an instance record to a `.bim` file |
| `update_instance` | Patch per-instance param overrides |

---

## Example 1 — Window family

```
create_family({
  "path": "/families/windows/standard.family.json",
  "name": "Standard Window",
  "category": "Window",
  "params": [
    {"name": "width",       "type": "number", "unit": "mm", "default": 900,  "min": 300, "max": 3000},
    {"name": "height",      "type": "number", "unit": "mm", "default": 1200, "min": 300, "max": 3000},
    {"name": "glazing",     "type": "enum",   "options": ["single","double","triple"], "default": "double"},
    {"name": "sill_height", "type": "number", "unit": "mm", "default": 900}
  ]
})
```

Add a narrow casement type preset:

```
add_family_type({
  "file_id": "<family-uuid>",
  "id": "type-narrow",
  "name": "Narrow Casement",
  "params": {"width": 450, "glazing": "double"}
})
```

Place an instance on wall-e1, overriding sill_height:

```
instantiate_family({
  "family_file_id": "<family-uuid>",
  "host_file_id": "<bim-uuid>",
  "host_ref": "wall-e1",
  "type_id": "type-narrow",
  "params": {"sill_height": 850}
})
```

Resolved params: `width=450, height=1200, glazing=double, sill_height=850`.

---

## Example 2 — Door family

```
create_family({
  "path": "/families/doors/hinged.family.json",
  "name": "Hinged Door",
  "category": "Door",
  "params": [
    {"name": "width",           "type": "number", "unit": "mm", "default": 900, "min": 600, "max": 2400},
    {"name": "height",          "type": "number", "unit": "mm", "default": 2100, "min": 1800, "max": 3000},
    {"name": "swing_direction", "type": "enum",   "options": ["left","right","double"], "default": "right"},
    {"name": "threshold",       "type": "number", "unit": "mm", "default": 0, "min": 0, "max": 50}
  ]
})
```

Add a double-door type:

```
add_family_type({
  "file_id": "<family-uuid>",
  "id": "type-double",
  "name": "Double Door",
  "params": {"width": 1800, "swing_direction": "double"}
})
```

---

## Example 3 — Structural column with steel section types

```
create_family({
  "path": "/families/structure/steel-column.family.json",
  "name": "Steel Column",
  "category": "Column",
  "params": [
    {"name": "height",       "type": "number", "unit": "mm", "default": 3000, "min": 500, "max": 20000},
    {"name": "section_depth","type": "number", "unit": "mm", "default": 200},
    {"name": "section_width","type": "number", "unit": "mm", "default": 100},
    {"name": "steel_grade",  "type": "enum",   "options": ["S235","S275","S355"], "default": "S275"}
  ]
})
```

Add IPE section types:

```
add_family_type({ "file_id": "<fam>", "id": "ipe200", "name": "IPE 200",
  "params": {"section_depth": 200, "section_width": 100} })

add_family_type({ "file_id": "<fam>", "id": "ipe300", "name": "IPE 300",
  "params": {"section_depth": 300, "section_width": 150} })
```

Place a column instance with S355 grade override:

```
instantiate_family({
  "family_file_id": "<fam>",
  "host_file_id": "<bim>",
  "type_id": "ipe300",
  "params": {"steel_grade": "S355", "height": 4500}
})
```

Resolved: `height=4500, section_depth=300, section_width=150, steel_grade=S355`.
