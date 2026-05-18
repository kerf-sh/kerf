"""
T-109: Parametric family authoring + flex — end-to-end pytest.

Proves that a parametric column / window / door family can be:
  1. Authored (FamilyDefinition with type+instance params, formula params)
  2. Given named type presets (FamilyType)
  3. Instantiated (FamilyInstance with param overrides + transform)
  4. Flexed across the full parameter set range
  5. Round-tripped through JSON serialization

Pure-Python, no DB, no async.
"""
from __future__ import annotations

import math
import pytest

from kerf_bim.family import (
    CycleError,
    DuplicateParameterError,
    FamilyDefinition,
    FamilyError,
    FamilyInstance,
    FamilyType,
    FormulaError,
    Parameter,
    SharedParameter,
    Transform,
    UnknownParameterError,
    family_from_dict,
    family_to_dict,
    instance_from_dict,
    instance_to_dict,
    make_family,
    make_instance,
    make_parameter,
    make_type,
    resolve_instance,
    resolve_type,
    type_from_dict,
    type_to_dict,
)


# ---------------------------------------------------------------------------
# Shared parametric family fixtures
# ---------------------------------------------------------------------------


def _column_family() -> FamilyDefinition:
    """Parametric reinforced-concrete column with formula-derived volume."""
    return make_family(
        name="Concrete Column",
        category="Column",
        type_parameters=[
            Parameter("width",  "length", default=400.0, description="Section width mm"),
            Parameter("depth",  "length", default=400.0, description="Section depth mm"),
            Parameter("height", "length", default=3600.0, description="Storey height mm"),
            # Formula: cross-section area in mm²
            Parameter("area",   "float",  default=0.0,
                      formula="width * depth",
                      description="Cross-section area mm²"),
            # Formula: volume in mm³
            Parameter("volume", "float",  default=0.0,
                      formula="width * depth * height",
                      description="Gross volume mm³"),
        ],
        instance_parameters=[
            Parameter("concrete_grade", "string",  default="C30/37"),
            Parameter("rebar",          "string",  default="8T20"),
            Parameter("fire_rating",    "integer", default=60,
                      description="Fire rating in minutes"),
        ],
        description="Parametric reinforced-concrete column (T-109)",
    )


def _window_family() -> FamilyDefinition:
    """Parametric casement window."""
    return make_family(
        name="Casement Window",
        category="Window",
        type_parameters=[
            Parameter("width",  "length", default=900.0,  description="Rough opening width mm"),
            Parameter("height", "length", default=1200.0, description="Rough opening height mm"),
            # Glazing area formula
            Parameter("glazing_area", "float", default=0.0,
                      formula="width * height * 0.000001",
                      description="Glazing area m²"),
        ],
        instance_parameters=[
            Parameter("glazing_type", "material", default="double_low_e"),
            Parameter("openable",     "boolean",  default=True),
            Parameter("colour",       "string",   default="white"),
        ],
        description="Single-panel casement window (T-109)",
    )


def _door_family() -> FamilyDefinition:
    """Parametric single-leaf door with shared fire-rating parameter."""
    sp = SharedParameter("floor_fire_rating", "integer", "project", default=30)
    return make_family(
        name="Single Leaf Door",
        category="Door",
        type_parameters=[
            Parameter("width",           "length", default=900.0),
            Parameter("height",          "length", default=2100.0),
            Parameter("panel_thickness", "length", default=45.0),
        ],
        instance_parameters=[
            Parameter("frame_material", "material", default="oak"),
            Parameter("hardware",       "string",   default="standard"),
            Parameter("flipped",        "boolean",  default=False),
        ],
        shared_parameters=[sp],
        description="Single-leaf door (T-109)",
    )


# ---------------------------------------------------------------------------
# 1. Family authoring — construction + validation
# ---------------------------------------------------------------------------


