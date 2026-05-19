# Responsive Audit Report

Audit date: 2026-05-19  
Scope: `src/components/` — 89 `.jsx` files  
New utilities: `useBreakpoint`, `useViewportFit`, `ResponsiveContainer`, `MobileNavSheet`

---

## Summary

| Category | Count |
|---|---|
| Components audited | 25+ (representative sample, all high-traffic) |
| Components with existing responsive classes | 14 |
| Components with zero responsive handling | 11+ |
| High-priority retrofit candidates | 8 |
| Components already well-structured | 6 |

---

## Component-by-Component Findings

### 1. Layout.jsx
**Status: Partial — 3 breakpoint classes, mobile nav missing**

- Desktop nav is `hidden sm:inline` / `hidden md:flex` — items collapse on small screens.
- No mobile navigation drawer exists; the hamburger-style menu items simply vanish below `md`.
- **Recommendation:** Wire `MobileNavSheet` to replace the hidden nav items below `md`. Breakpoint detection via `useBreakpoint` can drive the open/close logic without additional media-query boilerplate.

---

### 2. Header.jsx
**Status: Partial — 5 breakpoint classes, mobile-nav handled inline**

- Desktop nav links: `hidden md:flex`, account area: `hidden md:flex`.
- A `md:hidden` mobile block exists but is a bare `<div>` with no accessible drawer semantics.
- **Recommendation:** Replace the bare mobile `<div>` with `MobileNavSheet` to gain slide-up animation, focus trap, aria-modal, Escape-to-close, and body-scroll lock for free.

---

### 3. Footer.jsx
**Status: Partial — 5 breakpoint classes, mostly correct**

- Uses `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` — appropriate CSS-grid responsive stacking.
- Bottom bar: `flex-col sm:flex-row` — good pattern already in use.
- **Recommendation:** No structural change needed. Could adopt `ResponsiveContainer` to replace the bottom-bar `flex-col sm:flex-row` pattern for consistency, but the pure CSS approach is valid here.

---

### 4. FeatureView.jsx
**Status: Partial — 10 breakpoint classes, most layout concerns handled**

- Uses `md:grid` + `md:hidden` to toggle between stacked-mobile and side-by-side-desktop inspector.
- The mobile inspector is an off-canvas overlay with manual `translate-y-full / translate-y-0` toggling (lines 2403–2410) — duplicates exactly what `MobileNavSheet` provides.
- **Recommendation (high priority):** Replace the hand-rolled off-canvas inspector panel with `MobileNavSheet` (or extract a shared `SlideUpPanel` that `MobileNavSheet` itself can extend). This removes ~30 lines of CSS duplication and adds the missing focus trap and `aria-modal`.

---

### 5. ChatPanel.jsx
**Status: Minimal — 1 breakpoint class**

- One `md:` class on a width constraint; the panel itself is always full-height.
- The panel has no min-width; on xs it can compress to unusable widths.
- **Recommendation:** Wrap the split layout that contains `ChatPanel` in `ResponsiveContainer stackedAt="md"` at the page level so the panel stacks below md rather than shrinking.

---

### 6. BOMPanel.jsx / BOMTable.jsx
**Status: No responsive classes**

- `BOMTable` uses a fixed-column `<table>` that overflows horizontally on small screens with no `overflow-x-auto` wrapper.
- `BOMPanel` contains the table inside a flex column with no width constraints.
- **Recommendation (high priority):** Add `overflow-x-auto` to the table container. On narrow screens the panel is not typically shown, but the lack of overflow handling causes layout breaking if it is rendered. `useViewportFit` could drive a "compact mode" that collapses less-important columns below a threshold.

---

### 7. ObjectsPanel.jsx
**Status: No responsive classes**

- Panel is a fixed-width sidebar; relies on the parent layout to show/hide it on mobile.
- `useBreakpoint` is not used; the panel has no awareness of its current breakpoint.
- **Recommendation:** Low priority on its own, but the parent layout (`FeatureView.jsx`) should control its visibility. The panel itself is fine as-is.

---

### 8. LayersPanel.jsx
**Status: No responsive classes**

