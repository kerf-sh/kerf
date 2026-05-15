"""The contract every authored generator module must satisfy.

An authored generator is a single committed MIT Python module under
``kerf_partsgen/generators/`` that exposes exactly two module-level names:

    FAMILY : dict
        Static metadata about the part family.  Keys:
          family_id   str   slug, must match the markdown row + filename stem
          name        str   human label ("ISO 4762 socket-head cap screw")
          standard    str   the referenced standard ("ISO 4762")
          domain      str   wishlist domain ("mechanical")
          category    str   library category path ("mechanical/fastener")
          units       str   always "mm"

    SIZES : list[dict]
        The family's *authoritative tabulated dimension table* — one dict per
        catalogued size, transcribed once from the standard by the LLM author
        and frozen in the committed diff.  Every row MUST carry a unique
        ``size`` key plus an ``expect`` sub-dict the verification gate checks
        the built solid's measured bbox/volume against:

          expect.bbox_mm   [x, y, z]   nominal overall bounding box (mm)
          expect.volume_mm3 float|null approx solid volume (null = skip vol)

    def build(row: dict): -> kerf_partsgen.kernel.GeneratedPart
        Pure function.  Given one SIZES row, compose kerf_partsgen.kernel
        ops and return the solid.  No I/O, no network, no globals.

That is the ENTIRE surface ``enumerate`` depends on, so the human PR diff
(table + build()) is a complete, self-contained correctness audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SizeRow:
    size: str
    params: dict[str, Any]
    expect_bbox_mm: tuple[float, float, float] | None
    expect_volume_mm3: float | None


@dataclass
class GeneratorModule:
    family_id: str
    name: str
    standard: str
    domain: str
    category: str
    sizes: list[dict]
    build: Callable[[dict], Any]
    source_path: str = ""


@dataclass
class VariantResult:
    family_id: str
    size: str
    status: str  # "PASS" | "FAIL"
    reasons: list[str] = field(default_factory=list)
    measured_bbox_mm: tuple[float, float, float] | None = None
    measured_volume_mm3: float | None = None
    artifact_dir: str = ""


@dataclass
class FamilyResult:
    family_id: str
    name: str
    standard: str
    variants: list[VariantResult] = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> int:
        return sum(1 for v in self.variants if v.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for v in self.variants if v.status == "FAIL")
