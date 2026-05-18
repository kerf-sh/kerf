// Regression: the Hero shot is invoked from the top-bar Export dropdown,
// NOT a floating viewport button.
//
// User ask: "also move hero button, it should be in export dropdown
// rather". @testing-library/react is not installed in this project (see
// freecadImport.test.jsx), and the dropdown content is gated behind
// internal open-state, so this pins the wiring contract at the source
// level — same approach as the Python source-contract regressions.

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, it, expect } from 'vitest'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(root, p), 'utf8')

describe('Hero capture lives in the Export dropdown', () => {
  const exportBtn = read('components/ExportButton.jsx')
  const renderer = read('components/Renderer.jsx')
  const editor = read('routes/Editor.jsx')

  it('ExportButton accepts an onCaptureHero prop', () => {
    expect(exportBtn).toMatch(/function ExportButton\(\{\s*onCaptureHero\s*\}\)/)
  })

  it('ExportButton has a hero capture handler that downloads a kerf-hero PNG', () => {
    expect(exportBtn).toContain('async function doCaptureHero()')
    expect(exportBtn).toMatch(/downloadBlob\(blob, `kerf-hero-\$\{Date\.now\(\)\}\.png`\)/)
  })

  it('the hero menu item only renders when onCaptureHero is provided', () => {
    expect(exportBtn).toMatch(/onCaptureHero && \(/)
    expect(exportBtn).toContain('Capture hero image')
  })

  it('Editor wires onCaptureHero to the renderer ref imperative API', () => {
    expect(editor).toContain(
      '<ExportButton onCaptureHero={() => rendererRef.current?.captureHeroShot?.({})} />',
    )
  })

  it('Renderer no longer renders a standalone floating Hero button', () => {
    expect(renderer).not.toContain("{heroBusy ? 'Rendering…' : 'Hero'}")
  })

  it('Renderer still exposes captureHeroShot via its imperative handle', () => {
    expect(renderer).toMatch(/captureHeroShot:\s*\(opts\s*=\s*\{\}\)\s*=>\s*doCaptureHeroShot\(opts\)/)
  })
})
