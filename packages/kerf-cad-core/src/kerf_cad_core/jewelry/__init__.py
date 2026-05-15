"""
kerf_cad_core.jewelry — jewelry-domain CAD tools for Kerf.

Submodules (loaded via the plugin's ``_TOOL_MODULES`` registry, not eagerly
imported here, so a missing optional dep in one area never breaks the others):

gemstones        — parametric gemstone solids (round brilliant, princess, oval,
                    emerald, marquise, pear, cushion); carat↔mm sizing.
gem_seat         — automated seat/bearing cutter + boolean subtraction from a host.
settings         — prong heads, bezel, channel, pavé stone settings.
ring             — ring-size system (US/UK/EU/JP) + shank profiles + shoulders.
metal_cost       — metal density table, weight-from-volume, casting cost.
tool_metal_cost  — @register LLM tool wrapper for metal_cost.
"""