- Same as ObjectsPanel — fixed-width sidebar, relies on parent to control visibility.
- **Recommendation:** No change needed at the component level. Parent-level `ResponsiveContainer` or `useBreakpoint` is the right integration point.

---

### 9. ShareModal.jsx
**Status: No responsive classes**

- Modal uses `fixed inset-0` backdrop + a centred panel.
- The panel has a fixed `max-w-md` — good for desktop but the panel itself has no `mx-4` margin on small screens, causing the panel to bleed to the viewport edges on very narrow phones.
- **Recommendation:** Add `mx-4 sm:mx-0` to the modal panel, or use `ResponsiveContainer` to apply a different layout inside the modal body at narrow widths.

---

### 10. ShortcutsModal.jsx
**Status: Minimal — 1 breakpoint class**

- One `sm:` width modifier; otherwise no responsive handling.
- Two-column shortcut layout collapses to a single column via CSS but the column widths are hardcoded.
- **Recommendation:** Low priority. Could use `ResponsiveContainer stackedAt="sm"` to drive column layout more explicitly.

---

### 11. RevisionDrawer.jsx
**Status: No responsive classes**

- Drawer uses a fixed right-side slide-in at `w-80`; at narrow viewports the drawer covers most of the screen without a backdrop.
- **Recommendation (medium priority):** Below `md` the drawer should use full-width `inset-x-0 bottom-0` (slide-up) rather than a right-side panel. `MobileNavSheet` or a shared `<SlidePanel direction>` variant would handle this. `useBreakpoint` can drive the direction prop.

---

### 12. WorkspaceSwitcher.jsx
**Status: No responsive classes**

- Dropdown is always a fixed-width popover anchored to the nav bar.
- At narrow widths the popover can overflow the right edge of the viewport.
- **Recommendation:** Add `right-0` anchor and `max-w-[calc(100vw-2rem)]` cap to prevent overflow.

---

### 13. Button.jsx
**Status: Partial — 3 breakpoint classes present via callers**

- The component itself has no responsive behaviour; callers pass responsive `className` overrides.
- Sizes `sm/md/lg` are fixed — no responsive size switching.
- **Recommendation:** Optionally add a `responsiveSize={{ base: 'sm', md: 'md' }}` prop pattern driven by `useBreakpoint`. Not urgent; the current design works.

---

### 14. Card.jsx
**Status: No responsive classes**

- Card has no width constraints; relies entirely on the grid/flex parent.
- **Recommendation:** No change needed at component level.

---

### 15. ActivityTimeline.jsx
**Status: No responsive classes**

- Timeline items are horizontally arranged with absolute-positioned connector lines.
- At narrow widths the connector lines overlap the text.
- **Recommendation (medium priority):** `useBreakpoint` can switch between the horizontal layout (md+) and a vertical stacked timeline (below md). `ResponsiveContainer` can drive the flex direction.

---

### 16. DrawingView.jsx
**Status: Minimal — 2 breakpoint classes**

- Canvas container uses `md:` classes for toolbar visibility.
- The main canvas itself is always full-size; `useViewportFit` is relevant here.
- **Recommendation:** Use `useViewportFit` in `DrawingView` to compute `scaleX/scaleY` for the canvas-to-screen transform instead of the current manual `getBoundingClientRect` calls (if any). This gives automatic ResizeObserver-based updates.

---

### 17. SketchView.jsx
**Status: Minimal — 2 breakpoint classes**

- Uses `sm:` for a toolbar item visibility toggle.
- The 3D canvas has no explicit viewport fit tracking.
- **Recommendation:** `useViewportFit` integration for the canvas container would provide reliable width/height without manual resize event listeners.

---

### 18. MaterialEditor.jsx
**Status: Minimal — 2 breakpoint classes**

- Side-by-side preview + form at large sizes; stacked at small.
- Already uses `md:flex-row` implicitly via Tailwind classes.
- **Recommendation:** Replace the manual `flex-col md:flex-row` pattern with `<ResponsiveContainer stackedAt="md">` for consistency and to pick up the `data-breakpoint` + `data-layout` attributes for automated testing.

---

### 19. LibraryEditor.jsx
**Status: Minimal — 2 breakpoint classes**

