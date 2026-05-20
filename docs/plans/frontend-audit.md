# Frontend Audit — Phase 1 (responsive / a11y / state)

Planning artifact only. No code in this branch. Subsequent agents pull tasks
from Section 2's checkbox list; `[HARD]` tasks are reserved for opus agents.

Audited at base SHA `b79971b`. Stack: React 18 + react-router + Tailwind v4
(`@theme` tokens in `src/index.css`, no custom breakpoint config — Tailwind
defaults `sm 640 / md 768 / lg 1024 / xl 1280`). Three.js viewport via raw
`OrbitControls`. Dark-only (`ink-*` surfaces, `kerf-*` brand yellow).

Legend: ✅ good · ⚠️ partial / risky · ❌ broken or absent.

---

## Section 1 — Inventory

### Auth & shell

| File / URL | Purpose | mobile / tablet / desktop | Missing states | a11y | Touch / flow |
|---|---|---|---|---|---|
| `src/routes/Login.jsx` `/login` | Email + OAuth sign-in | ✅ / ✅ / ✅ (`max-w-sm` centered) | error ✅, submitting ✅; no rate-limit / lockout copy | labels via `Input`; error block not `role="alert"`/`aria-live`; OAuth `<a>` ✅ | tap targets ≥44px ✅ |
| `src/routes/Signup.jsx` `/signup` | Register | ✅ / ✅ / ✅ | error ✅, inline pw error ✅ | same `aria-live` gap on error banner | ✅ |
| `src/routes/AuthCallback.jsx` `/auth/callback` | OAuth token exchange → /projects | ✅ / ✅ / ✅ (text only) | only "Signing you in…"; no visible error state (always redirects) | bare centered text, no `aria-busy`/spinner/role=status | n/a |
| `src/routes/ProtectedRoute.jsx` | Auth gate | n/a | redirects to /login w/ `from` ✅; no "session expired" toast on bounce | n/a | n/a |
| `src/App.jsx` | Router shell, bootstrap probe | renders `null` while bootstrapping (blank frame); `*` → `/` (no 404 page) | bootstrap returns `null` (no spinner) — perceived hang on slow local API | n/a | dead-ish: `/usage` linked in Layout UserMenu but **no `/usage` route** in App.jsx → redirects to `/` |
| `src/components/Layout.jsx` | Authed chrome (header, user menu, workspace switcher) | header ⚠️ — nav links `hidden sm:flex`, name `hidden sm:inline`; logo+switcher can crowd <360px | user "loading…" ✅ | UserMenu: `aria-haspopup`/`aria-expanded` ✅, Esc ✅, click-outside ✅, `role=menu/menuitem` ✅; avatar `<img alt="">` ok (decorative) | menu items ≥36px (slightly under 44) |

### Editor (project dashboard) — `src/routes/Editor.jsx` `/projects/:projectId[/files/:fileId]`

1982-line god-component hosting ~25 view sub-editors.

- Layout: `<div className="flex-1 grid" style={{ gridTemplateColumns: chatCollapsed ? '240px 1fr' : '240px 1fr 380px' }}>`. **Fixed px tracks, zero breakpoints.** mobile ❌ / tablet ❌ / desktop ✅. Below ~900px the 3D canvas + code split + chat are unusable; left tree `240px` + chat `380px` consume a phone viewport entirely.
- Top bar: ~12 icon buttons in one non-wrapping `h-12` flex row — overflows < ~1100px, no overflow menu. desktop ✅ only.
- Vertical split (3D over code) drag handle `cursor-row-resize`, mouse-only (`onSplitMouseDown`); left split same. No touch.
- States: skeleton/loading present in sub-panels (RevisionDrawer skeletons ✅); save indicator ✅ (saving/dirty/saved); error banner on eval ✅. No offline state; no top-level project-load error/empty (relies on workspace store).
- a11y: rename input `autoFocus` ✅ but the inline name `<button>` has no `aria-label`; many icon buttons rely on `title` only (no `aria-label`) — screen-reader names weak; modals defined here (`Build3DModal`) are `fixed inset-0` with **no `role="dialog"`/`aria-modal`/focus trap**; the Projects-style `Modal` (used for New/Rename/Delete) DOES have `role=dialog`+`aria-modal`+Esc ✅ (good reference impl).
- Flow: `RevisionDrawer` is `absolute top-12 right-0 bottom-0 w-80` — overlays content, fine on desktop, off-canvas-unfriendly on mobile.

