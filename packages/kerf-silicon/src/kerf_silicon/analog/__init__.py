"""kerf_silicon.analog — open analog-cell library for SKY130.

Families shipped in v1
----------------------
- opamp_2stage   : two-stage Miller-compensated PMOS-input op-amp
- comparator_strongarm : strong-arm latched comparator (clocked)
- bandgap_brokaw : Brokaw bandgap voltage reference

Entry point
-----------
    from kerf_silicon.analog.library import instantiate, list_families
"""
from kerf_silicon.analog.library import instantiate, list_families

__all__ = ["instantiate", "list_families"]
