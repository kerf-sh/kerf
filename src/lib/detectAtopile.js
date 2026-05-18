// detectAtopile.js — heuristic to detect whether a string contains atopile
// hardware-description source code (a ```.ato` code fence or bare .ato text).
//
// The heuristic looks for two mandatory signals that distinguish .ato from
// arbitrary text:
//
//   1. A module declaration:   `module SomeName:` or `component SomeName:`
//      at the start of a line (case-sensitive, atopile keyword).
//
//   2. A body-level construct: either a tilde-pin assignment (`~` is the
//      atopile shorthand for anonymous signal connections) OR an explicit
//      `signal` keyword (port / net declaration).
//
// Both conditions must be satisfied to return `true`, keeping false-positive
// rates low on JSON, JSX, and plain text.
//
// ---
// Code-fence form — strips the ` ```ato ... ``` ` wrapper before analysis:
//
//   ```ato
//   module VoltageDivider:
//     r1 = new Resistor
//     r2 = new Resistor
//     signal gnd
//     r1.~[1] ~ r2.~[2]
//   ```
//
// Bare .ato form — the raw source text itself (no fencing required):
//
//   module VoltageDivider:
//     signal gnd
//     r1 = new Resistor

// Matches a line that starts a module or component block.
const MODULE_RE = /^\s*(module|component)\s+[A-Za-z_]\w*\s*:/m

// Matches any use of the tilde operator (anonymous signal pin connection) or
// an explicit `signal` keyword port declaration.
const SIGNAL_RE = /(?:^\s*signal\b|~)/m

/**
 * Return `true` when `source` looks like atopile source code.
 *
 * Accepts either a raw .ato text string or a markdown code block string that
 * contains an ` ```ato` fence.  Non-string values always return `false`.
 *
 * @param {unknown} source
 * @returns {boolean}
 */
export function detectAtopile(source) {
  if (typeof source !== 'string' || source.length === 0) return false

  // Strip a leading ` ```ato` / ` ```atopile` fence and trailing ` ``` ` so
  // the regex can see the raw source lines regardless of how the LLM wraps
  // the snippet.
  const body = _stripFence(source)

  return MODULE_RE.test(body) && SIGNAL_RE.test(body)
}

/**
 * Extract the raw .ato source from `source`.
 *
 * - If `source` contains an ` ```ato` / ` ```atopile` code fence, returns the
 *   text inside the fence.
 * - Otherwise returns `source` unchanged so callers can compile it directly.
 *
 * Returns `null` when `source` is not a string or is empty.
 *
 * @param {unknown} source
 * @returns {string | null}
 */
export function extractAtopileSource(source) {
  if (typeof source !== 'string' || source.length === 0) return null
  return _stripFence(source)
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

// Matches ```ato or ```atopile (with optional whitespace after the language tag)
const FENCE_OPEN_RE = /^```(?:ato(?:pile)?)\s*\n?/i
const FENCE_CLOSE_RE = /\n?```\s*$/

function _stripFence(text) {
  const trimmed = text.trim()
  if (FENCE_OPEN_RE.test(trimmed)) {
    const withoutOpen = trimmed.replace(FENCE_OPEN_RE, '')
    const withoutClose = withoutOpen.replace(FENCE_CLOSE_RE, '')
    return withoutClose
  }
  return trimmed
}
