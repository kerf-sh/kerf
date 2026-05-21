/**
 * editor-responsive-layout.test.js — T-L1: Responsive Editor layout
 *
 * Verifies the narrow-viewport responsive shell in Editor.jsx:
 *   - File-tree toggle button is present and hidden at ≥ lg (lg:hidden)
 *   - Inline left aside is hidden < lg (hidden lg:flex)
 *   - Off-canvas tree drawer is rendered conditionally (treeDrawerOpen state)
 *   - Off-canvas chat drawer is rendered conditionally (chatDrawerOpen state)
 *   - Toggle buttons have correct aria-expanded / aria-controls / aria-label
 *   - Drawers have role="dialog" + aria-modal="true" + aria-label
 *   - Drawers have close buttons with aria-label
 *   - Focus-trap / focus-return refs exist (treeOpenerRef / chatOpenerRef)
 *   - Pointer-event split handles have touch-none + touchAction: none
 *   - Body scroll lock effect exists for open drawer
 *   - Esc key handler closes drawers (capture-phase keydown)
 *   - kerf-editor-grid CSS class used on grid wrapper
 *   - CSS breakpoint at 1024px sets 240px 1fr columns
 *
 * Source-level checks following the project's established pattern.
 * No jsdom or heavy mocking required.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const EDITOR_SRC = readFileSync(resolve(__dirname, '../Editor.jsx'), 'utf8')
const INDEX_CSS = readFileSync(resolve(__dirname, '../../index.css'), 'utf8')

// ---------------------------------------------------------------------------
// File-tree toggle — narrow-viewport opener
// ---------------------------------------------------------------------------

describe('Editor.jsx — file-tree toggle button', () => {
  it('toggle button is only visible on < lg (lg:hidden class)', () => {
    expect(EDITOR_SRC).toContain('lg:hidden')
  })

  it('toggle button has aria-label="Open file tree"', () => {
    expect(EDITOR_SRC).toContain('aria-label="Open file tree"')
  })

  it('toggle button has aria-expanded bound to treeDrawerOpen', () => {
    expect(EDITOR_SRC).toContain('aria-expanded={treeDrawerOpen}')
  })

  it('toggle button has aria-controls="editor-tree-drawer"', () => {
    expect(EDITOR_SRC).toContain('aria-controls="editor-tree-drawer"')
  })

  it('toggle button has a ref (treeOpenerRef) for focus return on close', () => {
    expect(EDITOR_SRC).toContain('ref={treeOpenerRef}')
  })
})

// ---------------------------------------------------------------------------
// Inline left aside — hidden on mobile, visible on desktop
// ---------------------------------------------------------------------------

describe('Editor.jsx — inline left aside visibility', () => {
  it('inline aside is hidden < lg (hidden lg:flex)', () => {
    expect(EDITOR_SRC).toContain('hidden lg:flex')
  })

  it('inline aside has id="editor-left"', () => {
    expect(EDITOR_SRC).toContain('id="editor-left"')
  })
})

// ---------------------------------------------------------------------------
// Off-canvas tree drawer — structure, a11y, id
// ---------------------------------------------------------------------------

describe('Editor.jsx — off-canvas tree drawer', () => {
  it('drawer outer wrapper has lg:hidden so it is unreachable on desktop', () => {
    // The outermost presentation wrapper carries lg:hidden
    const drawerSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{treeDrawerOpen && ('),
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(drawerSection).toContain('lg:hidden')
  })

  it('drawer panel has id="editor-tree-drawer" (links aria-controls)', () => {
    expect(EDITOR_SRC).toContain('id="editor-tree-drawer"')
  })

  it('drawer panel has role="dialog"', () => {
    // Ensure it's specifically on the tree drawer, not just anywhere
    const treeSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{treeDrawerOpen && ('),
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(treeSection).toContain('role="dialog"')
  })

  it('drawer panel has aria-modal="true"', () => {
    const treeSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{treeDrawerOpen && ('),
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(treeSection).toContain('aria-modal="true"')
  })

  it('drawer panel has aria-label for screen readers', () => {
    expect(EDITOR_SRC).toContain('aria-label="File tree and objects"')
  })

  it('drawer has a close button with aria-label="Close file tree drawer"', () => {
    expect(EDITOR_SRC).toContain('aria-label="Close file tree drawer"')
  })

  it('backdrop div has aria-hidden="true" (decorative)', () => {
    const treeSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{treeDrawerOpen && ('),
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(treeSection).toContain('aria-hidden="true"')
  })
})

// ---------------------------------------------------------------------------
// Off-canvas chat drawer — structure, a11y
// ---------------------------------------------------------------------------

describe('Editor.jsx — off-canvas chat drawer', () => {
  it('drawer outer wrapper has lg:hidden so it is unreachable on desktop', () => {
    const chatSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(chatSection).toContain('lg:hidden')
  })

  it('drawer panel has role="dialog"', () => {
    const chatSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(chatSection).toContain('role="dialog"')
  })

  it('drawer panel has aria-modal="true"', () => {
    const chatSection = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('{chatDrawerOpen && ('),
    )
    expect(chatSection).toContain('aria-modal="true"')
  })

  it('drawer panel has aria-label="Chat"', () => {
    expect(EDITOR_SRC).toContain('aria-label="Chat"')
  })

  it('drawer has a close button with aria-label="Close chat drawer"', () => {
    expect(EDITOR_SRC).toContain('aria-label="Close chat drawer"')
  })

  it('chat opener ref exists for focus return on close', () => {
    expect(EDITOR_SRC).toContain('ref={chatOpenerRef}')
  })
})

// ---------------------------------------------------------------------------
// Keyboard: Esc closes drawers
// ---------------------------------------------------------------------------

describe('Editor.jsx — Esc key closes drawers', () => {
  it('Esc handler is registered as a capture-phase listener', () => {
    expect(EDITOR_SRC).toContain("e.key !== 'Escape'")
    // Capture phase: true as third addEventListener argument
    expect(EDITOR_SRC).toContain("window.addEventListener('keydown', onEsc, true)")
  })

  it('Esc handler calls setTreeDrawerOpen(false)', () => {
    expect(EDITOR_SRC).toContain('setTreeDrawerOpen(false)')
  })

  it('Esc handler calls setChatDrawerOpen(false)', () => {
    expect(EDITOR_SRC).toContain('setChatDrawerOpen(false)')
  })
})

// ---------------------------------------------------------------------------
// Body scroll lock while a drawer is open
// ---------------------------------------------------------------------------

describe('Editor.jsx — body scroll lock', () => {
  it('sets document.body.style.overflow = "hidden" when a drawer is open', () => {
    expect(EDITOR_SRC).toContain("document.body.style.overflow = 'hidden'")
  })

  it('restores overflow on cleanup', () => {
    // Cleanup restores previous value (via closure variable `prev`)
    expect(EDITOR_SRC).toContain('document.body.style.overflow = prev')
  })
})

// ---------------------------------------------------------------------------
// Focus management
// ---------------------------------------------------------------------------

describe('Editor.jsx — focus management', () => {
  it('treeOpenerRef receives focus when tree drawer closes', () => {
    expect(EDITOR_SRC).toContain('treeOpenerRef.current?.focus?.()')
  })

  it('chatOpenerRef receives focus when chat drawer closes', () => {
    expect(EDITOR_SRC).toContain('chatOpenerRef.current?.focus?.()')
  })

  it('tree drawer traps Tab focus with a keydown handler on the root', () => {
    // The trap function in the treeDrawerOpen effect captures Tab
    const trapBlock = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('if (!treeDrawerOpen) return'),
      EDITOR_SRC.indexOf('}, [treeDrawerOpen])'),
    )
    expect(trapBlock).toContain("e.key !== 'Tab'")
  })

  it('chat drawer traps Tab focus with a keydown handler on the root', () => {
    const trapBlock = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('if (!chatDrawerOpen) return'),
      EDITOR_SRC.indexOf('}, [chatDrawerOpen])'),
    )
    expect(trapBlock).toContain("e.key !== 'Tab'")
  })
})

// ---------------------------------------------------------------------------
// Touch-friendly drag handles (pointer events)
// ---------------------------------------------------------------------------

describe('Editor.jsx — touch drag handles', () => {
  it('split handles use onPointerDown (works with touch)', () => {
    expect(EDITOR_SRC).toContain('onPointerDown={onSplitPointerDown}')
  })

  it('split handles use onPointerMove', () => {
    expect(EDITOR_SRC).toContain('onPointerMove={onSplitPointerMove}')
  })

  it('split handles use onPointerCancel for robust cleanup', () => {
    expect(EDITOR_SRC).toContain('onPointerCancel={onSplitPointerUp}')
  })

  it('split handles have touch-none Tailwind class', () => {
    expect(EDITOR_SRC).toContain('touch-none')
  })

  it('split handles have inline touchAction: none for iOS Safari', () => {
    expect(EDITOR_SRC).toContain("touchAction: 'none'")
  })

  it('pointer capture is set on drag start for reliable tracking', () => {
    expect(EDITOR_SRC).toContain('setPointerCapture(e.pointerId)')
  })

  it('pointer capture is released on drag end', () => {
    expect(EDITOR_SRC).toContain('releasePointerCapture(e.pointerId)')
  })
})

// ---------------------------------------------------------------------------
// Grid wrapper
// ---------------------------------------------------------------------------

describe('Editor.jsx — responsive grid wrapper', () => {
  it('grid wrapper uses kerf-editor-grid class for CSS breakpoint columns', () => {
    expect(EDITOR_SRC).toContain('kerf-editor-grid')
  })

  it('grid wrapper defaults to grid-cols-1 on mobile', () => {
    expect(EDITOR_SRC).toContain('grid-cols-1')
  })
})

// ---------------------------------------------------------------------------
// CSS — breakpoint definition
// ---------------------------------------------------------------------------

describe('index.css — kerf-editor-grid breakpoint', () => {
  it('defines .kerf-editor-grid at min-width 1024px (lg breakpoint)', () => {
    expect(INDEX_CSS).toContain('@media (min-width: 1024px)')
    expect(INDEX_CSS).toContain('.kerf-editor-grid')
  })

  it('sets 240px 1fr columns at ≥ lg', () => {
    expect(INDEX_CSS).toContain('grid-template-columns: 240px 1fr')
  })
})

// ---------------------------------------------------------------------------
// Route-change drawer auto-close
// ---------------------------------------------------------------------------

describe('Editor.jsx — route-change auto-close', () => {
  it('auto-closes tree drawer when project or file changes', () => {
    // useEffect with setTreeDrawerOpen(false) depends on projectId + currentFileId
    const autoCloseBlock = EDITOR_SRC.slice(
      EDITOR_SRC.indexOf('// Route-change auto-close'),
      EDITOR_SRC.indexOf('// Esc closes drawers'),
    )
    expect(autoCloseBlock).toContain('setTreeDrawerOpen(false)')
    expect(autoCloseBlock).toContain('setChatDrawerOpen(false)')
  })
})