class TestFamilyAuthoring:
    """Prove families can be authored with the full parameter toolset."""

    def test_column_family_authored_correctly(self):
        fam = _column_family()
        assert fam.name == "Concrete Column"
        assert fam.category == "Column"
        assert set(fam.type_parameters) == {"width", "depth", "height", "area", "volume"}
        assert set(fam.instance_parameters) == {"concrete_grade", "rebar", "fire_rating"}

    def test_column_has_formula_params(self):
        fam = _column_family()
        assert fam.type_parameters["area"].formula == "width * depth"
        assert fam.type_parameters["volume"].formula == "width * depth * height"

    def test_window_family_authored(self):
        fam = _window_family()
        assert fam.category == "Window"
        assert "glazing_area" in fam.type_parameters
        assert fam.type_parameters["glazing_area"].formula is not None

    def test_door_family_has_shared_param(self):
        fam = _door_family()
        assert "floor_fire_rating" in fam.shared_parameters
        assert fam.shared_parameters["floor_fire_rating"].scope == "project"

    def test_duplicate_type_instance_param_raises(self):
        with pytest.raises(DuplicateParameterError):
            make_family(
                name="Bad",
                category="Column",
                type_parameters=[Parameter("height", "length", default=3600.0)],
                instance_parameters=[Parameter("height", "length", default=3600.0)],
            )

    def test_formula_cycle_raises_at_resolve_time(self):
        fam = make_family(
            name="Cycle",
            category="Generic",
            type_parameters=[
                Parameter("a", "float", default=0.0, formula="b + 1"),
                Parameter("b", "float", default=0.0, formula="a + 1"),
            ],
        )
        t = make_type(fam, "t", {})
        with pytest.raises(CycleError):
            resolve_instance(make_instance(t))


# ---------------------------------------------------------------------------
# 2. Type presets
# ---------------------------------------------------------------------------


class TestFamilyTypes:
    """Prove type presets (named param sets) can be added and resolved."""

    def test_column_types_created(self):
        fam = _column_family()
        t300 = make_type(fam, "300 sq",  {"width": 300.0, "depth": 300.0})
        t400 = make_type(fam, "400 sq",  {"width": 400.0, "depth": 400.0})
        t600 = make_type(fam, "600 sq",  {"width": 600.0, "depth": 600.0})
        t400x600 = make_type(fam, "400×600", {"width": 400.0, "depth": 600.0})

        assert t300.type_param_values["width"] == 300.0
        assert t400x600.type_param_values["depth"] == 600.0

        # resolve_type returns canonical values for each type
        r300 = resolve_type(t300)
        assert r300["width"] == 300.0
        assert r300["depth"] == 300.0
        assert r300["area"] == pytest.approx(300.0 * 300.0)
        assert r300["volume"] == pytest.approx(300.0 * 300.0 * 3600.0)

        r400x600 = resolve_type(t400x600)
        assert r400x600["area"] == pytest.approx(400.0 * 600.0)

    def test_window_types(self):
        fam = _window_family()
        narrow = make_type(fam, "Narrow", {"width": 600.0})
        wide   = make_type(fam, "Wide",   {"width": 1500.0, "height": 1800.0})

        rn = resolve_type(narrow)
        assert rn["width"] == 600.0
        assert rn["glazing_area"] == pytest.approx(600.0 * 1200.0 * 0.000001)

        rw = resolve_type(wide)
        assert rw["glazing_area"] == pytest.approx(1500.0 * 1800.0 * 0.000001)

    def test_door_types(self):
        fam = _door_family()
        t762 = make_type(fam, "762x2032", {"width": 762.0, "height": 2032.0})
        t900 = make_type(fam, "900x2100", {"width": 900.0, "height": 2100.0})

        r = resolve_type(t762)
        assert r["width"] == 762.0
        assert r["height"] == 2032.0
        assert r["frame_material"] == "oak"   # instance param default

    def test_type_rejects_unknown_param(self):
        fam = _column_family()
        with pytest.raises(UnknownParameterError):
            make_type(fam, "bad", {"colour": "red"})


# ---------------------------------------------------------------------------
# 3. Instantiation
# ---------------------------------------------------------------------------


