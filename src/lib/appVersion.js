// Thin accessor for the build-time version global injected by Vite.
// Wrapping it in a function lets call-sites remain testable without
// reaching into the global namespace directly.

/* global __APP_VERSION__ */

/** Returns the app version string (e.g. "0.1.0"). */
export function appVersion() {
  // __APP_VERSION__ is replaced at build time by Vite's define plugin
  // (vite.config.js: `define: { __APP_VERSION__: JSON.stringify(pkg.version) }`).
  // In tests the global may be set on globalThis directly.
  try {
    // eslint-disable-next-line no-undef
    return __APP_VERSION__
  } catch {
    return globalThis.__APP_VERSION__ ?? ''
  }
}
