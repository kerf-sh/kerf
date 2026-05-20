"""
kerf_textiles
=============
Textile weave + knit pattern generators and cloth drape simulation for Kerf.

Supported structures
--------------------
Weave: plain, twill (N/M, RH/LH), satin, jacquard-from-draft
Knit:  jersey, rib, interlock, custom stitch notation
Drape: mass-spring cloth solver, BS 5058 drape coefficient

Quick start::

    from kerf_textiles.weave import plain_weave, twill_weave, satin_weave
    from kerf_textiles.knit import jersey_knit, rib_knit, interlock_knit
    from kerf_textiles.draft import canonical_twill_draft, draft_to_dict, draft_from_dict
    from kerf_textiles.export import weave_to_svg, draft_to_wif, draft_from_wif
    from kerf_textiles.drape import drape_simulate, drape_on_disc

    pw = plain_weave()
    tw = twill_weave(over=2, under=1, direction="RH")
    sat = satin_weave(shafts=5, move=2)

    jk = jersey_knit(needles=20, courses=20, gauge=5.0, courses_per_cm=7.0)
    assert jk.density_stats["density_within_1pct"]

    d = canonical_twill_draft(over=2, under=1)
    d.validate()
    wif = draft_to_wif(d)
    d2 = draft_from_wif(wif)
    assert d2.threading == d.threading

    result = drape_simulate(rows=20, cols=20, spacing=0.05, pin_indices=[(0,0),(0,19)])
    print(result.max_sag)  # metres

    dc = drape_on_disc(cloth_radius=0.14, disc_radius=0.07)
    print(dc.drape_coefficient)  # 0.30–0.95
"""

__version__ = "0.1.0"

from kerf_textiles.weave import (
    plain_weave,
    twill_weave,
    satin_weave,
    jacquard_from_draft,
    WeaveResult,
)
from kerf_textiles.knit import (
    jersey_knit,
    rib_knit,
    interlock_knit,
    custom_knit,
    KnitResult,
)
from kerf_textiles.draft import (
    Draft,
    draft_to_dict,
    draft_from_dict,
    canonical_plain_draft,
    canonical_twill_draft,
    canonical_satin_draft,
)
from kerf_textiles.export import (
    weave_to_svg,
    knit_to_svg,
    draft_to_wif,
    draft_from_wif,
    matrix_to_csv,
    weave_to_json,
    knit_to_json,
)
from kerf_textiles.drape import (
    drape_simulate,
    drape_on_disc,
    catenary_max_sag,
    DrapeResult,
)
from kerf_textiles.mass_spring import (
    ClothMesh,
    Spring,
    SpherePrimitive,
    PlanePrimitive,
    solve_step,
)
from kerf_textiles.sublimation import (
    unwrap_cylinder,
    project_artwork,
    add_bleed,
    add_registration_marks,
    render_panel_png,
    CylinderPanel,
    BleedResult,
    RegMarkResult,
    SubliResult,
)
from kerf_textiles.screen_print import (
    separate_spot_colours,
    render_separations,
    render_separations_pdf,
    SpotColour,
    SeparationResult,
    PrintReadySeparation,
    ScreenPrintResult,
)
from kerf_textiles.etextiles import (
    ResistiveYarn,
    HeaterSegment,
    heating_calc,
    ThreadRoute,
    thread_route,
    LEDNode,
    LEDBranch,
    LEDLayout,
    led_layout,
    YARN_SHIELDEX_117,
    YARN_BEKINOX_50,
    LED_FLORA_NEOPIXEL,
    LED_FLORA_RGB,
)
from kerf_textiles.materials import (
    TextileMaterial,
    CATALOGUE,
    CATEGORIES,
    by_id,
    by_category,
    by_subcategory,
    with_certification,
    biodegradable_materials,
)
from kerf_textiles.sustainability import (
    GarmentImpact,
    MaterialContribution,
    score_garment,
    compare_garments,
)

__all__ = [
    # weave
    "plain_weave",
    "twill_weave",
    "satin_weave",
    "jacquard_from_draft",
    "WeaveResult",
    # knit
    "jersey_knit",
    "rib_knit",
    "interlock_knit",
    "custom_knit",
    "KnitResult",
    # draft
    "Draft",
    "draft_to_dict",
    "draft_from_dict",
    "canonical_plain_draft",
    "canonical_twill_draft",
    "canonical_satin_draft",
    # export
    "weave_to_svg",
    "knit_to_svg",
    "draft_to_wif",
    "draft_from_wif",
    "matrix_to_csv",
    "weave_to_json",
    "knit_to_json",
    # drape
    "drape_simulate",
    "drape_on_disc",
    "catenary_max_sag",
    "DrapeResult",
    # mass-spring
    "ClothMesh",
    "Spring",
    "SpherePrimitive",
    "PlanePrimitive",
    "solve_step",
    # sublimation
    "unwrap_cylinder",
    "project_artwork",
    "add_bleed",
    "add_registration_marks",
    "render_panel_png",
    "CylinderPanel",
    "BleedResult",
    "RegMarkResult",
    "SubliResult",
    # screen_print
    "separate_spot_colours",
    "render_separations",
    "render_separations_pdf",
    "SpotColour",
    "SeparationResult",
    "PrintReadySeparation",
    "ScreenPrintResult",
    # etextiles
    "ResistiveYarn",
    "HeaterSegment",
    "heating_calc",
    "ThreadRoute",
    "thread_route",
    "LEDNode",
    "LEDBranch",
    "LEDLayout",
    "led_layout",
    "YARN_SHIELDEX_117",
    "YARN_BEKINOX_50",
    "LED_FLORA_NEOPIXEL",
    "LED_FLORA_RGB",
    # materials
    "TextileMaterial",
    "CATALOGUE",
    "CATEGORIES",
    "by_id",
    "by_category",
    "by_subcategory",
    "with_certification",
    "biodegradable_materials",
    # sustainability
    "GarmentImpact",
    "MaterialContribution",
    "score_garment",
    "compare_garments",
]
