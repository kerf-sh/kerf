/**
 * Playwright configuration for Kerf end-to-end tests.
 *
 * LOCAL MODE
 * ----------
 * The backend reads KERF_LOCAL_MODE=true and calls /auth/bootstrap-local on
 * startup, auto-minting a singleton user so tests never need a sign-in form.
 * The webServer stanza below wires this up automatically when you run
 * `npm test` from this directory.
 *
 * DEV USAGE (reuse an already-running server):
 *   VITE_API_URL=http://localhost:8080 npm run dev   # terminal 1
 *   npm test                                         # terminal 2 — reuseExistingServer=true skips boot
 *
 * CI (fresh server each run):
 *   DATABASE_URL=postgres://... KERF_LOCAL_MODE=true npm test
 *
 * Port layout (separate from the dev port so dev + test can coexist):
 *   :8081  — kerf-server (FastAPI)
 *   :5174  — Vite dev server (proxies /api + /auth to :8081)
 */

import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './specs',

  // Run tests serially — all share one DB instance; parallel writes would
  // require isolated schemas per worker which is overkill for v1.
  fullyParallel: false,
  workers: 1,

  retries: 0,

  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5174',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',

    // Give slow WASM workers (OCCT, JSCAD) time to finish
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
  },

  // webServer boots a throwaway Vite dev server + kerf-server. If you
  // already have servers running on these ports (local dev) Playwright will
  // reuse them instead of starting new ones (reuseExistingServer=true when
  // not in CI).
  //
  // Adjust the python command if your environment uses `python3` or a
  // virtualenv — `python -m kerf_core` is what `pip install -e .[full]`
  // makes available.
  webServer: [
    {
      // Backend: kerf-server on :8081
      // NOTE: kerf_core.config.Settings has no env prefix, so it reads the
      // UNPREFIXED names (LOCAL_MODE / DATABASE_URL / CORS_ORIGIN). The
      // KERF_* duplicates are kept for any deploy path that consumes them.
      // CORS_ORIGIN must be the Vite e2e origin (:5174) — the browser calls
      // the API cross-origin (VITE_API_URL=http://localhost:8081), and the
      // default cors_origin is :5173, which would block /auth/bootstrap-local
      // and leave every local-mode spec stuck on the sign-in page.
      command:
        'KERF_PORT=8081 KERF_LOCAL_MODE=true LOCAL_MODE=true ' +
        'CORS_ORIGIN=http://localhost:5174 ' +
        (process.env.DATABASE_URL
          ? `KERF_DATABASE_URL=${process.env.DATABASE_URL} ` +
            `DATABASE_URL=${process.env.DATABASE_URL} `
          : '') +
        'python -m kerf_core --port 8081',
      url: 'http://localhost:8081/health',
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // Frontend: Vite on :5174 (proxies /api + /auth to :8081)
      command:
        'VITE_API_URL=http://localhost:8081 ' +
        'npx vite --port 5174 --host localhost',
      cwd: '../..',
      url: 'http://localhost:5174',
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
})
