"""
Tests for kerf_bim.family_authoring — T-109 parametric family-authoring UX.

Test plan
---------
1. validate_family_template — valid template returns no errors.
2. validate_family_template — cyclic expression dependencies detected.
3. validate_family_template — expression referencing an undeclared name.
4. validate_family_template — invalid expression syntax.
5. validate_family_template — duplicate parameter names.
6. validate_family_template — empty template name.
7. generate_body — COLUMN_TEMPLATE with default params produces π·D²·H/4 volume.
8. generate_body — doubling D doubles the *squared* factor so volume ×4.
9. generate_body — formula (expression) parameters are evaluated correctly.
10. generate_body — raises ValueError for an invalid template.
"""
from __future__ import annotations

import math
import pytest

from kerf_bim.family_authoring import (
    COLUMN_TEMPLATE,
    FamilyTemplate,
    TemplateParameter,
    generate_body,
    validate_family_template,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _column(D: float = 0.3, H: float = 3.0) -> FamilyTemplate:
    """Return a copy of COLUMN_TEMPLATE (leaves the module-level singleton untouched)."""
    return FamilyTemplate(
        name=COLUMN_TEMPLATE.name,
        category=COLUMN_TEMPLATE.category,
        parameters=list(COLUMN_TEMPLATE.parameters),
        geometry_type=COLUMN_TEMPLATE.geometry_type,
        description=COLUMN_TEMPLATE.description,
    )


# ---------------------------------------------------------------------------
# 1. Valid template — no errors
# ---------------------------------------------------------------------------

def test_valid_template_returns_no_errors():
    errors = validate_family_template(COLUMN_TEMPLATE)
    assert errors == [], f"unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# 2. Cyclic dependency — must be detected
# ---------------------------------------------------------------------------

def test_cyclic_dependency_detected():
    """A ↔ B mutual cycle must surface as a validation error."""
    tmpl = FamilyTemplate(
        name="CycleTest",
        category="Generic",
        parameters=[
            TemplateParameter(name="A", kind="float", default=1.0, expression="B * 2"),
            TemplateParameter(name="B", kind="float", default=1.0, expression="A * 2"),
        ],
    )
    errors = validate_family_template(tmpl)
    assert any("cycle" in e.lower() for e in errors), (
        f"Expected a cycle error, got: {errors}"
    )


# ---------------------------------------------------------------------------
# 3. Expression references an undeclared parameter name
# ---------------------------------------------------------------------------

def test_expression_references_missing_param():
    tmpl = FamilyTemplate(
        name="MissingRef",
        category="Generic",
        parameters=[
            TemplateParameter(
                name="X",
                kind="float",
                default=1.0,
                expression="undefined_param * 2",
            ),
        ],
    )
    errors = validate_family_template(tmpl)
    assert any("undefined_param" in e for e in errors), (
        f"Expected missing-param error, got: {errors}"
    )


# ---------------------------------------------------------------------------
# 4. Invalid expression syntax
# ---------------------------------------------------------------------------

def test_invalid_expression_syntax():
    tmpl = FamilyTemplate(
        name="BadSyntax",
        category="Generic",
        parameters=[
            TemplateParameter(
                name="X",
                kind="float",
                default=1.0,
                expression="2 +* 3",  # malformed
            ),
        ],
    )
    errors = validate_family_template(tmpl)
    assert errors, "expected a syntax error to be reported"


# ---------------------------------------------------------------------------
# 5. Duplicate parameter names
# ---------------------------------------------------------------------------

def test_duplicate_parameter_names():
    tmpl = FamilyTemplate(
        name="DupTest",
        category="Generic",
        parameters=[
            TemplateParameter(name="width", kind="length", default=0.5),
            TemplateParameter(name="width", kind="length", default=1.0),
        ],
    )
    errors = validate_family_template(tmpl)
    assert any("duplicate" in e.lower() for e in errors), (
        f"Expected duplicate-name error, got: {errors}"
    )


# ---------------------------------------------------------------------------
# 6. Empty template name
# ---------------------------------------------------------------------------

def test_empty_template_name():
    tmpl = FamilyTemplate(name="", category="Column")
    errors = validate_family_template(tmpl)
    assert any("name" in e.lower() for e in errors), (
        f"Expected name error, got: {errors}"
    )


# ---------------------------------------------------------------------------
# 7. Analytic volume oracle — default parameters
# ---------------------------------------------------------------------------

def test_column_default_volume():
    """Volume = π·D²·H / 4 with D=0.3, H=3.0."""
    body = generate_body(COLUMN_TEMPLATE)
    D, H = 0.3, 3.0
    expected = math.pi * D * D * H / 4.0
    assert math.isclose(body["volume"], expected, rel_tol=1e-9), (
        f"volume mismatch: got {body['volume']}, expected {expected}"
    )


# ---------------------------------------------------------------------------
# 8. D doubles → volume quadruples (π·D²·H/4 proportionality)
# ---------------------------------------------------------------------------

def test_doubling_D_quadruples_volume():
    """When D doubles, volume = π·(2D)²·H/4 = 4 · π·D²·H/4."""
    D0, H = 0.3, 3.0
    body_base = generate_body(COLUMN_TEMPLATE, {"D": D0, "H": H})
    body_2x = generate_body(COLUMN_TEMPLATE, {"D": D0 * 2, "H": H})

    ratio = body_2x["volume"] / body_base["volume"]
    assert math.isclose(ratio, 4.0, rel_tol=1e-9), (
        f"Expected volume ratio 4.0 when D doubles; got {ratio}"
    )


# ---------------------------------------------------------------------------
# 9. Expression (formula) parameters evaluated correctly
# ---------------------------------------------------------------------------

def test_expression_parameter_evaluated():
    """A derived parameter 'area' = π·D²/4 should equal body volume / H."""
    tmpl = FamilyTemplate(
        name="ExpressionColumn",
        category="Column",
        parameters=[
            TemplateParameter(name="D", kind="length", default=0.4, min_val=0.05),
            TemplateParameter(name="H", kind="length", default=4.0, min_val=0.5),
            TemplateParameter(
                name="area",
                kind="float",
                default=0.0,
                expression="pi * D * D / 4",
                description="Cross-sectional area (m²)",
            ),
        ],
        geometry_type="circular_column",
    )
    errors = validate_family_template(tmpl)
    assert errors == [], f"template has errors: {errors}"

    body = generate_body(tmpl)
    D, H = 0.4, 4.0
    expected_area = math.pi * D * D / 4.0
    resolved_area = body["params"]["area"]
    assert math.isclose(resolved_area, expected_area, rel_tol=1e-9), (
        f"area mismatch: got {resolved_area}, expected {expected_area}"
    )
    # Volume should still match π·D²·H/4
    expected_vol = expected_area * H
    assert math.isclose(body["volume"], expected_vol, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 10. generate_body raises ValueError for invalid template
# ---------------------------------------------------------------------------

def test_generate_body_raises_on_invalid_template():
    tmpl = FamilyTemplate(name="", category="Column")
    with pytest.raises(ValueError, match="invalid"):
        generate_body(tmpl)


# ---------------------------------------------------------------------------
# Bonus: varying H scales volume linearly
# ---------------------------------------------------------------------------

def test_height_scales_volume_linearly():
    body_base = generate_body(COLUMN_TEMPLATE, {"D": 0.3, "H": 3.0})
    body_2h = generate_body(COLUMN_TEMPLATE, {"D": 0.3, "H": 6.0})
    ratio = body_2h["volume"] / body_base["volume"]
    assert math.isclose(ratio, 2.0, rel_tol=1e-9), (
        f"Expected linear scaling; got ratio {ratio}"
    )
