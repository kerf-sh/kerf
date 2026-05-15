"""kerf-partsgen — token-frugal parametric standard-parts library generator.

Two phases:

* ``author``    — the ONLY token spend. An LLM writes a *parametric generator*
                  for a part FAMILY (committed, reviewable MIT Python). One
                  author call + at most two bounded repair calls per family.
* ``enumerate`` — ZERO tokens, deterministic. Loops each authored generator's
                  size table, builds geometry by composing Kerf's OCCT kernel
                  facade (:mod:`kerf_partsgen.kernel`), runs the verification
                  gate, and emits artifacts into the gitignored ``.parts-out/``.

Re-running ``enumerate`` / ``seed`` costs zero tokens. See README.md.
"""

__version__ = "0.1.0"

from kerf_partsgen.kernel import (  # noqa: F401
    GeneratedPart,
    KERNEL_BACKEND,
    KernelUnavailable,
    box,
    cylinder,
    hex_prism,
    sketch_circle,
    sketch_polygon,
    sketch_regular_polygon,
)
from kerf_partsgen.spec import (  # noqa: F401
    FamilyResult,
    GeneratorModule,
    SizeRow,
    VariantResult,
)

__all__ = [
    "__version__",
    "GeneratedPart",
    "KERNEL_BACKEND",
    "KernelUnavailable",
    "box",
    "cylinder",
    "hex_prism",
    "sketch_circle",
    "sketch_polygon",
    "sketch_regular_polygon",
    "FamilyResult",
    "GeneratorModule",
    "SizeRow",
    "VariantResult",
]
