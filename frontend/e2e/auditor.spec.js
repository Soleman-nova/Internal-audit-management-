// TESTING.md §4 — Lead Auditor.
// The refresh checks are the point of this whole suite: a handler that mutates
// local state and shows a success toast without calling the API passes every
// backend test, and only a reload catches it (README §Testing).
import { test, expect } from '@playwright/test';
import { api, NAV, expectNavHidden } from './helpers.js';

async function setupProgram(page, stamp) {
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const planId = plans.body.results[0].id;
  const engagement = await api(page, 'POST', '/planning/engagements/', {
    plan: planId, title: `E2E Auditor Eng ${stamp}`,
    engagement_type: 'financial',
  });
  expect(engagement.status).toBe(201);
  const program = await api(page, 'POST', '/execution/programs/', {
    engagement: engagement.body.id, title: `E2E Auditor Program ${stamp}`,
  });
  expect(program.status).toBe(201);

  const p1 = await api(page, 'POST', '/execution/procedures/', {
    program: program.body.id, step_number: '1',
    title: `Procedure One ${stamp}`, description: 'Inspect the supporting documentation.',
    procedure_type: 'substantive',
  });
  const p2 = await api(page, 'POST', '/execution/procedures/', {
    program: program.body.id, step_number: '2',
    title: `Procedure Two ${stamp}`, description: 'Recalculate the sample totals.',
    procedure_type: 'analytical',
  });
  expect(p1.status).toBe(201);
  expect(p2.status).toBe(201);
  return { engagementId: engagement.body.id, programId: program.body.id };
}

async function openEngagement(page, engagementId) {
  await page.goto('/execution');
  await page.locator('#active_engagement').selectOption(String(engagementId));
}

test('an edited procedure survives a reload', async ({ page }) => {
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);
  const newTitle = `Renamed procedure ${stamp}`;

  await openEngagement(page, engagementId);
  await page.locator('.procedure-item-card').first().locator('button[title="Edit"]').click();
  await page.locator('#proc_title').fill(newTitle);
  await page.locator('button[type="submit"][form="procedure-form"]').click();
  await expect(page.locator('.procedure-list')).toContainText(newTitle);

  // The edit must have PATCHed, not POSTed a duplicate…
  const list = await api(page, 'GET', `/execution/procedures/?program=${programId}`);
  expect(list.body.count).toBe(2);
  expect(list.body.results.some(p => p.title === newTitle)).toBe(true);

  // …and survive the reload.
  await page.reload();
  await openEngagement(page, engagementId);
  await expect(page.locator('.procedure-list')).toContainText(newTitle);
});

test('a deleted procedure stays deleted after a reload', async ({ page }) => {
  const stamp = Date.now();
  const { engagementId } = await setupProgram(page, stamp);
  const goneTitle = `Procedure Two ${stamp}`;

  await openEngagement(page, engagementId);
  const card = page.locator('.procedure-item-card', { hasText: goneTitle });
  await expect(card).toBeVisible();
  page.on('dialog', d => d.accept());
  await card.locator('button[title="Delete"]').click();
  await expect(card).not.toBeVisible();

  await page.reload();
  await openEngagement(page, engagementId);
  await expect(page.locator('.procedure-list')).not.toContainText(goneTitle);
});

test('a status change survives a reload', async ({ page }) => {
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);

  await openEngagement(page, engagementId);
  const firstCard = page.locator('.procedure-item-card').first();
  await firstCard.locator('select').selectOption('in_progress');
  await expect(firstCard.locator('select')).toHaveValue('in_progress');

  await page.reload();
  await openEngagement(page, engagementId);
  await expect(page.locator('.procedure-item-card').first().locator('select')).toHaveValue('in_progress');

  // The server really holds it.
  const list = await api(page, 'GET', `/execution/procedures/?program=${programId}`);
  expect(list.body.results.some(p => p.status === 'in_progress')).toBe(true);
});

test('submitting the program for review works (the old submit-for-review 404)', async ({ page }) => {
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);

  await openEngagement(page, engagementId);
  await page.getByRole('button', { name: 'Submit for Review' }).click();

  // The submission is async — the UI badge flips before the API has committed.
  await expect(page.locator('.program-header')).toContainText('SUBMITTED', { timeout: 20_000 });

  const record = await api(page, 'GET', `/execution/programs/${programId}/`);
  expect(record.body.status).toBe('submitted');
});

test('auditor cannot approve a plan (403)', async ({ page }) => {
  await page.goto('/dashboard');
  await expectNavHidden(page, NAV.auditTrail, NAV.users);

  // Create a fresh draft plan so the check never depends on leftover state.
  const stamp = Date.now();
  const plan = await api(page, 'POST', '/planning/plans/', {
    title: `E2E Blocked Plan ${stamp}`, year: new Date().getFullYear(),
  });
  expect(plan.status).toBe(201);
  const attempt = await api(page, 'POST', `/planning/plans/${plan.body.id}/approve/`);
  expect(attempt.status).toBe(403);
});

test('deep-link to the 25th finding still renders', async ({ page }) => {
  // Seed enough findings that the one we deep-link to is off the first page.
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const engagement = await api(page, 'POST', '/planning/engagements/', {
    plan: plans.body.results[0].id, title: `E2E Deep Link ${Date.now()}`,
    engagement_type: 'financial',
  });
  expect(engagement.status).toBe(201);

  let targetId = null;
  for (let i = 0; i < 25; i += 1) {
    const created = await api(page, 'POST', '/findings/findings/', {
      engagement: engagement.body.id,
      title: `Deep-link finding ${i} ${Date.now()}`,
      description: 'Generated for the deep-link regression check.',
      severity: 'medium',
      category: 'operational',
    });
    expect(created.status).toBe(201);
    targetId = created.body.id;
  }

  await page.goto(`/findings/${targetId}`);
  await expect(page.locator('body')).toContainText('Deep-link finding 24', { timeout: 20_000 });
});
