/**
 * AutosaveStatus.jsx — toolbar indicator for L1 / L2 dirty state.
 *
 * Reads `useDirtyL1Count()` from the dirty store. When the count is > 0 the
 * dot is amber (unsaved local changes in IndexedDB). When 0 it is green (L1
 * clean). The T-184 sibling agent will add L2-flush status signals here;
 * this component intentionally only handles the L1 badge for now.
 *
 * Usage:
 *   <AutosaveStatus />
 */

import { useDirtyL1Count } from '../stores/dirtyStore.js'

export default function AutosaveStatus() {
  const dirtyCount = useDirtyL1Count()
  const isDirty = dirtyCount > 0

  return (
    <span
      title={isDirty ? `${dirtyCount} unsaved change${dirtyCount !== 1 ? 's' : ''} (local)` : 'All changes saved locally'}
      aria-label={isDirty ? `${dirtyCount} unsaved local changes` : 'Saved'}
      className="inline-flex items-center gap-1.5 text-xs select-none"
    >
      <span
        className={[
          'h-2 w-2 rounded-full flex-shrink-0 transition-colors duration-300',
          isDirty ? 'bg-amber-400' : 'bg-emerald-500',
        ].join(' ')}
      />
      <span className="sr-only">{isDirty ? 'Unsaved changes' : 'Saved'}</span>
    </span>
  )
}
