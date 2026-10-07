// TESTING.md §5 — Auditee. This role holds no capabilities at all, so
// everything it can do runs through object-level checks and everything it sees
// through queryset scoping — the class of gates that each used to 403.
import { test, expect } from '@playwright/test';
import {
  api, createEngagement, createFinding, login, publishFinding, NAV, expectNavHidden,
} from './helpers.js';

// The auditee cannot create their own finding (no WRITE_AUDIT), so the setup
// runs as the auditor in a throwaway context. A CAPA is the exception: the
// auditee formulates the remediation plan for a finding that concerns them
// (spec Step 11), so that one is created through the auditee's own session —
// see the last test, which walks the real form.
async function createOwnedFinding(browser, stamp) {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await login(p, 'EEU-10004', 'user123');

  const auditee = await api(p, 'GET', '/auth/users/?search=EEU-10005&page_size=5');
  const target = auditee.body.results.find(u => u.employee_id === 'EEU-10005');
  const plans = await api(p, 'GET', '/planning/plans/?status=approved&page_size=1');
  // The auditee is named on the *engagement*, not on the finding. This is the
  // whole mechanism — the register's create form asks for no auditee, so the
  // finding inherits the engagement's, and the object-level gate on respond /
  // comment / upload-evidence / dispute matches on that inherited field. Naming
  // it on the finding directly, as this helper used to, proves only that the
  // gate works when someone has already done the job the form leaves undone;
  // every auditee test below passed while the real flow dead-ended.
  const engagement = await createEngagement(p, {
    plan: plans.body.results[0].id, title: `E2E Auditee Eng ${stamp}`,
    department: target.department, auditee: target.id,
  });
  expect(engagement.status).toBe(201);
  const finding = await createFinding(p, {
    engagement: engagement.body.id, title: `E2E Auditee Finding ${stamp}`,
    description: 'Generated for the auditee end-to-end check.',
    severity: 'high', category: 'compliance',
    assigned_to: target.id,
  });
  expect(finding.status).toBe(201);
  // Asserted rather than assumed: if the inheritance ever stops working, this is
  // the line that says so, instead of every test below failing with a 403 and
  // looking like a permissions regression.
  expect(finding.body.auditee).toBe(target.id);

  // The supervisor endorses it, which is what puts it in front of the auditee at
  // all. The auditor above cannot do this — publishing is gated on APPROVE_PLANS,
  // precisely so whoever raised a finding is not also the one who signs it off.
  const supervisorCtx = await browser.newContext();
  const sp = await supervisorCtx.newPage();
  await login(sp, 'EEU-10003', 'user123');
  const published = await publishFinding(sp, finding.body.id);
  expect(published.status).toBe(200);
  await supervisorCtx.close();

  await ctx.close();
  return { findingId: finding.body.id, auditeeId: target.id };
}

async function createOwnedRecords(browser, stamp) {
  const { findingId, auditeeId } = await createOwnedFinding(browser, stamp);
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await login(p, 'EEU-10004', 'user123');
  const capa = await api(p, 'POST', '/corrective/actions/', {
    finding: findingId, title: `E2E Auditee CAPA ${stamp}`,
    description: 'Remediate the compliance gap.',
    recommendation: 'Reinforce the control.',
    owner: auditeeId, priority: 'high',
    due_date: new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10),
  });
  expect(capa.status).toBe(201);
  await ctx.close();
  return { findingId, capaId: capa.body.id };
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

test('formulate a remediation plan, then be refused the sign-off', async ({ page, browser }) => {
  const stamp = Date.now();
  // Created as the auditor: a finding must hang off a failed procedure, which
  // the auditee has no capability to raise.
  const { findingId } = await createOwnedFinding(browser, stamp);
  const title = `E2E Auditee Proposal ${stamp}`;

  await page.goto('/capa');
  await page.getByRole('button', { name: 'Formulate Remediation Plan' }).click();

  // The owner picker is replaced by the auditee's own name: the server forces
  // `owner` to the requester, so a select here would discard whatever it showed.
  await expect(page.locator('#capa_finding')).toBeVisible();
  await expect(page.locator('#capa_owner')).toHaveCount(0);

  await page.locator('#capa_finding').selectOption(String(findingId));
  await page.locator('#capa_title').fill(title);
  await page.locator('#capa_description')
    .fill('Reinstate dual authorisation over the journal entry workflow.');
  await page.locator('#capa_recommendation')
    .fill('Configure the ERP approval workflow and re-test next cycle.');
  await page.locator('#capa_due_date')
    .fill(new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10));
  await page.locator('button[type="submit"][form="capa-form"]').click();

  // Persistence, polled rather than read once: the click returns as soon as the
  // form is submitted, so an immediate read races the POST. Ordered by due_date,
  // so the new row's page is not predictable — search for it instead.
  const listUrl = `/corrective/actions/?search=${encodeURIComponent(title)}`;
  await expect.poll(
    async () => (await api(page, 'GET', listUrl)).body.count,
    { timeout: 20_000 },
  ).toBe(1);

  // It landed as a proposal, owned by its author, not as an assigned task.
  const proposed = (await api(page, 'GET', listUrl)).body.results[0];
  expect(proposed.status).toBe('pending_approval');
  expect(proposed.owner).toBeTruthy();

  // And the sign-off is not theirs to give — the whole point of the state it
  // landed in. Historically this endpoint 403'd at creation, so neither half of
  // Step 11 existed to assert.
  const attempt = await api(page, 'POST', `/corrective/actions/${proposed.id}/approve/`);
  expect(attempt.status).toBe(403);
  const after = await api(page, 'GET', `/corrective/actions/${proposed.id}/`);
  expect(after.body.status).toBe('pending_approval');
});
