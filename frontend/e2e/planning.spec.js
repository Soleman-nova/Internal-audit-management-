// TESTING.md §2 — Audit Manager. The planning page.
//
// Why this spec exists at all: the planning page is the largest surface in the
// app, and before this the *only* thing any test did through the UI was press
// Approve on a plan card (manager.spec.js). The universe table, the engagements
// table and all six modals had no UI coverage, so a tab or a modal could stop
// rendering entirely and the suite would stay green — which is exactly the risk
// a refactor of that page carries. Every assertion below is therefore on
// rendered content (column headers, a row, a field inside the dialog) rather
// than on a container that exists whether or not anything is in it.
import { test, expect } from '@playwright/test';
import { api } from './helpers.js';

test.describe('planning page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/planning');
    // The page renders its tab bar before the first fetch settles, so waiting on
    // a tab is not enough on its own — each test below waits for the content it
    // asserts on, which is what actually proves the tab finished loading.
    await expect(page.getByRole('button', { name: 'Audit Universe' })).toBeVisible();
  });

  test('the audit universe tab renders its table and all three of its dialogs', async ({ page }) => {
    await page.getByRole('button', { name: 'Audit Universe' }).click();
    await expect(page.getByRole('heading', { name: 'EEU Risk-Weighted Audit Universe' })).toBeVisible();

    // Column headers rather than a bare table: a table that rendered with no
    // columns at all would otherwise pass.
    for (const header of ['Code', 'Entity Name', 'Category', 'Risk Score', 'Re-Audit']) {
      await expect(page.locator('.planning-view th').filter({ hasText: header })).toBeVisible();
    }

    // The Add form. `#universe_name` is the first control in it and is rendered
    // by the modal body, so it only exists if the modal really opened.
    await page.getByRole('button', { name: 'Add Entity' }).click();
    let dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Add Auditable Entity' })).toBeVisible();
    await expect(dialog.locator('#universe_name')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();

    // Import and export are separate modals with their own state.
    await page.getByRole('button', { name: 'Import', exact: true }).click();
    dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Import Audit Universe' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();

    await page.getByRole('button', { name: 'Export', exact: true }).click();
    dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Export Audit Universe' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  test('the plans tab renders plan cards and opens its create dialog', async ({ page }) => {
    await page.getByRole('button', { name: 'Annual Audit Plans' }).click();
    await expect(page.getByRole('heading', { name: 'Annual Audit Plans' })).toBeVisible();

    // A real card, not just the empty-state message: the seed data has plans and
    // every other spec on this page depends on one being listed.
    await expect(page.locator('.plan-card').first()).toBeVisible();

    await page.getByRole('button', { name: 'Create Plan' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Create Annual Audit Plan' })).toBeVisible();
    await expect(dialog.locator('#plan_title')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  test('the engagements tab renders its table and opens both of its dialogs', async ({ page }) => {
    await page.getByRole('button', { name: /^Engagements/ }).click();
    await expect(page.getByRole('heading', { name: 'Audit Engagements' })).toBeVisible();

    // 'Ref Number' and 'Audit Title' are the first two columns of this table;
    // there is no column called "Engagement", which is what an earlier version
    // of this line waited for.
    for (const header of ['Ref Number', 'Audit Title', 'Lead Auditor', 'Risk Level']) {
      await expect(page.locator('.planning-view th').filter({ hasText: header })).toBeVisible();
    }

    // The Schedule form.
    await page.getByRole('button', { name: 'Schedule Engagement' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Schedule Audit Engagement' })).toBeVisible();
    await expect(dialog.locator('#engagement_title')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();

    // The team dialog, opened from a row's Assign button. It is the one dialog
    // whose data is fetched *because* it opened (`enabled: Boolean(id)`), so
    // asserting its heading alone would not prove that wiring survived.
    const assign = page.getByRole('button', { name: 'Assign' }).first();
    await expect(assign).toBeVisible();
    await assign.click();
    await expect(page.getByRole('dialog').getByRole('heading', { name: /Team/i })).toBeVisible();
    await expect(page.getByRole('dialog').locator('#team-member-form')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toBeHidden();
  });

  test('a deep link selects the tab holding the record and renders it', async ({ page }) => {
    // This is the one contract that spans the page's internals: the scroll target
    // is resolved in the shell (`document.getElementById(deepLinkKey)`, where the
    // key is built from the query string) while the id it looks for is rendered
    // inside a tab component. Renaming either side leaves a page that opens the
    // right tab and silently scrolls nowhere, so both halves are asserted.
    //
    // The notifications the backend emits use exactly these links, which is why
    // it is worth a test rather than trusting the two halves to stay in step.
    const plans = await api(page, 'GET', '/planning/plans/?page_size=1');
    const planId = plans.body.results[0].id;
    await page.goto(`/planning?plan=${planId}`);
    // The tab was *derived* from the query string, not defaulted to and corrected
    // afterwards — so this also pins that the deep link beats the 'universe' default.
    await expect(page.getByRole('heading', { name: 'Annual Audit Plans' })).toBeVisible();
    await expect(page.locator(`#plan-${planId}`)).toBeVisible();

    const engagements = await api(page, 'GET', '/planning/engagements/?page_size=1');
    const engagementId = engagements.body.results[0].id;
    await page.goto(`/planning?engagement=${engagementId}`);
    await expect(page.getByRole('heading', { name: 'Audit Engagements' })).toBeVisible();
    await expect(page.locator(`#engagement-${engagementId}`)).toBeVisible();
  });
});