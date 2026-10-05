// TESTING.md §3 — Supervisor.
import { test, expect } from '@playwright/test';
import { api, createEngagement, createFinding, publishFinding, NAV, expectNavVisible, expectNavHidden } from './helpers.js';

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

  const engagement = await createEngagement(page, {
    plan: planId, title: `E2E Engagement ${stamp}`,
    department: plans.body.results[0].directorate || null,
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

test('a new finding reads as Pending Supervisor Review until it is endorsed', async ({ page }) => {
  // Two halves of the same report. The register's create form sends no auditee,
  // so the finding inherits the engagement's — and because it is then a real
  // person, the endorsement below actually puts the finding in front of someone
  // rather than publishing it into an audience of NULLs. The label half is here
  // because "Draft" named the wrong party's job: from the moment the lead
  // auditor raises it, the finding is waiting on this role.
  const stamp = Date.now();
  const auditee = await api(page, 'GET', '/auth/users/?search=EEU-10005&page_size=5');
  const target = auditee.body.results.find(u => u.employee_id === 'EEU-10005');

  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const engagement = await createEngagement(page, {
    plan: plans.body.results[0].id, title: `E2E Review Eng ${stamp}`,
    department: target.department, auditee: target.id,
  });
  expect(engagement.status).toBe(201);

  const finding = await createFinding(page, {
    engagement: engagement.body.id,
    title: `Pending review finding ${stamp}`,
    description: 'Seeded to walk the endorsement step.',
    severity: 'high',
    category: 'control_deficiency',
  });
  expect(finding.status).toBe(201);
  // The inheritance is what makes the endorsement meaningful, so it is asserted
  // here rather than left to the auditee specs to trip over as a 403.
  expect(finding.body.auditee).toBe(target.id);

  await page.goto(`/findings/${finding.body.id}`);
  const badge = page.locator('.badge', { hasText: /PENDING SUPERVISOR REVIEW|AWAITING AUDITEE RESPONSE/ });
  await expect(badge).toHaveText('PENDING SUPERVISOR REVIEW', { timeout: 20_000 });

  await page.getByRole('button', { name: 'Publish to Auditee' }).click();

  // Reload, as ever: a handler flipping local state would satisfy everything
  // above without the server having agreed to any of it.
  await expect(badge).toHaveText('AWAITING AUDITEE RESPONSE', { timeout: 20_000 });
  await page.reload();
  await expect(badge).toHaveText('AWAITING AUDITEE RESPONSE');

  const record = await api(page, 'GET', `/findings/findings/${finding.body.id}/`);
  expect(record.body.status).toBe('awaiting_auditee_response');
  expect(record.body.auditee).toBe(target.id);
});

test('verify and close a CAPA in one step (and the finding behind it)', async ({ page }) => {
  // Verification and closure used to be two disconnected halves. The follow-up
  // route recorded a visit and left the action exactly where it was, so a CAPA
  // could be verified as effective and sit in `in_progress` indefinitely; and the
  // only thing that actually closed one was a bare status write that recorded no
  // verification at all. This walks the single route that does both — and the
  // reload is the point of it, as ever: a handler that flipped local state and
  // toasted would pass every assertion before the reload.
  const stamp = Date.now();
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const engagement = await createEngagement(page, {
    plan: plans.body.results[0].id, title: `E2E Verify Eng ${stamp}`,
  });
  expect(engagement.status).toBe(201);

  const finding = await createFinding(page, {
    engagement: engagement.body.id,
    title: `Verify & close finding ${stamp}`,
    description: 'Seeded for the verify-and-close walkthrough.',
    severity: 'high',
    category: 'control_deficiency',
  });
  expect(finding.status).toBe(201);
  // Publishing makes the finding live — and live is the only state the closure
  // cascades from, so an unpublished finding would leave the cascade unproven.
  expect((await publishFinding(page, finding.body.id)).status).toBe(200);

  // Filed by the owner, which is where this step of the flow starts.
  const capa = await api(page, 'POST', '/corrective/actions/', {
    finding: finding.body.id,
    title: `Verify & close CAPA ${stamp}`,
    description: 'Reinstate the control over the journal entry workflow.',
    recommendation: 'Document the control and test it monthly.',
    priority: 'high',
    due_date: new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10),
    status: 'evidence_submitted',
  });
  expect(capa.status).toBe(201, capa.body);
  const capaId = capa.body.id;

  await page.goto(`/capa/${capaId}`);
  const verifyButton = page.getByRole('button', { name: 'Verify & Close CAPA' });
  await expect(verifyButton).toBeVisible();
  await page.locator('#verify_notes').fill('Re-tested the workflow over a full cycle.');
  await verifyButton.click();

  // The card disappears only once `status` is no longer closeable, which is the
  // server's answer — but that is still local state, so it is not the proof.
  await expect(verifyButton).toHaveCount(0, { timeout: 20_000 });
  await page.reload();
  await expect(page.locator('.capa-detail-view')).toContainText('CLOSED');

  const record = await api(page, 'GET', `/corrective/actions/${capaId}/`);
  expect(record.body.status).toBe('closed');
  // The follow-up is what makes the closure a verification rather than a claim,
  // and it is written in the same transaction — so it cannot be missing here.
  expect(record.body.follow_ups.length).toBe(1);
  expect(record.body.follow_ups[0].status).toBe('completed');

  const settled = await api(page, 'GET', `/findings/findings/${finding.body.id}/`);
  expect(settled.body.status).toBe('closed');
});
