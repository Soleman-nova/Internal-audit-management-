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

test('an invalid finding form names the fields that need attention', async ({ page }) => {
  // Regression guard for a bug that shipped silently. Six validated forms ran
  // `if (hasErrors(errors)) { setFormErrors(errors); return; }` — collecting the
  // errors, storing them, and then rendering nothing and saying nothing, so a
  // refused submit looked like a dead button. Every other test in this suite
  // submits *valid* data, which is precisely why nothing caught it: the only way
  // to see this bug is to submit an invalid form, and nothing did.
  await page.goto('/findings');
  await page.getByRole('button', { name: /Log Finding/i }).click();

  // Title, description and recommendation are all required, so an empty submit
  // must be refused. The button lives in the modal footer outside the <form> and
  // targets it by id.
  await page.locator('button[type="submit"][form="finding-form"]').click();

  const banner = page.locator('[role="alert"]').filter({ hasText: 'need attention' });
  await expect(banner).toBeVisible({ timeout: 10_000 });

  // It has to *name* them. "Some fields need attention" on its own leaves the user
  // hunting for which, which is the half of the defect that matters.
  await expect(banner).toContainText('Title');
  await expect(banner).toContainText('Description');

  // And the modal is still open — a refused submit must not read as a success.
  await expect(page.locator('#finding-form')).toBeVisible();
});

test('switching engagement swaps the findings on screen', async ({ page }) => {
  // The FindingsPage was rewritten to drive its findings request from the picker's
  // value instead of calling `fetchFindings` by hand from the tail of the
  // engagements load. Nothing else in this suite touched that wiring — the specs
  // that mention findings only mount the page or deep-link to a detail route — so
  // without this the refactor's core behaviour ships unverified.
  const stamp = Date.now();
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const planId = plans.body.results[0].id;

  const engagementWithFinding = async (name, title) => {
    const eng = await api(page, 'POST', '/planning/engagements/', {
      plan: planId, title: `${name} ${stamp}`, engagement_type: 'financial',
    });
    expect(eng.status).toBe(201);
    const finding = await api(page, 'POST', '/findings/findings/', {
      engagement: eng.body.id, title,
      description: 'Seeded for the engagement-switch check.',
      severity: 'medium', category: 'operational',
    });
    expect(finding.status).toBe(201);
    return eng.body.id;
  };

  const engA = await engagementWithFinding('E2E Switch A', `Alpha ${stamp}`);
  const engB = await engagementWithFinding('E2E Switch B', `Beta ${stamp}`);

  await page.goto('/findings');
  const picker = page.locator('#findings_engagement');
  await expect(picker).toBeVisible();

  await picker.selectOption(String(engA));
  // The positive assertion first: it waits for the refetch, which is what makes
  // the negative one below mean "the list was replaced" rather than "the refetch
  // has not landed yet".
  await expect(page.locator('.findings-list')).toContainText(`Alpha ${stamp}`);
  await expect(page.locator('.findings-list')).not.toContainText(`Beta ${stamp}`);

  await picker.selectOption(String(engB));
  await expect(page.locator('.findings-list')).toContainText(`Beta ${stamp}`);
  await expect(page.locator('.findings-list')).not.toContainText(`Alpha ${stamp}`);
});

test('a finding logged without touching the picker lands on the engagement shown', async ({ page }) => {
  // The picker's selection reaches state only when the user touches it, so the
  // page holds '' while displaying the first engagement. Reading that raw value
  // when building the create payload posts an empty engagement id: the save 400s,
  // the modal stays open and the finding is lost — on the one path a user takes
  // when the default engagement is already the one they want. This submits
  // without selecting anything, deliberately.
  const stamp = Date.now();
  const title = `Picker default finding ${stamp}`;
  await page.goto('/findings');

  const picker = page.locator('#findings_engagement');
  await expect(picker).toBeVisible();
  // Something is selected on arrival. That is what the save below depends on.
  await expect(picker).not.toHaveValue('');
  const shownEngagement = await picker.inputValue();

  await page.getByRole('button', { name: /Log Finding/i }).click();
  await page.locator('#finding_title').fill(title);
  await page.locator('#finding_description').fill('Logged without touching the engagement picker.');
  await page.locator('#finding_recommendation').fill('Confirm the displayed engagement is used.');
  await page.locator('button[type="submit"][form="finding-form"]').click();

  // The modal closes only on a successful save.
  await expect(page.locator('#finding-form')).not.toBeVisible({ timeout: 15_000 });
  await expect(page.locator('.findings-list')).toContainText(title);
  // The new row is also the one being inspected, so the prepend keeps the pane in
  // step with the list rather than leaving the previous finding selected.
  await expect(page.locator('.detail-column')).toContainText(title);

  // It reached the server against the engagement that was on screen, not against
  // nothing.
  const list = await api(page, 'GET', `/findings/findings/?engagement=${shownEngagement}&page_size=100`);
  expect(list.body.results.some(f => f.title === title)).toBe(true);
});
