/**
 * projects.spec.ts — golden-path CRUD for the /projects page.
 *
 * LOCAL MODE
 * ----------
 * The test server runs with KERF_LOCAL_MODE=true so the frontend auto-mints a
 * singleton user via /auth/bootstrap-local. No sign-in form is shown. The app
 * immediately redirects / → /projects.
 *
 * What this suite covers
 * ----------------------
 * 1. Page loads and shows the "Projects" heading
 * 2. Create a project — modal opens, name fills, submit → card appears in grid
 * 3. Rename a project — kebab → Rename modal → new name shows on card
 * 4. Delete a project — kebab → Delete confirm → card disappears
 */

import { test, expect } from '@playwright/test'
import { ProjectsPage } from '../pages/ProjectsPage'

// Unique suffix keeps parallel test runs from colliding in a shared DB.
const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`

test.describe('Projects page (local mode)', () => {
  test('shows the Projects heading', async ({ page }) => {
    const pp = new ProjectsPage(page)
    await pp.goto()
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
  })

  test('create a project — card appears in grid', async ({ page }) => {
    const pp = new ProjectsPage(page)
    const name = `e2e-create-${uid()}`
    await pp.goto()

    // The page redirects to /w/:slug/projects; wait for it to settle.
    await pp.waitForList()

    // Creating a project navigates to the new project's editor; return to
    // the list to verify the card is in the grid.
    await pp.createProject(name)
    await pp.goto()
    await pp.waitForList()

    await pp.expectProjectVisible(name)
  })

  test('rename a project', async ({ page }) => {
    const pp = new ProjectsPage(page)
    const original = `e2e-rename-${uid()}`
    const renamed = `${original}-renamed`
    await pp.goto()
    await pp.waitForList()

    // Create a project to rename, then return to the list.
    await pp.createProject(original)
    await pp.goto()
    await pp.waitForList()

    await pp.expectProjectVisible(original)

    await pp.openProjectMenu(original, 'Rename')

    // Rename modal opens
    await pp.submitRename(renamed)

    // Card should now show the new name
    await pp.expectProjectVisible(renamed)
    await pp.expectProjectGone(original)
  })

  test('delete a project', async ({ page }) => {
    const pp = new ProjectsPage(page)
    const name = `e2e-delete-${uid()}`
    await pp.goto()
    await pp.waitForList()

    await pp.createProject(name)
    await pp.goto()
    await pp.waitForList()

    await pp.expectProjectVisible(name)

    await pp.openProjectMenu(name, 'Delete')
    await pp.confirmDelete()

    await pp.expectProjectGone(name)
  })
})
