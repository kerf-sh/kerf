# BIM Family System Contract (T-109)

**Status:** FROZEN — downstream BIM agents (T-110 library, T-111 walls/doors/
windows/slabs, T-112 stairs, T-113 structural grid, T-114 site, T-115
materials) build on the interfaces listed below. **Do not change semantics in
this contract.** Add new fields / methods backward-compatibly only.

This document describes the public surface of `kerf_bim.family`, frozen
behaviours, and the rules downstream BIM modules must obey when they
subclass or compose against the model.

---

## 1. Three layers

The model is a strict three-layer pyramid mirrored on Revit's terminology:

```
FamilyDefinition  — schema: name, category, parameters, shared parameters
       │
       ▼
FamilyType        — named preset of *type-parameter* values
       │
       ▼
FamilyInstance    — placement: type ref + instance-parameter overrides + transform
```

* A `FamilyDefinition` declares two parameter groups: `type_parameters`
  and `instance_parameters`. The two groups **must not share a name**;
  doing so raises `DuplicateParameterError`.
* A `FamilyType` references its `FamilyDefinition` and stores a sparse
  map of `type_param_values`. Unset parameters fall through to the
  family-level default (or formula).
* A `FamilyInstance` references its `FamilyType` and stores a sparse
  map of `instance_param_values` plus a `Transform`.

This layering is **load-bearing**: schedules, libraries, and BOMs walk
families through all three layers in this order.

## 2. Parameter kinds

`Parameter.kind` is one of the following seven strings (frozen):

| Kind        | Storage     | Default policy                              |
|-------------|-------------|---------------------------------------------|
| `integer`   | Python `int` (not `bool`) | int required                                |
| `float`     | `float`     | numeric required                            |
| `string`    | `str`       | str required                                |
| `length`    | `float`, mm | numeric required; unit policy is renderer's |
| `angle`     | `float`, rad | numeric required; unit policy is renderer's |
| `boolean`   | `bool`      | bool required                               |
| `material`  | `str` (material id) | str required                          |

`length` and `angle` are deliberately numeric kinds (not new types) — they
carry a *semantic hint* for renderers and exporters without complicating
the resolver. Downstream BIM modules **must not** introduce new kinds
without bumping the schema version.

## 3. Formula grammar (safe AST evaluator)

`Parameter.formula` is an optional arithmetic expression evaluated against
already-resolved parameter values (plus any shared parameter bindings
exposed to the family).

**Allowed AST nodes:**

* Expression, BinOp, UnaryOp, Constant, Name, Load
* Call (callee must be a whitelisted name — see below)
* IfExp, Compare, BoolOp (for `a if cond else b`)
* Operators: `+ - * / // % **` plus unary `+ -` and `not`
* Comparisons: `== != < <= > >=`
* Boolean: `and`, `or`

**Whitelisted callables / constants (`SAFE_NAMES`):**

* Constants: `pi`, `e`, `tau`
* Trig: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`
* Misc: `sqrt`, `abs`, `floor`, `ceil`, `round`, `min`, `max`, `log`,
  `exp`, `radians`, `degrees`

**Banned outright:**

* `__import__`, `eval`, `exec`, `compile`, `open`, attribute access
  (`x.y`), subscript (`x[y]`), lambdas, comprehensions, function/class
  definitions, keyword arguments, `*args` / `**kwargs`, walrus,
  formatted strings, assignments — anything outside the whitelist.

Violations raise `FormulaError` at *parameter construction time* for
syntax/safety issues and at *resolve time* for runtime errors
(division-by-zero, math domain errors, etc.).

## 4. Evaluation order

Formula parameters are evaluated in **topological order** of their
declared dependencies. Algorithm: Kahn's algorithm with deterministic
(alphabetic) tie-breaks for stability.

* Non-formula parameters have no inbound edges.
* A formula's referenced names that resolve to whitelisted callables /
  constants / shared parameters are **not** part of the dependency graph
  (only references to *other family parameters* create edges).
* If a cycle is detected, resolution raises `CycleError`, which is a
  subclass of `FormulaError`. The error message lists every parameter
  participating in the cycle.

## 5. Resolution semantics (load-bearing)

```
final = (formula? evaluated_in_topo_order
                : instance_override
                : type_override
                : family_default)