### Shared viewport / 3D

| File | Purpose | resp. | states | a11y | touch |
|---|---|---|---|---|---|
| `src/components/Renderer.jsx` | Three.js scene, picking, measure, zebra, DFM | canvas ✅ via `ResizeObserver`; HUD chips `absolute` ✅ | no explicit "empty scene" / WebGL-unavailable / context-lost fallback | `<canvas>` not focusable, no keyboard orbit, no `role`/label; pick is pointer-only | ❌ only `mousemove`+`click`; orbit/zoom rely on OrbitControls default touch (untuned, no pinch tuning, `enablePan` default); feature-pick (face/edge/vertex) is **mouse-click-only** — no tap pick |
| `src/components/Gumball.jsx` | 3D transform handles | scales with canvas | n/a | no keyboard nudge, no ARIA | ❌ `mousedown/mousemove/mouseup` on `window`/`domElement` only — drag-transform impossible on touch |
| `src/lib/dfmOverlay.js` | DFM marker tooltips | tooltip `position:fixed; z-index:9999` inline | hover tooltip only | tooltip is non-interactive `pointer-events:none` div, no SR text | hover-only — no touch reveal |
| `src/components/CurvatureCombOverlay.jsx` | G3 comb viz panel | `absolute` panel | viz-only badge ✅ | decorative; small text contrast risk on `ink` | hover/desktop only |
| `src/components/FeatureView.jsx` (3085 ln) | Feature-tree inspector + add-feature menu | add-feature popover `w-[420px]` fixed, `grid-cols-3`; tree rows fixed | selection/empty states present | delete control uses `role="button"` on non-button + `aria-label` ✅; popover `role=menu` ✅; deep tree no keyboard traversal | row hover affordances; menu mouse-oriented |
| `src/components/FileTree.jsx` (760 ln) | Project file tree | `min-w-[80px]` badges, fixed context menu | rename/empty inline ✅ | rows `tabIndex=0`+`onKeyDown` ✅; context menu `onContextMenu` only (no keyboard equivalent / Shift-F10); hover-only action buttons (`opacity-0 group-hover`) | ❌ rename = `onDoubleClick`, actions = hover-reveal → unreachable on touch; context menu = right-click only |

### ChatPanel — `src/components/ChatPanel.jsx`

- Root `div className="h-full w-[380px] …"` — **hard-coded 380px**, not fluid; only works because Editor grid reserves exactly 380px. mobile ❌.
- States: `loadingMessages` ✅, empty state ✅, `sending` "thinking" ✅. No send-error / retry state surfaced in panel (errors swallowed upstream). No offline.
- a11y: `textarea` has placeholder but **no `<label>`/`aria-label`**; model picker `role=listbox` but options are `<button>` not `role=option`; "↵ send" hint `hidden sm:inline`; auto-scroll-to-bottom can fight screen readers (no `aria-live` region for streamed assistant text).
- Touch: Enter-to-send (`onKey`) makes a soft-keyboard newline impossible without Shift; Send button ≥44px ✅.

### Project list / dashboard

| File / URL | resp. | states | a11y | notes |
|---|---|---|---|---|
| `src/routes/Projects.jsx` `/projects`, `/w/:slug/projects` | ✅ grid `sm:grid-cols-2 lg:grid-cols-3`; header actions `flex-wrap` ✅ | skeleton ✅, empty ✅, error banner ✅ (no `aria-live`) | `Modal` is the good a11y reference (`role=dialog` + `aria-modal` + Esc + labelled); KebabMenu `role=menu` ✅; card link `focus-visible:ring` ✅ | thumbnail `<img alt="">` decorative ok; solid overall |
| `src/routes/Profile.jsx` `/profile` | ⚠️ unknown grid; avatar block fixed `w-20 h-20` | check save/loading | avatar `<img alt="">` | low risk |
| `src/routes/BOM.jsx` `/projects/:id/bom` | `h-screen` wrapper desktop-shaped; delegates to `BOMPanel` | inherits BOMPanel | header icon button `title` only | thin wrapper |
| `src/routes/Library.jsx`, `LibraryPart.jsx` | cloud-only; not deep-audited | — | — | scan in T-E task |

### Settings / billing / workspace

