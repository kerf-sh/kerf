"""
kerf_cad_core.composites — Classical Lamination Theory (CLT) for composite laminates.

Public API (re-exported for convenience):

    from kerf_cad_core.composites import (
        reduced_stiffness,
        transform_Q,
        abd_matrix,
        laminate_response,
        failure_indices,
        laminate_engineering_moduli,
        first_ply_failure_load,
    )

References
----------
Jones, R.M. "Mechanics of Composite Materials", 2nd ed. (1999)
Gibson, R.F. "Principles of Composite Material Mechanics", 4th ed. (2016)
Reddy, J.N. "Mechanics of Laminated Composite Plates and Shells", 2nd ed. (2004)

Author: imranparuk
"""

from kerf_cad_core.composites.laminate import (
    reduced_stiffness,
    transform_Q,
    abd_matrix,
    laminate_response,
    failure_indices,
    laminate_engineering_moduli,
    first_ply_failure_load,
)

__all__ = [
    "reduced_stiffness",
    "transform_Q",
    "abd_matrix",
    "laminate_response",
    "failure_indices",
    "laminate_engineering_moduli",
    "first_ply_failure_load",
]
