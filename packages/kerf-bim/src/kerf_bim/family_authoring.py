"""
kerf_bim.family_authoring
==========================

High-level authoring helpers for parametric BIM families (T-109).

Public surface
--------------
* :class:`FamilyTemplate`     — lightweight authoring schema: declares
  parameters and an expression-driven geometry generator.
* :func:`validate_family_template` — checks for missing params, invalid
  expressions, and formula dependency cycles; returns a list of error
  strings (empty ⇒ valid).
* :func:`generate_body`       — resolves a template against a concrete
  parameter set and returns a plain-dict "body" describing the geometry.
  For a circular-section column the body carries ``diameter``,
  ``height``, and ``volume`` (= π D²H / 4).

Design notes
------------
* This module is intentionally pure-Python with no dependency on the
  wider Kerf runtime or kerf-bim's IFC machinery. It composes on top of
  the existing :mod:`kerf_bim.family` primitive layer.
* The ``FamilyTemplate`` authoring schema is intentionally simpler than
  :class:`kerf_bim.family.FamilyDefinition` — it is the *authoring*
  surface (what the UI exposes to the user) and maps onto
  ``FamilyDefinition`` when the template is committed.
* ``validate_family_template`` is the oracle tested by
  ``test_family_authoring.py``: it must detect cycles, missing-param
  references in expressions, and invalid expression syntax.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from kerf_bim.family.evaluator import (
    CycleError,
    FormulaError,
    evaluate_formula,
    extract_referenced_names,
    topo_sort,
)


__all__ = [
    "FamilyTemplate",
    "TemplateParameter",
    "validate_family_template",
    "generate_body",
    "COLUMN_TEMPLATE",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TemplateParameter:
    """A single parameter declaration in a :class:`FamilyTemplate`.

    Attributes
    ----------
    name : str
        Identifier, unique within the template.
    kind : str
        One of ``"length"``, ``"float"``, ``"material"``, ``"angle"``,
        ``"integer"``, ``"string"``, ``"boolean"``.
    default : Any
        Default value used when no override is supplied.
    min_val : float | None
        Optional inclusive lower bound (for numeric kinds).
    max_val : float | None
        Optional inclusive upper bound (for numeric kinds).
    expression : str | None
        If set, the parameter's value is *computed* from other resolved
        parameters via the same safe-expression evaluator as the family
        layer. Overrides any explicit value.
    description : str
        Human-readable hint displayed in the authoring UI.
    """
    name: str
    kind: str = "length"
    default: Any = 0.0
    min_val: float | None = None
    max_val: float | None = None
    expression: str | None = None
    description: str = ""


@dataclass
class FamilyTemplate:
    """Authoring-level schema for a parametric BIM family.

    Parameters
    ----------
    name : str
        Human-readable family name (e.g. ``"Parametric Column"``).
    category : str
        BIM category (e.g. ``"Column"``, ``"Door"``, ``"Window"``).
    parameters : list[TemplateParameter]
        Ordered list of parameter declarations.  Formula parameters may
        reference *earlier-declared* parameters (or any parameter — the
        topological sort handles ordering).
    geometry_type : str
        Tags the body shape generator.  Recognised values:
        ``"circular_column"`` (diameter + height → cylinder),
        ``"rectangular_column"`` (width + depth + height → box).
        Unknown values are passed through verbatim in the body dict.
    description : str
        Free-text description shown in the UI.
    """
    name: str
    category: str = "Column"
    parameters: list[TemplateParameter] = field(default_factory=list)
    geometry_type: str = "circular_column"
    description: str = ""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_family_template(template: FamilyTemplate) -> list[str]:
    """Validate *template* and return a list of human-readable error strings.

    An empty list means the template is valid.

    Checks performed
    ----------------
    1. Template-level: ``name`` non-empty, ``category`` non-empty.
    2. Parameter-level: each parameter has a non-empty name; numeric
       defaults within [min_val, max_val]; expression syntax valid.
    3. Cross-parameter: no duplicate parameter names.
    4. Dependency graph: expressions may only reference names that are
       declared as parameters on the template (or are whitelisted math
       constants/functions); a cycle among formula parameters raises a
       :class:`CycleError` which is caught and surfaced as an error string.

    Parameters
    ----------
    template : FamilyTemplate

    Returns
    -------
    list[str]
        Validation error messages.  Empty ⇒ valid.
    """
    errors: list[str] = []

    # -- template-level -------------------------------------------------------

    if not template.name or not template.name.strip():
        errors.append("template name must be a non-empty string")

    if not template.category or not template.category.strip():
        errors.append("template category must be a non-empty string")

    # -- parameter-level -------------------------------------------------------

    seen_names: set[str] = set()

    for i, p in enumerate(template.parameters):
        prefix = f"parameter[{i}] '{p.name}'"

        if not p.name or not p.name.strip():
            errors.append(f"parameter[{i}]: name must be a non-empty string")
            continue

        if p.name in seen_names:
            errors.append(f"duplicate parameter name: '{p.name}'")
        else:
            seen_names.add(p.name)

        numeric_kinds = {"length", "float", "angle", "integer"}
        if p.kind in numeric_kinds and p.expression is None:
            try:
                val = float(p.default)
            except (TypeError, ValueError):
                errors.append(f"{prefix}: default is not numeric for kind '{p.kind}'")
                val = None

            if val is not None:
                if p.min_val is not None and val < p.min_val:
                    errors.append(
                        f"{prefix}: default {val} is below min_val {p.min_val}"
                    )
                if p.max_val is not None and val > p.max_val:
                    errors.append(
                        f"{prefix}: default {val} is above max_val {p.max_val}"
                    )

        if p.expression is not None:
            try:
                # Smoke-test: bind all referenced names to 1.0 placeholders
                refs = extract_referenced_names(p.expression)
                evaluate_formula(p.expression, {n: 1.0 for n in refs})
            except FormulaError as exc:
                errors.append(f"{prefix}: invalid expression: {exc}")

    # -- dependency / cycle check ---------------------------------------------

    if not errors:
        # Only run when no prior errors (param names must be stable).
        param_names: set[str] = {p.name for p in template.parameters}

        # Check that expression references only declared params (or safe names).
        from kerf_bim.family.evaluator import SAFE_NAMES  # lazy import

        for p in template.parameters:
            if p.expression is None:
                continue
            refs = extract_referenced_names(p.expression)
            missing = refs - param_names - set(SAFE_NAMES)
            for m in sorted(missing):
                errors.append(
                    f"parameter '{p.name}': expression references unknown name '{m}'"
                )

        if not errors:
            # Build the dependency graph for formula parameters and topo-sort.
            deps: dict[str, set[str]] = {}
            for p in template.parameters:
                if p.expression is not None:
                    deps[p.name] = extract_referenced_names(p.expression) & param_names
                else:
                    deps[p.name] = set()
            try:
                topo_sort(deps)
            except CycleError as exc:
                errors.append(f"formula dependency cycle: {exc}")

    return errors


# ---------------------------------------------------------------------------
# Body generator
# ---------------------------------------------------------------------------


def generate_body(
    template: FamilyTemplate,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve *template* with *overrides* and return a geometry body dict.

    The returned dict always contains:

    * ``"name"``          — template name
    * ``"category"``      — BIM category
    * ``"geometry_type"`` — geometry tag from the template
    * ``"params"``        — fully-resolved parameter map
    * geometry-specific computed values (e.g. ``"volume"`` for columns)

    Parameters
    ----------
    template : FamilyTemplate
    overrides : dict[str, Any] | None
        Parameter values that override defaults.  Formula parameters
        cannot be overridden — their expressions always win.

    Returns
    -------
    dict[str, Any]

    Raises
    ------
    ValueError
        If the template fails validation.
    FormulaError, CycleError
        On expression evaluation problems (only if the template was not
        pre-validated by the caller).
    """
    errors = validate_family_template(template)
    if errors:
        raise ValueError(
            f"FamilyTemplate '{template.name}' is invalid: " + "; ".join(errors)
        )

    overrides = dict(overrides or {})

    # --- resolve parameters in topological order ----------------------------

    param_map: dict[str, TemplateParameter] = {p.name: p for p in template.parameters}
    deps: dict[str, set[str]] = {}
    for p in template.parameters:
        if p.expression is not None:
            deps[p.name] = extract_referenced_names(p.expression) & set(param_map)
        else:
            deps[p.name] = set()

    order = topo_sort(deps)

    resolved: dict[str, Any] = {}
    for name in order:
        p = param_map[name]
        if p.expression is not None:
            resolved[name] = evaluate_formula(p.expression, resolved)
        elif name in overrides:
            val = overrides[name]
            # Clamp numeric values to declared bounds.
            if p.kind in {"length", "float", "angle", "integer"}:
                if p.min_val is not None:
                    val = max(p.min_val, float(val))
                if p.max_val is not None:
                    val = min(p.max_val, float(val))
            resolved[name] = val
        else:
            resolved[name] = p.default

    # --- geometry-specific augmentation ------------------------------------

    body: dict[str, Any] = {
        "name": template.name,
        "category": template.category,
        "geometry_type": template.geometry_type,
        "params": resolved,
    }

    if template.geometry_type == "circular_column":
        D = float(resolved.get("D", resolved.get("diameter", 0.0)))
        H = float(resolved.get("H", resolved.get("height", 0.0)))
        body["volume"] = math.pi * D * D * H / 4.0
        body["diameter"] = D
        body["height"] = H

    elif template.geometry_type == "rectangular_column":
        W = float(resolved.get("W", resolved.get("width", 0.0)))
        DEP = float(resolved.get("depth", resolved.get("D", 0.0)))
        H = float(resolved.get("H", resolved.get("height", 0.0)))
        body["volume"] = W * DEP * H
        body["width"] = W
        body["depth"] = DEP
        body["height"] = H

    return body


# ---------------------------------------------------------------------------
# Built-in template: parametric circular column
# ---------------------------------------------------------------------------

#: A ready-made parametric column template (diameter D, height H).
#: The volume formula π·D²·H/4 is exercised by the analytic pytest oracle.
COLUMN_TEMPLATE = FamilyTemplate(
    name="Parametric Column",
    category="Column",
    parameters=[
        TemplateParameter(
            name="D",
            kind="length",
            default=0.3,
            min_val=0.05,
            max_val=5.0,
            description="Column diameter (m)",
        ),
        TemplateParameter(
            name="H",
            kind="length",
            default=3.0,
            min_val=0.5,
            max_val=50.0,
            description="Column height (m)",
        ),
        TemplateParameter(
            name="material",
            kind="material",
            default="concrete_m30",
            description="Structural material from the T-115 catalogue",
        ),
    ],
    geometry_type="circular_column",
    description="Round concrete (or steel/timber) column parameterised by diameter and height.",
)
