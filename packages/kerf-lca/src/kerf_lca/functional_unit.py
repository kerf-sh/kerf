"""
Functional Unit (FU) declaration and normalisation — ISO 14044 §4.2.3.2.

A functional unit quantifies the performance of a product system and is
used as the reference to which all inputs and outputs are related.

Example:
    fu = FunctionalUnit(
        name="structural bracket",
        quantity=1.0,
        unit="kg",
        reference_flow=2.5,   # actual mass of the bracket
    )
    normalised = fu.normalise({"gwp100": 18.32})
    # → {"gwp100": 7.328}  (per-FU, i.e. per-kg result)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FunctionalUnit:
    """
    Declare the functional unit for an LCA study (ISO 14044 §4.2.3.2).

    Attributes:
        name: Description of the function (e.g. 'carry 5 kN load for 20 years').
        quantity: Amount expressed in the declared unit (e.g. 1.0).
        unit: Unit of measurement (e.g. 'kg', 'piece', 'm²', 'kWh').
        reference_flow: Physical flow that delivers the function
            (e.g. actual mass of the product that fulfils the FU).
            Used as denominator for per-FU normalisation.
        notes: Optional free-text notes (system boundary, cut-off criteria, etc.).
    """

    name: str
    quantity: float
    unit: str
    reference_flow: float
    notes: str = ""

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError(f"FunctionalUnit.quantity must be > 0, got {self.quantity}")
        if self.reference_flow <= 0:
            raise ValueError(
                f"FunctionalUnit.reference_flow must be > 0, got {self.reference_flow}"
            )

    @property
    def scale_factor(self) -> float:
        """
        Scale factor to convert reference-flow-based results to per-FU results.

        per_fu_result = absolute_result * scale_factor
        """
        return self.quantity / self.reference_flow

    def normalise(self, impact_dict: dict[str, float]) -> dict[str, float]:
        """
        Normalise absolute impact values to per-functional-unit values.

        Args:
            impact_dict: {impact_category: absolute_value, ...}
                where values are calculated for *reference_flow* units of product.

        Returns:
            Same structure scaled to *quantity* functional units.
        """
        sf = self.scale_factor
        return {cat: v * sf for cat, v in impact_dict.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "reference_flow": self.reference_flow,
            "scale_factor": self.scale_factor,
            **({"notes": self.notes} if self.notes else {}),
        }


def normalise_results(
    results: dict[str, float],
    fu: FunctionalUnit,
) -> dict[str, float]:
    """
    Convenience wrapper: normalise an impact results dict to the given FU.

    Args:
        results: {category: value} computed for the reference flow.
        fu: FunctionalUnit instance.

    Returns:
        {category: per_fu_value}
    """
    return fu.normalise(results)


def compare_alternatives(
    alternatives: list[dict[str, Any]],
    impact_category: str = "gwp100",
) -> list[dict[str, Any]]:
    """
    Rank a list of product alternatives by a single impact category.

    Each alternative dict should have:
        name           (str)
        results        (dict: {impact_category: value})
        functional_unit (FunctionalUnit, optional)

    Returns list sorted ascending by per-FU impact.
    """
    ranked = []
    for alt in alternatives:
        name = alt.get("name", "unnamed")
        results = alt.get("results", {})
        fu: FunctionalUnit | None = alt.get("functional_unit")
        per_fu = fu.normalise(results) if fu else dict(results)
        ranked.append({
            "name": name,
            "impact_value": per_fu.get(impact_category, 0.0),
            "impact_category": impact_category,
            "per_fu_results": per_fu,
        })

    ranked.sort(key=lambda x: x["impact_value"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    return ranked
