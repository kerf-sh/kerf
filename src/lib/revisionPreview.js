/**
 * revisionPreview — helpers for the revisions panel lazy-preview feature.
 *
 * The list endpoint returns ``content_preview`` (max 200 chars) rather than
 * the full content.  These helpers format that preview for display and also
 * post-process the full content returned by the ``/content`` endpoint.
 */

/** Maximum characters shown as the inline preview in the revisions list. */
export const PREVIEW_MAX = 120

/**
 * Format a ``content_preview`` string for display in the revisions panel.
 *
 * - Collapses all whitespace runs to a single space (to handle JSON / code
 *   indentation that doesn't render well in a one-liner).
 * - Truncates to ``maxLen`` characters and appends an ellipsis.
 * - Returns an empty string when the input is null / undefined / empty.
 *
 * @param {string|null|undefined} preview  Raw content_preview from the API.
 * @param {number} [maxLen]                Truncation limit (default PREVIEW_MAX).
 * @returns {string}
 */
export function formatPreview(preview, maxLen = PREVIEW_MAX) {
  if (!preview) return ''
  const flat = preview.replace(/\s+/g, ' ').trim()
  if (flat.length <= maxLen) return flat
  return flat.slice(0, maxLen) + '…' // U+2026 HORIZONTAL ELLIPSIS
}

/**
 * Truncate a full content string to ``maxLen`` characters for display.
 *
 * Unlike ``formatPreview`` this does NOT collapse whitespace — it is meant
 * for the expanded "full content" panel where formatting matters.
 *
 * @param {string|null|undefined} content  Full file content.
 * @param {number} [maxLen]                Truncation limit (default 4096).
 * @returns {string}
 */
export function truncateContent(content, maxLen = 4096) {
  if (!content) return ''
  if (content.length <= maxLen) return content
  return content.slice(0, maxLen) + '…'
}

/**
 * Return a display-safe preview string for a revision row.
 *
 * Priority:
 *   1. ``content_preview`` from the list endpoint (already short).
 *   2. Fallback: first ``PREVIEW_MAX`` characters of ``content`` if somehow
 *      the full content was included (legacy / local mode).
 *   3. Empty string.
 *
 * @param {object} rev  Revision row from the API.
 * @returns {string}
 */
export function revisionDisplayPreview(rev) {
  if (!rev) return ''
  const raw = rev.content_preview || (rev.content ? rev.content.slice(0, 200) : '')
  return formatPreview(raw)
}
