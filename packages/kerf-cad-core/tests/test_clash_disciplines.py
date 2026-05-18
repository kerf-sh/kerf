"""
Tests for cross-discipline clash detection (T-51).

Validates that clash_detect correctly:
  - tags each clash record with discipline_a / discipline_b / discipline_pair
  - aggregates results into by_discipline_pair summary
  - exposes the ClashReport structured view and clashes_for_pair filter
  - handles a realistic multi-discipline assembly fixture with known
    interferences (structural vs MEP, structural vs architectural, MEP
    vs architectural, same-discipline pairs)

Fixture: 3-storey office building extract
  Structure:
    col-1   structural  300×300mm steel column from Z=0 to Z=4000
    beam-1  structural  200×300mm beam at Z=3800, spanning X=0..6000
  MEP:
    duct-1  mep         400×250mm HVAC duct at Z=3600, spans X=0..6000
              → overlaps column col-1 (Z 3600-4000 within col bbox)
    pipe-1  mep         100mm dia pipe routed at Z=3850, X=2500..3500
              → overlaps beam-1 (both at Z≈3800-3900)
  Architectural:
    wall-1  architectural  150mm thick wall at X=5800..5950, full height
              → overlaps beam-1 end (beam ends near X=6000, wall at 5800-5950)
    slab-1  architectural  200mm thick floor slab at Z=3750..3950
              → overlaps duct-1 (duct at 3600-3850 overlaps slab at 3750-3950)
              → overlaps pipe-1 (pipe at 3850 is within 3750-3950)

Known clashes (hard, all overlapping):
  col-1  vs duct-1  → structural vs mep
  beam-1 vs pipe-1  → structural vs mep
  beam-1 vs wall-1  → structural vs architectural
  duct-1 vs slab-1  → architectural vs mep
  pipe-1 vs slab-1  → architectural vs mep

Author: imranparuk
"""

from __future__ import annotations

import pytest

