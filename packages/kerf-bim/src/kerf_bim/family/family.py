"""
kerf_bim.family.family
=======================

Core data model for the BIM parametric family system.

The model is a three-layer pyramid, inspired by (and named after) the
Revit family system:

    FamilyDefinition  — the schema: name, category, declared parameters
        │
        ▼
    FamilyType        — a named preset of type-parameter values
                          (e.g. "Door — 36×80")
        │
        ▼
    FamilyInstance    — a placement: references a FamilyType, carries
                          its own instance-parameter overrides and a
                          world transform.

Parameters split into two groups:

* **type_parameters**   — properties that vary *between types* but are
                           shared by all instances of a type
                           (e.g. door panel thickness).
* **instance_parameters** — properties that vary *between instances*
                            (e.g. frame_material on a specific door).

A :class:`SharedParameter` lets multiple families publish a value
under the same name with project- or global-wide scope, so reports /
schedules can group across heterogeneous element kinds.

Resolution semantics (formal, downstream modules must rely on this):

    1. For a *type parameter* on a FamilyInstance:
         a. If the type has a value (or a formula) for it → use that.
         b. Otherwise → use the parameter's default.
    2. For an *instance parameter* on a FamilyInstance:
         a. If the instance overrides it → use that.
         b. Else if a type-level override exists (rare but legal) → use that.
         c. Otherwise → use the parameter's default.
    3. Formula parameters override any explicit value at their layer.
       Formulae are evaluated in dependency order (topological sort).
       Cycles raise :class:`CycleError`.

This module is intentionally pure-Python with no dependency on the
wider Kerf runtime. Downstream BIM agents (T-110 library, T-111
walls/doors/windows/slabs, T-112 stairs, T-113 structural grid,
T-114 site, T-115 materials) compose against this model directly.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping, Sequence
from uuid import uuid4

from .evaluator import (
    CycleError,
    FormulaError,
    evaluate_formula,
    extract_referenced_names,
    resolve_parameters,
)

__all__ = [
    # Kinds
    "ParameterKind",
    "VALID_PARAMETER_KINDS",
    "SharedScope",
    "VALID_SHARED_SCOPES",
    # Errors
    "FamilyError",
    "FormulaError",
    "CycleError",
    "UnknownParameterError",
    "DuplicateParameterError",
    # Data classes
    "Parameter",
    "SharedParameter",
    "FamilyDefinition",
    "FamilyType",
    "FamilyInstance",
    "Transform",
    # Factory helpers
    "make_parameter",
    "make_family",
    "make_type",
    "make_instance",
    "identity_transform",
    # Resolution
    "resolve_instance",
    "resolve_type",
]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

ParameterKind = Literal[
    "integer",
    "float",
    "string",
    "length",
    "angle",
    "boolean",
    "material",
]

VALID_PARAMETER_KINDS: frozenset[str] = frozenset({
    "integer",
    "float",
    "string",
    "length",
    "angle",
    "boolean",
    "material",
})

SharedScope = Literal["project", "global"]
VALID_SHARED_SCOPES: frozenset[str] = frozenset({"project", "global"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FamilyError(ValueError):
    """Base class for all family-model errors raised by this module."""


class UnknownParameterError(FamilyError):
    """Raised when a referenced parameter is not declared on the family."""


class DuplicateParameterError(FamilyError):
    """Raised when two parameters share a name on the same family."""


# ---------------------------------------------------------------------------
# Transform — small 4x4 wrapper kept dependency-free
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Transform:
    """A 4x4 affine transform stored row-major.

    Kept intentionally simple (no numpy) so the family module remains
    importable from any environment. Downstream renderers can convert
    to whatever matrix type they prefer.
    """
    matrix: tuple[tuple[float, ...], ...] = field(
        default_factory=lambda: (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )

    def as_list(self) -> list[list[float]]:
        """Return a plain nested-list copy (for JSON / serialization)."""
        return [list(row) for row in self.matrix]

    @classmethod
    def from_translation(cls, x: float, y: float, z: float) -> "Transform":
        """Build a pure-translation transform."""
        return cls(matrix=(
            (1.0, 0.0, 0.0, float(x)),
            (0.0, 1.0, 0.0, float(y)),
            (0.0, 0.0, 1.0, float(z)),
            (0.0, 0.0, 0.0, 1.0),
        ))

    @classmethod
    def from_list(cls, rows: Sequence[Sequence[float]]) -> "Transform":
        """Build a Transform from a 4x4 nested list (validated)."""
        rows = tuple(tuple(float(v) for v in row) for row in rows)
        if len(rows) != 4 or any(len(r) != 4 for r in rows):
            raise FamilyError("transform must be a 4x4 matrix")
        return cls(matrix=rows)


def identity_transform() -> Transform:
    """Return the identity transform (factory helper)."""
    return Transform()


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------


@dataclass
class Parameter:
    """A single parameter declaration on a :class:`FamilyDefinition`.

    Attributes
    ----------
    name : str
        Identifier (unique within its parameter group — type or
        instance — on a family).
    kind : ParameterKind
        Value kind. One of:
        ``integer | float | string | length | angle | boolean | material``.

        * ``length`` and ``angle`` are numeric units (mm and radians,
          by convention). Stored as floats; renderers / exporters
          apply unit policy.
        * ``material`` stores a material identifier (string).
    default : Any
        Default value used when no override is supplied. Must match
        ``kind`` per :func:`_validate_default`.
    formula : str | None
        Optional safe arithmetic expression evaluated against other
        resolved parameters. When set, the formula's result *replaces*
        any explicit value supplied for this parameter.
    description : str
        Human-readable description (free text).
    """
    name: str
    kind: ParameterKind = "float"
    default: Any = 0.0
    formula: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FamilyError("parameter name must be a non-empty string")
        if self.kind not in VALID_PARAMETER_KINDS:
            raise FamilyError(
                f"parameter '{self.name}': unknown kind '{self.kind}' "
                f"(allowed: {sorted(VALID_PARAMETER_KINDS)})"
            )
        _validate_default(self)
        if self.formula is not None:
            if not isinstance(self.formula, str):
                raise FamilyError(
                    f"parameter '{self.name}': formula must be a string"
                )
            # Smoke-test the formula at declaration time. We bind every
            # referenced name to a placeholder numeric so legitimate
            # forward-references (other family params) succeed, while
            # syntax / unsafe-construct / unknown-callable errors fail
            # loudly here — *before* the family is in use.
            try:
                evaluate_formula(
                    self.formula,
                    {n: 1.0 for n in extract_referenced_names(self.formula)},
                )
            except FormulaError as exc:
                msg = str(exc)
                # Defer pure runtime errors (e.g. division-by-zero with
                # placeholder bindings) to resolve-time; surface
                # structural problems immediately.
                if (
                    "syntax" in msg
                    or "unsafe" in msg
                    or "not whitelisted" in msg
                    or "must use a plain name" in msg
                    or "keyword arguments" in msg
                    or "unknown name" in msg
                    or "empty" in msg
                ):
                    raise FamilyError(
                        f"parameter '{self.name}': {msg}"
                    ) from None


def _validate_default(p: Parameter) -> None:
    """Check that ``p.default`` is compatible with ``p.kind``."""
    if p.formula is not None:
        # Formula values are computed; default is irrelevant.
        return
    if p.kind == "integer":
        if not isinstance(p.default, int) or isinstance(p.default, bool):
            raise FamilyError(
                f"parameter '{p.name}': default must be int for kind 'integer'"
            )
    elif p.kind in ("float", "length", "angle"):
        if isinstance(p.default, bool) or not isinstance(p.default, (int, float)):
            raise FamilyError(
                f"parameter '{p.name}': default must be numeric for kind '{p.kind}'"
            )
    elif p.kind == "string":
        if not isinstance(p.default, str):
            raise FamilyError(
                f"parameter '{p.name}': default must be str for kind 'string'"
            )
    elif p.kind == "boolean":
        if not isinstance(p.default, bool):
            raise FamilyError(
                f"parameter '{p.name}': default must be bool for kind 'boolean'"
            )
    elif p.kind == "material":
        if not isinstance(p.default, str):
            raise FamilyError(
                f"parameter '{p.name}': default must be str (material id) "
                f"for kind 'material'"
            )


# ---------------------------------------------------------------------------
# SharedParameter
# ---------------------------------------------------------------------------


@dataclass
class SharedParameter:
    """A parameter shared between multiple families.

    Shared parameters live in a *scope* — ``project`` (this project
    only) or ``global`` (every Kerf project). They are typically used
    so schedules can group "wall thickness" across many distinct wall
    families with the same key.

    The dataclass itself just stores the declaration; resolution is
    handled by a :class:`SharedParameterTable` (see
    :func:`resolve_instance`'s ``shared_values`` argument).
    """
    name: str
    kind: ParameterKind = "float"
    scope: SharedScope = "project"
    default: Any = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FamilyError("shared parameter name must be a non-empty string")
        if self.kind not in VALID_PARAMETER_KINDS:
            raise FamilyError(
                f"shared parameter '{self.name}': unknown kind '{self.kind}'"
            )
        if self.scope not in VALID_SHARED_SCOPES:
            raise FamilyError(
                f"shared parameter '{self.name}': unknown scope '{self.scope}' "
                f"(allowed: {sorted(VALID_SHARED_SCOPES)})"
            )


# ---------------------------------------------------------------------------
# FamilyDefinition / FamilyType / FamilyInstance
# ---------------------------------------------------------------------------


@dataclass
class FamilyDefinition:
    """The schema layer: a family's declared identity and parameter set.

    Subclassing
    -----------
    Downstream BIM modules (walls, doors, stairs, ...) are expected to
    subclass this and add module-specific helpers — *but they must
    not change the parameter-resolution semantics*. Add behaviour, not
    state. See ``BIM_FAMILY_CONTRACT.md`` for the frozen invariants.
    """
    name: str
    category: str
    type_parameters: dict[str, Parameter] = field(default_factory=dict)
    instance_parameters: dict[str, Parameter] = field(default_factory=dict)
    shared_parameters: dict[str, SharedParameter] = field(default_factory=dict)
    description: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FamilyError("family name must be a non-empty string")
        if not isinstance(self.category, str) or not self.category:
            raise FamilyError("family category must be a non-empty string")
        # Allow dict-or-list-of-Parameter for ergonomic construction.
        self.type_parameters = _coerce_param_map(self.type_parameters, "type_parameters")
        self.instance_parameters = _coerce_param_map(self.instance_parameters, "instance_parameters")
        # type / instance parameter names must not collide — that would
        # make resolution ambiguous.
        collisions = set(self.type_parameters) & set(self.instance_parameters)
        if collisions:
            raise DuplicateParameterError(
                f"family '{self.name}': parameter name(s) declared as both "
                f"type and instance: {sorted(collisions)}"
            )
        self.shared_parameters = _coerce_shared_map(self.shared_parameters)

    # -- introspection ------------------------------------------------------

    def parameter(self, name: str) -> Parameter:
        """Return the declared :class:`Parameter` for *name* or raise."""
        if name in self.type_parameters:
            return self.type_parameters[name]
        if name in self.instance_parameters:
            return self.instance_parameters[name]
        raise UnknownParameterError(
            f"family '{self.name}' has no parameter '{name}'"
        )

    def has_parameter(self, name: str) -> bool:
        return name in self.type_parameters or name in self.instance_parameters

    def all_parameters(self) -> dict[str, Parameter]:
        """Return type ∪ instance parameters as a single map."""
        merged: dict[str, Parameter] = {}
        merged.update(self.type_parameters)
        merged.update(self.instance_parameters)
        return merged


@dataclass
class FamilyType:
    """A named preset of *type-parameter* values within a family.

    ``type_param_values`` is a sparse map — params not listed inherit
    the family-level default (or formula).
    """
    definition: FamilyDefinition
    name: str
    type_param_values: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FamilyError("family-type name must be a non-empty string")
        for k in self.type_param_values:
            if k not in self.definition.type_parameters:
                raise UnknownParameterError(
                    f"family '{self.definition.name}' type '{self.name}': "
                    f"value provided for unknown type parameter '{k}'"
                )


@dataclass
class FamilyInstance:
    """A placed instance of a :class:`FamilyType`.

    ``instance_param_values`` is sparse — unset params fall through to
    the family-level default. ``transform`` defaults to identity.
    """
    type: FamilyType
    instance_param_values: dict[str, Any] = field(default_factory=dict)
    transform: Transform = field(default_factory=identity_transform)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        defn = self.type.definition
        for k in self.instance_param_values:
            if k not in defn.instance_parameters:
                # Soft path: allow an instance to *also* override a type
                # parameter — this matches Revit's behaviour. We do not
                # raise on that case.
                if k not in defn.type_parameters:
                    raise UnknownParameterError(
                        f"family '{defn.name}': instance overrides "
                        f"unknown parameter '{k}'"
                    )
        if not isinstance(self.transform, Transform):
            self.transform = Transform.from_list(self.transform)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_param_map(
    src: Mapping[str, Parameter] | Iterable[Parameter],
    label: str,
) -> dict[str, Parameter]:
    """Coerce a dict-or-iterable of Parameter into a dict keyed by name."""
    if isinstance(src, dict):
        out: dict[str, Parameter] = {}
        for k, v in src.items():
            if not isinstance(v, Parameter):
                raise FamilyError(f"{label}: value for '{k}' must be a Parameter")
            if v.name != k:
                # Keep dict key authoritative — but warn loudly.
                out[k] = Parameter(
                    name=k,
                    kind=v.kind,
                    default=v.default,
                    formula=v.formula,
                    description=v.description,
                )
            else:
                out[k] = v
        return out
    out2: dict[str, Parameter] = {}
    for p in src:
        if not isinstance(p, Parameter):
            raise FamilyError(f"{label}: every entry must be a Parameter")
        if p.name in out2:
            raise DuplicateParameterError(
                f"{label}: duplicate parameter name '{p.name}'"
            )
        out2[p.name] = p
    return out2


def _coerce_shared_map(
    src: Mapping[str, SharedParameter] | Iterable[SharedParameter] | None,
) -> dict[str, SharedParameter]:
    if src is None:
        return {}
    if isinstance(src, dict):
        out: dict[str, SharedParameter] = {}
        for k, v in src.items():
            if not isinstance(v, SharedParameter):
                raise FamilyError(
                    f"shared_parameters: value for '{k}' must be a SharedParameter"
                )
            out[k] = v
        return out
    out2: dict[str, SharedParameter] = {}
    for sp in src:
        if not isinstance(sp, SharedParameter):
            raise FamilyError("shared_parameters: every entry must be a SharedParameter")
        if sp.name in out2:
            raise DuplicateParameterError(
                f"shared_parameters: duplicate name '{sp.name}'"
            )
        out2[sp.name] = sp
    return out2


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_parameter(
    name: str,
    kind: ParameterKind = "float",
    default: Any = None,
    formula: str | None = None,
    description: str = "",
) -> Parameter:
    """Create a :class:`Parameter` with kind-appropriate default if omitted."""
    if default is None and formula is None:
        default = _zero_for_kind(kind)
    if default is None and formula is not None:
        # placeholder default — never used because formula wins, but
        # keeps dataclass typing happy.
        default = _zero_for_kind(kind)
    return Parameter(
        name=name,
        kind=kind,
        default=default,
        formula=formula,
        description=description,
    )


def _zero_for_kind(kind: ParameterKind) -> Any:
    if kind == "integer":
        return 0
    if kind in ("float", "length", "angle"):
        return 0.0
    if kind == "string":
        return ""
    if kind == "boolean":
        return False
    if kind == "material":
        return ""
    return None


def make_family(
    name: str,
    category: str,
    type_parameters: Iterable[Parameter] | Mapping[str, Parameter] | None = None,
    instance_parameters: Iterable[Parameter] | Mapping[str, Parameter] | None = None,
    shared_parameters: Iterable[SharedParameter] | None = None,
    description: str = "",
    id: str | None = None,
) -> FamilyDefinition:
    """Construct a :class:`FamilyDefinition` ergonomically."""
    kwargs: dict[str, Any] = {
        "name": name,
        "category": category,
        "type_parameters": _coerce_param_map(type_parameters or {}, "type_parameters"),
        "instance_parameters": _coerce_param_map(instance_parameters or {}, "instance_parameters"),
        "shared_parameters": _coerce_shared_map(shared_parameters),
        "description": description,
    }
    if id is not None:
        kwargs["id"] = id
    return FamilyDefinition(**kwargs)


def make_type(
    definition: FamilyDefinition,
    name: str,
    type_param_values: Mapping[str, Any] | None = None,
    description: str = "",
) -> FamilyType:
    """Construct a :class:`FamilyType` ergonomically."""
    return FamilyType(
        definition=definition,
        name=name,
        type_param_values=dict(type_param_values or {}),
        description=description,
    )


def make_instance(
    type: FamilyType,
    instance_param_values: Mapping[str, Any] | None = None,
    transform: Transform | Sequence[Sequence[float]] | None = None,
    id: str | None = None,
) -> FamilyInstance:
    """Construct a :class:`FamilyInstance` ergonomically."""
    kwargs: dict[str, Any] = {
        "type": type,
        "instance_param_values": dict(instance_param_values or {}),
        "transform": (
            transform if isinstance(transform, Transform)
            else (Transform.from_list(transform) if transform is not None
                  else identity_transform())
        ),
    }
    if id is not None:
        kwargs["id"] = id
    return FamilyInstance(**kwargs)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _build_overrides(
    defn: FamilyDefinition,
    type_values: Mapping[str, Any],
    instance_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Layer overrides per the contract (type < instance, instance wins).

    Formula parameters are *not* overridden — formulae always win.
    """
    out: dict[str, Any] = {}

    # Type-layer overrides (apply to type parameters).
    for k, v in type_values.items():
        p = defn.type_parameters.get(k) or defn.instance_parameters.get(k)
        if p is None:
            raise UnknownParameterError(
                f"family '{defn.name}': type override for unknown "
                f"parameter '{k}'"
            )
        if p.formula:
            continue
        out[k] = v

    # Instance-layer overrides (apply to anything, win over type).
    for k, v in instance_values.items():
        p = defn.instance_parameters.get(k) or defn.type_parameters.get(k)
        if p is None:
            raise UnknownParameterError(
                f"family '{defn.name}': instance override for unknown "
                f"parameter '{k}'"
            )
        if p.formula:
            continue
        out[k] = v

    return out


def resolve_type(
    ftype: FamilyType,
    *,
    shared_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a :class:`FamilyType`'s parameter values *without* an
    instance.

    Useful for libraries / schedules where you want canonical type
    metadata. Instance parameters fall back to family defaults.

    Raises
    ------
    CycleError, FormulaError, UnknownParameterError
    """
    defn = ftype.definition
    overrides = _build_overrides(defn, ftype.type_param_values, {})
    extras = _shared_extras(defn, shared_values or {})
    return resolve_parameters(defn.all_parameters(), overrides, extra_bindings=extras)


def resolve_instance(
    instance: FamilyInstance,
    *,
    shared_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a :class:`FamilyInstance`'s parameter values.

    The full resolution sequence is:

        family defaults  ←  type values  ←  instance values  ←  formulae

    Parameters
    ----------
    instance : FamilyInstance
    shared_values : Mapping[str, Any] | None
        Optional concrete values for any :class:`SharedParameter`
        declared on the family. Made available to formula evaluation
        as additional name bindings.

    Returns
    -------
    dict[str, Any]
        ``name → resolved value`` map. The keys cover every parameter
        declared on the family (type + instance).

    Raises
    ------
    CycleError
        Formula dependencies form a cycle.
    FormulaError
        A formula is malformed or fails to evaluate.
    UnknownParameterError
        Type or instance values reference a parameter not on the family.
    """
    defn = instance.type.definition
    overrides = _build_overrides(
        defn,
        instance.type.type_param_values,
        instance.instance_param_values,
    )
    extras = _shared_extras(defn, shared_values or {})
    return resolve_parameters(defn.all_parameters(), overrides, extra_bindings=extras)


def _shared_extras(
    defn: FamilyDefinition,
    shared_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the bindings made available to formulae from shared params.

    Resolution order: caller-supplied value > shared parameter default.
    Only shared parameters declared on the family are exposed.
    """
    out: dict[str, Any] = {}
    for name, sp in defn.shared_parameters.items():
        if name in shared_values:
            out[name] = shared_values[name]
        else:
            out[name] = sp.default
    return out


# ---------------------------------------------------------------------------
# Misc utilities
# ---------------------------------------------------------------------------


def deep_copy_value(v: Any) -> Any:
    """Public alias around :func:`copy.deepcopy` for downstream code."""
    return copy.deepcopy(v)


def _is_finite_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
