/**
 * RouteFallback — Suspense fallback for lazily-loaded routes.
 *
 * Rendered while a code-split route chunk is being fetched. Stays accessible
 * via `role="status"` + `aria-live="polite"` so screen readers announce the
 * in-flight load. Intentionally minimal — no header/footer — so it never
 * blocks first paint while the route chunk streams in.
 */
export default function RouteFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="min-h-screen bg-ink-950 text-ink-100 grid place-items-center"
    >
      <div className="flex flex-col items-center gap-3">
        <span
          aria-hidden="true"
          className="inline-block w-6 h-6 rounded-full border-2 border-ink-700 border-t-kerf-300 animate-spin"
        />
        <span className="sr-only">Loading…</span>
      </div>
    </div>
  )
}