| File / URL | resp. | states | a11y | notes |
|---|---|---|---|---|
| `src/routes/Settings.jsx` `/profile`-ish (account) | ✅ `max-w-3xl mx-auto`, `max-w-md` forms stack | per-section save msg ✅, delete confirm ✅ | inline `<Field>` uses `<label>` wrapping ✅; status msgs not `aria-live`; danger button disabled-until-DELETE ✅ | clean |
| `src/cloud/BillingPanel.jsx` `/billing` | ✅ `grid md:grid-cols-2`; tables `truncate max-w-[180px/280px]` (can clip) | check loading/empty/error of credits + ledger | tables: no `<caption>`/scope; numeric cells ok | tables overflow on narrow — needs `overflow-x-auto` wrapper |
| `src/cloud/UsageWidget.jsx` | n/a — referenced but `/usage` route absent | — | — | dead link (see App.jsx row) |
| `src/routes/WorkspaceSettings.jsx`, `WorkspaceMembers.jsx` | not deep-audited | — | — | scan in T-F task |

### Workshop (cloud)

| File / URL | resp. | states | a11y | notes |
|---|---|---|---|---|
| `src/cloud/Workshop.jsx` `/workshop` | ✅ `grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`; header `sm:text-4xl` | check loading/empty/error of listings | like button `aria-label` ✅; card `<img alt={title}>` ✅ / hero `<img alt="">` ✅ | solid |
| `src/cloud/WorkshopListing.jsx` `/workshop/:slug` | ✅ `grid lg:grid-cols-3`, gallery `absolute` caption | check 404 / private listing | gallery thumbs `<img alt="">`; main `<img alt={title}>` ✅ | gallery thumb strip likely mouse-scroll; verify keyboard |

### Landing / marketing / comparison / domains

| File / URL | resp. | a11y | notes |
|---|---|---|---|
| `src/routes/Landing.jsx` `/` | ✅ strong — `lg:grid-cols`, `sm:`/`lg:` throughout, hero illustration `hidden md:block`, floating chips `hidden lg:flex` | decorative bg `aria-hidden` ✅, copy-install `aria-label` ✅ | best-in-codebase responsive; reference for breakpoint usage |
| `src/routes/Pricing.jsx` `/pricing` (cloud only) | not deep-audited | — | scan in T-H |
| `src/routes/Roadmap.jsx` `/roadmap` | not deep-audited | — | scan in T-H |
| `src/routes/domains/*` (`/domains`, `/domains/jewelry|mechanical|electronics|architecture|automotive`) | meta-driven pages, not deep-audited | — | scan in T-H (likely share Landing patterns) |
| `src/routes/compare/*` (`/compare`, `/compare/{freecad,kicad,rhino,revit,fusion}`) | not deep-audited | — | scan in T-H |
| `src/routes/Docs/*` (`/docs`, `/docs/:slug`) | sidebar layout, not deep-audited | — | sidebar likely needs mobile drawer — T-H |

### Configurator / share

| File / URL | resp. | states | a11y | notes |
|---|---|---|---|---|
| `src/routes/JewelryConfigurator.jsx` `/jewelry-configurator` | ✅ `min-h-screen`, `max-w-2xl`, `grid grid-cols-2 sm:grid-cols-4`, `grid-cols-3 sm:grid-cols-5` | step progress ✅; needs verify of estimate loading/error (api.jewelryQuote) | `aria-pressed` on choices ✅, `aria-label` on inputs ✅, step labels `hidden sm:block` | strong; verify stepper keyboard nav + estimate error state |
| `src/routes/JewelryShare.jsx` `/share/:token` | ✅ `min-h-screen`, `max-w-3xl`, `sm:py-12` | loading ✅, invalid-token ✅, error ✅ (3 `min-h-screen` branches) | sections `aria-label` ✅, inputs `aria-label` ✅; 3D preview region `aria-label` ✅ | good; verify approve/comment submit error + 3D fallback on no-WebGL |

### Modals / toasts / overlays (cross-route)

