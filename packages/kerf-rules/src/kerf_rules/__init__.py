"""kerf-rules — Knowledge-based engineering code-compliance rule engine for Kerf.

Provides a declarative DSL for engineering standards (AISC, Eurocode 2, ASME B18,
ACI, ISO, etc.) and an evaluation engine that produces structured violation reports
citing rule IDs and standard clauses.
"""

from kerf_rules.dsl import Rule, RulePack, load_rule_file, load_rule_pack
from kerf_rules.engine import RulesEngine, Violation, evaluate

__all__ = [
    "Rule",
    "RulePack",
    "load_rule_file",
    "load_rule_pack",
    "RulesEngine",
    "Violation",
    "evaluate",
]