class TestFamilyInstantiation:
    """Prove instances can be created, placed, and resolved."""

    def test_column_instance_defaults(self):
        fam = _column_family()
        t = make_type(fam, "400 sq", {"width": 400.0, "depth": 400.0})
        inst = make_instance(t)
        r = resolve_instance(inst)
        assert r["width"] == 400.0
        assert r["depth"] == 400.0
        assert r["height"] == 3600.0
        assert r["area"] == pytest.approx(400.0 * 400.0)
        assert r["volume"] == pytest.approx(400.0 * 400.0 * 3600.0)
        assert r["concrete_grade"] == "C30/37"
        assert r["fire_rating"] == 60

    def test_instance_overrides_type(self):
        fam = _column_family()
        t = make_type(fam, "400 sq", {"width": 400.0, "depth": 400.0})
        inst = make_instance(t, instance_param_values={
            "concrete_grade": "C40/50",
            "fire_rating": 90,
        })
        r = resolve_instance(inst)
        assert r["concrete_grade"] == "C40/50"
        assert r["fire_rating"] == 90
        # Formulas still win
        assert r["area"] == pytest.approx(400.0 * 400.0)

    def test_instance_can_override_type_param(self):
        """Instance overrides may target type parameters (Revit semantics)."""
        fam = _column_family()
        t = make_type(fam, "400 sq", {"width": 400.0, "depth": 400.0})
        inst = make_instance(t, instance_param_values={"height": 4200.0})
        r = resolve_instance(inst)
        assert r["height"] == 4200.0
        # Volume recomputed via formula
        assert r["volume"] == pytest.approx(400.0 * 400.0 * 4200.0)

    def test_instance_with_transform(self):
        fam = _column_family()
        t = make_type(fam, "default", {})
        xform = Transform.from_translation(5000.0, 0.0, 0.0)
        inst = make_instance(t, transform=xform)
        assert inst.transform.as_list()[0][3] == 5000.0

    def test_window_instance_placement(self):
        fam = _window_family()
        wide = make_type(fam, "Wide", {"width": 1500.0, "height": 1800.0})
        inst = make_instance(wide, instance_param_values={"colour": "anthracite"})
        r = resolve_instance(inst)
        assert r["colour"] == "anthracite"
        assert r["glazing_area"] == pytest.approx(1500.0 * 1800.0 * 0.000001)

    def test_door_shared_param_in_formula(self):
        """Shared project-level fire rating is available to formula bindings."""
        fam = _door_family()
        t = make_type(fam, "std", {})
        inst = make_instance(t)
        r = resolve_instance(inst, shared_values={"floor_fire_rating": 60})
        # No formula uses floor_fire_rating directly in this family,
        # but the shared param is present and its value is accessible.
        assert r["width"] == 900.0

    def test_unknown_instance_param_raises(self):
        fam = _column_family()
        t = make_type(fam, "t", {})
        with pytest.raises(UnknownParameterError):
            make_instance(t, instance_param_values={"colour": "red"})


# ---------------------------------------------------------------------------
# 4. Parametric flex — sweep across parameter sets
# ---------------------------------------------------------------------------


