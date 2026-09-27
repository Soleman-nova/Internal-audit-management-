// TESTING.md §1 — System Admin.
import { test, expect } from '@playwright/test';
import { api, NAV, expectNavVisible } from './helpers.js';

test('sidebar shows User Management and Audit Trail', async ({ page }) => {
  await page.goto('/dashboard');
  await expectNavVisible(page, NAV.users, NAV.auditTrail);
});

test('creates a user through the UI and the registry lists them', async ({ page }) => {
  const stamp = Date.now();
  const employeeId = `E2E-${stamp}`;
  await page.goto('/users');
  await page.getByRole('button', { name: 'Add Account' }).click();

  await page.locator('#add_first_name').fill('E2E');
  await page.locator('#add_last_name').fill(`Tester${stamp}`);
  await page.locator('#add_username').fill(`e2euser${stamp}`);
  await page.locator('#add_employee_id').fill(employeeId);
  await page.locator('#add_email').fill(`e2e${stamp}@eeu.com`);
  await page.locator('#add_role').selectOption({ label: 'Lead Auditor' });
  await page.locator('#add_password').fill('E2e-pass-123');
  // The submit button lives in the modal footer outside the <form>; it targets
  // the form by its id attribute.
  await page.locator('button[type="submit"][form="add-user-form"]').click();

  // Persistence first — and polled, not asserted once. The click returns as soon
  // as the form is submitted, so a single immediate read races the POST. This is
  // the check a handler that toasts without saving cannot pass.
  await expect.poll(
    async () => (await api(page, 'GET', `/auth/users/?search=${employeeId}`)).body.count,
    { timeout: 20_000 },
  ).toBe(1);

  const found = await api(page, 'GET', `/auth/users/?search=${employeeId}`);
  expect(found.body.results[0].employee_id).toBe(employeeId);

  // Then the registry itself — but NOT by assuming the row lands on page 1. The
  // list is ordered by first_name and every run adds one more `first_name='E2E'`
  // row, so the new row sinks one position per run (within that name block the
  // tiebreaker is employee_id ascending, so the newest sorts last). The original
  // assertion passed only while that block still fit on the page being shown, and
  // it was consequently not repeatable: 36 such rows already exist here, which is
  // why it failed once and then passed again untouched. Widening to the largest
  // page size and walking forward finds the row whatever has accumulated.
  const card = page.locator('.users-list-card');
  await card.locator('.data-table-page-size-select').selectOption('100');

  const next = card.locator('button[aria-label="Next page"]');
  let listed = false;
  for (let attempt = 0; attempt < 15 && !listed; attempt += 1) {
    try {
      // Auto-retrying, so this waits for the page's own fetch to land rather than
      // sleeping a guessed interval.
      await expect(card).toContainText(employeeId, { timeout: 2_000 });
      listed = true;
    } catch {
      // The control is only rendered when there is more than one page.
      if ((await next.count()) === 0 || (await next.isDisabled())) break;
      await next.click();
    }
  }
  expect(listed, `created user ${employeeId} never appeared in the registry`).toBe(true);
});

test('a deactivated user cannot log in', async ({ page, browser }) => {
  // Create the account first (fast path via the API), then deactivate it.
  const stamp = Date.now();
  const employeeId = `E2E-DIS-${stamp}`;
  const created = await api(page, 'POST', '/auth/users/', {
    first_name: 'E2E', last_name: 'Disabled', username: `e2edis${stamp}`,
    employee_id: employeeId, email: `e2edis${stamp}@eeu.com`,
    role: 'auditor', password: 'E2e-pass-123',
  });
  expect(created.status).toBe(201);
  const id = created.body.id;

  const deactivated = await api(page, 'POST', `/auth/users/${id}/deactivate/`);
  expect(deactivated.status).toBe(200);

  const context = await browser.newContext();
  const page2 = await context.newPage();
  await page2.goto('/login');
  await page2.locator('#login-employee-id').fill(employeeId);
  await page2.locator('#login-password').fill('E2e-pass-123');
  await page2.locator('#login-submit-btn').click();
  // Two [role=alert] nodes can be live (inline error + toast); the inline one
  // is first in the document.
  await expect(page2.locator('[role="alert"]').first()).toBeVisible();
  await expect(page2).toHaveURL(/\/login/);
  await context.close();
});

test('an admin password reset lets the new password log in', async ({ page, browser }) => {
  const stamp = Date.now();
  const employeeId = `E2E-RESET-${stamp}`;
  const created = await api(page, 'POST', '/auth/users/', {
    first_name: 'E2E', last_name: 'Reset', username: `e2ereset${stamp}`,
    employee_id: employeeId, email: `e2ereset${stamp}@eeu.com`,
    role: 'auditee', password: 'E2e-pass-123',
  });
  expect(created.status).toBe(201);
  const id = created.body.id;

  const reset = await api(page, 'POST', `/auth/users/${id}/reset-password/`,
    { password: 'Brand-new-pass-9' });
  expect(reset.status).toBe(200);

  const context = await browser.newContext();
  const page2 = await context.newPage();
  await page2.goto('/login');
  await page2.locator('#login-employee-id').fill(employeeId);
  await page2.locator('#login-password').fill('Brand-new-pass-9');
  await page2.locator('#login-submit-btn').click();
  await expect(page2).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await context.close();
});