- `src/routes/Projects.jsx` `Modal` — **the good one**: `role="dialog" aria-modal aria-labelledby`, Esc, backdrop click, labelled close. Use as the canonical pattern.
- `src/components/ShareModal.jsx` — `fixed inset-0 z-50`, Esc handler ✅, but **no `role="dialog"`/`aria-modal`/focus trap**.
- `src/components/ShortcutsModal.jsx` — `fixed inset-0 z-50`, Esc ✅, `grid md:grid-cols-2` ✅, but **no `role="dialog"`/`aria-modal`/focus trap**.
- `Editor.jsx` `Build3DModal` — `fixed inset-0`, no dialog role / no Esc / no focus trap; backdrop not click-dismiss.
- Toasts: `Editor.jsx` `w.toast` is a bare `absolute` div, dismiss on click, **no `role="status"`/`aria-live`**; `thumbToast` likewise.
- `dfmOverlay` tooltip injects a raw `document.body` div at `z-index:9999` (highest in app) — z-index ad hoc, no token scale.

---

## Section 2 — Prioritized task list

Each task ≈1–3h sonnet unless `[HARD]`. Always isolate in a worktree.

### Group A — Auth

- [x] **T-A1 Announce auth errors to screen readers**
  Scope: wrap the red error banners in Login/Signup (and AuthCallback failure path) in `role="alert"` + `aria-live="assertive"`; give AuthCallback a `role="status"` busy state with spinner.
  Files: `src/routes/Login.jsx`, `src/routes/Signup.jsx`, `src/routes/AuthCallback.jsx`.
  Success: VoiceOver/NVDA announces the error on submit failure; AuthCallback no longer a silent text-only frame.

- [ ] **T-A2 Session-expired feedback on protected bounce**
  Scope: when `ProtectedRoute` redirects to `/login`, pass a reason in `state`; Login renders a one-line "Your session expired — sign in again." banner when present.
  Files: `src/routes/ProtectedRoute.jsx`, `src/routes/Login.jsx`.
  Success: deep-link to a protected page while logged out shows context, not a bare login.

- [x] **T-A3 Add a real 404 / catch-all page**
  Scope: replace `<Route path="*" element={<Navigate to="/" replace />}/>` with a lightweight NotFound route (logo, "Page not found", home link) so mistyped/dead URLs don't silently bounce.
  Files: `src/App.jsx` (+ new `src/routes/NotFound.jsx`).
  Success: unknown URL renders a 404 page; existing redirects (localShortcut etc.) unaffected.

### Group B — Chat

- [ ] **T-B1 Label the chat input + model options**
  Scope: add `aria-label` (or visually-hidden `<label>`) to the chat `textarea`; change model-picker option `<button>`s to `role="option"` with `aria-selected`, set `aria-activedescendant` on the listbox.
  Files: `src/components/ChatPanel.jsx`.
  Success: input and model list are properly named/announced; axe shows no listbox violation.

- [x] **T-B2 Live region for streamed assistant replies**
  Scope: wrap the message scroll container's latest assistant block in an `aria-live="polite"` region; ensure auto-scroll doesn't yank SR focus.
  Files: `src/components/ChatPanel.jsx`.
  Success: assistant responses are announced as they arrive without trapping focus.

- [ ] **T-B3 Surface send failures in the panel**
  Scope: add an inline error/retry row in ChatPanel when `onSend` rejects (thread the error state down from `useWorkspace.sendMessage`).
  Files: `src/components/ChatPanel.jsx`, `src/store/workspace.js` (read-only of send result; minimal state add).
  Success: a failed send shows "Couldn't send — Retry" instead of silently doing nothing.

### Group C — Viewport (Three.js)

- [ ] **T-C1 [HARD] Touch orbit / pan / pinch-zoom parity in Renderer**
  Scope: explicitly configure `OrbitControls` `touches`/`enablePan`/`enableZoom`, tune pinch + two-finger pan damping, and ensure single-tap maps to the same pick path as `click` (add `pointerup` with movement threshold so drag ≠ pick). Desktop wheel/drag must remain unchanged.
  Files: `src/components/Renderer.jsx`.
  Success: on a touch device the model can be rotated, pinch-zoomed, two-finger-panned, and parts tapped to select; desktop behaviour byte-for-byte unchanged; existing renderer tests green.

- [ ] **T-C2 [HARD] Touch feature-pick (face/edge/vertex) + tap-vs-drag**
  Scope: extend the feature-pick (`onClick`/`pickFeature`) path to fire on a tap that didn't move beyond a px threshold; keep shift-add behaviour reachable (long-press or an on-canvas "add to selection" toggle).
  Files: `src/components/Renderer.jsx`.
  Success: measure/inspect works by tapping faces/edges on touch; accidental orbit no longer mis-selects.

