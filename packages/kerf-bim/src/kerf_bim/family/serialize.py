"""
kerf_bim.family.serialize
==========================

Round-trip serialization of :class:`FamilyDefinition` (and its
companion types) to/from plain ``dict`` for JSON storage.

The on-disk schema is a versioned envelope::

    {
      "schema": "kerf.bim.family",
      "version": 1,
      "id": "...",
      "name": "Door",
      "category": "Door",
      "description": "...",
      "type_parameters":     [<param-dict>, ...],
      "instance_parameters": [<param-dict>, ...],
      "shared_parameters":   [<shared-param-dict>, ...]
    }

This module provides:

    family_to_dict(family) -> dict
    family_from_dict(d)    -> FamilyDefinition

plus helpers for the supporting types: ``type_to_dict`` /
``type_from_dict``, ``instance_to_dict`` / ``instance_from_dict``.

Round-trip semantics: ``family_from_dict(family_to_dict(f))`` produces
a :class:`FamilyDefinition` whose attributes match ``f`` exactly,
including the generated ``id``.
"""
from __future__ import annotations

from typing import Any

from .family import (
    FamilyDefinition,
    FamilyError,
    FamilyInstance,
    FamilyType,
    Parameter,
    SharedParameter,
    Transform,
    VALID_PARAMETER_KINDS,
    VALID_SHARED_SCOPES,
    identity_transform,
)

