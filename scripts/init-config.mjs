// Copies kerf.example.toml → kerf.toml on first run so `npm run dev` works
// without manual setup. Idempotent: refuses to overwrite an existing file.

import { existsSync, copyFileSync } from 'node:fs'

const target = 'kerf.toml'
const source = 'kerf.example.toml'

if (existsSync(target)) {
  process.exit(0)
}
if (!existsSync(source)) {
  console.error(`init-config: ${source} not found; cannot bootstrap ${target}`)
  process.exit(1)
}
copyFileSync(source, target)
console.log(`init-config: wrote ${target} from ${source}. Edit it to set DB URL, LLM keys, etc.`)