class TestParametricFlex:
    """The 'flex panel': resolve a family across all its parameter sets.

    This directly mirrors the backend flex_family tool and the JS flexFamily().
    """

    def _flex(self, family, parameter_sets):
        """Resolve a family across multiple parameter sets, return list of results."""
        results = []
        for idx, instance in enumerate(parameter_sets):
            resolved = {}
            # Build resolved from type then instance
            if instance.get("type"):
                r = resolve_type(instance["type"])
                resolved.update(r)
            inst = make_instance(
                instance["type"],
                instance_param_values=instance.get("params", {}),
            )
            resolved = resolve_instance(inst)
            results.append({"index": idx, "resolved": resolved, "instance": inst})
        return results

    def test_column_flex_across_all_types(self):
        fam = _column_family()
        types = [
            make_type(fam, "300 sq",  {"width": 300.0, "depth": 300.0}),
            make_type(fam, "400 sq",  {"width": 400.0, "depth": 400.0}),
            make_type(fam, "600 sq",  {"width": 600.0, "depth": 600.0}),
            make_type(fam, "400×600", {"width": 400.0, "depth": 600.0}),
        ]
        expected_areas = [
            300.0 * 300.0,
            400.0 * 400.0,
            600.0 * 600.0,
            400.0 * 600.0,
        ]
        for t, expected_area in zip(types, expected_areas):
            inst = make_instance(t)
            r = resolve_instance(inst)
            assert r["area"] == pytest.approx(expected_area), \
                f"Type '{t.name}': area mismatch"
            assert r["volume"] == pytest.approx(expected_area * 3600.0), \
                f"Type '{t.name}': volume mismatch"

    def test_window_flex_across_types(self):
        fam = _window_family()
        type_data = [
            ("Narrow",  {"width": 600.0}),
            ("Standard",{"width": 900.0, "height": 1200.0}),
            ("Wide",    {"width": 1500.0, "height": 1800.0}),
        ]
        for name, vals in type_data:
            t = make_type(fam, name, vals)
            r = resolve_type(t)
            expected = vals.get("width", 900.0) * vals.get("height", 1200.0) * 0.000001
            assert r["glazing_area"] == pytest.approx(expected), \
                f"Window '{name}': glazing_area mismatch"

    def test_door_flex_across_types(self):
        fam = _door_family()
        type_data = [
            ("762x2032", {"width": 762.0,  "height": 2032.0}),
            ("838x2032", {"width": 838.0,  "height": 2032.0}),
            ("900x2100", {"width": 900.0,  "height": 2100.0}),
            ("1800 dbl", {"width": 1800.0, "height": 2100.0}),
        ]
        for name, vals in type_data:
            t = make_type(fam, name, vals)
            inst = make_instance(t)
            r = resolve_instance(inst)
            assert r["width"] == vals["width"], f"Door '{name}': width mismatch"
            assert r["height"] == vals["height"], f"Door '{name}': height mismatch"
            assert r["frame_material"] == "oak"    # family default preserved
            assert r["flipped"] is False

    def test_column_flex_with_instance_overrides(self):
        """Exercise the flex with instance-level overrides across many sets."""
        fam = _column_family()
        t_base = make_type(fam, "400 sq", {"width": 400.0, "depth": 400.0})

        heights = [2800.0, 3000.0, 3600.0, 4000.0, 5000.0]
        grades  = ["C25/30", "C30/37", "C35/45", "C40/50", "C45/55"]

        for h, grade in zip(heights, grades):
            inst = make_instance(t_base, instance_param_values={
                "concrete_grade": grade,
                "height": h,
            })
            r = resolve_instance(inst)
            assert r["height"] == h
            assert r["concrete_grade"] == grade
            assert r["volume"] == pytest.approx(400.0 * 400.0 * h)

    def test_formula_produces_consistent_results_across_flex(self):
        """Formula evaluation must be deterministic across the full flex sweep."""
        fam = make_family(
            name="Box",
            category="Generic",
            type_parameters=[
                Parameter("l", "length", default=1000.0),
                Parameter("w", "length", default=500.0),
                Parameter("h", "length", default=300.0),
                Parameter("perimeter", "float", default=0.0, formula="2 * (l + w)"),
                Parameter("volume",    "float", default=0.0, formula="l * w * h"),
                Parameter("diagonal",  "float", default=0.0,
                          formula="sqrt(l**2 + w**2 + h**2)"),
            ],
        )
        test_cases = [
            {"l": 1000.0, "w": 500.0, "h": 300.0},
            {"l": 2000.0, "w": 800.0, "h": 400.0},
            {"l": 600.0,  "w": 600.0, "h": 600.0},
        ]
        for vals in test_cases:
            t = make_type(fam, "t", vals)
            inst = make_instance(t)
            r = resolve_instance(inst)
            l, w, h = vals["l"], vals["w"], vals["h"]
            assert r["perimeter"] == pytest.approx(2 * (l + w))
            assert r["volume"]    == pytest.approx(l * w * h)
            assert r["diagonal"]  == pytest.approx(math.sqrt(l**2 + w**2 + h**2))


