/**
 * Mold.jsx — Mold / Injection domain page (kerf-mold, T-165).
 */
import DomainPage from './DomainPage.jsx'
import * as meta from './mold.meta.js'
import { WorkshopIllustration, CamIllustration } from '../../components/illustrations/index.js'

export const HERO_ILLUSTRATION = WorkshopIllustration
export const CAPABILITY_ILLUSTRATIONS = [
  { Illustration: CamIllustration, caption: 'CAM toolpaths for core and cavity machining from the mold base.' },
]

const BULLETS = [
  {
    title: 'Core/cavity split with undercut analysis',
    body: 'Automatic parting surface generation from OCCT B-rep. Undercut regions highlighted before split so tooling decisions are made with full visibility.',
  },
  {
    title: 'Fill simulation from the feature tree',
    body: 'Gate and runner geometry feeds directly into the finite-difference fill solver. Weld-line, air-trap, and shrinkage maps update whenever you change gate location or wall thickness.',
  },
  {
    title: 'Chat-driven, open-source',
    body: 'MIT licensed. Describe a PP housing with four side-pulls and Kerf designs the mold base, locates the gates, routes the cooling channels, and quotes the cycle time — in one session.',
  },
]

const COMPARISON = {
  products: ['Moldflow', 'SOLIDWORKS Plastics', 'Creo Mold', 'Kerf'],
  rows: [
    {
      feature: 'Core / cavity split',
      note: null,
      values: [null, true, true, true],
    },
    {
      feature: 'Fill & pack simulation',
      note: null,
      values: [true, true, null, true],
    },
    {
      feature: 'Cooling channel analysis',
      note: null,
      values: [true, null, null, true],
    },
    {
      feature: 'Mold base from catalogue',
      note: 'DME / Hasco / Meusburger',
      values: [null, true, true, true],
    },
    {
      feature: 'Open-source',
      note: null,
      values: [false, false, false, true],
    },
    {
      feature: 'Chat-driven design',
      note: 'Kerf-exclusive',
      values: [false, false, false, true],
    },
    {
      feature: 'Price (starting)',
      note: null,
      values: ['$$$$', '$$$', '$$$', 'Free'],
    },
  ],
}

export default function Mold() {
  return (
    <DomainPage
      meta={meta}
      slug="mold"
      accentColor="kerf-300"
      domainName="mold"
      heroIllustration={HERO_ILLUSTRATION}
      capabilityIllustrations={CAPABILITY_ILLUSTRATIONS}
      heroHeadline={
        <>
          Injection mold design from
          <br />
          <span className="relative inline-block">
            <span className="relative z-10 text-kerf-300">split to simulation</span>
            <span
              aria-hidden
              className="absolute left-0 right-0 -bottom-2 h-2.5 bg-kerf-300/15 -skew-x-12 rounded-sm"
            />
          </span>
          .
        </>
      }
      heroParagraph="Kerf combines core/cavity split, mold base design, gate and runner layout, cooling channel routing, and fill simulation into one chat-driven workspace. The same OCCT kernel that powers the mechanical vertical drives every parting surface."
      heroTags={['MIT licensed', 'DME / Hasco / Meusburger catalogues', 'ASME B16 fittings', 'STEP export']}
      bullets={BULLETS}
      comparison={COMPARISON}
      compareLinks={[{ slug: 'cimatron', label: 'Cimatron' }]}
    />
  )
}
