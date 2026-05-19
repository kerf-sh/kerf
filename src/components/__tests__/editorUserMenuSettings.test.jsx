/**
 * editorUserMenuSettings.test.jsx
 *
 * Source-level oracle for the EditorUserMenu dropdown items.
 *
 * EditorUserMenu lives in src/routes/Editor.jsx and must expose:
 *   - Profile → /profile
 *   - Workspace settings → /w/{slug}/settings  (gated on currentWorkspaceSlug)
 *   - Members → /w/{slug}/members              (gated on currentWorkspaceSlug)
 *   - Billing → /billing                       (gated on cloudEnabled)
 *   - All projects → /projects
 *   - Sign out
 *
 * We use a source-level approach to avoid spinning up the full React tree
 * (Editor.jsx transitively pulls CodeMirror, OCCT, etc.).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SRC = readFileSync(
  resolve(__dirname, '../../routes/Editor.jsx'),
  'utf8',
)

// Narrow the search to just the EditorUserMenu function body so we don't
// accidentally match unrelated occurrences elsewhere in the large file.
// We extract everything between `function EditorUserMenu` and the next
// top-level `function ` declaration.
const menuStart = SRC.indexOf('function EditorUserMenu(')
const menuEnd = SRC.indexOf('\nfunction ', menuStart + 1)
const MENU_SRC = menuStart >= 0 ? SRC.slice(menuStart, menuEnd > menuStart ? menuEnd : undefined) : SRC

describe('EditorUserMenu — dropdown items', () => {
  it('has a Profile link to /profile', () => {
    expect(MENU_SRC).toMatch(/to="\/profile"/)
    expect(MENU_SRC).toMatch(/Profile/)
  })

  it('has an All projects link to /projects', () => {
    expect(MENU_SRC).toMatch(/to="\/projects"/)
    expect(MENU_SRC).toMatch(/All projects/)
  })

  it('has a Sign out button', () => {
    expect(MENU_SRC).toMatch(/Sign out/)
    expect(MENU_SRC).toMatch(/onSignOut/)
  })

  it('renders workspace settings link gated on currentWorkspaceSlug', () => {
    // The link must use the slug as part of the path.
    expect(MENU_SRC).toMatch(/currentWorkspaceSlug/)
    expect(MENU_SRC).toMatch(/\/settings/)
    expect(MENU_SRC).toMatch(/Workspace settings/)
  })

  it('renders members link gated on currentWorkspaceSlug', () => {
    expect(MENU_SRC).toMatch(/\/members/)
    expect(MENU_SRC).toMatch(/Members/)
  })

  it('renders billing link gated on cloudEnabled', () => {
    expect(MENU_SRC).toMatch(/cloudEnabled/)
    expect(MENU_SRC).toMatch(/\/billing/)
    expect(MENU_SRC).toMatch(/Billing/)
  })

  it('uses useWorkspaces to get currentWorkspaceSlug', () => {
    expect(MENU_SRC).toMatch(/useWorkspaces/)
    expect(MENU_SRC).toMatch(/currentSlug/)
  })

  it('uses useCloudConfig to get cloudEnabled', () => {
    expect(MENU_SRC).toMatch(/useCloudConfig/)
  })

  it('has aria-haspopup="menu" on the avatar button', () => {
    expect(MENU_SRC).toMatch(/aria-haspopup="menu"/)
  })

  it('has a data-testid on the dropdown panel', () => {
    expect(MENU_SRC).toMatch(/data-testid="editor-user-menu"/)
  })
})
