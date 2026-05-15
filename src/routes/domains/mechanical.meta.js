/**
 * mechanical.meta.js — SEO metadata + JSON-LD for the Mechanical domain page.
 *
 * Exported constants are consumed by Mechanical.jsx for <head> injection
 * (via react-helmet or equivalent) and tested in mechanicalDomainPage.test.jsx.
 */

export const META_TITLE = 'Mechanical CAD with chat-driven design — Kerf'

export const META_DESCRIPTION =
  'Full parametric mechanical CAD in the browser. Feature tree, OCCT boolean/fillet/draft, ' +
  'sheet metal, drawings, 5-axis CAM, STEP/IFC import — chat-driven.'

export const META_OG_IMAGE = 'https://kerf.sh/og/mechanical.png'

export const META_URL = 'https://kerf.sh/domains/mechanical'

// Feature list — one entry per capability card. Used by JSON-LD ItemList and
// the capability grid section. Add new capabilities here; the grid renders
// whatever is in this array.
export const FEATURES = [
  {
    id: 'sketcher',
    name: 'Parametric 2D sketcher',
    description:
      'planegcs constraint solver. Parallel, perpendicular, tangent, equal, distance, angle constraints. Trim/extend/fillet 2D, mirror/pattern, ellipse, B-spline, multi-loop holes, external geometry. Live DOF feedback.',
  },
  {
    id: 'feature-tree',
    name: 'Feature tree',
    description:
      'Ordered history of B-rep operations: Pad, Pocket, Revolve, Fillet, Chamfer, Shell, Hole, Draft, Loft, Section. Scrub or reorder at any time. Built on OpenCascade (OCCT).',
  },
  {
    id: 'occt-booleans',
    name: 'OCCT boolean & dress-up operations',
    description:
      'Union, cut, intersection via OpenCascade. Fillet and chamfer with variable radius. Draft angles on faces. Shell. All operations are history-aware and parametric.',
  },
  {
    id: 'persistent-face-names',
    name: 'Persistent face names (Phase 4)',
    description:
      'Faces retain stable identifiers across feature regeneration. Downstream fillets, chamfers, and drawings reference named faces — no broken references when you edit an upstream feature.',
  },
  {
    id: 'loft-section',
    name: 'Loft, section & boss with draft',
    description:
      'feature_loft blends profile curves. feature_section cuts with a plane. feature_boss_with_draft extrudes with taper. feature_cut_from_sketch and feature_hole_pattern_from_sketch drive pockets and hole arrays from sketches.',
  },
  {
    id: 'sheet-metal',
    name: 'Sheet metal: flange, unfold, DXF',
    description:
      'Parametric flanges, bend relief, and corner notches. Automatic unbend/unfold to flat pattern. Export flat pattern as DXF for laser-cut or waterjet production.',
  },
  {
    id: 'drawings',
    name: 'Engineering drawings (TechDraw)',
    description:
      'Multi-sheet 2D drawings. Orthographic, section, and auxiliary views. Linear, aligned, radius, diameter, angular, baseline, chain, and ordinate dimensions. GD&T frames per ASME Y14.5.',
  },
  {
    id: 'cam-5axis',
    name: '5-axis CAM (3+2 indexed)',
    description:
      '3+2 indexed G-code generation. Tool-tilt strategies, work-coordinate rotation. Produces verifiable G-code for 5-axis VMCs without requiring a separate CAM package.',
  },
  {
    id: 'cam-3axis',
    name: '3-axis CAM + tool database',
    description:
      'Facing, pocketing, contouring, drilling cycles. Persistent tool DB with feeds, speeds, and tool geometry. Post-processors for common CNC controllers.',
  },
  {
    id: 'slicing',
    name: '3D-print G-code slicing (Tier 1)',
    description:
      'Integrated slicer for FFF/FDM printers. Layer, infill, support, and temperature settings. Exports .gcode directly — no round-trip to a separate slicer.',
  },
  {
    id: 'nurbs',
    name: 'NURBS surfacing: trim, G3 curvature combs',
    description:
      'Phase 4 NURBS surface editing. Trim-by-curve, G3 continuity blends with curvature comb visualisation. Suitable for consumer product surfacing and jewelry.',
  },
  {
    id: 'quad-remesh',
    name: 'Quad remesh',
    description:
      'Convert triangulated meshes to structured quad topology. Useful for downstream FEA, subdivision, and organic re-modelling workflows.',
  },
  {
    id: 'import',
    name: 'STEP / IFC / IGES / DXF / FreeCAD import',
    description:
      'Import industry-standard CAD formats. STEP and IGES for solid exchange, IFC for BIM/architecture. DXF for 2D profiles. FreeCAD .FCStd import (Tier 3) opens parametric parts from the FreeCAD ecosystem.',
  },
]

// JSON-LD structured data for the page. Injected as a <script type="application/ld+json">.
export const JSON_LD = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'WebPage',
      '@id': META_URL,
      url: META_URL,
      name: META_TITLE,
      description: META_DESCRIPTION,
      image: META_OG_IMAGE,
      publisher: {
        '@type': 'Organization',
        name: 'Kerf',
        url: 'https://kerf.sh',
      },
    },
    {
      '@type': 'ItemList',
      name: 'Kerf Mechanical CAD capabilities',
      description: 'Core mechanical CAD features in Kerf',
      numberOfItems: FEATURES.length,
      itemListElement: FEATURES.map((f, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: f.name,
        description: f.description,
      })),
    },
  ],
}
