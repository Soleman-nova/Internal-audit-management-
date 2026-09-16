// TESTING.md §0 — the login page.
import { test, expect } from '@playwright/test';
import { login, signOut } from './helpers.js';

// Every seeded role, matching the DEMO_ROLES array in LoginPage.jsx.
// The sidebar shows the role name uppercased, not the employee id.
const DEMO_BUTTONS = [
  { id: '#demo-system-admin', employeeId: 'EEU-10001', role: 'ADMIN' },
  { id: '#demo-audit-manager', employeeId: 'EEU-10002', role: 'AUDIT MANAGER' },
  { id: '#demo-supervisor', employeeId: 'EEU-10003', role: 'SUPERVISOR' },
  { id: '#demo-lead-auditor', employeeId: 'EEU-10004', role: 'AUDITOR' },
  { id: '#demo-auditee', employeeId: 'EEU-10005', role: 'AUDITEE' },
];

test.describe('login page', () => {
  test('0.1 every one-click demo button authenticates', async ({ page }) => {
    for (const demo of DEMO_BUTTONS) {
      await page.goto('/login');
      await page.locator(demo.id).click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
      await expect(page.locator('.sidebar-user .user-role')).toHaveText(demo.role);
      await signOut(page);
    }
  });

  test('0.2 a wrong password is refused without a redirect', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#login-employee-id').fill('EEU-10001');
    await page.locator('#login-password').fill('definitely-wrong');
    await page.locator('#login-submit-btn').click();
    // Two [role=alert] nodes can be live (the inline form error and the toast
    // stack); the inline one is the first in the document.
    await expect(page.locator('[role="alert"]').first()).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test('0.3 a reload keeps the session alive', async ({ page }) => {
    await login(page, 'EEU-10002', 'user123');
    await page.goto('/dashboard');
    await page.reload();
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
