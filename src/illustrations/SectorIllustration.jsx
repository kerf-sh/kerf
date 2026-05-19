/**
 * SectorIllustration — picks the correct per-sector SVG illustration by `sector` prop.
 *
 * Props:
 *   sector    {string}  — sector key (see SECTOR_ILLUSTRATIONS in index.js)
 *   className {string}  — forwarded to the SVG element
 *   size      {number}  — width/height in px (default 120)
 */

import MechanicalIllustration from './mechanical.jsx'
import ElectronicsIllustration from './electronics.jsx'
import ArchitectureIllustration from './architecture.jsx'
import JewelryIllustration from './jewelry.jsx'
import AutomotiveIllustration from './automotive.jsx'
import AerospaceIllustration from './aerospace.jsx'
import SiliconIllustration from './silicon.jsx'
import FirmwareIllustration from './firmware.jsx'
import PLCIllustration from './plc.jsx'
import CompositesIllustration from './composites.jsx'
import DentalIllustration from './dental.jsx'
import OpticsIllustration from './optics.jsx'
import HorologyIllustration from './horology.jsx'
import MarineIllustration from './marine.jsx'
import WoodworkingIllustration from './woodworking.jsx'
import TextilesIllustration from './textiles.jsx'
import CivilIllustration from './civil.jsx'

/** Map of sector key → component */
const SECTOR_MAP = {
  mechanical: MechanicalIllustration,
  electronics: ElectronicsIllustration,
  architecture: ArchitectureIllustration,
  jewelry: JewelryIllustration,
  automotive: AutomotiveIllustration,
  aerospace: AerospaceIllustration,
  silicon: SiliconIllustration,
  firmware: FirmwareIllustration,
  plc: PLCIllustration,
  composites: CompositesIllustration,
  dental: DentalIllustration,
  optics: OpticsIllustration,
  horology: HorologyIllustration,
  marine: MarineIllustration,
  woodworking: WoodworkingIllustration,
  textiles: TextilesIllustration,
  civil: CivilIllustration,
}

/**
 * Renders the illustration for the given sector, or a plain empty SVG placeholder
 * when no match is found.
 */
export default function SectorIllustration({ sector, className = '', size = 120 }) {
  const Component = SECTOR_MAP[sector]

  if (!Component) {
    // Graceful fallback — empty viewBox-preserved SVG
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 120 120"
        fill="none"
        className={className}
        aria-hidden="true"
        data-sector={sector}
        data-fallback="true"
      />
    )
  }

  return <Component className={className} size={size} data-sector={sector} />
}
