"""
kerf_cad_core.cam_wizard — stock-setup wizard for CNC milling/turning setups.

Public API::

    from kerf_cad_core.cam_wizard import (
        recommend_stock,
        recommend_orientation,
        fixture_suggestion,
        setup_sheet,
    )

All functions are pure Python, never raise, and return structured dicts.

Author: imranparuk
"""

from kerf_cad_core.cam_wizard.stock_setup import (
    recommend_stock,
    recommend_orientation,
    fixture_suggestion,
    setup_sheet,
)

__all__ = [
    "recommend_stock",
    "recommend_orientation",
    "fixture_suggestion",
    "setup_sheet",
]