- [ ] **T-C3 [HARD] Gumball touch transforms**
  Scope: convert Gumball's `mousedown/mousemove/mouseup` to Pointer Events with `setPointerCapture`; raise hit threshold for finger-size targets.
  Files: `src/components/Gumball.jsx`.
  Success: translate/rotate/scale handles are draggable by finger; mouse path unchanged; `gumball.test.js` green.

- [ ] **T-C4 WebGL-unavailable / context-lost fallback**
  Scope: detect failed WebGL context creation and `webglcontextlost`; render a graceful message panel instead of a blank/black canvas.
  Files: `src/components/Renderer.jsx`.
  Success: browsers without WebGL (or after GPU reset) see an explanatory state, not a dead viewport.

- [ ] **T-C5 Keyboard + SR affordance for the canvas**
  Scope: make the canvas container focusable with an `aria-label`, add a visually-hidden hint, and basic arrow-key orbit nudge (small, optional) so the viewport isn't a total keyboard dead-zone.
  Files: `src/components/Renderer.jsx`.
  Success: Tab reaches the viewport with a name; arrows nudge the camera; no regression to mouse/touch.

### Group D — FeatureView

- [ ] **T-D1 Keyboard traversal for the feature tree**
  Scope: add roving-tabindex + Up/Down/Enter handling to feature-tree rows; ensure the add-feature popover (`role=menu`) supports arrow keys + Esc + focus return.
  Files: `src/components/FeatureView.jsx`.
  Success: the feature tree and add menu are fully operable without a mouse.

- [ ] **T-D2 Replace `role="button"` divs with real buttons**
  Scope: swap the delete-feature `role="button"` div for a `<button>` (keeps `aria-label`); audit FeatureView for other clickable non-buttons.
  Files: `src/components/FeatureView.jsx`.
  Success: axe reports no "interactive role on non-interactive element"; Enter/Space works.

### Group E — ProjectList / Dashboard

- [ ] **T-E1 aria-live on Projects error + scan Library/Profile**
  Scope: add `role="alert"` to the Projects error banner; quick responsive/a11y pass over `Library.jsx`, `LibraryPart.jsx`, `Profile.jsx` and log any fixed-width or label gaps inline as follow-up sub-bullets here.
  Files: `src/routes/Projects.jsx`, `src/routes/Library.jsx`, `src/routes/LibraryPart.jsx`, `src/routes/Profile.jsx`.
  Success: project load errors announced; the three unscanned routes have a documented status line in this doc.

### Group F — Settings / Billing

- [ ] **T-F1 Billing tables: overflow + semantics**
  Scope: wrap the credits/ledger tables in `overflow-x-auto`; add `<caption class="sr-only">`, `scope="col"` on headers; relax `truncate max-w-[…]` so values aren't silently clipped on desktop.
  Files: `src/cloud/BillingPanel.jsx`.
  Success: tables scroll instead of clip on narrow widths; screen reader announces table purpose + column headers.

- [ ] **T-F2 aria-live on Settings status messages + scan workspace routes**
  Scope: make `Inline` status messages in Settings polite live regions; quick pass over `WorkspaceSettings.jsx`/`WorkspaceMembers.jsx` for fixed widths / label gaps, log findings here.
  Files: `src/routes/Settings.jsx`, `src/routes/WorkspaceSettings.jsx`, `src/routes/WorkspaceMembers.jsx`.
  Success: save/error feedback announced; workspace routes have a status line in this doc.

### Group G — Workshop

- [x] **T-G1 Workshop listing keyboard + empty/error states**
  Scope: verify and fix the `WorkshopListing` gallery thumb strip for keyboard operation (arrow/Enter), add explicit empty + private + 404 states to `Workshop.jsx`/`WorkshopListing.jsx`.
  Files: `src/cloud/Workshop.jsx`, `src/cloud/WorkshopListing.jsx`.
  Success: gallery navigable by keyboard; missing/empty/private listings show real states.

### Group H — Landing / Marketing

- [ ] **T-H1 Scan + fix marketing/domain/compare/docs pages**
  Scope: responsive + a11y pass over `Pricing.jsx`, `Roadmap.jsx`, `domains/*`, `compare/*`, `Docs/*` (sidebar likely needs a mobile drawer / disclosure). Use `Landing.jsx` as the breakpoint reference. Record per-file status as sub-bullets here.
  Files: `src/routes/Pricing.jsx`, `src/routes/Roadmap.jsx`, `src/routes/domains/*.jsx`, `src/routes/compare/*.jsx`, `src/routes/Docs/*.jsx`.
  Success: each page works mobile→desktop; Docs sidebar collapses on mobile; statuses logged.

