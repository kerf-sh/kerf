"""kerf_silicon.tinytapeout — Tiny Tapeout submission packager.

Public API
----------
package_for_tt(design_dir, info_dict) -> pathlib.Path
    Validate a user RTL directory and produce a ready-to-submit package.

ValidationError
    Raised for module-name, I/O signature, or tile-constraint failures.
"""

from .packager import package_for_tt
from .packager import ValidationError

__all__ = ["package_for_tt", "ValidationError"]
