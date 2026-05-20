"""
kerf_rules.tools.validate_against_rules — LLM tool surface.

Exposes ``validate_against_rules(project, rule_pack)`` as a plain Python
function that can be registered as an LLM tool (JSON-RPC, FastAPI endpoint,
or Anthropic tool-use schema).

Function signature
------------------
validate_against_rules(project, rule_pack) -> dict

Args:
    project   : dict — the project model containing an ``elements`` list,
                       where each element has an ``element_type`` and
                       engineering property fields.
    rule_pack : str | dict — either a built-in pack name ("aisc", "eurocode2",
                             "asme_b18") or a raw RulePack dict for custom packs.

Returns:
    {
        "ok":             bool,    # True iff zero violations
        "violation_count": int,
        "violations": [
            {
                "rule_id":    str,
                "standard":   str,
                "clause":     str,
                "element_id": str,
                "severity":   str,   # "error" | "warning"
                "message":    str,
                "value":      float | None,
                "description": str,
            },
            ...
        ],
        "rule_pack_name": str,
        "rule_count":     int,
        "elements_checked": int,
    }

LLM tool schema (Anthropic tool_use format)
-------------------------------------------
{
  "name": "validate_against_rules",
  "description": "Validate a Kerf project model against a named code-compliance rule pack (AISC/Eurocode2/ASME_B18). Returns a structured list of violations citing rule IDs and standard clauses.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project": {
        "type": "object",
        "description": "Project model dict with 'name' and 'elements' list",
        "required": ["elements"]
      },
      "rule_pack": {
        "type": "string",
        "description": "Built-in rule pack name: 'aisc', 'eurocode2', or 'asme_b18'",
        "enum": ["aisc", "eurocode2", "asme_b18"]
      }
    },
    "required": ["project", "rule_pack"]
  }
}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kerf_rules.dsl import RulePack, load_rule_pack
from kerf_rules.engine import evaluate, Violation

# ── Built-in pack registry ──────────────────────────────────────────────────

_BUILTIN_PACKS: dict[str, RulePack | None] = {}


def _get_builtin_pack(name: str) -> RulePack:
    """Load (and cache) a built-in rule pack by short name."""
    if name not in _BUILTIN_PACKS:
        # Resolve the rules/ directory relative to this file's package root
        _pkg_root = Path(__file__).parent.parent.parent.parent.parent
        rules_dir = _pkg_root / "rules" / name
        if not rules_dir.exists():
            # Fallback for installed package layout
            rules_dir = Path(__file__).parent.parent.parent.parent / "rules" / name
        if not rules_dir.exists():
            raise FileNotFoundError(
                f"Built-in rule pack {name!r} not found. "
                f"Looked at: {rules_dir}"
            )
        _BUILTIN_PACKS[name] = load_rule_pack(rules_dir, name=name)
    return _BUILTIN_PACKS[name]  # type: ignore[return-value]


def _resolve_pack(rule_pack: str | dict | RulePack) -> RulePack:
    """Resolve a rule pack from a name string, raw dict, or RulePack object."""
    if isinstance(rule_pack, RulePack):
        return rule_pack

    if isinstance(rule_pack, str):
        return _get_builtin_pack(rule_pack)

    if isinstance(rule_pack, dict):
        # Raw dict — re-hydrate into a RulePack
        from kerf_rules.dsl import Rule
        rules = [Rule.from_dict(r) for r in rule_pack.get("rules", [])]
        return RulePack(name=rule_pack.get("name", "custom"), rules=rules)

    raise TypeError(f"rule_pack must be str, dict, or RulePack; got {type(rule_pack)}")


# ── Main tool function ──────────────────────────────────────────────────────

def validate_against_rules(
    project: dict[str, Any],
    rule_pack: str | dict[str, Any] | RulePack,
) -> dict[str, Any]:
    """
    Validate a Kerf project model against a code-compliance rule pack.

    This is the primary LLM tool entry point for KBE rule checking.

    Args:
        project:   Project model dict with an ``elements`` list.
        rule_pack: Built-in pack name ("aisc", "eurocode2", "asme_b18"),
                   a raw RulePack dict, or a RulePack object.

    Returns:
        Structured result dict — see module docstring.
    """
    pack = _resolve_pack(rule_pack)
    violations: list[Violation] = evaluate(project, pack)

    elements_checked = len(project.get("elements", []))

    return {
        "ok": len(violations) == 0,
        "violation_count": len(violations),
        "violations": [v.as_dict() for v in violations],
        "rule_pack_name": pack.name,
        "rule_count": len(pack),
        "elements_checked": elements_checked,
    }


# ── Anthropic tool schema ───────────────────────────────────────────────────

TOOL_SCHEMA = {
    "name": "validate_against_rules",
    "description": (
        "Validate a Kerf project model against a named code-compliance rule pack. "
        "Checks structural / mechanical elements against AISC 360, Eurocode 2, "
        "or ASME B18 rules and returns a structured list of violations, each "
        "citing the rule ID and standard clause."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project": {
                "type": "object",
                "description": (
                    "Project model with 'name' (str) and 'elements' (list of "
                    "objects). Each element must have 'id', 'element_type', and "
                    "domain-specific property fields."
                ),
            },
            "rule_pack": {
                "type": "string",
                "description": "Built-in rule pack name.",
                "enum": ["aisc", "eurocode2", "asme_b18"],
            },
        },
        "required": ["project", "rule_pack"],
    },
}