- [ ] **T-H2 [HARD] Docs sidebar → responsive mobile drawer**
  Scope: if the Docs sidebar is a fixed side column (confirm in T-H1), convert to a slide-in drawer < `lg` with a hamburger toggle, focus trap, Esc, and route-change auto-close, keeping desktop two-column intact.
  Files: `src/routes/Docs/index.jsx`, `src/routes/Docs/Sidebar.jsx`, `src/routes/Docs/Article.jsx`.
  Success: docs are navigable on a phone; desktop layout unchanged.

### Group I — Configurator

- [ ] **T-I1 Configurator stepper a11y + estimate states**
  Scope: give the step indicator `aria-current="step"`, ensure Back/Next are reachable and announce step changes; add explicit loading + error states for the `api.jewelryQuote` estimate in step 5.
  Files: `src/routes/JewelryConfigurator.jsx`.
  Success: stepper announced; review step shows spinner on quote fetch and a retryable error if it fails.

### Group J — Share

- [ ] **T-J1 JewelryShare submit + 3D fallback states**
  Scope: add submitting/success/error feedback to the approve + comment forms; show a fallback when the 3D preview can't initialise (lean on T-C4 detection if landed, else local guard).
  Files: `src/routes/JewelryShare.jsx`.
  Success: customers get clear feedback on approve/comment; no blank 3D box on unsupported devices.

### Group K — Overlays

- [ ] **T-K1 DFM tooltip SR text + z-index token**
  Scope: mirror the `dfmOverlay` tooltip content into an off-screen `aria-live` node so SR users get DFM warnings; replace the hard-coded `z-index:9999` with the shared z-scale from T-L2.
  Files: `src/lib/dfmOverlay.js`.
  Success: DFM issues are announced; tooltip z-index comes from the token scale.

- [ ] **T-K2 Curvature comb overlay contrast/labelling**
  Scope: verify the comb overlay panel text against `ink` background for ≥4.5:1 contrast; add an accessible label/legend; bump small text where it fails.
  Files: `src/components/CurvatureCombOverlay.jsx`.
  Success: overlay text meets WCAG AA; legend has a name.

### Group L — Shell

- [ ] **T-L1 [HARD] Responsive Editor layout**
  Scope: replace the hard-coded `gridTemplateColumns: '240px 1fr 380px'` with a breakpoint-aware layout: < `md` collapse file-tree and chat into toggleable off-canvas drawers (reuse the chat-collapse + a new tree-collapse), 1fr canvas as the default mobile view; ≥ `lg` keep the current three-pane. Make the split drag handles pointer-event based so they work on touch.
  Files: `src/routes/Editor.jsx`.
  Success: the editor is usable on tablet/phone (drawers, single canvas), unchanged on desktop ≥1024px; resize handles draggable by touch.

- [ ] **T-L2 [HARD] Top-bar overflow menu**
  Scope: collapse the ~12 Editor top-bar icon actions into a responsive "More" overflow menu below a width threshold (priority+ pattern); add `aria-label` to every icon-only button (Undo/Redo/History/Activity/Git/Thumbnail/Chat-toggle).
  Files: `src/routes/Editor.jsx`.
  Success: top bar never overflows down to ~768px; all actions reachable; every control has an SR name.

- [ ] **T-L3 Canonical accessible Modal + retire ad-hoc ones**
  Scope: promote the `Projects.jsx` `Modal` (role=dialog + aria-modal + Esc + labelled + backdrop) into a shared `src/components/Modal.jsx`; refactor `ShareModal`, `ShortcutsModal`, and `Editor.jsx` `Build3DModal` to use it (focus trap + focus return + scroll lock).
  Files: new `src/components/Modal.jsx`; `src/components/ShareModal.jsx`, `src/components/ShortcutsModal.jsx`, `src/routes/Editor.jsx`, `src/routes/Projects.jsx`.
  Success: every modal traps focus, returns focus on close, is dialog-roled; one implementation.

- [ ] **T-L4 Toast → accessible status component**
  Scope: build a small shared toast that renders into an `aria-live="polite"` region; route `Editor.jsx` `w.toast` and `thumbToast` (and any other ad-hoc toasts) through it.
  Files: new `src/components/Toast.jsx`; `src/routes/Editor.jsx` (and grep other inline toasts).
  Success: toasts are announced; consistent placement/dismiss.

