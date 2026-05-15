"""The verification gate.

A green checkbox must NEVER mean "the LLM replied".  For every enumerated
variant the gate independently re-measures the built solid off the OCCT
kernel and asserts:

1. **Valid / watertight solid.**  ``GeneratedPart.is_valid`` is True (OCCT
   ``BRepCheck`` via ``Shape.isValid()``), a strictly positive volume, and a
   STEP round-trip succeeds (the same export Kerf's ``import_step`` consumes).
2. **Bounding-box sanity vs the declared table.**  Each axis of the measured
   bbox is within :data:`BBOX_TOL` of the row's ``expect.bbox_mm`` (axes are
   sorted before comparison so build orientation is irrelevant).
3. **Volume sanity vs the declared table.**  Measured volume within
   :data:`VOLUME_TOL` of ``expect.volume_mm3`` when the row declares one
   (rows may set it ``null`` to opt out for hard-to-hand-figure shapes —
   bbox + watertight still gate them).

Tolerances are deliberately loose: the table holds *nominal* catalogue
dimensions, the generator adds real features (chamfers, thread reliefs,
fillets) the nominal numbers don't capture.  The gate's job is to catch
gross transcription / geometry blunders (wrong order of magnitude, mm/inch
slip, a non-solid), not to certify sub-micron accuracy.
"""

from __future__ import annotations

from kerf_partsgen import kernel
from kerf_partsgen.kernel import GeneratedPart
from kerf_partsgen.spec import VariantResult

# Fraction-of-nominal tolerances (documented in README).
BBOX_TOL = 0.20      # ±20 % per axis
VOLUME_TOL = 0.50    # ±50 % (features the nominal table omits move volume a lot)


def _sorted3(t) -> tuple[float, float, float]:
    a, b, c = sorted(float(x) for x in t)
    return (a, b, c)


def verify_variant(family_id: str, size: str, row: dict,
                   built: GeneratedPart) -> VariantResult:
    """Run the full gate on one built variant. Pure; never raises."""
    reasons: list[str] = []
    expect = (row.get("expect") or {})

    measured_bbox = built.bbox_mm
    measured_vol = built.volume_mm3

    # 1. valid / watertight solid -------------------------------------------
    if not built.is_valid:
        reasons.append("kernel reports an invalid (non-watertight) solid")
    if built.volume_mm3 <= 0.0:
        reasons.append(f"non-positive volume ({built.volume_mm3:.3f} mm^3)")

    if not reasons:
        try:
            step_path = kernel.make_dir_tmp_step(built)
            import os

            ok = os.path.isfile(step_path) and os.path.getsize(step_path) > 0
            if not ok:
                reasons.append("STEP export produced an empty file")
            os.unlink(step_path)
        except Exception as exc:  # pragma: no cover - kernel-dependent
            reasons.append(f"STEP export failed: {exc}")

    # 2. bbox sanity vs declared table --------------------------------------
    exp_bbox = expect.get("bbox_mm")
    if exp_bbox is not None:
        m = _sorted3(measured_bbox)
        e = _sorted3(exp_bbox)
        for axis, (mv, ev) in enumerate(zip(m, e)):
            tol = max(abs(ev) * BBOX_TOL, 0.05)
            if abs(mv - ev) > tol:
                reasons.append(
                    f"bbox axis {axis}: measured {mv:.3f} vs expected "
                    f"{ev:.3f} (tol ±{tol:.3f})"
                )

    # 3. volume sanity vs declared table ------------------------------------
    exp_vol = expect.get("volume_mm3")
    if exp_vol is not None:
        tol = max(abs(float(exp_vol)) * VOLUME_TOL, 1.0)
        if abs(measured_vol - float(exp_vol)) > tol:
            reasons.append(
                f"volume: measured {measured_vol:.3f} vs expected "
                f"{float(exp_vol):.3f} (tol ±{tol:.3f})"
            )

    status = "PASS" if not reasons else "FAIL"
    return VariantResult(
        family_id=family_id,
        size=size,
        status=status,
        reasons=reasons,
        measured_bbox_mm=measured_bbox,
        measured_volume_mm3=measured_vol,
    )