from kerf_cad_core.clash.detect import (
    ClashType,
    ClashRecord,
    ClashReport,
    ComponentShape,
    clash_detect,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _comp(
    iid: str,
    discipline: str,
    lo: tuple,
    hi: tuple,
    transform=None,
) -> ComponentShape:
    return ComponentShape(
        instance_id=iid,
        discipline=discipline,
        bbox_min=lo,
        bbox_max=hi,
        transform=transform,
    )


# ---------------------------------------------------------------------------
# Multi-discipline building fixture
# ---------------------------------------------------------------------------

def _building_fixture() -> list[ComponentShape]:
    """
    Return 6 components from a 3-storey office building extract.

    Coordinate system: X = East, Y = North, Z = Up.  Units: mm.

    Known hard clashes:
      col-1  vs duct-1  (structural vs mep)
      beam-1 vs pipe-1  (structural vs mep)
      beam-1 vs wall-1  (structural vs architectural)
      duct-1 vs slab-1  (architectural vs mep)
      pipe-1 vs slab-1  (architectural vs mep)
    """
    # Structural: 300×300 column, full storey height
    col_1 = _comp("col-1", "structural",
                  lo=(0, 0, 0), hi=(300, 300, 4000))
    # Structural: 200×300 beam spanning 6 m at near top-of-storey
    beam_1 = _comp("beam-1", "structural",
                   lo=(0, 0, 3800), hi=(6000, 300, 4100))
    # MEP: 400×250 HVAC duct along corridor, runs through column zone
    duct_1 = _comp("duct-1", "mep",
                   lo=(0, 50, 3600), hi=(6000, 450, 3850))
    # MEP: 100 dia pipe crossing beam mid-span
    pipe_1 = _comp("pipe-1", "mep",
                   lo=(2500, 100, 3840), hi=(3500, 200, 3940))
    # Architectural: 150mm partition wall near column line
    wall_1 = _comp("wall-1", "architectural",
                   lo=(5800, 0, 0), hi=(5950, 3000, 4200))
    # Architectural: 200mm concrete slab
    slab_1 = _comp("slab-1", "architectural",
                   lo=(0, 0, 3750), hi=(6000, 3000, 3950))
    return [col_1, beam_1, duct_1, pipe_1, wall_1, slab_1]


# ---------------------------------------------------------------------------
# Core fixture clash tests
# ---------------------------------------------------------------------------

class TestBuildingFixtureClashes:
    """Known interferences in the multi-discipline fixture must all be found."""

    def setup_method(self):
        comps = _building_fixture()
        self.result = clash_detect(comps)
        self.clashes = self.result["clashes"]

    def _clash_pair(self, id_a: str, id_b: str) -> dict | None:
        for c in self.clashes:
            if {c["a"], c["b"]} == {id_a, id_b}:
                return c
        return None

    def test_ok(self):
        assert self.result["ok"] is True

    def test_col1_vs_duct1_found(self):
        """col-1 (structural) penetrates duct-1 (mep)."""
        c = self._clash_pair("col-1", "duct-1")
        assert c is not None, "col-1 vs duct-1 clash not detected"
        assert c["type"] == ClashType.HARD
        assert c["depth"] > 0

    def test_beam1_vs_pipe1_found(self):
        """beam-1 (structural) penetrates pipe-1 (mep)."""
        c = self._clash_pair("beam-1", "pipe-1")
        assert c is not None, "beam-1 vs pipe-1 clash not detected"
        assert c["type"] == ClashType.HARD

    def test_beam1_vs_wall1_found(self):
        """beam-1 (structural) penetrates wall-1 (architectural)."""
        c = self._clash_pair("beam-1", "wall-1")
        assert c is not None, "beam-1 vs wall-1 clash not detected"
        assert c["type"] == ClashType.HARD

    def test_duct1_vs_slab1_found(self):
        """duct-1 (mep) penetrates slab-1 (architectural)."""
        c = self._clash_pair("duct-1", "slab-1")
        assert c is not None, "duct-1 vs slab-1 clash not detected"
        assert c["type"] == ClashType.HARD

    def test_pipe1_vs_slab1_found(self):
        """pipe-1 (mep) is inside slab-1 (architectural) zone."""
        c = self._clash_pair("pipe-1", "slab-1")
        assert c is not None, "pipe-1 vs slab-1 clash not detected"
        assert c["type"] == ClashType.HARD

    def test_all_expected_clashes_present(self):
        """All 5 known cross-discipline hard clashes are detected."""
        expected = [
            ("col-1", "duct-1"),
            ("beam-1", "pipe-1"),
            ("beam-1", "wall-1"),
            ("duct-1", "slab-1"),
            ("pipe-1", "slab-1"),
        ]
        for id_a, id_b in expected:
            c = self._clash_pair(id_a, id_b)
            assert c is not None, f"Expected clash {id_a} vs {id_b} not found"
            assert c["type"] == ClashType.HARD


# ---------------------------------------------------------------------------
# Discipline tags on clash records
# ---------------------------------------------------------------------------

class TestDisciplineTagsOnClashRecords:
    """Each clash record must carry correct discipline_a/b and discipline_pair."""

    def setup_method(self):
        comps = _building_fixture()
        self.result = clash_detect(comps)
        self.clashes = self.result["clashes"]

    def _clash_pair(self, id_a: str, id_b: str) -> dict | None:
        for c in self.clashes:
            if {c["a"], c["b"]} == {id_a, id_b}:
                return c
        return None

    def test_col1_duct1_discipline_tags(self):
        c = self._clash_pair("col-1", "duct-1")
        assert c is not None
        disciplines = {c["discipline_a"], c["discipline_b"]}
        assert disciplines == {"structural", "mep"}

    def test_col1_duct1_discipline_pair_canonical(self):
        c = self._clash_pair("col-1", "duct-1")
        assert c is not None
        assert c["discipline_pair"] == "mep vs structural"

    def test_beam1_wall1_discipline_pair(self):
        c = self._clash_pair("beam-1", "wall-1")
        assert c is not None
        assert c["discipline_pair"] == "architectural vs structural"

    def test_duct1_slab1_discipline_pair(self):
        c = self._clash_pair("duct-1", "slab-1")
        assert c is not None
        assert c["discipline_pair"] == "architectural vs mep"

    def test_discipline_pair_is_sorted(self):
        """discipline_pair should always be lexicographically sorted."""
        for c in self.clashes:
            pair = c.get("discipline_pair", "")
            if " vs " in pair:
                left, right = pair.split(" vs ", 1)
                assert left <= right, f"discipline_pair not sorted: {pair!r}"

    def test_all_clash_records_have_discipline_keys(self):
        for c in self.clashes:
            assert "discipline_a" in c
            assert "discipline_b" in c
            assert "discipline_pair" in c


# ---------------------------------------------------------------------------
# by_discipline_pair summary
# ---------------------------------------------------------------------------

class TestByDisciplinePairSummary:
    """by_discipline_pair aggregates counts by discipline combination."""

    def setup_method(self):
        comps = _building_fixture()
        self.result = clash_detect(comps)
        self.by_pair = self.result["by_discipline_pair"]

    def test_by_pair_present(self):
        assert "by_discipline_pair" in self.result

    def test_mep_vs_structural_present(self):
        assert "mep vs structural" in self.by_pair

    def test_mep_vs_structural_count(self):
        """col-1/duct-1 and beam-1/pipe-1 → 2 structural vs mep hard clashes."""
        entry = self.by_pair["mep vs structural"]
        assert entry["hard"] >= 2
        assert entry["total"] >= 2

    def test_architectural_vs_mep_present(self):
        assert "architectural vs mep" in self.by_pair

    def test_architectural_vs_mep_count(self):
        """duct-1/slab-1 and pipe-1/slab-1 → 2 architectural vs mep clashes."""
        entry = self.by_pair["architectural vs mep"]
        assert entry["hard"] >= 2

    def test_architectural_vs_structural_present(self):
        assert "architectural vs structural" in self.by_pair

    def test_totals_match_clashes(self):
        """Sum of all by_discipline_pair totals should equal total clash count."""
        total = sum(v["total"] for v in self.by_pair.values())
        assert total == len(self.result["clashes"])

    def test_no_non_existent_pair(self):
        """There is no civil discipline in this fixture."""
        for key in self.by_pair:
            assert "civil" not in key


# ---------------------------------------------------------------------------
# ClashReport structured view
# ---------------------------------------------------------------------------

class TestClashReport:
    """ClashReport wraps the raw dict and provides typed access."""

    def setup_method(self):
        comps = _building_fixture()
        result = clash_detect(comps)
        self.report = ClashReport(result)

    def test_ok(self):
        assert self.report.ok is True

    def test_clash_count(self):
        assert self.report.clash_count == len(self.report.clashes)

    def test_hard_clashes_list(self):
        assert all(r.type == ClashType.HARD for r in self.report.hard_clashes)
        assert len(self.report.hard_clashes) >= 5

    def test_clashes_for_pair_structural_mep(self):
        pairs = self.report.clashes_for_pair("structural", "mep")
        assert len(pairs) >= 2
        for r in pairs:
            disciplines = {r.discipline_a, r.discipline_b}
            assert disciplines == {"structural", "mep"}

    def test_clashes_for_pair_is_order_independent(self):
        """clashes_for_pair("mep", "structural") == clashes_for_pair("structural", "mep")."""
        a = self.report.clashes_for_pair("structural", "mep")
        b = self.report.clashes_for_pair("mep", "structural")
        assert len(a) == len(b)

    def test_clashes_for_pair_returns_records(self):
        records = self.report.clashes_for_pair("architectural", "mep")
        assert all(isinstance(r, ClashRecord) for r in records)

    def test_to_dict_has_clash_count(self):
        d = self.report.to_dict()
        assert d["clash_count"] == self.report.clash_count
        assert "by_discipline_pair" in d

    def test_no_errors(self):
        assert self.report.errors == []


# ---------------------------------------------------------------------------
# Discipline field on ComponentShape
# ---------------------------------------------------------------------------

class TestComponentShapeDisciplineField:
    def test_discipline_stored_lowercase(self):
        c = ComponentShape("x", discipline="Structural", bbox_min=(0,0,0), bbox_max=(1,1,1))
        assert c.discipline == "structural"

    def test_discipline_none_default(self):
        c = ComponentShape("x", bbox_min=(0,0,0), bbox_max=(1,1,1))
        assert c.discipline is None

    def test_empty_discipline_becomes_none(self):
        c = ComponentShape("x", discipline="", bbox_min=(0,0,0), bbox_max=(1,1,1))
        assert c.discipline is None

    def test_discipline_whitespace_stripped(self):
        c = ComponentShape("x", discipline="  mep  ", bbox_min=(0,0,0), bbox_max=(1,1,1))
        assert c.discipline == "mep"


# ---------------------------------------------------------------------------
# Dict input with discipline field
# ---------------------------------------------------------------------------

class TestDictInputWithDiscipline:
    def test_discipline_from_dict(self):
        comps = [
            {"instance_id": "s1", "discipline": "structural",
             "bbox_min": [0, 0, 0], "bbox_max": [300, 300, 4000]},
            {"instance_id": "d1", "discipline": "mep",
             "bbox_min": [0, 50, 3600], "bbox_max": [6000, 450, 3850]},
        ]
        result = clash_detect(comps)
        assert result["ok"] is True
        assert len(result["clashes"]) == 1
        c = result["clashes"][0]
        assert c["discipline_pair"] == "mep vs structural"

    def test_dict_discipline_case_normalised(self):
        comps = [
            {"instance_id": "s1", "discipline": "Structural",
             "bbox_min": [0, 0, 0], "bbox_max": [100, 100, 100]},
            {"instance_id": "m1", "discipline": "MEP",
             "bbox_min": [50, 0, 0], "bbox_max": [150, 100, 100]},
        ]
        result = clash_detect(comps)
        c = result["clashes"][0]
        assert c["discipline_pair"] == "mep vs structural"

    def test_no_discipline_becomes_unclassified(self):
        comps = [
            {"instance_id": "a", "bbox_min": [0, 0, 0], "bbox_max": [2, 2, 2]},
            {"instance_id": "b", "bbox_min": [1, 0, 0], "bbox_max": [3, 2, 2]},
        ]
        result = clash_detect(comps)
        c = result["clashes"][0]
        assert c["discipline_a"] is None
        assert c["discipline_b"] is None
        assert c["discipline_pair"] == "unclassified vs unclassified"


# ---------------------------------------------------------------------------
# Clearance detection across disciplines
# ---------------------------------------------------------------------------

class TestClearanceAcrossDisciplines:
    def test_clearance_gets_discipline_tags(self):
        """Clearance violations carry discipline info."""
        s = ComponentShape("col", discipline="structural",
                           bbox_min=(0, 0, 0), bbox_max=(300, 300, 4000))
        p = ComponentShape("pipe", discipline="mep",
                           bbox_min=(350, 0, 1000), bbox_max=(450, 100, 1100))
        # gap on X = 350 - 300 = 50mm; min_clearance=100 → clearance violation
        result = clash_detect([s, p], min_clearance=100.0)
        assert len(result["clashes"]) == 1
        c = result["clashes"][0]
        assert c["type"] == ClashType.CLEARANCE
        assert c["discipline_pair"] == "mep vs structural"

    def test_clearance_appears_in_by_discipline_pair(self):
        s = ComponentShape("col", discipline="structural",
                           bbox_min=(0, 0, 0), bbox_max=(300, 300, 4000))
        p = ComponentShape("pipe", discipline="mep",
                           bbox_min=(350, 0, 1000), bbox_max=(450, 100, 1100))
        result = clash_detect([s, p], min_clearance=100.0)
        by_pair = result["by_discipline_pair"]
        assert "mep vs structural" in by_pair
        assert by_pair["mep vs structural"]["clearance"] == 1


# ---------------------------------------------------------------------------
# Unclassified discipline mixing with tagged
# ---------------------------------------------------------------------------

class TestMixedDisciplineTags:
    def test_unclassified_and_structural(self):
        s = ComponentShape("col", discipline="structural",
                           bbox_min=(0, 0, 0), bbox_max=(100, 100, 100))
        u = ComponentShape("thing", discipline=None,
                           bbox_min=(50, 0, 0), bbox_max=(150, 100, 100))
        result = clash_detect([s, u])
        c = result["clashes"][0]
        assert c["discipline_pair"] == "structural vs unclassified"

    def test_by_pair_key_for_unclassified(self):
        s = ComponentShape("col", discipline="structural",
                           bbox_min=(0, 0, 0), bbox_max=(100, 100, 100))
        u = ComponentShape("thing",
                           bbox_min=(50, 0, 0), bbox_max=(150, 100, 100))
        result = clash_detect([s, u])
        assert "structural vs unclassified" in result["by_discipline_pair"]