- [ ] **T-L5 Fix `/usage` dead link**
  Scope: either add the `/usage` route mounting `UsageWidget` (cloud-gated, inside `ProtectedRoute`) or remove the `/usage` link from the Layout user menu.
  Files: `src/components/Layout.jsx`, `src/App.jsx` (+ `src/cloud/UsageWidget.jsx` if wiring the route).
  Success: no menu item navigates to a non-existent route (currently bounces to `/`).

- [ ] **T-L6 prefers-reduced-motion guard**
  Scope: add a global `@media (prefers-reduced-motion: reduce)` rule in `src/index.css` that neutralises `animate-*`/`transition`/`animate-pulse`; spot-check the heavy spinners/pulses still convey state.
  Files: `src/index.css`.
  Success: with reduced-motion on, animations are suppressed app-wide without breaking loading affordances.

- [ ] **T-L7 Header crowding < 360px**
  Scope: ensure `Layout.jsx` header (logo + `/` + WorkspaceSwitcher + user menu) degrades gracefully on very narrow screens (truncate/hide switcher label, keep tap targets ≥44px).
  Files: `src/components/Layout.jsx`, `src/components/WorkspaceSwitcher.jsx`.
  Success: no horizontal overflow at 320px; controls remain tappable.

---

## Section 3 — Cross-cutting findings

1. **No breakpoint convention.** Marketing surface (`Landing.jsx`, `JewelryConfigurator`, `JewelryShare`, `Workshop`, `Projects`) is genuinely responsive and uses Tailwind `sm/md/lg` well — adopt `Landing.jsx` as the house reference. The *application* surface (`Editor.jsx`, `ChatPanel.jsx`, `FileTree`, `FeatureView`) is hard-coded desktop px (`240px / 1fr / 380px`, `w-[380px]`, `w-[420px]`, `w-80`). Decision needed and documentable: treat the editor as desktop-first with mobile drawers (T-L1) rather than sprinkling breakpoints ad hoc.

2. **Modal pattern fragmentation.** Exactly one good modal exists (`Projects.jsx` `Modal`: dialog role + aria-modal + Esc + labelled). `ShareModal`, `ShortcutsModal`, `Build3DModal` each reimplement `fixed inset-0 z-50` with no role/trap. One shared `Modal` (T-L3) removes the largest single a11y debt.

3. **Focus visibility is rare.** Only ~5 of ~101 component/route files use `focus-visible`. Most interactive elements rely on browser default outline (often suppressed by `outline-none` without a replacement ring). Recommend a global `*:focus-visible` ring in `src/index.css` using the existing `--color-kerf-300` token, plus auditing every `outline-none` (157 occurrences of focus/outline utilities) for a paired ring.

4. **Status changes are not announced.** Error banners (Login/Signup/Projects), inline save messages (Settings), toasts (Editor), and streamed chat are all visually-only — no `role="alert"`/`status`/`aria-live`. A shared Toast (T-L4) + a convention of `role="alert"` on error blocks fixes this class-wide.

5. **Touch is unimplemented in 3D.** Renderer, Gumball, FileTree (hover-reveal actions, dbl-click rename, right-click menu), and DFM tooltips are all mouse/hover-bound. The viewport trio (T-C1/C2/C3) is the deepest work and is correctly fenced as `[HARD]`. FileTree touch is a smaller, separate concern worth folding into a future task if not covered.

6. **Icon-only buttons lack names.** Pervasive pattern: `title="…"` with no `aria-label` (Editor top bar, BOM header, FileTree actions). `title` is not a reliable accessible name. A sweep adding `aria-label` everywhere `title` is the only text would clear most remaining axe name violations.

7. **Ad-hoc z-index.** Values range from `z-20`/`z-30`/`z-40`/`z-50` (Tailwind) up to inline `z-index:9999` (`dfmOverlay`). No scale/token. Define a small documented z-layer scale and route overlays/tooltips/modals through it (touched by T-K1, T-L3).

8. **No reduced-motion support.** Many `animate-pulse`/`animate-spin`/`transition-*`; nothing honours `prefers-reduced-motion` except a JS pref in `userPrefs.js`. One CSS media block (T-L6) covers the whole app.

STATUS: COMPLETE
