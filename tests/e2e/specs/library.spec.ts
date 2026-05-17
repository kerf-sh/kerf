/**
 * library.spec.ts — browse the Library catalog and open a Library Part.
 *
 * Runs under the `cloud` Playwright project (CLOUD_ENABLED). The Library
 * catalog (GET /api/library/parts → list_public_parts) lists files of
 * kind='part' from projects with visibility='public' — no verified-publisher
 * requirement for the default (non-verified-only) listing. We seed that
 * state via the API, then browse + open the part in the browser.
 */

import { test, expect, type APIRequestContext } from '@playwright/test'

const uniq = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`
const PASSWORD = 'e2e-passw0rd!'

async function seedLibraryPart(req: APIRequestContext) {
  const email = `e2e-lib-${uniq()}@kerf.test`
  const reg = await req.post('/auth/register', {
    data: { email, password: PASSWORD, name: 'Lib Author' },
  })
  expect(reg.status()).toBe(201)
  const { access_token, default_workspace } = await reg.json()
  const auth = { Authorization: `Bearer ${access_token}` }

  const pr = await req.post('/api/projects', {
    headers: auth,
    data: {
      workspace_id: default_workspace.id,
      name: `e2e-lib-proj-${uniq()}`,
      starter: 'blank',
    },
  })
  expect(pr.ok()).toBeTruthy()
  const project = await pr.json()

  const partName = `e2e-libpart-${uniq()}`
  const fr = await req.post(`/api/projects/${project.id}/files`, {
    headers: auth,
    data: { name: partName, kind: 'part', content: '{}' },
  })
  expect(fr.ok()).toBeTruthy()

  const up = await req.patch(`/api/projects/${project.id}`, {
    headers: auth,
    data: { visibility: 'public' },
  })
  expect(up.ok()).toBeTruthy()

  return { email, partName }
}

test.describe('Library browse + open (cloud mode)', () => {
  test('open Library Part from the catalog', async ({ page }) => {
    const { email, partName } = await seedLibraryPart(page.request)

    // Authenticate via the real /login UI.
    await page.goto('/login')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(
      page.getByRole('heading', { name: 'Projects' }),
    ).toBeVisible({ timeout: 20_000 })

    // Navigate to Library via the in-app link (client-side route — a hard
    // page.goto races useCloudConfig and the catch-all bounces it away).
    await page.getByRole('link', { name: 'Library', exact: true }).first().click()
    await expect(
      page.getByRole('heading', { name: 'Library', exact: true }).first(),
    ).toBeVisible({ timeout: 15_000 })

    // The seeded part appears in the catalog.
    const card = page.getByText(partName, { exact: false }).first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    // Opening it navigates to the part detail (/library/:slug or
    // /workshop/:slug) and shows the part name as the page heading.
    await card.click()
    await expect(
      page.getByRole('heading', { name: new RegExp(partName) }).first(),
    ).toBeVisible({ timeout: 15_000 })
  })
})
