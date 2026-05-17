/**
 * workshop.spec.ts — a public project with a Part appears in /workshop.
 *
 * Runs under the `cloud` Playwright project (CLOUD_ENABLED). The Workshop
 * index lists parts (kind='part') from projects with visibility='public'
 * (kerf_core.db.queries.library.list_public_parts). We seed that state via
 * the API, then assert the listing renders in the browser.
 */

import { test, expect, type APIRequestContext } from '@playwright/test'

const uniq = () => `${Date.now()}-${Math.floor(Math.random() * 1e4)}`
const PASSWORD = 'e2e-passw0rd!'

async function seedPublicPart(req: APIRequestContext) {
  const email = `e2e-ws-${uniq()}@kerf.test`
  const reg = await req.post('/auth/register', {
    data: { email, password: PASSWORD, name: 'WS Author' },
  })
  expect(reg.status()).toBe(201)
  const { access_token, default_workspace } = await reg.json()
  const auth = { Authorization: `Bearer ${access_token}` }

  const projectName = `e2e-ws-proj-${uniq()}`
  const pr = await req.post('/api/projects', {
    headers: auth,
    data: {
      workspace_id: default_workspace.id,
      name: projectName,
      starter: 'blank',
    },
  })
  expect(pr.ok()).toBeTruthy()
  const project = await pr.json()

  const fr = await req.post(`/api/projects/${project.id}/files`, {
    headers: auth,
    data: { name: 'widget.part', kind: 'part', content: '{}' },
  })
  expect(fr.ok()).toBeTruthy()

  const up = await req.patch(`/api/projects/${project.id}`, {
    headers: auth,
    data: { visibility: 'public' },
  })
  expect(up.ok()).toBeTruthy()

  return { email, projectName, projectId: project.id }
}

test.describe('Workshop (cloud mode)', () => {
  test('public project with a Part appears in Workshop listing', async ({
    page,
  }) => {
    const { email, projectName } = await seedPublicPart(page.request)

    // Authenticate the browser as the author via the real /login UI.
    await page.goto('/login')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(
      page.getByRole('heading', { name: 'Projects' }),
    ).toBeVisible({ timeout: 20_000 })

    // Navigate to Workshop via the in-app link (client-side route) — a hard
    // page.goto('/workshop') races useCloudConfig: until /api/config
    // resolves, the cloud-gated route isn't registered and the catch-all
    // ("*" → "/") bounces back to /projects.
    await page.getByRole('link', { name: 'Workshop', exact: true }).first().click()
    await expect(
      page.getByRole('heading', { name: /workshop/i }),
    ).toBeVisible({ timeout: 15_000 })
    await expect(
      page.getByText(projectName, { exact: false }).first(),
    ).toBeVisible({ timeout: 15_000 })
  })
})
