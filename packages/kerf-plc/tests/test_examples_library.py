"""
tests/test_examples_library.py — oracles for the kerf-plc example library (T-225e).

Test plan
---------
T1  EXAMPLES has exactly 10 entries; all slugs are unique.
T2  Every entry has required keys: slug, name, category, description, file_path.
T3  Every fixture file exists on disk.
T4  Every fixture parses through reader.load() without raising.
T5  Every parsed project has >= 1 POU.
T6  Every parsed project has >= 1 rung across all POUs.
T7  Every parsed project has >= 2 variables across all POUs.
T8  load_example("traffic_light") returns a Project whose first POU is "TrafficLight".
T9  examples_by_category("safety") returns >= 1 entry (door_interlock).
T10 list_categories() returns a sorted, non-empty list of strings.
T11 load_example with an unknown slug raises KeyError.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from kerf_plc.examples.library import (
    EXAMPLES,
    examples_by_category,
    list_categories,
    load_example,
)
from kerf_plc.plcopen.ast import Project
from kerf_plc.plcopen.reader import load as reader_load


# ---------------------------------------------------------------------------
# T1: Manifest size and slug uniqueness
# ---------------------------------------------------------------------------

class TestManifest:
    def test_exactly_10_examples(self):
        assert len(EXAMPLES) == 10, f"Expected 10 examples, got {len(EXAMPLES)}"

    def test_all_slugs_distinct(self):
        slugs = [e["slug"] for e in EXAMPLES]
        assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"

    def test_required_keys_present(self):
        required = {"slug", "name", "category", "description", "file_path"}
        for entry in EXAMPLES:
            missing = required - entry.keys()
            assert not missing, f"Entry {entry.get('slug')} missing keys: {missing}"

    def test_no_empty_values(self):
        for entry in EXAMPLES:
            for key in ("slug", "name", "category", "description", "file_path"):
                assert entry[key], f"Entry {entry['slug']!r} has empty value for {key!r}"


# ---------------------------------------------------------------------------
# T2: Fixture files exist
# ---------------------------------------------------------------------------

class TestFixtureFiles:
    def test_all_fixture_files_exist(self):
        from pathlib import Path
        for entry in EXAMPLES:
            path = Path(entry["file_path"])
            assert path.exists(), f"Fixture missing: {entry['file_path']}"

    def test_fixture_files_are_xml(self):
        for entry in EXAMPLES:
            with open(entry["file_path"], encoding="utf-8") as fh:
                first_line = fh.readline()
            assert "<?xml" in first_line, (
                f"{entry['slug']}: fixture does not start with XML declaration"
            )


# ---------------------------------------------------------------------------
# T3: Every example parses without raising
# ---------------------------------------------------------------------------

class TestParsing:
    @pytest.mark.parametrize("entry", EXAMPLES, ids=[e["slug"] for e in EXAMPLES])
    def test_parses_without_error(self, entry):
        project = reader_load(entry["file_path"])
        assert isinstance(project, Project)

    @pytest.mark.parametrize("entry", EXAMPLES, ids=[e["slug"] for e in EXAMPLES])
    def test_project_name_not_empty(self, entry):
        project = reader_load(entry["file_path"])
        assert project.name, f"{entry['slug']}: project name is empty"


# ---------------------------------------------------------------------------
# T4: Structural depth — >= 1 POU, >= 1 rung, >= 2 variables
# ---------------------------------------------------------------------------

class TestStructuralDepth:
    @pytest.mark.parametrize("entry", EXAMPLES, ids=[e["slug"] for e in EXAMPLES])
    def test_at_least_one_pou(self, entry):
        project = reader_load(entry["file_path"])
        assert len(project.pous) >= 1, (
            f"{entry['slug']}: expected >= 1 POU, got {len(project.pous)}"
        )

    @pytest.mark.parametrize("entry", EXAMPLES, ids=[e["slug"] for e in EXAMPLES])
    def test_at_least_one_rung(self, entry):
        project = reader_load(entry["file_path"])
        total_rungs = sum(len(pou.rungs) for pou in project.pous)
        assert total_rungs >= 1, (
            f"{entry['slug']}: expected >= 1 rung, got {total_rungs}"
        )

    @pytest.mark.parametrize("entry", EXAMPLES, ids=[e["slug"] for e in EXAMPLES])
    def test_at_least_two_variables(self, entry):
        project = reader_load(entry["file_path"])
        total_vars = sum(len(pou.variables) for pou in project.pous)
        assert total_vars >= 2, (
            f"{entry['slug']}: expected >= 2 variables, got {total_vars}"
        )


# ---------------------------------------------------------------------------
# T5: load_example("traffic_light") returns Project with correct POU name
# ---------------------------------------------------------------------------

class TestLoadExample:
    def test_traffic_light_pou_name(self):
        project = load_example("traffic_light")
        assert isinstance(project, Project)
        assert len(project.pous) >= 1
        assert project.pous[0].name == "TrafficLight", (
            f"Expected pou.name='TrafficLight', got {project.pous[0].name!r}"
        )

    def test_unknown_slug_raises_key_error(self):
        with pytest.raises(KeyError):
            load_example("this_does_not_exist")

    def test_load_example_returns_project_instance(self):
        for entry in EXAMPLES:
            result = load_example(entry["slug"])
            assert isinstance(result, Project), (
                f"{entry['slug']}: load_example returned {type(result)!r}"
            )


# ---------------------------------------------------------------------------
# T6: examples_by_category("safety") >= 1 entry
# ---------------------------------------------------------------------------

class TestCategoryHelpers:
    def test_safety_category_has_entries(self):
        safety = examples_by_category("safety")
        assert len(safety) >= 1, "Expected >= 1 example in 'safety' category"

    def test_door_interlock_is_safety(self):
        safety = examples_by_category("safety")
        slugs = [e["slug"] for e in safety]
        assert "door_interlock" in slugs, (
            f"door_interlock not in safety category; safety entries: {slugs}"
        )

    def test_list_categories_non_empty(self):
        cats = list_categories()
        assert isinstance(cats, list)
        assert len(cats) > 0

    def test_list_categories_sorted(self):
        cats = list_categories()
        assert cats == sorted(cats), f"list_categories() not sorted: {cats}"

    def test_list_categories_contains_safety(self):
        assert "safety" in list_categories()

    def test_examples_by_category_unknown_returns_empty(self):
        result = examples_by_category("nonexistent_category")
        assert result == []

    def test_all_category_values_in_list_categories(self):
        all_cats = set(list_categories())
        for entry in EXAMPLES:
            assert entry["category"] in all_cats
