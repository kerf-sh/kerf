/**
 * Barrel export for the illustrations library.
 *
 * Named exports for each sector illustration + the router wrapper.
 * `SECTOR_ILLUSTRATIONS` provides the canonical list used by Landing/Domains pages.
 */

export { default as SectorIllustration } from './SectorIllustration.jsx'

export { default as MechanicalIllustration } from './mechanical.jsx'
export { default as ElectronicsIllustration } from './electronics.jsx'
export { default as ArchitectureIllustration } from './architecture.jsx'
export { default as JewelryIllustration } from './jewelry.jsx'
export { default as AutomotiveIllustration } from './automotive.jsx'
export { default as AerospaceIllustration } from './aerospace.jsx'
export { default as SiliconIllustration } from './silicon.jsx'
export { default as FirmwareIllustration } from './firmware.jsx'
export { default as PLCIllustration } from './plc.jsx'
export { default as CompositesIllustration } from './composites.jsx'
export { default as DentalIllustration } from './dental.jsx'
export { default as OpticsIllustration } from './optics.jsx'
export { default as HorologyIllustration } from './horology.jsx'
export { default as MarineIllustration } from './marine.jsx'
export { default as WoodworkingIllustration } from './woodworking.jsx'
export { default as TextilesIllustration } from './textiles.jsx'
export { default as CivilIllustration } from './civil.jsx'

/**
 * Canonical array of sector metadata with illustration keys.
 * Used by Landing and Domains pages to render the sector grid.
 */
export const SECTOR_ILLUSTRATIONS = [
  { key: 'mechanical',   label: 'Mechanical',     description: 'Parametric solids, assemblies & GD&T' },
  { key: 'electronics',  label: 'Electronics',    description: 'Schematics, PCB layout & simulation' },
  { key: 'architecture', label: 'Architecture',   description: 'BIM, IFC import & technical drawings' },
  { key: 'jewelry',      label: 'Jewelry',        description: 'Gemstone faceting, ring design & cost' },
  { key: 'automotive',   label: 'Automotive',     description: 'Class-A surfaces, zebra & curvature' },
  { key: 'aerospace',    label: 'Aerospace',      description: 'Airfoil design, CFD prep & weight' },
  { key: 'silicon',      label: 'Silicon',        description: 'IC floorplan, standard cells & PDK' },
  { key: 'firmware',     label: 'Firmware',       description: 'MCU board layout, flash & debug' },
  { key: 'plc',          label: 'PLC & Automation', description: 'Ladder logic, function blocks & HMI' },
  { key: 'composites',   label: 'Composites',     description: 'Ply stack-up, draping & fibre paths' },
  { key: 'dental',       label: 'Dental',         description: 'Crown design, implant placement & CBCT' },
  { key: 'optics',       label: 'Optics',         description: 'Lens design, ray tracing & tolerancing' },
  { key: 'horology',     label: 'Horology',       description: 'Escapement, gear trains & tolerances' },
  { key: 'marine',       label: 'Marine',         description: 'Hull form, hydrostatics & stability' },
  { key: 'woodworking',  label: 'Woodworking',    description: 'Joinery, patterns & cut sheets' },
  { key: 'textiles',     label: 'Textiles',       description: 'Weave patterns, grading & DXF export' },
  { key: 'civil',        label: 'Civil',          description: 'Bridge design, truss analysis & survey' },
]
