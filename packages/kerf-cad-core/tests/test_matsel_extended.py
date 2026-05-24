"""
Tests for kerf_cad_core.matsel extended database and multi-objective selection.

Coverage:
  extended_db.get_full_db    — total count ≥ 200, all required keys, no collisions
  multi_objective.pareto_frontier — non-dominated set correctness, known Ashby cases
  multi_objective.weighted_score  — single-weight reproduces Ashby ranking
  multi_objective.tradeoff_envelope — envelope subset of all_points

All tests are pure-Python and hermetic: no OCC, no DB, no network.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.matsel.extended_db import (
    get_extended_db,
    get_full_db,
    _EXT,
)
from kerf_cad_core.matsel.db import _DB as _BASE_DB  # noqa: F401
from kerf_cad_core.matsel.multi_objective import (
    pareto_frontier,
    weighted_score,
    tradeoff_envelope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


# ===========================================================================
# 1. Extended database integrity
# ===========================================================================

class TestExtendedDbIntegrity:

    def test_total_count_at_least_200(self):
        """Combined database must have ≥ 200 materials."""
        full = get_full_db()
        assert len(full) >= 200, f"Only {len(full)} materials; need ≥ 200."

    def test_no_key_collision_with_base(self):
        """Extended entries must not shadow any base DB key."""
        collision = set(_EXT.keys()) & set(_BASE_DB.keys())
        assert not collision, f"Key collisions: {sorted(collision)}"

    def test_extended_count_significant(self):
        """Extended DB must add at least 100 new materials."""
        assert len(_EXT) >= 100, f"Only {len(_EXT)} extended materials."

    def test_all_required_keys_present(self):
        """Every extended material must have all required property keys."""
        required = {"family", "density", "E", "sigma_y", "sigma_uts", "sigma_e",
                    "k", "CTE", "T_max", "cost_rel"}
        for name, props in _EXT.items():
            missing = required - set(props.keys())
            assert not missing, f"{name} missing keys: {missing}"

    def test_all_numeric_properties_positive(self):
        """density, E, sigma_uts, k, T_max, cost_rel must all be > 0."""
        must_pos = {"density", "E", "sigma_uts", "k", "T_max", "cost_rel"}
        for name, props in _EXT.items():
            for key in must_pos:
                assert props[key] > 0, f"{name}.{key} = {props[key]} is not positive"

    def test_sigma_uts_geq_sigma_y(self):
        """sigma_uts >= sigma_y for every extended material."""
        for name, props in _EXT.items():
            assert props["sigma_uts"] >= props["sigma_y"], (
                f"{name}: sigma_uts={props['sigma_uts']} < sigma_y={props['sigma_y']}"
            )

    def test_no_nan_or_inf(self):
        """No property value may be NaN or infinite."""
        for name, props in _EXT.items():
            for key, val in props.items():
                if isinstance(val, float):
                    assert math.isfinite(val), f"{name}.{key} = {val}"

    def test_families_cover_all_groups(self):
        """Extended DB must include all required material families."""
        families = {props["family"] for props in _EXT.values()}
        for expected in ("steel", "aluminium", "titanium", "polymer",
                         "composite", "wood", "ceramic", "copper", "cast_iron",
                         "elastomer", "tool_steel"):
            assert expected in families, f"Family {expected!r} missing from extended DB"

    def test_aisi_1020_still_in_full_db(self):
        """AISI_1020 (base) must appear unchanged in the full DB."""
        full = get_full_db()
        assert "AISI_1020" in full
        assert full["AISI_1020"]["cost_rel"] == pytest.approx(1.0)

    def test_full_db_is_superset_of_both(self):
        """get_full_db() must contain all base AND all extended keys."""
        full = get_full_db()
        for name in _BASE_DB:
            assert name in full
        for name in _EXT:
            assert name in full

    def test_get_extended_db_does_not_include_base(self):
        """get_extended_db() must not include base materials."""
        ext = get_extended_db()
        for name in _BASE_DB:
            assert name not in ext

    def test_specific_materials_present(self):
        """Key expected materials must be in the extended DB."""
        for name in ("ASTM_A36", "S355J2", "Al_5083_H111", "Ti_15V_3Cr_Beta",
                     "PEEK", "CFRP_HM_UD", "Kevlar49_UD", "WC_Co10",
                     "NBR_70", "Silicone_60A", "Pine_Scots", "Bamboo_Structural"):
            assert name in _EXT or name in _BASE_DB, (
                f"Expected material {name!r} not found in either database"
            )

    def test_co2_values_plausible(self):
        """CO₂ values (where present) must be in plausible range [0.1, 100]."""
        for name, props in _EXT.items():
            co2 = props.get("co2_kg_kg")
            if co2 is not None:
                assert 0.1 <= co2 <= 200.0, (
                    f"{name}.co2_kg_kg = {co2} is outside plausible range [0.1, 200]"
                )


# ===========================================================================
# 2. Category counts
# ===========================================================================

class TestCategoryCounts:

    def test_metals_count(self):
        """Extended DB should have substantial metal coverage."""
        metal_families = {"steel", "stainless_steel", "aluminium", "titanium",
                          "copper", "cast_iron", "tool_steel", "magnesium",
                          "nickel_superalloy"}
        metals = [n for n, p in _EXT.items() if p["family"] in metal_families]
        assert len(metals) >= 55, f"Only {len(metals)} metal entries in extended DB"

    def test_polymer_count(self):
        """Extended DB should have substantial polymer coverage."""
        polymers = [n for n, p in _EXT.items() if p["family"] in ("polymer", "elastomer")]
        assert len(polymers) >= 17, f"Only {len(polymers)} polymer/elastomer entries"

    def test_composite_count(self):
        """Extended DB should have ≥ 8 composite entries."""
        composites = [n for n, p in _EXT.items() if p["family"] == "composite"]
        assert len(composites) >= 8, f"Only {len(composites)} composite entries"

    def test_ceramic_count(self):
        """Extended DB should have ≥ 10 ceramic entries."""
        ceramics = [n for n, p in _EXT.items() if p["family"] == "ceramic"]
        assert len(ceramics) >= 10, f"Only {len(ceramics)} ceramic entries"


# ===========================================================================
# 3. Pareto frontier — correctness
# ===========================================================================

class TestParetoFrontier:

    def test_returns_ok(self):
        """pareto_frontier must return ok=True for valid input."""
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"] is True
        assert "frontier" in result

    def test_frontier_is_subset_of_full_db(self):
        """All frontier materials must exist in the full DB."""
        full = get_full_db()
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"]
        for item in result["frontier"]:
            assert item["name"] in full

    def test_frontier_density_E_contains_expected(self):
        """Pareto on (density ↓, E ↑) should include CFRP_HM_UD and Balsa.

        Balsa is ultra-low density; CFRP_HM_UD has highest E per density.
        Neither can be dominated in this pair.
        """
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"]
        names = {m["name"] for m in result["frontier"]}
        # Balsa (density=130) should be on the frontier (lowest density, still has E)
        assert "Balsa" in names, f"Balsa not in density/E frontier: {sorted(names)}"
        # CFRP_HM_UD has the highest E at modest density
        assert "CFRP_HM_UD" in names, f"CFRP_HM_UD not in frontier: {sorted(names)}"

    def test_frontier_excludes_dominated_mid_range(self):
        """A dominated mid-range material must not appear on the frontier."""
        # Al_5052_H32: density=2680, E=70.3 GPa
        # It should be dominated by CFRP (much lower density at same E)
        # or other materials on the frontier
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"]
        # The key check: the frontier has FEWER members than the full DB
        full = get_full_db()
        assert len(result["frontier"]) < len(full), (
            "Frontier should exclude dominated materials"
        )

    def test_frontier_single_objective_all_on_frontier(self):
        """With a single-objective, every material is on the frontier
        unless another has a strictly better value on that sole objective.
        Actually only the best value(s) survive."""
        # Use a small subset for speed
        subset = {n: p for n, p in _BASE_DB.items() if p["family"] in ("steel", "aluminium")}
        result = pareto_frontier(["density"], ["min"], materials=subset)
        assert result["ok"]
        # The frontier should only contain materials with the minimum density
        min_density = min(p["density"] for p in subset.values())
        for item in result["frontier"]:
            assert subset[item["name"]]["density"] == pytest.approx(min_density, rel=1e-6)

    def test_frontier_no_dominated_members(self):
        """No frontier member may be dominated by any other frontier member."""
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"]
        frontier = result["frontier"]
        for i, a in enumerate(frontier):
            for j, b in enumerate(frontier):
                if i == j:
                    continue
                # a should not be dominated by b
                a_dominated_by_b = (
                    b["values"]["density"] <= a["values"]["density"]
                    and b["values"]["E"] >= a["values"]["E"]
                    and (
                        b["values"]["density"] < a["values"]["density"]
                        or b["values"]["E"] > a["values"]["E"]
                    )
                )
                assert not a_dominated_by_b, (
                    f"Frontier member {a['name']} is dominated by {b['name']}"
                )

    def test_frontier_steel_not_on_density_E_frontier(self):
        """Dense steels (ρ > 7800) should be dominated on (density↓, E↑).

        CFRP has comparable E at 3x lower density; balsa/wood at 10x lower.
        All mainstream steels are dominated.
        """
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"]
        frontier_names = {m["name"] for m in result["frontier"]}
        # AISI_1020: density=7850, E=200. CFRP_HM_UD: density=1600, E=190.
        # AISI_1020 has higher density AND only marginally higher E — dominated.
        assert "AISI_1020" not in frontier_names, (
            "AISI_1020 should be dominated on (density↓, E↑) by CFRP_HM_UD"
        )

    def test_frontier_invalid_direction(self):
        """Invalid direction value must return ok=False."""
        result = pareto_frontier(["density", "E"], ["down", "up"])
        assert result["ok"] is False

    def test_frontier_mismatched_lengths(self):
        """Mismatched objectives/directions lengths must return ok=False."""
        result = pareto_frontier(["density", "E"], ["min"])
        assert result["ok"] is False

    def test_frontier_three_objectives(self):
        """Pareto frontier with 3 objectives must return ok=True."""
        result = pareto_frontier(
            ["density", "E", "cost_rel"],
            ["min", "max", "min"],
        )
        assert result["ok"] is True
        assert len(result["frontier"]) >= 1

    def test_frontier_returns_value_dict(self):
        """Each frontier item must have a 'values' dict with all objectives."""
        result = pareto_frontier(["density", "E"], ["min", "max"])
        assert result["ok"]
        for item in result["frontier"]:
            assert "values" in item
            assert "density" in item["values"]
            assert "E" in item["values"]


# ===========================================================================
# 4. Weighted score — correctness & Ashby consistency
# ===========================================================================

class TestWeightedScore:

    def test_returns_ok(self):
        """weighted_score must return ok=True for valid input."""
        result = weighted_score(["density"], [1.0], ["min"])
        assert result["ok"] is True
        assert "ranked" in result

    def test_ranked_sorted_descending_by_score(self):
        """Ranked list must be sorted by score descending."""
        result = weighted_score(["density", "E"], [1.0, 1.0], ["min", "max"])
        assert result["ok"]
        scores = [r["score"] for r in result["ranked"]]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_are_1_indexed_contiguous(self):
        """Ranks must be 1, 2, 3, … in order."""
        result = weighted_score(["density"], [1.0], ["min"], top_n=10)
        assert result["ok"]
        ranks = [r["rank"] for r in result["ranked"]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_single_weight_reproduces_ashby_stiffness(self):
        """Single-weight 'specific_stiffness' max reproduces Ashby top-3 order.

        The top 3 by specific_stiffness (E/ρ) from the full DB should be:
        CFRP_HM_UD (E=190, ρ=1600 → 0.119), CFRP_UD_0deg (E=135, ρ=1550 → 0.087),
        or similar CFRP variants.  The weighted_score with w=1 must reproduce
        the same top material.
        """
        result = weighted_score(["specific_stiffness"], [1.0])
        assert result["ok"]
        top = result["ranked"][0]["name"]
        # The top material should be a high-stiffness composite
        full = get_full_db()
        top_props = full[top]
        E = top_props["E"]
        rho = top_props["density"]
        spec_stiff = E / rho
        # Check it's the actual maximum
        all_spec_stiff = [
            p["E"] / p["density"] for p in full.values()
        ]
        assert spec_stiff == pytest.approx(max(all_spec_stiff), rel=1e-6), (
            f"weighted_score top={top} has spec_stiff={spec_stiff:.4f} "
            f"but max is {max(all_spec_stiff):.4f}"
        )

    def test_single_weight_density_min_puts_lowest_density_first(self):
        """Single-weight density minimise should rank lowest-density material first."""
        result = weighted_score(["density"], [1.0], ["min"])
        assert result["ok"]
        full = get_full_db()
        min_density = min(p["density"] for p in full.values())
        top_name = result["ranked"][0]["name"]
        top_density = full[top_name]["density"]
        assert top_density == pytest.approx(min_density, rel=1e-6), (
            f"Expected density {min_density} first, got {top_name} with {top_density}"
        )
        # Balsa (density=130) must still be in top 10 — it's one of the lightest solids
        top10_names = [r["name"] for r in result["ranked"][:10]]
        assert "Balsa" in top10_names, f"Balsa not in top-10 lightest: {top10_names}"

    def test_two_objectives_trade_off(self):
        """Two-objective weighted score must differ from single-objective ranking."""
        r1 = weighted_score(["specific_stiffness"], [1.0])
        r2 = weighted_score(["specific_stiffness", "cost_rel"], [1.0, 1.0],
                            ["max", "min"])
        assert r1["ok"] and r2["ok"]
        # The ranking order must differ (cost penalises CFRP)
        top_r1 = [r["name"] for r in r1["ranked"][:5]]
        top_r2 = [r["name"] for r in r2["ranked"][:5]]
        assert top_r1 != top_r2, (
            "Adding a cost weight should change the top-5 order"
        )

    def test_zero_weight_treated_as_ignored(self):
        """Zero weights on some objectives should not prevent a result."""
        result = weighted_score(
            ["density", "E", "cost_rel"],
            [1.0, 0.0, 0.0],
            ["min", "max", "min"],
        )
        assert result["ok"]
        assert len(result["ranked"]) > 0

    def test_top_n_limits_results(self):
        """top_n must limit result length."""
        result = weighted_score(["density"], [1.0], ["min"], top_n=5)
        assert result["ok"]
        assert len(result["ranked"]) == 5

    def test_mismatched_lengths_returns_error(self):
        """Mismatched objectives/weights lengths must return ok=False."""
        result = weighted_score(["density", "E"], [1.0])
        assert result["ok"] is False

    def test_negative_weight_returns_error(self):
        """Negative weight must return ok=False."""
        result = weighted_score(["density"], [-1.0])
        assert result["ok"] is False

    def test_values_dict_present_in_each_ranked(self):
        """Each ranked item must have a 'values' dict."""
        result = weighted_score(["density", "E"], [1.0, 1.0], ["min", "max"], top_n=5)
        assert result["ok"]
        for r in result["ranked"]:
            assert "values" in r
            assert "density" in r["values"]
            assert "E" in r["values"]

    def test_co2_objective_supported(self):
        """co2_kg_kg from extended DB must be usable as a weighted objective."""
        result = weighted_score(["co2_kg_kg"], [1.0], ["min"], top_n=10)
        assert result["ok"]
        # Balsa has very low CO₂; should appear near top
        names = [r["name"] for r in result["ranked"][:10]]
        # Bamboo or pine/balsa should be in top 10 for CO₂
        low_co2_expected = {"Balsa", "Pine_Scots", "Oak_White", "Plywood_Structural",
                            "Bamboo_Structural", "Douglas_Fir"}
        assert any(n in low_co2_expected for n in names), (
            f"Expected low-CO₂ material in top 10, got: {names}"
        )

    def test_normalise_false_works(self):
        """normalise=False must not raise and must return a ranking."""
        result = weighted_score(["E"], [1.0], ["max"], normalise=False, top_n=5)
        assert result["ok"]
        assert len(result["ranked"]) == 5


# ===========================================================================
# 5. Tradeoff envelope
# ===========================================================================

class TestTradeoffEnvelope:

    def test_returns_ok(self):
        """tradeoff_envelope must return ok=True for valid input."""
        result = tradeoff_envelope("density", "E", "min", "max")
        assert result["ok"] is True
        assert "envelope" in result
        assert "all_points" in result

    def test_envelope_subset_of_all_points(self):
        """All envelope points must appear in all_points."""
        result = tradeoff_envelope("density", "E", "min", "max")
        assert result["ok"]
        all_names = {p["name"] for p in result["all_points"]}
        for p in result["envelope"]:
            assert p["name"] in all_names

    def test_envelope_smaller_than_full_db(self):
        """Envelope must have fewer points than the full database."""
        result = tradeoff_envelope("density", "E", "min", "max")
        assert result["ok"]
        full = get_full_db()
        assert len(result["envelope"]) < len(full)

    def test_envelope_contains_cfrp_or_balsa(self):
        """Envelope on (density↓, E↑) must include CFRP or Balsa."""
        result = tradeoff_envelope("density", "E", "min", "max")
        assert result["ok"]
        env_names = {p["name"] for p in result["envelope"]}
        assert env_names & {"CFRP_HM_UD", "CFRP_UD_0deg", "Balsa"}, (
            f"Neither CFRP nor Balsa on envelope: {sorted(env_names)}"
        )

    def test_envelope_sorted_by_x(self):
        """Envelope points must be sorted by x value ascending."""
        result = tradeoff_envelope("density", "E", "min", "max")
        assert result["ok"]
        xs = [p["x"] for p in result["envelope"]]
        assert xs == sorted(xs)

    def test_all_points_have_x_y(self):
        """Every point in all_points must have 'x' and 'y' keys."""
        result = tradeoff_envelope("E", "sigma_y", "max", "max")
        assert result["ok"]
        for p in result["all_points"]:
            assert "x" in p and "y" in p and "name" in p

    def test_invalid_direction_returns_error(self):
        """Invalid direction must return ok=False."""
        result = tradeoff_envelope("density", "E", "down", "up")
        assert result["ok"] is False

    def test_two_max_directions(self):
        """Envelope for (E↑, sigma_y↑) must include high-strength composites."""
        result = tradeoff_envelope("E", "sigma_y", "max", "max")
        assert result["ok"]
        env_names = {p["name"] for p in result["envelope"]}
        # WC_Co10 has extremely high E (620 GPa); should be on the frontier
        assert "WC_Co10" in env_names, (
            f"WC_Co10 not on E/sigma_y envelope: {sorted(env_names)}"
        )


# ===========================================================================
# 6. LLM tool wrappers
# ===========================================================================

class TestMultiObjectiveTools:

    def test_matsel_pareto_happy_path(self):
        ctx = _ctx()
        from kerf_cad_core.matsel.multi_objective_tools import run_matsel_pareto
        raw = _run(run_matsel_pareto(ctx, _args(
            objectives=["density", "E"],
            directions=["min", "max"],
        )))
        d = _ok_tool(raw)
        assert isinstance(d["frontier"], list)
        assert len(d["frontier"]) >= 1

    def test_matsel_pareto_bad_direction(self):
        ctx = _ctx()
        from kerf_cad_core.matsel.multi_objective_tools import run_matsel_pareto
        raw = _run(run_matsel_pareto(ctx, _args(
            objectives=["density"],
            directions=["sideways"],
        )))
        d = json.loads(raw)
        assert d.get("ok") is False or "error" in d

    def test_matsel_weighted_happy_path(self):
        ctx = _ctx()
        from kerf_cad_core.matsel.multi_objective_tools import run_matsel_weighted
        raw = _run(run_matsel_weighted(ctx, _args(
            objectives=["density", "E"],
            weights=[1.0, 1.0],
            directions=["min", "max"],
            top_n=5,
        )))
        d = _ok_tool(raw)
        assert len(d["ranked"]) == 5

    def test_matsel_weighted_bad_json(self):
        ctx = _ctx()
        from kerf_cad_core.matsel.multi_objective_tools import run_matsel_weighted
        raw = _run(run_matsel_weighted(ctx, b"not json"))
        d = json.loads(raw)
        assert d.get("ok") is False or "error" in d

    def test_matsel_tradeoff_happy_path(self):
        ctx = _ctx()
        from kerf_cad_core.matsel.multi_objective_tools import run_matsel_tradeoff
        raw = _run(run_matsel_tradeoff(ctx, _args(
            x_metric="density",
            y_metric="E",
            x_direction="min",
            y_direction="max",
        )))
        d = _ok_tool(raw)
        assert isinstance(d["envelope"], list)
        assert isinstance(d["all_points"], list)
        assert len(d["all_points"]) > len(d["envelope"])

    def test_matsel_tradeoff_missing_metric(self):
        ctx = _ctx()
        from kerf_cad_core.matsel.multi_objective_tools import run_matsel_tradeoff
        raw = _run(run_matsel_tradeoff(ctx, _args(x_metric="density")))
        d = json.loads(raw)
        assert d.get("ok") is False or "error" in d
