// TESTING.md §5 — Auditee. This role holds no capabilities at all, so
// everything it can do runs through object-level checks and everything it sees
// through queryset scoping — the class of gates that each used to 403.
import { test, expect } from '@playwright/test';
import { api, login, NAV, expectNavHidden } from './helpers.js';

// The auditee cannot create their own finding/CAPA (no WRITE_AUDIT), so the
// setup runs as the auditor in a throwaway context.
async function createOwnedRecords(browser, stamp) {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await login(p, 'EEU-10004', 'user123');

  const auditee = await api(p, 'GET', '/auth/users/?search=EEU-10005&page_size=5');
  const target = auditee.body.results.find(u => u.employee_id === 'EEU-10005');
  const plans = await api(p, 'GET', '/planning/plans/?status=approved&page_size=1');
  const engagement = await api(p, 'POST', '/planning/engagements/', {
    plan: plans.body.results[0].id, title: `E2E Auditee Eng ${stamp}`,
    engagement_type: 'financial', department: target.department,
  });
  expect(engagement.status).toBe(201);
  const finding = await api(p, 'POST', '/findings/findings/', {
    engagement: engagement.body.id, title: `E2E Auditee Finding ${stamp}`,
    description: 'Generated for the auditee end-to-end check.',
    severity: 'high', category: 'compliance',
    assigned_to: target.id, auditee: target.id,
  });
  expect(finding.status).toBe(201);
  const capa = await api(p, 'POST', '/corrective/actions/', {
    finding: finding.body.id, title: `E2E Auditee CAPA ${stamp}`,
    description: 'Remediate the compliance gap.',
    recommendation: 'Reinforce the control.',
    owner: target.id, priority: 'high',
    due_date: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10),
  });
  expect(capa.status).toBe(201);
  await ctx.close();
  return { findingId: finding.body.id, capaId: capa.body.id };
}

test('sidebar and dashboard: My Work only, no admin surfaces', async ({ page }) => {
  await page.goto('/dashboard');
  await expectNavHidden(page, NAV.users, NAV.auditTrail);
  await expect(page.locator('body')).toContainText('My Work');
});

test('comment, evidence and dispute on an own finding each succeed', async ({ page, browser }) => {
  const stamp = Date.now();
  const { findingId } = await createOwnedRecords(browser, stamp);
  const commentText = `E2E auditee comment ${stamp}`;

  await page.goto(`/findings/${findingId}`);
  await expect(page.locator('body')).toContainText(`E2E Auditee Finding ${stamp}`);
  await expect(page.getByRole('button', { name: 'Dispute' })).toBeVisible();

  // Comment (historically 403: the action inherited a WRITE_AUDIT gate).
  await page.getByPlaceholder('Write a comment for the audit team…').fill(commentText);
  await page.getByRole('button', { name: 'Post Comment' }).click();
  await expect(page.locator('body')).toContainText(commentText);

  // Evidence upload (historically 403).
  await page.getByPlaceholder('Evidence title').fill('Signed authorisation log');
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'log.txt', mimeType: 'text/plain', buffer: Buffer.from('signed'),
  });
  await page.getByRole('button', { name: 'Attach Evidence' }).click();
  await expect(page.locator('body')).toContainText('Signed authorisation log');

  // Dispute (the lifecycle action the auditee may take).
  await page.getByRole('button', { name: 'Dispute' }).click();
  await expect(page.locator('body')).toContainText('DISPUTED', { timeout: 20_000 });
});

test('resolve and close are neither offered nor allowed', async ({ page, browser }) => {
  const stamp = Date.now();
  const { findingId } = await createOwnedRecords(browser, stamp);

  await page.goto(`/findings/${findingId}`);
  await expect(page.getByRole('button', { name: 'Dispute' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Mark Resolved' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Close Finding' })).toHaveCount(0);

  const attempt = await api(page, 'POST', `/findings/findings/${findingId}/resolve/`);
  expect(attempt.status).toBe(403);
});

test('respond to an owned CAPA with evidence', async ({ page, browser }) => {
  const stamp = Date.now();
  const { capaId } = await createOwnedRecords(browser, stamp);

  await page.goto(`/capa/${capaId}`);
  await page.getByPlaceholder('Describe the progress made…').fill('Controls reinstated.');
  await page.getByPlaceholder('Describe the progress made…').locator('..')
    .locator('select').selectOption('in_progress');
  await page.getByRole('button', { name: 'Submit Response' }).click();

  // Wait for the response to render as a list item in the responses feed. A
  // getByText would also match the textarea's own value, which passes before
  // the POST has committed — the item only appears after the refetch.
  await expect(page.locator('li', { hasText: 'Controls reinstated.' })).toBeVisible({ timeout: 20_000 });

  // The server recorded the response and the status move.
  const capa = await api(page, 'GET', `/corrective/actions/${capaId}/`);
  expect(capa.body.status).toBe('in_progress');
  expect(capa.body.responses.length).toBeGreaterThan(0);
  expect(capa.body.responses[0].response_text).toContain('Controls reinstated');
});
