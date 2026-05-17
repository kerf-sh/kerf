/**
 * Page-object model for /projects (and /w/:slug/projects).
 *
 * In local mode the app auto-bootstraps a singleton user, so the test server
 * starts with KERF_LOCAL_MODE=true and there is no manual sign-in step. The
 * browser hits / → /projects redirect without any form interaction.
 */

import { Page, Locator, expect } from '@playwright/test'

export class ProjectsPage {
  readonly page: Page

  // Header toolbar
  readonly newProjectButton: Locator

  // New project modal
  readonly modal: Locator
  readonly modalNameInput: Locator
  readonly modalCreateButton: Locator
  readonly modalCancelButton: Locator

  // Project grid
  readonly projectGrid: Locator

  constructor(page: Page) {
    this.page = page

    // The Projects page exposes two "New project" buttons (header toolbar +
    // empty-state CTA). Either opens the same modal; take the first.
    this.newProjectButton = page
      .getByRole('button', { name: 'New project' })
      .first()

    // The modal is keyed by title text
    this.modal = page.getByRole('dialog')
    this.modalNameInput = page.getByLabel('Name')
    this.modalCreateButton = page.getByRole('button', { name: 'Create project' })
    this.modalCancelButton = page.getByRole('button', { name: 'Cancel' })

    // Project cards live in a CSS grid — no explicit role; we key by heading
    // level inside each card.
    this.projectGrid = page.locator('.grid')
  }

  /** Navigate to the projects page and wait for it to settle. */
  async goto() {
    await this.page.goto('/projects')
    // Wait until the page has either loaded projects or shown the empty state.
    // The spinner is absent and either EmptyState or at least one h3 is visible.
    await this.page.waitForSelector('h1', { state: 'visible' })
  }

  /**
   * Wait for the projects list view to be ready. Robust against the
   * client-side redirect to /w/:slug/projects — asserting on a UI signal
   * instead of the URL avoids the SPA "waitForURL until load" hang (there
   * is no document load event on a pushState navigation).
   */
  async waitForList() {
    await expect(
      this.page.getByRole('heading', { name: 'Projects' }),
    ).toBeVisible({ timeout: 20_000 })
  }

  /** Open the new project modal. */
  async openNewProjectModal() {
    await this.newProjectButton.click()
    await expect(this.modalNameInput).toBeVisible()
  }

  /**
   * Fill and submit the new project form.
   * @returns the project name used, so callers can assert it appears in the grid.
   */
  async createProject(name: string) {
    await this.openNewProjectModal()
    await this.modalNameInput.fill(name)
    await this.modalCreateButton.click()
    // After creation the modal closes and we're redirected to the editor.
    // Callers should await the editor URL if needed.
  }

  /**
   * Open a project card's kebab menu by project name and click an action.
   * @param projectName  exact name shown on the card h3
   * @param action       'Rename' | 'Delete' | 'Share'
   */
  async openProjectMenu(projectName: string, action: 'Rename' | 'Delete' | 'Share') {
    // Find the card that contains the h3 with the project name.
    const card = this.page
      .locator('.group')
      .filter({ has: this.page.locator('h3', { hasText: projectName }) })
      .first()

    const kebab = card.getByRole('button', { name: 'Project actions' })
    await kebab.click()

    const menuItem = this.page.getByRole('menuitem', { name: action })
    await menuItem.click()
  }

  /**
   * Wait for a project card with the given name to appear in the grid.
   */
  async expectProjectVisible(name: string) {
    // Exact match: a renamed project ("<name>-renamed") contains the
    // original name as a substring, so hasText would false-match.
    await expect(
      this.page.getByRole('heading', { level: 3, name, exact: true }),
    ).toBeVisible()
  }

  /**
   * Wait for a project card with the given name to disappear.
   */
  async expectProjectGone(name: string) {
    await expect(
      this.page.getByRole('heading', { level: 3, name, exact: true }),
    ).toHaveCount(0)
  }

  /** Fill and submit the Rename modal (assumes it is already open). */
  async submitRename(newName: string) {
    // Scope to the dialog: getByLabel('Name') alone also matches the
    // "Rename project" dialog (substring of "reName") — strict violation.
    const dialog = this.page.getByRole('dialog', { name: 'Rename project' })
    const nameInput = dialog.getByRole('textbox', { name: 'Name', exact: true })
    await nameInput.clear()
    await nameInput.fill(newName)
    await dialog.getByRole('button', { name: 'Save' }).click()
  }

  /** Click "Delete project" in the confirm dialog (assumes it is already open). */
  async confirmDelete() {
    await this.page.getByRole('button', { name: 'Delete project' }).click()
  }
}