- Similar two-column pattern to MaterialEditor.
- **Recommendation:** Same — adopt `ResponsiveContainer`.

---

### 20. FileTree.jsx
**Status: Minimal — 2 breakpoint classes**

- File tree uses `sm:` for text truncation widths.
- No structural layout change needed.
- **Recommendation:** No change needed.

---

### 21. PCBView.jsx
**Status: Partial — 8 breakpoint classes, mostly handled**

- The PCB canvas + side panels already have comprehensive breakpoint handling.
- **Recommendation:** `useViewportFit` could replace the existing canvas resize logic; low priority since the current approach works.

---

### 22. HeroRenderPanel.jsx
**Status: Minimal — 2 breakpoint classes**

- Thumbnail grid uses `sm:grid-cols-2`.
- **Recommendation:** No change needed at this priority level.

---

### 23. JewelryCostPanel.jsx
**Status: Minimal — 2 breakpoint classes**

- Uses `sm:` for column layout switching.
- **Recommendation:** Could adopt `ResponsiveContainer` for consistency; low priority.

---

### 24. ToleranceView.jsx
**Status: Minimal — 2 breakpoint classes**

- Canvas + inspector layout.
- **Recommendation:** `useViewportFit` for the canvas container; low priority.

---

### 25. SimulationView.jsx / TopoView.jsx / CAMView.jsx
**Status: Minimal or no responsive classes**

- These are full-bleed canvas views; they fill available space and do not have multi-column layouts.
- **Recommendation:** `useViewportFit` is the relevant hook for these views. Connect to the canvas container to get reactive `width/height/scaleX/scaleY` without manual resize listeners.

---

## Priority Matrix

| Priority | Component(s) | Action |
|---|---|---|
| High | `FeatureView.jsx` | Replace off-canvas inspector with `MobileNavSheet`-derived panel |
| High | `Header.jsx` | Replace bare mobile `<div>` with `MobileNavSheet` |
| High | `BOMTable.jsx` | Add `overflow-x-auto` wrapper; `useViewportFit` for compact-column mode |
| Medium | `RevisionDrawer.jsx` | `useBreakpoint` to switch slide direction at `md` |
| Medium | `ActivityTimeline.jsx` | `ResponsiveContainer` + `useBreakpoint` for vertical/horizontal layout |
| Medium | `ShareModal.jsx` | Add `mx-4 sm:mx-0` edge margins |
| Low | `MaterialEditor`, `LibraryEditor` | Adopt `ResponsiveContainer` for `flex-col → flex-row` pattern |
| Low | Canvas views (Sketch, Drawing, Sim, Topo, CAM) | `useViewportFit` for reactive canvas dimensions |
| None needed | `ObjectsPanel`, `LayersPanel`, `Card`, `FileTree`, `PCBView` | Already correct or parent-driven |

---

## New Utilities — Integration Guide

### `useBreakpoint`
```js
import { useBreakpoint } from '../lib/useBreakpoint.js'
const bp = useBreakpoint() // null | 'sm' | 'md' | 'lg' | 'xl' | '2xl'
const isMobile = !bp || bp === 'sm'
```

### `useViewportFit`
```js
import { useViewportFit } from '../lib/useViewportFit.js'
const { ref, width, height, scaleX, scaleY } = useViewportFit({
  designWidth: 1920, designHeight: 1080,
})
// Attach ref to the canvas container element.
```

### `ResponsiveContainer`
```jsx
import ResponsiveContainer from '../components/ResponsiveContainer.jsx'
<ResponsiveContainer stackedAt="md" gap="gap-6">
  <aside>…</aside>
  <main>…</main>
</ResponsiveContainer>
```
Emits `data-layout="col"` / `data-layout="row"` for Playwright selector targeting.

### `MobileNavSheet`
```jsx
import MobileNavSheet from '../components/MobileNavSheet.jsx'
const [open, setOpen] = useState(false)
<MobileNavSheet open={open} onClose={() => setOpen(false)} title="Menu">
  <nav>…</nav>
</MobileNavSheet>
```
Includes: slide-up animation, backdrop, aria-modal, focus trap, Escape-to-close, body-scroll lock.
