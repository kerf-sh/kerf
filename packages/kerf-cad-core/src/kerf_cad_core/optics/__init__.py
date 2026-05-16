"""
kerf_cad_core.optics — geometric optics & lens design.

Public API (re-exported for convenience):

    from kerf_cad_core.optics import (
        lensmaker,
        thin_lens_imaging,
        mirror_imaging,
        two_lens_system,
        abcd_system,
        fnumber,
        numerical_aperture,
        depth_of_field,
        hyperfocal_distance,
        airy_spot_radius,
        snell,
        critical_angle,
        brewster_angle,
        prism_deviation,
        chromatic_aberration,
        achromat_powers,
    )

References
----------
Hecht, E. — "Optics", 5th ed. (2017)
Smith, W.J. — "Modern Optical Engineering", 4th ed. (2008)
Born & Wolf — "Principles of Optics", 7th ed. (1999)

Author: imranparuk
"""

from kerf_cad_core.optics.lens import (
    lensmaker,
    thin_lens_imaging,
    mirror_imaging,
    two_lens_system,
    abcd_free_space,
    abcd_refraction,
    abcd_thin_lens,
    abcd_thick_lens,
    abcd_mirror,
    abcd_system,
    fnumber,
    numerical_aperture,
    depth_of_field,
    hyperfocal_distance,
    airy_spot_radius,
    snell,
    critical_angle,
    brewster_angle,
    prism_deviation,
    chromatic_aberration,
    achromat_powers,
)

__all__ = [
    "lensmaker",
    "thin_lens_imaging",
    "mirror_imaging",
    "two_lens_system",
    "abcd_free_space",
    "abcd_refraction",
    "abcd_thin_lens",
    "abcd_thick_lens",
    "abcd_mirror",
    "abcd_system",
    "fnumber",
    "numerical_aperture",
    "depth_of_field",
    "hyperfocal_distance",
    "airy_spot_radius",
    "snell",
    "critical_angle",
    "brewster_angle",
    "prism_deviation",
    "chromatic_aberration",
    "achromat_powers",
]
