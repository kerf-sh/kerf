"""feature.py — abstract Feature model for the parametric history DAG.

A ``Feature`` is the unit of the DAG. It carries:

  * an ``id`` (UUID4 string) — pinned at creation, never mutates
  * a ``kind`` — short label naming the evaluator to dispatch
  * ``inputs`` — named refs to upstream features and/or selectors (face/edge
    pointers that survive regeneration of the producing feature)
  * ``params`` — named scalar parameters (numbers, tuples, strings) frozen at
    the time the user set them; these are the EDIT surface of the feature

After evaluation, the feature gains:

  * ``outputs`` — last computed Body (and optionally other named outputs);
    cached and reused until invalidated
  * ``naming_table`` — the live :class:`NamingTable` from the producing
    evaluator, used by downstream selectors

Features are deliberately *not* dataclasses-with-evaluators-attached. The
evaluator dispatch lives on the DAG (see :mod:`dag`) so that the same
``Feature`` can be re-evaluated under different rules (e.g. fast/preview
mode) without duplicating state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MissingReferenceError(LookupError):
    """Raised when a :class:`PersistentSelector` cannot be resolved against
    the current naming table of its target feature.

    The exception's message describes:
      * which selector failed (its short persistent-id form)
      * the available roles on the target feature at the time of resolution

    Downstream callers catch this and either re-attempt with a healed
    reference or surface a user-visible "feature broken" warning.
    """

    def __init__(self, selector: "PersistentSelector", available: Dict[str, List[str]]):
        self.selector = selector
        self.available = available
        avail_summary = ", ".join(
            f"{k}: [{', '.join(v)}]" for k, v in available.items() if v
        )
        if not avail_summary:
            avail_summary = "<none>"
        super().__init__(
            f"persistent reference {selector.short} not resolvable on "
            f"feature {selector.feature_id[:8]}; available roles: {avail_summary}"
        )


# ---------------------------------------------------------------------------
# PersistentSelector
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersistentSelector:
    """A reference to a face / edge / vertex of an upstream feature's output,
    resolvable across regenerations.

    Fields
    ------
    feature_id : str
        UUID4 of the producing feature.
    entity_kind : str
        One of ``"face"``, ``"edge"``, ``"vertex"``.
    role : str
        The structural role tag assigned by the producing evaluator (e.g.
        ``+X``, ``rim_top``, ``+Y/+Z``). Pure structure, not parameter values.
    """

    feature_id: str
    entity_kind: str  # "face" | "edge" | "vertex"
    role: str

    @property
    def short(self) -> str:
        return f"{self.feature_id[:8]}::{self.entity_kind}:{self.role}"

    def __str__(self) -> str:
        return f"{self.feature_id}::{self.entity_kind}:{self.role}"


# ---------------------------------------------------------------------------
# FeatureRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureRef:
    """A reference to the named output of an upstream feature.

    For solid-body operations the output name is ``"body"`` by convention; the
    evaluators are free to expose multiple named outputs.
    """

    feature_id: str
    output_name: str = "body"

    def __str__(self) -> str:
        return f"{self.feature_id}#{self.output_name}"


# Union type for the values stored in Feature.inputs.
InputValue = Union[FeatureRef, PersistentSelector, int, float, bool, str, tuple, list]


# ---------------------------------------------------------------------------
# Feature
# ---------------------------------------------------------------------------


def _new_feature_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Feature:
    """A node in the parametric history DAG.

    Attributes
    ----------
    id : str
        UUID4 hex. Stable across the lifetime of the feature, including across
        re-evaluations, edits, and serialise/deserialise round-trips.
    kind : str
        Short kind label dispatched by the evaluator registry (e.g.
        ``"box"``, ``"cylinder"``, ``"boolean"``, ``"chamfer_edge"``).
    inputs : dict[str, InputValue]
        Named refs to upstream features, persistent selectors, or literal
        scalars. The evaluator decides how each named input is consumed.
    params : dict[str, scalar]
        Named scalar parameters frozen at creation. These are the EDIT surface
        — ``set_param`` on the DAG mutates these and invalidates the cache.
    outputs : dict[str, Any]
        Last-evaluated outputs, populated by the DAG. ``outputs["body"]`` is
        the canonical Body output by convention.
    naming_table : Any
        Last-evaluated :class:`NamingTable`. Stored as ``Any`` to keep this
        file free of a circular import to ``persistent_naming``.
    """

    kind: str
    inputs: Dict[str, InputValue] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_new_feature_id)
    outputs: Dict[str, Any] = field(default_factory=dict)
    naming_table: Optional[Any] = field(default=None, repr=False)

    # ── serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable snapshot of the feature (without
        outputs/naming_table — those are derived state)."""
        ser_inputs: Dict[str, Any] = {}
        for k, v in self.inputs.items():
            if isinstance(v, FeatureRef):
                ser_inputs[k] = {
                    "__type__": "FeatureRef",
                    "feature_id": v.feature_id,
                    "output_name": v.output_name,
                }
            elif isinstance(v, PersistentSelector):
                ser_inputs[k] = {
                    "__type__": "PersistentSelector",
                    "feature_id": v.feature_id,
                    "entity_kind": v.entity_kind,
                    "role": v.role,
                }
            else:
                ser_inputs[k] = v
        return {
            "id": self.id,
            "kind": self.kind,
            "inputs": ser_inputs,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Feature":
        ins: Dict[str, InputValue] = {}
        for k, v in (d.get("inputs") or {}).items():
            if isinstance(v, dict) and v.get("__type__") == "FeatureRef":
                ins[k] = FeatureRef(
                    feature_id=v["feature_id"],
                    output_name=v.get("output_name", "body"),
                )
            elif isinstance(v, dict) and v.get("__type__") == "PersistentSelector":
                ins[k] = PersistentSelector(
                    feature_id=v["feature_id"],
                    entity_kind=v["entity_kind"],
                    role=v["role"],
                )
            else:
                ins[k] = v
        return cls(
            id=d["id"],
            kind=d["kind"],
            inputs=ins,
            params=dict(d.get("params") or {}),
        )


__all__ = [
    "Feature",
    "FeatureRef",
    "PersistentSelector",
    "MissingReferenceError",
    "InputValue",
]