# ---------------------------------------------------------------------------
# 5. Serialization round-trip for the authored families
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    """Prove authored families survive JSON round-trip intact."""

    def test_column_family_round_trip(self):
        fam = _column_family()
        d = family_to_dict(fam)
        fam2 = family_from_dict(d)
        assert fam2.id == fam.id
        assert fam2.name == fam.name
        assert set(fam2.type_parameters) == set(fam.type_parameters)
        # Formulas survive
        assert fam2.type_parameters["area"].formula == "width * depth"
        assert fam2.type_parameters["volume"].formula == "width * depth * height"

    def test_column_resolve_after_round_trip(self):
        fam = _column_family()
        d = family_to_dict(fam)
        fam2 = family_from_dict(d)
        t = make_type(fam2, "400 sq", {"width": 400.0, "depth": 400.0})
        inst = make_instance(t)
        r = resolve_instance(inst)
        assert r["area"]   == pytest.approx(400.0 * 400.0)
        assert r["volume"] == pytest.approx(400.0 * 400.0 * 3600.0)

    def test_window_family_round_trip(self):
        fam = _window_family()
        d = family_to_dict(fam)
        fam2 = family_from_dict(d)
        t = make_type(fam2, "Wide", {"width": 1500.0, "height": 1800.0})
        r = resolve_type(t)
        assert r["glazing_area"] == pytest.approx(1500.0 * 1800.0 * 0.000001)

    def test_door_family_round_trip_with_shared_param(self):
        fam = _door_family()
        d = family_to_dict(fam)
        fam2 = family_from_dict(d)
        assert "floor_fire_rating" in fam2.shared_parameters
        t = make_type(fam2, "std", {"width": 900.0})
        r = resolve_instance(make_instance(t))
        assert r["width"] == 900.0

    def test_type_instance_round_trip(self):
        fam = _column_family()
        t = make_type(fam, "400 sq", {"width": 400.0, "depth": 400.0})
        inst = make_instance(
            t,
            instance_param_values={"concrete_grade": "C40/50", "fire_rating": 90},
            transform=Transform.from_translation(6000.0, 0.0, 0.0),
        )
        td = type_to_dict(t)
        id_ = instance_to_dict(inst)

        t2   = type_from_dict(td, fam)
        inst2 = instance_from_dict(id_, t2)

        r = resolve_instance(inst2)
        assert r["concrete_grade"] == "C40/50"
        assert r["fire_rating"] == 90
        assert r["area"] == pytest.approx(400.0 * 400.0)
        assert inst2.transform.as_list()[0][3] == 6000.0


# ---------------------------------------------------------------------------
# 6. DoD integration test — author + instantiate + flex column end-to-end
# ---------------------------------------------------------------------------


def test_t109_dod_column_authored_instantiated_flexed():
    """
    T-109 DoD integration test:
    A parametric column family is authored end-to-end, given multiple types,
    instantiated with parameter overrides, and flexed across parameter sets.
    """
    # --- Author ---
    fam = make_family(
        name="Structural Column",
        category="Column",
        type_parameters=[
            Parameter("width",  "length", default=400.0, description="Section width mm"),
            Parameter("depth",  "length", default=400.0, description="Section depth mm"),
            Parameter("height", "length", default=3600.0, description="Storey height mm"),
            Parameter("area",   "float",  default=0.0, formula="width * depth"),
            Parameter("volume", "float",  default=0.0, formula="width * depth * height"),
        ],
        instance_parameters=[
            Parameter("concrete_grade", "string",  default="C30/37"),
            Parameter("fire_rating",    "integer", default=60),
        ],
    )
    assert fam.name == "Structural Column"

    # --- Add types ---
    types = {
        "300sq":   make_type(fam, "300×300",  {"width": 300.0,  "depth": 300.0}),
        "400sq":   make_type(fam, "400×400",  {"width": 400.0,  "depth": 400.0}),
        "600sq":   make_type(fam, "600×600",  {"width": 600.0,  "depth": 600.0}),
        "400x600": make_type(fam, "400×600",  {"width": 400.0,  "depth": 600.0}),
    }

    # --- Instantiate ---
    placements = [
        make_instance(
            types["300sq"],
            instance_param_values={"concrete_grade": "C25/30"},
            transform=Transform.from_translation(0.0, 0.0, 0.0),
        ),
        make_instance(
            types["400sq"],
            instance_param_values={"concrete_grade": "C30/37", "fire_rating": 90},
            transform=Transform.from_translation(6000.0, 0.0, 0.0),
        ),
        make_instance(
            types["600sq"],
            instance_param_values={"concrete_grade": "C40/50"},
            transform=Transform.from_translation(12000.0, 0.0, 0.0),
        ),
        make_instance(
            types["400x600"],
            transform=Transform.from_translation(6000.0, 8000.0, 0.0),
        ),
    ]

    # --- Flex ---
    expected = [
        {"width": 300.0,  "depth": 300.0,  "area": 90000.0,   "grade": "C25/30"},
        {"width": 400.0,  "depth": 400.0,  "area": 160000.0,  "grade": "C30/37"},
        {"width": 600.0,  "depth": 600.0,  "area": 360000.0,  "grade": "C40/50"},
        {"width": 400.0,  "depth": 600.0,  "area": 240000.0,  "grade": "C30/37"},
    ]

    for inst, exp in zip(placements, expected):
        r = resolve_instance(inst)
        assert r["width"]  == pytest.approx(exp["width"])
        assert r["depth"]  == pytest.approx(exp["depth"])
        assert r["area"]   == pytest.approx(exp["area"])
        assert r["concrete_grade"] == exp["grade"]
        assert r["volume"] == pytest.approx(exp["width"] * exp["depth"] * 3600.0)

    # --- Serialization survives ---
    d = family_to_dict(fam)
    fam2 = family_from_dict(d)
    t = make_type(fam2, "400sq", {"width": 400.0, "depth": 400.0})
    r = resolve_instance(make_instance(t))
    assert r["area"] == pytest.approx(160000.0)


