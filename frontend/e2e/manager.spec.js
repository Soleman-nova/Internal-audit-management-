// TESTING.md §2 — Audit Manager.
import { test, expect } from '@playwright/test';
import { api, NAV, expectNavHidden } from './helpers.js';

test('/users is blocked by the route guard', async ({ page }) => {
  await page.goto('/dashboard');
  await expectNavHidden(page, NAV.users);
  await page.goto('/users');
  await expect(page).toHaveURL(/\/dashboard/);
});

test('approving a submitted plan through the UI stamps the approver', async ({ page }) => {
  const stamp = Date.now();
  const title = `FY E2E Plan ${stamp}`;

  // Setup: the manager drafts and submits the plan via the API.
  const created = await api(page, 'POST', '/planning/plans/', {
    title, year: new Date().getFullYear(),
  });
  expect(created.status).toBe(201);
  const planId = created.body.id;
  const submitted = await api(page, 'POST', `/planning/plans/${planId}/submit/`);
  expect(submitted.status).toBe(200);

  // Drive the approval through the real UI.
  await page.goto('/planning');
  await page.getByRole('button', { name: 'Annual Audit Plans' }).click();
  const card = page.locator('.plan-card', { hasText: title });
  await expect(card).toBeVisible();
  await card.getByRole('button', { name: 'Approve Plan' }).click();
  await expect(card).toContainText('APPROVED', { timeout: 20_000 });

  // The server recorded it, not just the UI.
  const plan = await api(page, 'GET', `/planning/plans/${planId}/`);
  expect(plan.body.status).toBe('approved');
  expect(plan.body.approved_by).toBeTruthy();
  expect(plan.body.approved_at).toBeTruthy();
});

test('a generated report flips to READY and downloads without a manual refresh', async ({ page }) => {
  const stamp = Date.now();
  const title = `E2E Engagement Report ${stamp}`;

  // Self-provisioning: this used to read whichever engagement the seed data
  // happened to leave behind, which failed as soon as the database was cleared
  // (see reset_business_data in TESTING.md). Draft, submit and approve a plan,
  // then hang an engagement off it — the same shape the other role specs use.
  const created = await api(page, 'POST', '/planning/plans/', {
    title: `FY E2E Report Plan ${stamp}`, year: new Date().getFullYear(),
  });
  expect(created.status).toBe(201);
  const submitted = await api(page, 'POST', `/planning/plans/${created.body.id}/submit/`);
  expect(submitted.status).toBe(200);
  const approved = await api(page, 'POST', `/planning/plans/${created.body.id}/approve/`);
  expect(approved.status).toBe(200);

  const engagement = await api(page, 'POST', '/planning/engagements/', {
    plan: created.body.id, title: `E2E Report Engagement ${stamp}`,
    engagement_type: 'financial',
  });
  expect(engagement.status).toBe(201);
  const engagementId = engagement.body.id;

  // Trigger generation against the live worker thread.
  const generated = await api(page, 'POST', '/reports/generated/', {
    title, format: 'pdf', engagement: engagementId,
  });
  expect(generated.status).toBe(201);
  const reportId = generated.body.id;

  // The reports page polls while any row is generating, so the row must flip
  // to READY here with no manual refresh — exactly the walkthrough's step 2.13.
  await page.goto('/reports');
  const row = page.locator('tr', { hasText: title });
  await expect(row).toBeVisible();
  await expect(row).toContainText('READY', { timeout: 60_000 });

  // And the download serves a real file through the gated export.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    row.getByRole('button', { name: /Download/ }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.pdf$/i);
});
