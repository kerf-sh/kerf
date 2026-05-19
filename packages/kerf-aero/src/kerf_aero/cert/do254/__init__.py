"""DO-254 (Design Assurance Guidance for Airborne Electronic Hardware)
artefact template generator.

Exports
-------
generate_template(doc_type, project_meta) -> str
    Return a Markdown skeleton for the specified DO-254 document type with
    ``[FILL IN]`` placeholders and *project_meta* values substituted.

Supported doc_type values
--------------------------
``"PHAC"``  Plan for Hardware Aspects of Certification
``"HDP"``   Hardware Development Plan
``"HVVP"``  Hardware Verification and Validation Plan
``"HPAP"``  Hardware Process Assurance Plan
"""

from kerf_aero.cert.do254.templates import generate_template, SUPPORTED_DOC_TYPES

__all__ = ["generate_template", "SUPPORTED_DOC_TYPES"]
