/**
 * sectorTourData.js
 *
 * Static data driving the SectorTour onboarding page.
 * Each entry describes one Kerf domain sector with:
 *   - title          — short sector name
 *   - blurb          — ~30-word plain-English description
 *   - llm_example_prompt — a single LLM prompt the user could type in Kerf
 *   - cta_route      — React Router path to send the user to
 *   - eyebrow_color  — Tailwind text-color class for the sector badge
 */

/** @type {Array<{title:string, blurb:string, llm_example_prompt:string, cta_route:string, eyebrow_color:string}>} */
export const SECTORS = [
  {
    title: 'Mechanical',
    blurb:
      'Sketch profiles, apply parametric features, and export production-ready STEP assemblies. Full constraint solver, fillets, shell, draft, and drawing views built in.',
    llm_example_prompt:
      'Create a 60 mm aluminium bracket with 4×M5 mounting holes, 2 mm fillets, and a 3° draft angle, then export to STEP.',
    cta_route: '/domains/mechanical',
    eyebrow_color: 'text-cyan-400',
  },
  {
    title: 'Electronics',
    blurb:
      'Author schematics and PCB layouts in tscircuit JSX, then export to KiCad projects or atopile netlists — all inside a single Kerf file.',
    llm_example_prompt:
      'Design a 2-layer PCB for an STM32F401 with USB-C power, decoupling caps, and a 2.54 mm debug header, export KiCad.',
    cta_route: '/domains/electronics',
    eyebrow_color: 'text-green-400',
  },
  {
    title: 'Architecture',
    blurb:
      'Model BIM walls, slabs, and roofs with correct host relationships. Generate IFC exports, section drawings, and room schedules automatically.',
    llm_example_prompt:
      'Model a 150 m² open-plan office floor with 100 mm concrete slab, curtain-wall facade, and a flat roof, output IFC.',
    cta_route: '/domains/architecture',
    eyebrow_color: 'text-amber-400',
  },
  {
    title: 'Jewelry',
    blurb:
      'Parametric gem cuts, prong and pavé settings, composite metal bodies, and wax-ready STL output. Works with rings, pendants, bangles, and chains.',
    llm_example_prompt:
      'Design an 18k rose-gold solitaire ring with a 1 ct round brilliant diamond, claw setting, and comfort-fit band — export STL.',
    cta_route: '/domains/jewelry',
    eyebrow_color: 'text-pink-400',
  },
  {
    title: 'Automotive',
    blurb:
      'Loft and sweep complex body panels with continuity controls, generate class-A surface networks, and validate curvature combs for production tooling.',
    llm_example_prompt:
      'Loft a Class-A hood surface from front grille to windscreen header with G2 continuity at both edges and export STEP.',
    cta_route: '/domains',
    eyebrow_color: 'text-red-400',
  },
  {
    title: 'Aerospace',
    blurb:
      'Run vortex-lattice aerodynamic analysis, design orbital trajectories, and model rocket propulsion geometry — all text-first with LLM-driven iteration.',
    llm_example_prompt:
      'Size a two-stage sounding rocket to reach 100 km apogee with 5 kg payload; run VLM on the fin geometry and plot Cn vs alpha.',
    cta_route: '/domains',
    eyebrow_color: 'text-violet-400',
  },
  {
    title: 'Silicon',
    blurb:
      'Write synthesisable VHDL or Verilog, run place-and-route on the SKY130 PDK, and emit GDS-II layout ready for open-source tapeout.',
    llm_example_prompt:
      'Implement a 4-bit synchronous counter in VHDL, synthesise for SKY130, run DRC/LVS, and export GDS-II.',
    cta_route: '/domains',
    eyebrow_color: 'text-indigo-400',
  },
  {
    title: 'Firmware',
    blurb:
      'Write Arduino-compatible sketches or ESP-IDF components, configure build targets, flash over serial, and iterate on embedded logic inside Kerf.',
    llm_example_prompt:
      'Write an ESP32 FreeRTOS task that reads a BME280 over I²C every 500 ms and publishes JSON to MQTT — include CMakeLists.',
    cta_route: '/domains',
    eyebrow_color: 'text-teal-400',
  },
  {
    title: 'Industrial Controls',
    blurb:
      'Author IEC 61131-3 Ladder and Structured Text programs, simulate PLC scan cycles in-browser, and export to common runtime formats.',
    llm_example_prompt:
      'Write a Ladder Diagram conveyor-belt interlock: motor runs only when safety gate is closed and E-stop is not active.',
    cta_route: '/domains',
    eyebrow_color: 'text-orange-400',
  },
  {
    title: 'Composites',
    blurb:
      'Define ply stacks, fibre orientations, and layup sequences using the T-173 composite engine. Export laminate schedules and flat patterns for CNC cutting.',
    llm_example_prompt:
      'Design a [0/±45/90]s carbon-fibre laminate for a 500×300 mm aerospace panel; output ply schedule and flat patterns.',
    cta_route: '/domains',
    eyebrow_color: 'text-lime-400',
  },
  {
    title: 'Dental',
    blurb:
      'Parametric crown and bridge libraries, aligner thermoform geometry, and scan-to-model workflows — all exportable to open dental CAM formats.',
    llm_example_prompt:
      'Generate a full-contour zirconia crown for tooth #14 with 0.5 mm margin chamfer and occlusal contacts at MIP — export STL.',
    cta_route: '/domains',
    eyebrow_color: 'text-sky-400',
  },
  {
    title: 'Optics',
    blurb:
      'Specify lens prescriptions, trace sequential ray paths, evaluate MTF and aberration maps, and export lens geometry to Zemax-compatible formats.',
    llm_example_prompt:
      'Design a 50 mm f/2.8 double-Gauss photographic lens, trace 589 nm rays, plot MTF to 100 lp/mm, export prescription.',
    cta_route: '/domains',
    eyebrow_color: 'text-yellow-400',
  },
  {
    title: 'Horology',
    blurb:
      'Model involute gear trains, Swiss lever escapements, and mainspring barrels. Simulate beat rate, power reserve, and print DXF cutouts for hand finishing.',
    llm_example_prompt:
      'Design a 3 Hz Swiss lever escapement for a 25 mm movement: calculate gear train, escapement geometry, and export DXF.',
    cta_route: '/domains',
    eyebrow_color: 'text-rose-400',
  },
  {
    title: 'Marine',
    blurb:
      'Compute displacement, metacentric height, and GZ stability curves from hull surfaces. Generate stability booklets and inclining-experiment reports.',
    llm_example_prompt:
      'Model a 10 m monohull sailboat hull, compute hydrostatics at 0°–60° heel, plot the GZ curve, and flag IMO compliance.',
    cta_route: '/domains',
    eyebrow_color: 'text-blue-400',
  },
]

export default SECTORS
