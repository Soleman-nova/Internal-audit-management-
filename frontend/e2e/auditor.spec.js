// TESTING.md §4 — Lead Auditor.
// The refresh checks are the point of this whole suite: a handler that mutates
// local state and shows a success toast without calling the API passes every
// backend test, and only a reload catches it (README §Testing).
import { test, expect } from '@playwright/test';
import {
  api, createEngagement, createFinding, login, publishFinding, NAV, expectNavHidden,
} from './helpers.js';

async function setupProgram(page, stamp) {
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const planId = plans.body.results[0].id;
  const engagement = await createEngagement(page, {
    plan: planId, title: `E2E Auditor Eng ${stamp}`,
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

/**
 * Take a program to `approved` through the routes that are supposed to own it.
 *
 * `status` is read-only on the program serializer, so a PATCH cannot do this any
 * more — and it should not have been able to: `approve` is gated on
 * APPROVE_PLANS, so the auditor who prepared the program cannot sign it off. That
 * is why this needs a second session rather than just another request.
 */
async function approveProgram(browser, programId) {
  const supervisorCtx = await browser.newContext();
  const sp = await supervisorCtx.newPage();
  await login(sp, 'EEU-10003', 'user123');
  expect((await api(sp, 'POST', `/execution/programs/${programId}/submit/`)).status).toBe(200);
  expect((await api(sp, 'POST', `/execution/programs/${programId}/approve/`)).status).toBe(200);
  await supervisorCtx.close();
}

/**
 * Close a program the way the application does: every step gets an outcome first,
 * then the `complete` action. Left to a PATCH this would assert that a program
 * can be closed with its fieldwork untouched — which is exactly what the action
 * refuses.
 */
async function completeProgram(page, programId) {
  const outstanding = await api(page, 'GET', `/execution/procedures/?program=${programId}`);
  for (const proc of outstanding.body.results) {
    expect(
      (await api(page, 'PATCH', `/execution/procedures/${proc.id}/`, {
        status: 'completed',
      })).status,
    ).toBe(200);
  }
  return api(page, 'POST', `/execution/programs/${programId}/complete/`);
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

test('a second procedure can be added through the UI on an approved program', async ({ page, browser }) => {
  // Every other procedure test in this file creates through the API, which is
  // exactly why this shipped broken: the "Add First Procedure" button in the empty
  // state had no status gate, while the header's "Add Procedure" required
  // draft/active and Edit/Delete required draft. So on an approved program you
  // added one procedure and every control for a second one disappeared — and the
  // API never had that limit, which is what made it invisible to the suite.
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);

  await approveProgram(browser, programId);
  const record = await api(page, 'GET', `/execution/programs/${programId}/`);
  expect(record.body.status).toBe('approved');

  const newTitle = `Procedure three ${stamp}`;
  await openEngagement(page, engagementId);

  // The regression assertion: on an approved program this button used to be absent.
  const add = page.getByRole('button', { name: 'Add Procedure' });
  await expect(add).toBeVisible();
  await add.click();

  await page.locator('#proc_title').fill(newTitle);
  // `description` is required with a 10-character minimum, so a form carrying only
  // the title is refused — which is what the first version of this test did, and
  // the refusal is silent apart from the error summary.
  await page.locator('#proc_description').fill('Confirm the procedure was created through the modal.');
  await page.locator('button[type="submit"][form="procedure-form"]').click();
  await expect(page.locator('.procedure-list')).toContainText(newTitle);

  // It reached the server against the same program, and the reload proves the row
  // is the server's rather than a line of local state.
  const list = await api(page, 'GET', `/execution/procedures/?program=${programId}`);
  expect(list.body.count).toBe(3);

  await page.reload();
  await openEngagement(page, engagementId);
  await expect(page.locator('.procedure-list')).toContainText(newTitle);
});

test('procedure controls are locked once the program is completed', async ({ page, browser }) => {
  // The other half of the rule: completed is the one status that does close the
  // program, so the control has to disappear *and* say why — a vanished button on
  // its own reads as a fault rather than as a rule.
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);

  await approveProgram(browser, programId);
  expect((await completeProgram(page, programId)).status).toBe(200);

  await openEngagement(page, engagementId);
  await expect(page.locator('.procedure-item-card').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add Procedure' })).toBeHidden();
  await expect(page.locator('.procedure-list-section')).toContainText('locked');

  // And the empty state, which is where the reported bug actually lived: that
  // button carried no status check at all, so a program with no procedures offered
  // a way in whatever its status — which is how exactly one procedure used to get
  // added before every control for a second one disappeared.
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const bareEngagement = await createEngagement(page, {
    plan: plans.body.results[0].id, title: `E2E Bare Engagement ${stamp}`,
  });
  expect(bareEngagement.status).toBe(201);
  const bareProgram = await api(page, 'POST', '/execution/programs/', {
    engagement: bareEngagement.body.id, title: `E2E Bare Program ${stamp}`,
  });
  expect(bareProgram.status).toBe(201);
  // A program with no procedures has nothing outstanding, so it closes outright —
  // the gate is about fieldwork that has not happened, not about an empty list.
  expect(
    (await api(page, 'POST', `/execution/programs/${bareProgram.body.id}/complete/`)).status,
  ).toBe(200);

  await openEngagement(page, bareEngagement.body.id);
  await expect(page.getByRole('button', { name: 'Add First Procedure' })).toBeHidden();
});

test('a program with fieldwork still outstanding cannot be completed', async ({ page, browser }) => {
  // The gate the `complete` action exists to enforce. A program whose steps are
  // still pending is fieldwork that has not happened, and `completed` is what
  // locks every procedure control on the board — so closing it early presented
  // unfinished work as finished and immutable. This used to be a plain PATCH that
  // checked nothing at all.
  const stamp = Date.now();
  const { programId } = await setupProgram(page, stamp);
  await approveProgram(browser, programId);

  const refused = await api(page, 'POST', `/execution/programs/${programId}/complete/`);

  expect(refused.status).toBe(400);
  expect(refused.body.detail).toContain('2 procedure(s)');
  // And the steps are named, because "you cannot close this" without saying what
  // is in the way is a dead end.
  expect(refused.body.detail).toContain('1');
  expect(refused.body.detail).toContain('2');

  const record = await api(page, 'GET', `/execution/programs/${programId}/`);
  expect(record.body.status).toBe('approved');
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
  const engagement = await createEngagement(page, {
    plan: plans.body.results[0].id, title: `E2E Deep Link ${Date.now()}`,
  });
  expect(engagement.status).toBe(201);

  // One failed procedure parents all 25 findings: the parent link is what the
  // API checks, and a step that found the control wanting can raise more than
  // one finding. Reusing it also saves a request per row.
  const seeded = await createFinding(page, {
    engagement: engagement.body.id,
    title: `Deep-link finding 0 ${Date.now()}`,
    description: 'Generated for the deep-link regression check.',
    severity: 'medium',
    category: 'operational',
  });
  expect(seeded.status).toBe(201);
  const procedureId = seeded.body.procedure;
  let targetId = seeded.body.id;

  for (let i = 1; i < 25; i += 1) {
    const created = await createFinding(page, {
      engagement: engagement.body.id,
      procedure: procedureId,
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
    const eng = await createEngagement(page, {
      plan: planId, title: `${name} ${stamp}`,
    });
    expect(eng.status).toBe(201);
    const finding = await createFinding(page, {
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
  // The *procedure* picker, which is a different control from the engagement
  // picker this test is about — and a required one, since a finding is raised
  // from the step that failed. Choosing it leaves the engagement untouched, so
  // the default-picker path under test is still exercised.
  await page.locator('#finding_procedure').selectOption({ index: 1 });
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

test('a finding awaiting supervisor review cannot be linked to a corrective action', async ({ page }) => {
  // The CAPA picker used to offer every finding the auditor could read, draft
  // ones included, and the server took the link — so a corrective action could be
  // raised against a finding no supervisor had endorsed. The register hides such
  // an action from the auditee and the compiled report drops it, leaving a record
  // the system created and then refused to show anybody. Both halves are checked
  // here: the picker no longer offers it, and a hand-made POST is refused.
  const stamp = Date.now();
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const engagement = await createEngagement(page, {
    plan: plans.body.results[0].id, title: `E2E Unendorsed CAPA ${stamp}`,
  });
  expect(engagement.status).toBe(201);
  const finding = await createFinding(page, {
    engagement: engagement.body.id,
    title: `Unendorsed finding ${stamp}`,
    description: 'Raised but not yet endorsed by a supervisor.',
    severity: 'high',
    category: 'control_deficiency',
  });
  expect(finding.status).toBe(201);
  expect(finding.body.status).toBe('draft');

  await page.goto('/capa');
  // 'Spawn CAPA Task' opens the modal; 'Spawn & Assign CAPA' is its submit.
  await page.getByRole('button', { name: 'Spawn CAPA Task' }).click();

  // The hint first, and not only because it is the thing a confused auditor
  // needs: it renders only once the picker data has arrived and it has something
  // to report, so its presence is what makes the assertion below mean anything.
  // Checking the option count alone would pass on an empty, still-loading select.
  await expect(
    page.getByText('Findings awaiting supervisor review are not listed'),
  ).toBeVisible();
  await expect(
    page.locator('#capa_finding option', { hasText: finding.body.finding_number }),
  ).toHaveCount(0);

  // The server refuses it too — the picker is a convenience, never the gate.
  const refused = await api(page, 'POST', '/corrective/actions/', {
    finding: finding.body.id,
    title: `Refused CAPA ${stamp}`,
    description: 'Should never be created.',
    recommendation: 'Should never be created.',
    due_date: new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10),
  });
  expect(refused.status).toBe(400);
  expect(refused.body.finding[0]).toContain('Pending Supervisor Review');
});

test('a failed procedure says whether its finding has been written up', async ({ page }) => {
  // The two boards disagreed silently: the findings register carried the
  // procedure link in one direction only, so a step that had already produced a
  // finding looked identical on the execution board to one nobody had written up,
  // and "Log Finding" on it led to a form that would happily accept a duplicate.
  // The badge is the answer, and it is asserted against the API rather than the
  // screenshot: a badge rendered from state the server never sent proves nothing.
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);
  const proc = await api(page, 'POST', '/execution/procedures/', {
    program: programId, step_number: '9',
    title: `Failing step ${stamp}`, description: 'Seeded to fail the control test.',
    procedure_type: 'test_of_controls', status: 'failed',
  });
  expect(proc.status).toBe(201);

  await openEngagement(page, engagementId);
  const card = page.locator(`.procedure-item-card:has-text("Failing step ${stamp}")`);
  // No finding yet, so no badge: the positive assertion below would otherwise
  // pass on a badge rendered for every failed step regardless.
  await expect(card).not.toContainText('finding(s) raised');

  await createFinding(page, {
    engagement: engagementId, procedure: proc.body.id,
    title: `Finding off a logged step ${stamp}`,
    description: 'The control named above did not operate.',
    severity: 'high', category: 'control_deficiency',
  });

  await page.reload();
  await page.locator('#active_engagement').selectOption(String(engagementId));
  await expect(card).toContainText('1 finding(s) raised');
});

test('a finding links back to the fieldwork it came from', async ({ page }) => {
  // The other direction of the same link, and the reason the forward one is worth
  // enforcing at all: a finding whose parent step is invisible is an assertion
  // with nothing behind it, and the reader cannot tell an evidenced finding from
  // an assertion someone typed.
  const stamp = Date.now();
  const { engagementId, programId } = await setupProgram(page, stamp);
  const proc = await api(page, 'POST', '/execution/procedures/', {
    program: programId, step_number: '7.2',
    title: `Vouch the ledger ${stamp}`, description: 'Agree each entry to its voucher.',
    procedure_type: 'substantive', status: 'failed',
  });
  const finding = await createFinding(page, {
    engagement: engagementId, procedure: proc.body.id,
    title: `Ledger finding ${stamp}`,
    description: 'Entries were made without supporting vouchers.',
    severity: 'high', category: 'control_deficiency',
  });
  expect(finding.status).toBe(201);

  await page.goto(`/findings/${finding.body.id}`);
  // Named, not merely an id: "7.2" tells the reader nothing.
  await expect(page.getByText(`7.2. Vouch the ledger ${stamp}`).first()).toBeVisible();

  // And the link resolves — to the right engagement, with that step highlighted,
  // because landing on the right page with no indication of which card to read
  // is the failure the deep link is meant to remove.
  await page.getByText(`7.2. Vouch the ledger ${stamp}`).first().click();
  await expect(page).toHaveURL(new RegExp(`/execution\\?engagement=${engagementId}`));
  await expect(page.locator('.procedure-item-card.focused-step')).toContainText(
    `Vouch the ledger ${stamp}`,
  );
});

test('a finding offers its own corrective action, pre-linked and prefilled', async ({ page, browser }) => {
  // The third stage was only reachable by going to the follow-up page and finding
  // the record in a dropdown of every finding in the register — at the exact
  // moment the user already knows which record they mean. Asserted end to end:
  // the section reports no action, the deep link opens the form against *this*
  // finding rather than a blank one, and the action it creates is linked back.
  const stamp = Date.now();
  const plans = await api(page, 'GET', '/planning/plans/?status=approved&page_size=1');
  const engagement = await createEngagement(page, {
    plan: plans.body.results[0].id, title: `E2E Finding-to-CAPA ${stamp}`,
  });
  const finding = await createFinding(page, {
    engagement: engagement.body.id,
    title: `Remediation candidate ${stamp}`,
    description: 'A control that needs a remedy.',
    // The CAPA form prefills its recommendation from the finding, and requires
    // ten characters of it — so a finding logged without one produces a form that
    // cannot be submitted. Seeding it is what makes this test about the handoff
    // rather than about the form's validation.
    recommendation: 'Institute a documented monthly review of the control.',
    severity: 'high', category: 'control_deficiency',
  });
  expect(finding.status).toBe(201);

  // Endorsed first, by a supervisor: an unendorsed finding cannot carry an action
  // at all, so without this the deep link would land on a form the server then
  // refuses — which is the eligibility rule, not a broken link.
  const supervisorCtx = await browser.newContext();
  const sp = await supervisorCtx.newPage();
  await login(sp, 'EEU-10003', 'user123');
  expect((await publishFinding(sp, finding.body.id)).status).toBe(200);
  await supervisorCtx.close();

  await page.goto(`/findings/${finding.body.id}`);
  await expect(page.getByText('No corrective action has been raised')).toBeVisible();
  await page.getByRole('link', { name: /Spawn CAPA Task linked to Finding/i }).click();

  await expect(page).toHaveURL(new RegExp(`/capa\\?finding=${finding.body.id}`));
  // The form opened by itself, against this finding — not a blank form the user
  // has to be trusted to complete correctly.
  await expect(page.locator('#capa_finding')).toHaveValue(String(finding.body.id));
  await expect(page.locator('#capa_title')).toHaveValue(`CAPA: Remediation candidate ${stamp}`);

  await page.locator('#capa_owner').selectOption({ index: 1 });
  await page.locator('#capa_due_date').fill(
    new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10),
  );
  await page.locator('button[type="submit"][form="capa-form"]').click();
  await expect(page.locator('#capa-form')).not.toBeVisible({ timeout: 15_000 });

  const actions = await api(page, 'GET', `/corrective/actions/?finding=${finding.body.id}`);
  expect(actions.body.results).toHaveLength(1);

  // And it is visible from the finding again — the same relationship, read back.
  // Asserted against the list's own hook rather than a card class: the section is
  // styled inline here, so `.card` is not what identifies it and would pass on a
  // match somewhere else on the page.
  await page.goto(`/findings/${finding.body.id}`);
  await expect(page.getByTestId('finding-capa-list')).toContainText(
    `CAPA: Remediation candidate ${stamp}`,
  );
});
