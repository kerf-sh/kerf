"""kerf-aero certification artefact templates.

Provides template generators for DO-178C (airborne software) and DO-254
(airborne hardware / complex electronic hardware) certification packages.

Usage::

    from kerf_aero.cert.do178c.templates import generate_template as do178c_template
    from kerf_aero.cert.do254.templates import generate_template as do254_template
    from kerf_aero.cert.dal_classifier import classify_dal

    dal = classify_dal("catastrophic")          # -> "A"
    psac = do178c_template("PSAC", {"project_name": "AutopilotFW", "dal": dal})
    phac = do254_template("PHAC", {"project_name": "FPGACore", "dal": dal})
"""

from kerf_aero.cert.dal_classifier import classify_dal
from kerf_aero.cert.do178c.templates import generate_template as do178c_template
from kerf_aero.cert.do254.templates import generate_template as do254_template

__all__ = [
    "classify_dal",
    "do178c_template",
    "do254_template",
]
