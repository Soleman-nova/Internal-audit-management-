import { expect } from '@playwright/test';

export const API = 'http://localhost:8000/api';

/** Sign in through the real login form and land on the dashboard. */
export async function login(page, employeeId, password) {
  await page.goto('/login');
  await page.locator('#login-employee-id').fill(employeeId);
  await page.locator('#login-password').fill(password);
  await page.locator('#login-submit-btn').click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
}

/** Sign out through the sidebar's logout button. */
export async function signOut(page) {
  await page.locator('.sidebar-footer .logout-btn').click();
  await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });
}

/**
 * Authenticated call to the Django API from inside the page context, reusing
 * the token the app stored in localStorage. If the page is not yet on the app
 * origin (Playwright starts each test on about:blank, where localStorage is
 * unreachable), land on the dashboard first.
 */
export async function api(page, method, path, body) {
  if (!page.url().startsWith('http://localhost:5173')) {
    await page.goto('/dashboard');
  }
  // DRF throttles authenticated requests at 1000/hour. A long-lived dev server
  // across several runs can approach that; retry a short backoff so a burst on
  // the edge of the window does not fail the suite.
  for (let attempt = 0; ; attempt += 1) {
    const result = await page.evaluate(async ({ method, path, body }) => {
      const token = localStorage.getItem('accessToken');
      const res = await fetch(`http://localhost:8000/api${path}`, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await res.text();
      return { status: res.status, body: text ? JSON.parse(text) : null };
    }, { method, path, body });

    if (result.status !== 429 || attempt >= 3) return result;
    await new Promise(r => setTimeout(r, 1500 * (attempt + 1)));
  }
}

/** English sidebar labels (I18nContext.jsx `en` block). */
export const NAV = {
  dashboard: 'Dashboard',
  planning: 'Audit Planning',
  execution: 'Audit Execution',
  findings: 'Findings Registry',
  risk: 'Risk Assessment',
  capa: 'Corrective Actions',
  reports: 'Reports & Analytics',
  users: 'User Management',
  auditTrail: 'Audit Trail',
};

export async function expectNavVisible(page, ...labels) {
  for (const label of labels) {
    await expect(page.locator('.sidebar-nav')).toContainText(label);
  }
}

export async function expectNavHidden(page, ...labels) {
  for (const label of labels) {
    await expect(page.locator('.sidebar-nav')).not.toContainText(label);
  }
}
