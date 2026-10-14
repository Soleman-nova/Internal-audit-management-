// TESTING.md — Executive Dashboard: the APPROVE_PLANS gate and the KPI band.
// Runs as the supervisor (who holds APPROVE_PLANS); the negative half switches
// to the auditor through the real login form, so both sides of the gate are
// exercised in one file.
import { test, expect } from '@playwright/test';
import { api, login, signOut, NAV, expectNavVisible, expectNavHidden } from './helpers.js';

const METRIC_GROUPS = [
  'plan_completion', 'engagement_progress', 'findings_aging',
  'capa', 'repeat_findings', 'compliance_trend',
];

test('supervisor: nav item, KPI band, and the metric groups behind it', async ({ page }) => {
  await page.goto('/dashboard');
  // The nav item is the cosmetic half of the gate; the API assertion below is
  // the real one.
  await expectNavVisible(page, NAV.executive);

  await page.goto('/executive');
  // Six tiles — plan completion, compliance, open findings, overdue findings,
  // CAPA implementation, repeat rate. Waiting on the tile count is waiting for
  // the payload to land, so an error state or a permanent skeleton fails here
  // rather than passing on an empty screen.
  await expect(page.locator('.kpi-band-6 .kpi-cell')).toHaveCount(6, { timeout: 20_000 });
  await expect(page.locator('.exec-filters')).toBeVisible();

  const exec = await api(page, 'GET', '/auth/dashboard/executive/');
  expect(exec.status).toBe(200);
  for (const key of METRIC_GROUPS) {
    expect(exec.body[key], `${key} missing from the payload`).toBeTruthy();
  }
  // The structures the page indexes into directly.
  expect(typeof exec.body.plan_completion.rate).toBe('number');
  expect(exec.body.findings_aging.buckets).toHaveLength(4);
});

test('auditor: no nav item, a 403 from the API, a bounce from the route', async ({ page }) => {
  // The negative half needs a role without APPROVE_PLANS, but this project's
  // storage state is the supervisor's — so switch identity through the real
  // login form, which is also what a human would do.
  await page.goto('/dashboard');
  await signOut(page);
  await login(page, 'EEU-10004', 'user123');

  await expectNavHidden(page, NAV.executive);

  const exec = await api(page, 'GET', '/auth/dashboard/executive/');
  expect(exec.status).toBe(403);

  // A direct URL is bounced by the route guard, not merely hidden from the nav.
  await page.goto('/executive');
  await expect(page).toHaveURL(/\/dashboard/);
});