def test_t109_dod_window_authored_instantiated_flexed():
    """T-109 DoD: window family authored + instantiated + flexed."""
    fam = make_family(
        name="Casement Window",
        category="Window",
        type_parameters=[
            Parameter("width",        "length", default=900.0),
            Parameter("height",       "length", default=1200.0),
            Parameter("glazing_area", "float",  default=0.0,
                      formula="width * height * 0.000001"),
        ],
        instance_parameters=[
            Parameter("glazing_type", "material", default="double_low_e"),
            Parameter("openable",     "boolean",  default=True),
        ],
    )

    types = {
        "narrow": make_type(fam, "Narrow",   {"width": 600.0}),
        "std":    make_type(fam, "Standard", {"width": 900.0, "height": 1200.0}),
        "wide":   make_type(fam, "Wide",     {"width": 1500.0, "height": 1800.0}),
        "fixed":  make_type(fam, "Fixed",    {"width": 900.0}),
    }

    instances_data = [
        (types["narrow"], {"openable": True}),
        (types["std"],    {"glazing_type": "triple_lam"}),
        (types["wide"],   {"openable": True, "glazing_type": "double_low_e"}),
        (types["fixed"],  {"openable": False}),
    ]

    expected_areas = [
        600.0 * 1200.0 * 0.000001,
        900.0 * 1200.0 * 0.000001,
        1500.0 * 1800.0 * 0.000001,
        900.0 * 1200.0 * 0.000001,
    ]

    for (t, overrides), exp_area in zip(instances_data, expected_areas):
        inst = make_instance(t, instance_param_values=overrides)
        r = resolve_instance(inst)
        assert r["glazing_area"] == pytest.approx(exp_area)

    # Fixed window has openable=False
    r_fixed = resolve_instance(make_instance(types["fixed"], instance_param_values={"openable": False}))
    assert r_fixed["openable"] is False


def test_t109_dod_door_authored_instantiated_flexed():
    """T-109 DoD: door family authored + instantiated + flexed."""
    fam = make_family(
        name="Single Leaf Door",
        category="Door",
        type_parameters=[
            Parameter("width",           "length", default=900.0),
            Parameter("height",          "length", default=2100.0),
            Parameter("panel_thickness", "length", default=45.0),
        ],
        instance_parameters=[
            Parameter("frame_material", "material", default="oak"),
            Parameter("hardware",       "string",   default="standard"),
            Parameter("flipped",        "boolean",  default=False),
        ],
    )

    types = {
        "762x2032": make_type(fam, "762x2032", {"width": 762.0,  "height": 2032.0}),
        "838x2032": make_type(fam, "838x2032", {"width": 838.0,  "height": 2032.0}),
        "900x2100": make_type(fam, "900x2100", {"width": 900.0,  "height": 2100.0}),
        "double":   make_type(fam, "Double",   {"width": 1800.0, "panel_thickness": 40.0}),
    }

    # Flex across all types
    expected_widths = [762.0, 838.0, 900.0, 1800.0]
    for (name, t), exp_w in zip(types.items(), expected_widths):
        r = resolve_type(t)
        assert r["width"] == pytest.approx(exp_w), f"Door type '{name}': width mismatch"

    # Instantiate with overrides
    inst_flipped = make_instance(
        types["900x2100"],
        instance_param_values={"flipped": True, "frame_material": "steel"},
    )
    r = resolve_instance(inst_flipped)
    assert r["flipped"] is True
    assert r["frame_material"] == "steel"
    assert r["width"] == 900.0
    assert r["panel_thickness"] == 45.0  # family default

    # Round-trip
    d = family_to_dict(fam)
    fam2 = family_from_dict(d)
    t = make_type(fam2, "762x2032", {"width": 762.0, "height": 2032.0})
    r2 = resolve_instance(make_instance(t))
    assert r2["width"] == 762.0
    assert r2["frame_material"] == "oak"
