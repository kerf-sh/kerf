"""
kerf_cad_core.tolstack — dimensional tolerance stack-up analysis.

1D: worst-case, RSS, modified-RSS, Monte-Carlo (stack.py)
3D: vector-loop 6-DOF worst-case, RSS, Monte-Carlo (tol3d.py)

Public API (re-exported for convenience):

    from kerf_cad_core.tolstack import analyze_stack, analyze_stack_3d

References
----------
Dimensioning and Tolerancing Handbook, McGraw-Hill (Drake, 1999)
Mechanical Tolerancing, Giesecke/Mitchell/Spencer, §§ 3-5
Bender, A. "Statistical Tolerancing as it Relates to Quality Control
  and the Designer" — SAE Technical Paper 680490, 1968.
Chase, K.W. & Parkinson, A.R. (1991). "A survey of research in the
  application of tolerance analysis to the design of mechanical
  assemblies." Research in Engineering Design, 3, 23-37.

Author: imranparuk
"""

from kerf_cad_core.tolstack.stack import analyze_stack
from kerf_cad_core.tolstack.tol3d import analyze_stack_3d

__all__ = ["analyze_stack", "analyze_stack_3d"]
