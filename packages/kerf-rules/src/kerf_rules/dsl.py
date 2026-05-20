"""
kerf_rules.dsl — Declarative rule loader for KBE code-compliance rules.

Rule file format (YAML)
-----------------------
Each .yaml file contains a list of rules under the top-level ``rules`` key:

  rules:
    - id: AISC-360-E3-1
      standard: AISC 360-22
      clause: E3.1
      description: "Steel column slenderness limit Kl/r ≤ 200"
      domain: structural
      when:
        element_type: steel_column
        has_properties:
          - effective_length_mm
          - radius_of_gyration_mm
      then:
        check: le
        expr: "effective_length_mm / radius_of_gyration_mm"
        limit: 200
        severity: error
        message: "Column Kl/r = {value:.1f} exceeds AISC 360-22 §E3.1 limit of 200"

DSL predicates (``when`` block)
--------------------------------
element_type        str | list[str] — match elements by type tag
has_properties      list[str]       — element must have all listed properties
predicate_expr      str             — arbitrary Python expression evaluated
                                      with element properties in scope (advanced)

Assertion (``then`` block)
--------------------------
check   : "le" | "ge" | "eq" | "between" | "in" | "not_in" | "expr"
expr    : Python expression string; result must satisfy the check
limit   : scalar limit for le/ge/eq
low/high: bounds for between check
values  : list for in/not_in check
severity: "error" | "warning"  (default: "error")
message : f-string template; {value} is the computed expression result
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class WhenClause:
    """Predicate — conditions that must hold for the rule to apply to an element."""
    element_type: list[str] = field(default_factory=list)
    has_properties: list[str] = field(default_factory=list)
    predicate_expr: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WhenClause":
        et = d.get("element_type", [])
        if isinstance(et, str):
            et = [et]
        return cls(
            element_type=et,
            has_properties=d.get("has_properties", []),
            predicate_expr=d.get("predicate_expr"),
        )


@dataclass
class ThenClause:
    """Assertion — what must hold for the rule to pass."""
    check: str                     # le | ge | eq | between | in | not_in | expr
    expr: str | None = None        # Python expression evaluated against element props
    limit: float | None = None     # for le/ge/eq
    low: float | None = None       # for between
    high: float | None = None      # for between
    values: list[Any] = field(default_factory=list)  # for in/not_in
    severity: str = "error"
    message: str = "Rule {rule_id} violated (value={value})"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ThenClause":
        return cls(
            check=d.get("check", "expr"),
            expr=d.get("expr"),
            limit=d.get("limit"),
            low=d.get("low"),
            high=d.get("high"),
            values=d.get("values", []),
            severity=d.get("severity", "error"),
            message=d.get("message", "Rule {rule_id} violated (value={value})"),
        )


@dataclass
class Rule:
    """A single KBE compliance rule."""
    id: str
    standard: str
    clause: str
    description: str
    domain: str
    when: WhenClause
    then: ThenClause
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        return cls(
            id=d["id"],
            standard=d.get("standard", ""),
            clause=d.get("clause", ""),
            description=d.get("description", ""),
            domain=d.get("domain", "general"),
            when=WhenClause.from_dict(d.get("when", {})),
            then=ThenClause.from_dict(d.get("then", {})),
            tags=d.get("tags", []),
        )


@dataclass
class RulePack:
    """A named collection of rules loaded from one or more files."""
    name: str
    rules: list[Rule] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rules)

    def filter_by_domain(self, domain: str) -> "RulePack":
        return RulePack(
            name=f"{self.name}:{domain}",
            rules=[r for r in self.rules if r.domain == domain],
        )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_rule_file(path: str | Path) -> list[Rule]:
    """Load rules from a single YAML file."""
    if not _YAML_OK:
        raise ImportError("PyYAML is required: pip install pyyaml")
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not raw or "rules" not in raw:
        return []
    return [Rule.from_dict(r) for r in raw["rules"]]


def load_rule_pack(directory: str | Path, name: str | None = None) -> RulePack:
    """Recursively load all .yaml rule files from a directory tree."""
    directory = Path(directory)
    pack_name = name or directory.name
    rules: list[Rule] = []
    for yaml_path in sorted(directory.rglob("*.yaml")):
        rules.extend(load_rule_file(yaml_path))
    return RulePack(name=pack_name, rules=rules)


def load_builtin_pack(pack_name: str) -> RulePack:
    """Load one of the built-in rule packs by name (aisc, eurocode2, asme_b18)."""
    rules_dir = Path(__file__).parent.parent.parent.parent / "rules" / pack_name
    if not rules_dir.exists():
        # Fallback: look relative to installed package
        rules_dir = Path(__file__).parent.parent.parent / "rules" / pack_name
    if not rules_dir.exists():
        raise FileNotFoundError(f"Built-in rule pack not found: {pack_name!r} (looked at {rules_dir})")
    return load_rule_pack(rules_dir, name=pack_name)
