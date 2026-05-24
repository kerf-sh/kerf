/**
 * Piping.jsx — Piping / P&ID domain page (kerf-piping, T-167).
 */
import DomainPage from './DomainPage.jsx'
import * as meta from './piping.meta.js'
import { PipelineIllustration } from '../../components/illustrations/index.js'

export const HERO_ILLUSTRATION = PipelineIllustration

const BULLETS = [
  {
    title: 'P&ID to isometric in one workflow',
    body: 'Draw a P&ID with ISO 10628 symbols, then generate a 3D isometric model from the same project. Clash detection, line-list extraction, and spool drawings all link back to the same source of truth.',
  },
  {
    title: 'ASME B31.3 stress compliance',
    body: 'Sustained, occasional, and thermal expansion load cases evaluated per B31.3. Spring-hanger sizing, nozzle load checks, and a PDF compliance report — generated from the 3D route.',
  },
  {
    title: 'Chat-driven, open-source',
    body: 'MIT licensed. Describe a 4-inch carbon-steel steam header and Kerf routes it, selects ASME B16.5 flanges and fittings, and produces the line list — all in one session.',
  },
]

const COMPARISON = {
  products: ['CAESAR II', 'CADWorx', 'AutoCAD P&ID', 'Kerf'],
  rows: [
    {
      feature: 'P&ID symbol library',
      note: 'ISO 10628 / ISA 5.1',
      values: [null, true, true, true],
    },
    {
      feature: '3D isometric piping',
      note: null,
      values: [null, true, null, true],
    },
    {
      feature: 'Pipe stress (ASME B31.3)',
      note: null,
      values: [true, true, null, true],
    },
    {
      feature: 'Material take-off',
      note: null,
      values: [null, true, null, true],
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
      values: ['$$$', '$$$', '$$', 'Free'],
    },
  ],
}

export default function Piping() {
  return (
    <DomainPage
      meta={meta}
      slug="piping"
      accentColor="cyan-edge"
      domainName="piping"
      heroIllustration={HERO_ILLUSTRATION}
      heroHeadline={
        <>
          Piping & P&ID from
          <br />
          <span className="relative inline-block">
            <span className="relative z-10 text-cyan-edge">symbol to stress analysis</span>
            <span
              aria-hidden
              className="absolute left-0 right-0 -bottom-2 h-2.5 bg-cyan-edge/10 -skew-x-12 rounded-sm"
            />
          </span>
          .
        </>
      }
      heroParagraph="Kerf combines ISO 10628 P&ID authoring, 3D isometric routing, ASME B31.3 stress analysis, spec-driven component selection, and material take-off into one chat-driven workspace for process engineers."
      heroTags={['MIT licensed', 'ISO 10628 / ISA 5.1 symbols', 'ASME B31.3', 'DXF / STEP export']}
      bullets={BULLETS}
      comparison={COMPARISON}
      compareLinks={[{ slug: 'aveva-e3d', label: 'AVEVA E3D Design' }]}
    />
  )
}
