"""
kerf_cad_core.sysml1d — acausal 1D lumped-parameter system simulation.

Supports electrical, thermal, hydraulic, and 1D mechanical domains via the
effort/flow analogy.  Assembles an index-1 DAE via generalised
modified-nodal analysis (MNA) and integrates with implicit trapezoidal
(Crank–Nicolson) + Newton–Raphson for nonlinear elements.

Public API
----------
    from kerf_cad_core.sysml1d import Network, simulate, steady_state

The LLM tool entry-point (registered via ``@register``) lives in
``kerf_cad_core.sysml1d.network``.
"""

from kerf_cad_core.sysml1d.network import Network, simulate, steady_state

__all__ = ["Network", "simulate", "steady_state"]