__all__ = [
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


SCHEMA: str = "kerf.bim.family"
SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Parameter / SharedParameter
# ---------------------------------------------------------------------------


def parameter_to_dict(p: Parameter) -> dict[str, Any]:
    """Serialize a :class:`Parameter` to a plain dict."""
    out: dict[str, Any] = {
        "name": p.name,
        "kind": p.kind,
        "default": p.default,
    }
    if p.formula is not None:
        out["formula"] = p.formula
    if p.description:
        out["description"] = p.description
    return out


def parameter_from_dict(d: dict[str, Any]) -> Parameter:
    """Deserialize a :class:`Parameter` from a plain dict."""
    if not isinstance(d, dict):
        raise FamilyError("parameter dict must be a mapping")
    name = d.get("name")
    kind = d.get("kind", "float")
    if kind not in VALID_PARAMETER_KINDS:
        raise FamilyError(
            f"parameter '{name}': invalid kind '{kind}' "
            f"(allowed: {sorted(VALID_PARAMETER_KINDS)})"
        )
    return Parameter(
        name=name,
        kind=kind,
        default=d.get("default"),
        formula=d.get("formula"),
        description=d.get("description", ""),
    )


def shared_parameter_to_dict(sp: SharedParameter) -> dict[str, Any]:
    """Serialize a :class:`SharedParameter` to a plain dict."""
    out: dict[str, Any] = {
        "name": sp.name,
        "kind": sp.kind,
        "scope": sp.scope,
        "default": sp.default,
    }
    if sp.description:
        out["description"] = sp.description
    return out


def shared_parameter_from_dict(d: dict[str, Any]) -> SharedParameter:
    """Deserialize a :class:`SharedParameter` from a plain dict."""
    if not isinstance(d, dict):
        raise FamilyError("shared-parameter dict must be a mapping")
    scope = d.get("scope", "project")
    if scope not in VALID_SHARED_SCOPES:
        raise FamilyError(
            f"shared parameter '{d.get('name')}': invalid scope '{scope}' "
            f"(allowed: {sorted(VALID_SHARED_SCOPES)})"
        )
    return SharedParameter(
        name=d.get("name"),
        kind=d.get("kind", "float"),
        scope=scope,
        default=d.get("default", 0.0),
        description=d.get("description", ""),
    )


# ---------------------------------------------------------------------------
# Family
# ---------------------------------------------------------------------------


def family_to_dict(family: FamilyDefinition) -> dict[str, Any]:
    """Serialize a :class:`FamilyDefinition` to a plain dict.

    The dict is JSON-safe (no datetime / set / tuple at top level).
    """
    return {
        "schema": SCHEMA,
        "version": SCHEMA_VERSION,
        "id": family.id,
        "name": family.name,
        "category": family.category,
        "description": family.description,
        "type_parameters": [
            parameter_to_dict(p) for p in family.type_parameters.values()
        ],
        "instance_parameters": [
            parameter_to_dict(p) for p in family.instance_parameters.values()
        ],
        "shared_parameters": [
            shared_parameter_to_dict(sp)
            for sp in family.shared_parameters.values()
        ],
    }


def family_from_dict(d: dict[str, Any]) -> FamilyDefinition:
    """Deserialize a :class:`FamilyDefinition` from a plain dict.

    Accepts (and ignores) any unknown top-level keys for forward
    compatibility. Raises :class:`FamilyError` on missing required
    fields or invalid sub-records.
    """
    if not isinstance(d, dict):
        raise FamilyError("family dict must be a mapping")
    schema = d.get("schema", SCHEMA)
    if schema != SCHEMA:
        raise FamilyError(
            f"family dict has wrong schema marker: {schema!r} "
            f"(expected {SCHEMA!r})"
        )
    version = d.get("version", SCHEMA_VERSION)
    if not isinstance(version, int) or version != SCHEMA_VERSION:
        raise FamilyError(
            f"family dict has unsupported version: {version} "
            f"(expected {SCHEMA_VERSION})"
        )
    name = d.get("name")
    category = d.get("category")
    if not isinstance(name, str) or not name:
        raise FamilyError("family dict missing 'name'")
    if not isinstance(category, str) or not category:
        raise FamilyError("family dict missing 'category'")

    type_params = [parameter_from_dict(p) for p in d.get("type_parameters", [])]
    inst_params = [parameter_from_dict(p) for p in d.get("instance_parameters", [])]
    shared = [
        shared_parameter_from_dict(sp) for sp in d.get("shared_parameters", [])
    ]

    kwargs: dict[str, Any] = {
        "name": name,
        "category": category,
        "type_parameters": {p.name: p for p in type_params},
        "instance_parameters": {p.name: p for p in inst_params},
        "shared_parameters": {sp.name: sp for sp in shared},
        "description": d.get("description", ""),
    }
    if "id" in d:
        kwargs["id"] = d["id"]
    return FamilyDefinition(**kwargs)


# ---------------------------------------------------------------------------
# FamilyType / FamilyInstance
# ---------------------------------------------------------------------------


def type_to_dict(t: FamilyType) -> dict[str, Any]:
    """Serialize a :class:`FamilyType`.

    Note: the type's owning ``FamilyDefinition`` is *not* embedded —
    callers store types alongside their family. The link is encoded as
    ``family_id``.
    """
    return {
        "schema": SCHEMA + ".type",
        "version": SCHEMA_VERSION,
        "family_id": t.definition.id,
        "family_name": t.definition.name,
        "name": t.name,
        "description": t.description,
        "type_param_values": dict(t.type_param_values),
    }


def type_from_dict(d: dict[str, Any], definition: FamilyDefinition) -> FamilyType:
    """Deserialize a :class:`FamilyType` using *definition* as the owner.

    The dict's ``family_id`` / ``family_name`` are validated against
    *definition* but are not required to be identical to it — the
    caller is the source of truth for the relationship.
    """
    if not isinstance(d, dict):
        raise FamilyError("type dict must be a mapping")
    fid = d.get("family_id")
    if fid is not None and fid != definition.id:
        raise FamilyError(
            f"type dict family_id '{fid}' does not match definition id "
            f"'{definition.id}'"
        )
    return FamilyType(
        definition=definition,
        name=d.get("name"),
        type_param_values=dict(d.get("type_param_values", {})),
        description=d.get("description", ""),
    )


def instance_to_dict(inst: FamilyInstance) -> dict[str, Any]:
    """Serialize a :class:`FamilyInstance`."""
    return {
        "schema": SCHEMA + ".instance",
        "version": SCHEMA_VERSION,
        "id": inst.id,
        "family_id": inst.type.definition.id,
        "family_name": inst.type.definition.name,
        "type_name": inst.type.name,
        "instance_param_values": dict(inst.instance_param_values),
        "transform": inst.transform.as_list(),
    }


def instance_from_dict(d: dict[str, Any], ftype: FamilyType) -> FamilyInstance:
    """Deserialize a :class:`FamilyInstance` using *ftype* as its type.

    *ftype* must be the live :class:`FamilyType` matching ``type_name``;
    cross-checking is the caller's responsibility (usually via a
    family-library lookup).
    """
    if not isinstance(d, dict):
        raise FamilyError("instance dict must be a mapping")
    if d.get("type_name") is not None and d["type_name"] != ftype.name:
        raise FamilyError(
            f"instance dict type_name '{d['type_name']}' does not match "
            f"provided type '{ftype.name}'"
        )
    transform_data = d.get("transform")
    transform: Transform
    if transform_data is None:
        transform = identity_transform()
    else:
        transform = Transform.from_list(transform_data)
    kwargs: dict[str, Any] = {
        "type": ftype,
        "instance_param_values": dict(d.get("instance_param_values", {})),
        "transform": transform,
    }
    if "id" in d:
        kwargs["id"] = d["id"]
    return FamilyInstance(**kwargs)
