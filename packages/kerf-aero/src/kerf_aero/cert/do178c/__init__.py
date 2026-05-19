"""DO-178C (Software Considerations in Airborne Systems and Equipment
Certification) artefact template generator.

Exports
-------
generate_template(doc_type, project_meta) -> str
    Return a Markdown skeleton for the specified DO-178C document type with
    ``[FILL IN]`` placeholders and *project_meta* values substituted.

Supported doc_type values
--------------------------
``"PSAC"``  Plan for Software Aspects of Certification
``"SDP"``   Software Development Plan
``"SVP"``   Software Verification Plan
``"SCMP"``  Software Configuration Management Plan
``"SQAP"``  Software Quality Assurance Plan
``"HLR"``   High-Level Requirements document
``"LLR"``   Low-Level Requirements document
``"SDD"``   Software Design Description
``"SVCP"``  Software Verification Cases and Procedures
"""

from kerf_aero.cert.do178c.templates import generate_template, SUPPORTED_DOC_TYPES

__all__ = ["generate_template", "SUPPORTED_DOC_TYPES"]
