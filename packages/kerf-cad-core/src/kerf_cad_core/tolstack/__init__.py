"""
kerf_cad_core.tolstack — 1D dimensional tolerance stack-up analysis.

Implements worst-case (arithmetic), RSS (root-sum-square),
modified-RSS / Benderized, and Monte-Carlo stack-up methods.

Public API (re-exported for convenience):

    from kerf_cad_core.tolstack import analyze_stack

References
----------
Dimensioning and Tolerancing Handbook, McGraw-Hill (Drake, 1999)
Mechanical Tolerancing, Giesecke/Mitchell/Spencer, §§ 3-5
Bender, A. "Statistical Tolerancing as it Relates to Quality Control
  and the Designer" — SAE Technical Paper 680490, 1968.

Author: imranparuk
"""

from kerf_cad_core.tolstack.stack import analyze_stack

__all__ = ["analyze_stack"]
