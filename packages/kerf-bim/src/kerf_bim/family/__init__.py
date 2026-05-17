"""
kerf_bim.family
================

Parametric family system for the BIM stack — T-109 foundation.

Public surface
--------------
* :class:`FamilyDefinition` — schema + parameter set
* :class:`FamilyType`       — named preset of type-parameter values
* :class:`FamilyInstance`   — placed instance with transform & overrides
* :class:`Parameter`        — typed parameter declaration
* :class:`SharedParameter`  — cross-family scoped parameter
* :class:`Transform`        — 4x4 transform wrapper

* :func:`resolve_instance` / :func:`resolve_type`
    Layered parameter resolution with formula evaluation.
* :func:`family_to_dict` / :func:`family_from_dict`
    Round-trip serialization.
* :func:`evaluate_formula`
    Safe arithmetic evaluator (AST whitelist).

See ``BIM_FAMILY_CONTRACT.md`` next to this package for the invariants
downstream BIM modules (walls, doors, stairs, ...) rely on.
"""
from __future__ import annotations

from .evaluator import (
    CycleError,
    FormulaError,
    SAFE_NAMES,
    evaluate_formula,
    extract_referenced_names,
    resolve_parameters,
    topo_sort,
)
from .family import (
    DuplicateParameterError,
    FamilyDefinition,
    FamilyError,
    FamilyInstance,
    FamilyType,
    Parameter,
    ParameterKind,
    SharedParameter,
    SharedScope,
    Transform,
    UnknownParameterError,
    VALID_PARAMETER_KINDS,
    VALID_SHARED_SCOPES,
    identity_transform,
    make_family,
    make_instance,
    make_parameter,
    make_type,
    resolve_instance,
    resolve_type,
)
from .serialize import (
    SCHEMA,
    SCHEMA_VERSION,
    family_from_dict,
    family_to_dict,
    instance_from_dict,
    instance_to_dict,
    parameter_from_dict,
    parameter_to_dict,
    shared_parameter_from_dict,
    shared_parameter_to_dict,
    type_from_dict,
    type_to_dict,
)

__all__ = [
    # Vocabulary / kinds
    "ParameterKind",
    "SharedScope",
    "VALID_PARAMETER_KINDS",
    "VALID_SHARED_SCOPES",
    "SAFE_NAMES",
    # Errors
    "FamilyError",
    "FormulaError",
    "CycleError",
    "DuplicateParameterError",
    "UnknownParameterError",
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
    "resolve_parameters",
    # Evaluator internals (occasionally needed downstream)
    "evaluate_formula",
    "extract_referenced_names",
    "topo_sort",
    # Serialization
    "SCHEMA",
    "SCHEMA_VERSION",
    "family_to_dict",
    "family_from_dict",
    "type_to_dict",
    "type_from_dict",
    "instance_to_dict",
    "instance_from_dict",
    "parameter_to_dict",
    "parameter_from_dict",
    "shared_parameter_to_dict",
    "shared_parameter_from_dict",
]
