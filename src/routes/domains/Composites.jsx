/**
 * Composites.jsx — Aerospace Composites domain page (kerf-composites, T-173).
 */
import DomainPage from './DomainPage.jsx'
import * as meta from './composites.meta.js'
import { ViewportScaleIllustration, FemIllustration } from '../../components/illustrations/index.js'

export const HERO_ILLUSTRATION = ViewportScaleIllustration
export const CAPABILITY_ILLUSTRATIONS = [
  { Illustration: FemIllustration, caption: 'Interlaminar stress distribution from CLT + FEniCSx on a curved CFRP panel.' },
]

const BULLETS = [
  {
    title: 'Ply stacks to laminate analysis',
    body: 'Define angle, thickness, and material per ply. The CLT solver computes the full ABD stiffness matrix, engineering constants, and thermally-induced curvature — in one chat turn.',
  },
  {
    title: 'Drape over any OCCT surface',
    body: 'Geodesic drape simulation predicts shear angles and wrinkling on doubly-curved surfaces. Export DXF flat patterns with dart placement direct to your cutting table.',
  },
  {
    title: 'Chat-driven, open-source',
    body: 'Every composites module is MIT licensed and ships in the same binary as the rest of Kerf. Describe a layup in plain language; the feature tree records every ply op.',
  },
]

const COMPARISON = {
  products: ['Fibersim', 'Laminate Tools', 'CoAT', 'Kerf'],
  rows: [
    {
      feature: 'CLT / ABD solver',
      note: null,
      values: [true, true, true, true],
    },
    {
      feature: 'Drape simulation',
      note: 'Geodesic drape over OCCT surfaces',
      values: [true, true, null, true],
    },
    {
      feature: 'Cure cycle planning',
      note: null,
      values: [true, null, true, true],
    },
    {
      feature: 'Failure criteria (Tsai-Wu / Hashin)',
      note: null,
      values: [true, true, true, true],
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
      values: ['$$$', '$$$', '$$$', 'Free'],
    },
  ],
}

export default function Composites() {
  return (
    <DomainPage
      meta={meta}
      slug="composites"
      accentColor="kerf-300"
      domainName="composites"
      heroIllustration={HERO_ILLUSTRATION}
      capabilityIllustrations={CAPABILITY_ILLUSTRATIONS}
      heroHeadline={
        <>
          Aerospace composites that
          <br />
          <span className="relative inline-block">
            <span className="relative z-10 text-kerf-300">analyse themselves</span>
            <span
              aria-hidden
              className="absolute left-0 right-0 -bottom-2 h-2.5 bg-kerf-300/15 -skew-x-12 rounded-sm"
            />
          </span>{' '}
          as you design.
        </>
      }
      heroParagraph="Kerf combines ply layup design, CLT laminate analysis, drape simulation, cure cycle planning, and failure criteria into one chat-driven workspace. Describe a carbon-fibre panel and watch the ply stack, ABD matrix, and flat patterns build alongside each other."
      heroTags={['MIT licensed', 'Tsai-Wu / Hashin criteria', 'DXF flat patterns', 'STEP export']}
      bullets={BULLETS}
      comparison={COMPARISON}
      compareLinks={[{ slug: 'fibersim', label: 'Siemens Fibersim' }]}
    />
  )
}
