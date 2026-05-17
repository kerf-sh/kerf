# Family — Parametric Family System

Pure-Python data model for parametric families: define named parameter sets (types),
instantiate them with optional overrides, evaluate arithmetic formulae safely, and
produce resolved build-recipe dicts.

---

## When to use

Keywords: parametric family, family table, design table, part family, product family,
FamilyDef, FamilyType, FamilyInstance, parameter formula, parametric configuration,
typed part, family instantiation, family variant, recipe template, configuration table.

---

## Concepts

**FamilyParam** — a named parameter with type (`"number"` | `"string"` | `"bool"`),
default value, optional range, and an optional arithmetic formula referencing other params.

**FamilyType** — a pre-defined set of parameter overrides within a family (e.g.
`"Door 900x2100"`).

**FamilyInstance** — a concrete instantiation of a type with per-instance overrides.

**Recipe template** — a plain dict whose string values may contain `{param_name}`
placeholders that are substituted at instantiation time.

---

## Entrypoints

### `family_define(name, params, recipe_template, description) -> dict`

Register a new parametric family in the in-memory store.

**Parameters:**
- `name` — unique family name
- `params` — list of param dicts: `{name, param_type?, default?, min_value?, max_value?, formula?, description?}`
- `recipe_template` — dict with `{param_name}` placeholders (optional)
- `description` — human-readable description (optional)

**Returns:** `{"ok": True, "family_name": "<name>"}` or `{"ok": False, "errors": [...]}`

---

### `family_add_type(family_name, type_name, values, description) -> dict`

Add a named type (parameter-value set) to an existing family.

- `values` — dict of param overrides; unknown param names produce an error
- Range validation is run against the merged (defaults + overrides) set

**Returns:** `{"ok": True, "family_name": ..., "type_name": ...}` or `{"ok": False, "errors": [...]}`

---

### `family_instantiate(family_name, type_name, instance_name, overrides) -> dict`

Instantiate a type and resolve the parametric recipe.

Merge order: type values → instance overrides → formula evaluation → range check → template substitution.

**Returns:**
```json
{
  "ok": true,
  "instance": {
    "name": "Entry Door",
    "family_name": "Door",
    "type_name": "Door 900x2100",
    "overrides": {}
  },
  "resolved_params": { "width": 900, "height": 2100, "area": 1.89 },
  "recipe": { "op": "pad", "width": "900", "height": "2100" }
}
```

---

### `family_validate(family_name, values) -> dict`

Validate a set of param values against a family's constraints without modifying the
registry.  Returns `{"ok": True, "resolved_params": {...}}` or `{"ok": False, "errors": [...]}`.

---

## Formula system

Formulae are safe arithmetic expressions:
- Operators: `+`, `-`, `*`, `/`, `**`, `//`, `%`, unary `-`
- Math functions: `sqrt`, `abs`, `floor`, `ceil`, `round`, `sin`, `cos`, `tan`, `pi`, `e`
- Variables: other param names in the same family
- No `eval` of arbitrary code — uses AST whitelist
- Cycle detection via Tarjan DFS before resolution

Example: `{"name": "area", "formula": "width * height / 1e6"}`

---

## Usage snippets

```python
from kerf_cad_core.family.model import family_define, family_add_type, family_instantiate

# Define a Door family
family_define(
    "Door",
    params=[
        {"name": "width",  "param_type": "number", "default": 800, "min_value": 600, "max_value": 1200},
        {"name": "height", "param_type": "number", "default": 2100},
        {"name": "area",   "param_type": "number", "default": 0, "formula": "width * height / 1e6"},
    ],
    recipe_template={"op": "door_panel", "w": "{width}", "h": "{height}"},
    description="Standard door panel",
)

# Add a type
family_add_type("Door", "Door 900x2100", {"width": 900, "height": 2100})

# Instantiate
result = family_instantiate("Door", "Door 900x2100", "Entry Door")
# result["resolved_params"]["area"] == 1.89
# result["recipe"] == {"op": "door_panel", "w": "900", "h": "2100"}
```

```python
# Validate without instantiating
from kerf_cad_core.family.model import family_validate
v = family_validate("Door", {"width": 750})
# v["resolved_params"]["area"] == 1.5750...
```

```python
# Formula with math function
family_define(
    "CircularPlate",
    params=[
        {"name": "diameter", "param_type": "number", "default": 100},
        {"name": "area",     "param_type": "number", "formula": "pi * (diameter/2)**2"},
    ],
)
```

---

## Caveats

- Registry is **in-memory** per Python process — not persisted automatically.  Caller is
  responsible for serializing/restoring family definitions across sessions.
- Formula params are always computed; explicit values for formula params in `overrides` are
  silently ignored.
- `family_define` errors if the family name already exists; use a different name or
  restart the process to redefine.
- `_clear_registry()` (test helper) resets the entire in-memory store.
