"""
kerf_rules.engine — Rule evaluation engine.

The engine evaluates a RulePack against a ``Project`` model (a dict containing
elements — structural members, fasteners, reinforcement, etc.) and returns a
structured list of ``Violation`` objects.

Project model shape
-------------------
A project is a plain dict:

  {
    "name": "My structure",
    "elements": [
      {
        "id": "col-1",
        "element_type": "steel_column",
        "material": "A992",
        "effective_length_mm": 6000,
        "radius_of_gyration_mm": 45.0,
        ...
      },
      ...
    ],
    "metadata": { ... }
  }

Violation shape
---------------
Each violation is a ``Violation`` dataclass exposing:

  {
    "rule_id":       str,    # e.g. "AISC-360-E3-1"
    "standard":      str,    # e.g. "AISC 360-22"
    "clause":        str,    # e.g. "E3.1"
    "element_id":    str,    # which element triggered the rule
    "severity":      str,    # "error" | "warning"
    "message":       str,    # human-readable, cites the value
    "value":         float | None,  # the computed expression value
    "description":   str,    # rule description
  }

Public API
----------
evaluate(project, rule_pack)  -> list[Violation]
RulesEngine.run(project)      -> list[Violation]   (OO wrapper)
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass, asdict
from typing import Any

from kerf_rules.dsl import Rule, RulePack, WhenClause, ThenClause


# ---------------------------------------------------------------------------
# Violation model
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A single rule-check failure."""
    rule_id: str
    standard: str
    clause: str
    element_id: str
    severity: str
    message: str
    value: float | None
    description: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:
        return (
            f"Violation({self.rule_id!r}, elem={self.element_id!r}, "
            f"severity={self.severity!r}, msg={self.message!r})"
        )


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------

def _element_matches_when(element: dict[str, Any], when: WhenClause) -> bool:
    """Return True if the element satisfies the WhenClause predicates."""
    # element_type filter
    if when.element_type:
        elem_type = element.get("element_type", "")
        if elem_type not in when.element_type:
            return False

    # has_properties filter — all listed props must be present
    for prop in when.has_properties:
        if prop not in element:
            return False

    # predicate_expr — evaluated with element as namespace
    if when.predicate_expr:
        try:
            result = eval(when.predicate_expr, {"__builtins__": {}}, dict(element))  # noqa: S307
        except Exception:
            return False
        if not result:
            return False

    return True


def _eval_expr(expr: str, element: dict[str, Any]) -> float:
    """Evaluate an arithmetic expression with element properties in scope."""
    import math as _math
    namespace = {"math": _math, "__builtins__": {}}
    namespace.update(element)
    try:
        result = eval(expr, namespace)  # noqa: S307
        return float(result)
    except Exception as exc:
        raise ValueError(f"Error evaluating rule expression {expr!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Assertion evaluation
# ---------------------------------------------------------------------------

_CHECK_OPS = {
    "le": operator.le,
    "lt": operator.lt,
    "ge": operator.ge,
    "gt": operator.gt,
    "eq": operator.eq,
}


def _check_assertion(then: ThenClause, element: dict[str, Any]) -> tuple[bool, float | None]:
    """
    Evaluate the ThenClause assertion against an element.

    Returns (passes: bool, value: float | None).
    ``passes=True`` means the rule is satisfied (no violation).
    """
    check = then.check.lower()

    # ---- simple property existence / truth check -------------------------
    if check == "exists":
        if then.expr is None:
            return True, None
        val = element.get(then.expr)
        return (val is not None), None

    # ---- in / not_in checks — raw property lookup, no float conversion ----
    if check == "in":
        raw = element.get(then.expr or "", None) if then.expr else None
        passes = raw in then.values
        return passes, None

    if check == "not_in":
        raw = element.get(then.expr or "", None) if then.expr else None
        passes = raw not in then.values
        return passes, None

    # ---- numeric / expression checks — evaluate expr to float first ------
    value: float | None = None
    if then.expr is not None:
        value = _eval_expr(then.expr, element)

    if check in _CHECK_OPS:
        if value is None:
            return True, None
        if then.limit is None:
            return True, value
        passes = _CHECK_OPS[check](value, then.limit)
        return passes, value

    if check == "between":
        if value is None:
            return True, None
        low = then.low if then.low is not None else float("-inf")
        high = then.high if then.high is not None else float("inf")
        return (low <= value <= high), value

    if check == "expr":
        # then.expr must evaluate to a truthy value
        if then.expr is None:
            return True, None
        import math as _math
        namespace = {"math": _math, "__builtins__": {}}
        namespace.update(element)
        try:
            result = eval(then.expr, namespace)  # noqa: S307
            return bool(result), float(result) if isinstance(result, (int, float)) else None
        except Exception:
            return False, None

    # Unknown check type — pass through (don't generate spurious failures)
    return True, None


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def _format_message(template: str, rule_id: str, value: float | None, element: dict[str, Any]) -> str:
    """Format a violation message template."""
    ctx: dict[str, Any] = {"rule_id": rule_id, "value": value}
    ctx.update(element)
    try:
        return template.format(**ctx)
    except (KeyError, ValueError):
        return template


def _evaluate_rule(rule: Rule, element: dict[str, Any]) -> Violation | None:
    """
    Evaluate a single rule against a single element.

    Returns a Violation if the rule applies and the assertion fails,
    or None if the rule does not apply or the assertion passes.
    """
    if not _element_matches_when(element, rule.when):
        return None

    passes, value = _check_assertion(rule.then, element)
    if passes:
        return None

    message = _format_message(rule.then.message, rule.id, value, element)
    return Violation(
        rule_id=rule.id,
        standard=rule.standard,
        clause=rule.clause,
        element_id=str(element.get("id", element.get("element_id", "unknown"))),
        severity=rule.then.severity,
        message=message,
        value=value,
        description=rule.description,
    )


def evaluate(project: dict[str, Any], rule_pack: RulePack) -> list[Violation]:
    """
    Evaluate a RulePack against a project model.

    Args:
        project:   dict with an ``elements`` list.
        rule_pack: RulePack loaded via dsl.load_rule_pack / load_builtin_pack.

    Returns:
        List of Violation objects (empty list means fully compliant).
    """
    elements: list[dict[str, Any]] = project.get("elements", [])
    violations: list[Violation] = []

    for rule in rule_pack.rules:
        for element in elements:
            v = _evaluate_rule(rule, element)
            if v is not None:
                violations.append(v)

    return violations


class RulesEngine:
    """Object-oriented wrapper around evaluate()."""

    def __init__(self, rule_pack: RulePack) -> None:
        self.rule_pack = rule_pack

    def run(self, project: dict[str, Any]) -> list[Violation]:
        return evaluate(project, self.rule_pack)

    @property
    def rule_count(self) -> int:
        return len(self.rule_pack)
