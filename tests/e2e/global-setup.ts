/**
 * Global Playwright setup — runs once before all specs.
 *
 * In KERF_LOCAL_MODE=true the kerf-server auto-creates a singleton user the
 * moment the first request hits /auth/bootstrap-local. The frontend calls
 * this endpoint inside App.jsx's useEffect on mount. Global setup just
 * verifies the server is healthy and accessible; the actual bootstrap happens
 * in-browser on first page load.
 *
 * If you need to seed fixture data (e.g. a specific project or file) do it
 * here via direct HTTP calls to the API on :8081 using a stored access token.
 */

import { chromium, FullConfig } from '@playwright/test'

async function globalSetup(_config: FullConfig) {
  // Verify the backend is reachable before tests begin. The webServer stanza
  // in playwright.config.ts already waits for the health endpoint, but an
  // explicit probe here gives a clearer error message if something is wrong.
  const apiBase = process.env.E2E_API_URL || 'http://localhost:8081'
  let attempts = 0
  while (attempts < 10) {
    try {
      const res = await fetch(`${apiBase}/health`)
      if (res.ok) break
    } catch {
      // server not ready yet
    }
    await new Promise((r) => setTimeout(r, 1_000))
    attempts++
  }
  if (attempts === 10) {
    throw new Error(`kerf-server at ${apiBase} did not become healthy in time`)
  }
}

export default globalSetup
