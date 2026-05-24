/**
 * Marine.jsx — Marine / Naval Architecture domain page (T-172).
 */
import DomainPage from './DomainPage.jsx'
import * as meta from './marine.meta.js'
import { ScriptingIllustration, PipelineIllustration } from '../../components/illustrations/index.js'

export const HERO_ILLUSTRATION = ScriptingIllustration
export const CAPABILITY_ILLUSTRATIONS = [
  { Illustration: PipelineIllustration, caption: 'Resistance curve from Holtrop-Mennen feeding propeller selection and shaft sizing.' },
]

const BULLETS = [
  {
    title: 'Hull-form design with hydrostatics',
    body: 'Model a hull as NURBS surfaces and Kerf computes displacement, GM, GZ curve, and freeboard at any waterline — with IMO A.749 stability criteria checked automatically.',
  },
  {
    title: 'Resistance prediction to propeller selection',
    body: 'Holtrop-Mennen or Savitsky method gives resistance; Ka-series charts select a matching propeller. Power budget and shaft sizing follow in the same session.',
  },
  {
    title: 'Chat-driven, open-source',
    body: 'MIT licensed. Describe a 12-metre aluminium dayboat and Kerf generates the hull lines, checks stability, computes resistance, and lays out the general arrangement — one conversation.',
  },
]

const COMPARISON = {
  products: ['Maxsurf', 'Rhino + Orca3D', 'ShipConstructor', 'Kerf'],
  rows: [
    {
      feature: 'Hull-form design',
      note: null,
      values: [true, true, null, true],
    },
    {
      feature: 'Hydrostatics & stability',
      note: null,
      values: [true, true, null, true],
    },
    {
      feature: 'Resistance & powering',
      note: null,
      values: [true, null, null, true],
    },
    {
      feature: 'Structural scantlings',
      note: null,
      values: [null, null, true, true],
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
      values: ['$$$', '$$', '$$$', 'Free'],
    },
  ],
}

export default function Marine() {
  return (
    <DomainPage
      meta={meta}
      slug="marine"
      accentColor="cyan-edge"
      domainName="marine"
      heroIllustration={HERO_ILLUSTRATION}
      capabilityIllustrations={CAPABILITY_ILLUSTRATIONS}
      heroHeadline={
        <>
          Naval architecture from
          <br />
          <span className="relative inline-block">
            <span className="relative z-10 text-cyan-edge">hull form to stability</span>
            <span
              aria-hidden
              className="absolute left-0 right-0 -bottom-2 h-2.5 bg-cyan-edge/10 -skew-x-12 rounded-sm"
            />
          </span>
          .
        </>
      }
      heroParagraph="Kerf combines parametric hull-form design, hydrostatics, resistance prediction, structural scantlings, and outfit routing into one chat-driven workspace for naval architects and marine engineers."
      heroTags={['MIT licensed', 'IMO A.749 stability', 'Holtrop-Mennen / Savitsky', 'STEP / IGES export']}
      bullets={BULLETS}
      comparison={COMPARISON}
      compareLinks={[{ slug: 'maxsurf', label: 'Bentley Maxsurf' }]}
    />
  )
}
