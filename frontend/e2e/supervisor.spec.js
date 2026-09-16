// TESTING.md §3 — Supervisor.
import { test, expect } from '@playwright/test';
import { api, NAV, expectNavVisible, expectNavHidden } from './helpers.js';

test('/users is blocked but Audit Trail is reachable', async ({ page }) => {
  await page.goto('/dashboard');
  await expectNavVisible(page, NAV.auditTrail);
  await expectNavHidden(page, NAV.users);
  await page.goto('/users');
  await expect(page).toHaveURL(/\/dashboard/);
  await page.goto('/audit-trail');
  await expect(page).toHaveURL(/\/audit-trail/);
});

test('risk parameters stay read-only: a direct POST is 403', async ({ page }) => {
  await page.goto('/risk');
  // The weightings card renders without a manage control for this role.
  await expect(page.locator('.risk-view')).toContainText('Risk Parameter Weightings');
  const attempt = await api(page, 'POST', '/risk/parameters/', {
    name: 'Blocked for supervisors', category: 'operational', weight: 0.5,
  });
  expect(attempt.status).toBe(403);
});

test('approving fieldwork through the UI (the old approve-fieldwork 404)', async ({ page }) => {
  const stamp = Date.now();
  const programTitle = `E2E Program ${stamp}`;

  // Setup via API: an approved plan → engagement → program → submitted.
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  expect(plans.body.count).toBeGreaterThan(0);
  const planId = plans.body.results[0].id;

  const engagement = await api(page, 'POST', '/planning/engagements/', {
    plan: planId, title: `E2E Engagement ${stamp}`,
    engagement_type: 'financial', department: plans.body.results[0].directorate || null,
  });
  expect(engagement.status).toBe(201);
  const engagementId = engagement.body.id;

  const program = await api(page, 'POST', '/execution/programs/', {
    engagement: engagement.body.id, title: programTitle,
  });
  expect(program.status).toBe(201);

  const submitted = await api(page, 'POST', `/execution/programs/${program.body.id}/submit/`);
  expect(submitted.status).toBe(200);

  // Approve it through the real UI.
  await page.goto('/execution');
  await page.locator('#active_engagement').selectOption(String(engagementId));
  await expect(page.getByRole('heading', { name: programTitle })).toBeVisible();
  await page.getByRole('button', { name: 'Review & Approve' }).click();
  await page.getByRole('button', { name: 'Approve Program' }).click();

  // The approval is async — wait for the UI badge to flip before querying the
  // API, or the GET races the POST.
  await expect(page.locator('.program-header')).toContainText('APPROVED', { timeout: 20_000 });

  // The server recorded the approval, not just the button.
  const record = await api(page, 'GET', `/execution/programs/${program.body.id}/`);
  expect(record.body.status).toBe('approved');
  expect(record.body.approved_by).toBeTruthy();
});
