// Parses `ROADMAP.md` at the repo root into:
//   - public/ROADMAP.md            — flat copy for the Roadmap page renderer
//   - public/roadmap-manifest.json — structured "Latest delta" items for Landing
//
// The Roadmap page fetches the .md and renders it with react-markdown.
// The Landing "Recently shipped" tile grid uses the manifest's latestDelta.items.
//
// Source of truth: ROADMAP.md (single file). Edit there; both surfaces update.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const ROOT = process.cwd()
const ROADMAP_PATH = join(ROOT, 'ROADMAP.md')
const PUBLIC_DIR = join(ROOT, 'public')

if (!existsSync(ROADMAP_PATH)) {
  console.warn(`build-roadmap-manifest: ROADMAP.md not found at ${ROADMAP_PATH} — skipping`)
  process.exit(0)
}

const md = readFileSync(ROADMAP_PATH, 'utf8')

mkdirSync(PUBLIC_DIR, { recursive: true })
writeFileSync(join(PUBLIC_DIR, 'ROADMAP.md'), md)

// ---------------------------------------------------------------------------
// Parse "### Latest delta (YYYY-MM-DD)" sections.
//
// We extract the MOST RECENT (= first listed) delta block. Inside it we look
// for `**Title** ✅ — body…` paragraphs and turn them into card entries.
// Domain is inferred from the first capitalised word of the title fallback.
// ---------------------------------------------------------------------------

// Accept both `### Latest delta (YYYY-MM-DD)` and `### Latest delta — YYYY-MM-DD`.
const DELTA_HEADER = /^###\s+Latest delta[\s(—-]+(\d{4}-\d{2}-\d{2})\)?\s*$/m

function findLatestDelta(text) {
  const lines = text.split(/\r?\n/)
  let startIdx = -1
  let date = null
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^###\s+Latest delta[\s(—-]+(\d{4}-\d{2}-\d{2})\)?\s*$/)
    if (m) { startIdx = i; date = m[1]; break }
  }
  if (startIdx < 0) return { date: null, body: '', items: [] }

  // Body runs until the next `### ` (any other H3) or `## ` (H2).
  let endIdx = lines.length
  for (let i = startIdx + 1; i < lines.length; i++) {
    if (/^##\s/.test(lines[i]) || /^###\s/.test(lines[i])) {
      endIdx = i
      break
    }
  }
  const body = lines.slice(startIdx + 1, endIdx).join('\n')

  // Find `**Title** ✅ — body` entries. Title may span up to the em-dash.
  // The body for each item runs from the dash to the next blank-line + `**`
  // boundary, OR to the next list bullet, OR to the next double-newline.
  const items = []
  const itemRe = /\*\*([^*]+)\*\*\s+✅\s+—\s+([\s\S]*?)(?=\n\n\*\*|\n\n###|\n\n##|$)/g
  let match
  while ((match = itemRe.exec(body)) !== null) {
    const title = match[1].trim()
    let bodyText = match[2].trim()
    // Collapse internal newlines (the source has many wrapped lines per item).
    bodyText = bodyText.replace(/\s+/g, ' ').trim()
    // Trim trailing closing punctuation noise.
    bodyText = bodyText.replace(/[;,.\s]+$/, '')
    items.push({
      title,
      body: bodyText,
      domain: inferDomain(title, bodyText),
    })
  }

  return { date, body, items }
}

function inferDomain(title, body) {
  const text = `${title} ${body}`.toLowerCase()
  if (/silicon|gds|yosys|liberty|sky130|asic|verilog|vhdl|pdk/.test(text)) return 'Silicon'
  if (/firmware|gcc|avr|esp32|stm32|rp2040|platformio|openocd/.test(text)) return 'Firmware'
  if (/aero|airfoil|vlm|flutter|orbital|lambert|propulsion|6-dof|adcs/.test(text)) return 'Aerospace'
  if (/marine|seakeeping|holtrop|naval/.test(text)) return 'Marine'
  if (/eurocode|aisc|aci|asce|ndsmitc4|frame|seismic|rsa|liquefaction|fatigue|p-delta/.test(text)) return 'Structural'
  if (/gear|bearing|iso 6336|iso\/ts 16281|planetary|fastener|vdi 2230|shaft|spring/.test(text)) return 'Machine'
  if (/iapws|steam|refrigerant|hvac|bell-delaware|psychrometric|hardy-cross|cltd|rts|moc|waterhammer/.test(text)) return 'Thermofluid'
  if (/ibis|signal integrity|emc|pdn|impedance|protection|arc-flash|load-flow|photonic/.test(text)) return 'Electronics'
  if (/cam|hsm|adaptive|trochoidal|tool life|moldflow|casting|nfp|nesting|sheet metal|slicing|gerber|odb/.test(text)) return 'Manufacturing'
  if (/civil|alignment|corridor|geotech|superelevation/.test(text)) return 'Civil'
  if (/controls|state-space|lqr|kalman|mbd|6-dof ik|frf|robotics/.test(text)) return 'Dynamics'
  if (/plc|iec 61131|ladder|structured text|harness|wiring|solar|pv/.test(text)) return 'Electrical'
  if (/gd&t|tolerance|spc|cpk|cmm|gauge r&r/.test(text)) return 'Tolerancing'
  if (/optics|gaussian|paraxial|abcd|acoustics|sea|helmholtz|fibre/.test(text)) return 'Optics'
  if (/jewelry|gem|setting|crown|dental|aligner|escapement|horology|mainspring|textile|drape|knit/.test(text)) return 'Verticals'
  if (/cost|should-cost|material selection|ashby|lca|iso 14040|granta/.test(text)) return 'Cost'
  if (/bim|ifc|revit|wall|slab|stair|family|schedule/.test(text)) return 'Architecture'
  if (/compare|landing|persona|illustration|seo|hero|matrix/.test(text)) return 'Frontend'
  if (/sketcher|b-rep|occt|nurbs|loft|fillet|chamfer|hole|sheet metal|drawing|sketch/.test(text)) return 'Mechanical'
  if (/sdk|scripting|api|json-rpc|python|rust|go|lua/.test(text)) return 'Scripting'
  if (/auth|fly|tigris|paystack|billing|cloud|workshop|git|s3|storer/.test(text)) return 'Platform'
  return 'Platform'
}

const { date, body, items } = findLatestDelta(md)

const payload = {
  version: 1,
  generatedAt: new Date().toISOString(),
  source: 'ROADMAP.md',
  latestDelta: {
    date,
    itemCount: items.length,
    items,
  },
}

writeFileSync(join(PUBLIC_DIR, 'roadmap-manifest.json'), JSON.stringify(payload, null, 2))

console.log(
  `roadmap-manifest: copied ROADMAP.md (${md.length} bytes) + ${items.length} delta items (${date}) to public/`,
)