```

Concretely, given a `FamilyInstance`, `resolve_instance(instance)`
applies — for each parameter declared on its family — the following
precedence:

1. **Formula:** if the parameter has a `formula`, evaluate it. Any
   explicit value at any layer is **ignored**.
2. Else, take the first defined value from:
   1. `instance.instance_param_values[name]`
   2. `instance.type.type_param_values[name]`
   3. `parameter.default`

Notes:

* Instance overrides **may target type parameters** — this matches
  Revit and is a deliberate flexibility for BIM authoring tools.
* Type overrides for *instance* parameters are also legal (used by
  T-110 library presets).
* Unknown parameter names in either layer raise
  `UnknownParameterError`.

## 6. Shared parameters

`SharedParameter(name, kind, scope, default)` — `scope` is `'project'`
or `'global'`. Shared parameters are declared on a `FamilyDefinition`
but their values are supplied externally to `resolve_instance` via the
`shared_values` keyword argument.

* They are **not** resolved as part of the family's parameter graph.
* They **are** exposed as additional name bindings during formula
  evaluation.
* Two distinct `FamilyDefinition`s that declare a `SharedParameter`
  with the same name resolve identically when given the same
  `shared_values` map. (This is what makes them *shared*.)

Scope semantics are advisory at the model layer — the storage layer
(project store vs global registry) enforces them.

## 7. Subclassing rules for downstream BIM modules

Modules like T-111 (`WallType`, `DoorType`, etc.) **may** subclass
`FamilyDefinition`, but **must**:

* Preserve the parameter-resolution semantics in §5. Do not add new
  override layers, do not change precedence.
* Use existing `ParameterKind` values. New kinds require a schema bump
  (coordinated across all BIM modules) and are forbidden at this
  schema version (`SCHEMA_VERSION = 1`).
* Only **add** state / methods, never remove or rename fields.
* If a module needs typed convenience accessors (e.g. `WallDefinition.
  height_param`), implement them as properties that read from
  `type_parameters` / `instance_parameters`.

A typical subclass pattern:

```python
from kerf_bim.family import FamilyDefinition, Parameter, make_family

class WallDefinition(FamilyDefinition):
    @classmethod
    def standard(cls, name: str) -> "WallDefinition":
        base = make_family(
            name=name,
            category="Wall",
            type_parameters=[
                Parameter("thickness", "length", default=100.0),
                Parameter("structure", "material", default="generic"),
            ],
            instance_parameters=[
                Parameter("base_offset", "length", default=0.0),
                Parameter("top_offset",  "length", default=0.0),
            ],
        )
        # promote to subclass — preserves id, fields:
        return cls(**base.__dict__)
```

## 8. Serialization

`family_to_dict(f)` / `family_from_dict(d)` produce / consume a
versioned envelope:

```
{
  "schema":  "kerf.bim.family",
  "version": 1,
  "id":      "<uuid>",
  "name":    "...",
  "category":"...",
  "description": "...",
  "type_parameters":     [<param-dict>, ...],
  "instance_parameters": [<param-dict>, ...],
  "shared_parameters":   [<shared-param-dict>, ...]
}
```

* Round-trip is **lossless** for everything stored on the dataclass.
  `family_from_dict(family_to_dict(f))` reconstructs an equal-by-fields
  `FamilyDefinition`, including its `id`.
* `FamilyType` / `FamilyInstance` have their own `type_to_dict` /
  `instance_to_dict` helpers. `*_from_dict` requires the live
  `FamilyDefinition` / `FamilyType` as a second argument (caller
  resolves the link from project storage).
* Unknown extra top-level keys are ignored on read for forward
  compatibility.

## 9. Errors

All errors raised by this package inherit from `FamilyError`
(`ValueError` subclass):

* `FormulaError` — formula syntax, unsafe construct, unknown name,
  runtime error
* `CycleError` — subclass of `FormulaError`; formula dependency cycle
* `UnknownParameterError` — value supplied for an undeclared parameter
* `DuplicateParameterError` — duplicate name across parameter groups

Downstream code should **catch `FamilyError`** (not bare `Exception`)
when graceful degradation is wanted.

## 10. Invariants (cheat sheet)

* Family parameter names: unique across `type_parameters` ∪
  `instance_parameters`.
* Parameter `kind` is one of seven frozen strings.
* `resolve_instance` returns a dict whose keys are exactly the union
  of declared type and instance parameter names.
* `SCHEMA_VERSION == 1`.
* No I/O, no DB access, no async — this module is pure-Python and
  importable from any environment.
