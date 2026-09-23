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

  test('0.4 signing out clears the stored session', async ({ page }) => {
    await login(page, 'EEU-10002', 'user123');
    await signOut(page);

    const leftover = await page.evaluate(() => ({
      accessToken: localStorage.getItem('accessToken'),
      refreshToken: localStorage.getItem('refreshToken'),
      user: localStorage.getItem('user'),
      authMethod: localStorage.getItem('authMethod'),
    }));
    expect(leftover).toEqual({
      accessToken: null, refreshToken: null, user: null, authMethod: null,
    });

    // And the guard must actually keep them out, not merely look logged out.
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });

  test('0.5 a Logto session ends SSO and clears locally first', async ({ page }) => {
    // Reproduces the real bug: logout for a Logto session handed off to
    // `signOut`, which navigates away as a *full page load*. AuthProvider
    // re-seeds `user` from localStorage on the way back, so unless the session
    // is cleared first, the round trip silently signs the user back in.
    //
    // It also pins the other half of the contract — that the button actually
    // reaches Logto's end-session endpoint. Dropping only our tokens would leave
    // Logto's own session cookie alive, and the next "Sign in with Logto" would
    // complete silently with no credential prompt.
    await login(page, 'EEU-10002', 'user123');

    // Pretend this session came from Logto.
    await page.evaluate(() => localStorage.setItem('authMethod', 'logto'));

    // Record attempts to reach Logto's OIDC endpoints, then block them. The
    // Logto host is unreachable from the test machine regardless; blocking keeps
    // the pending navigation from tearing the page down mid-assertion.
    const ssoRequests = [];
    await page.route('**/oidc/**', (route) => {
      ssoRequests.push(route.request().url());
      return route.abort();
    });

    // The SDK resolves the end-session URL from the discovery document, so
    // aborting that fetch stops sign-out before it starts — the test would then
    // be asserting on its own block rather than on the app. Serving a discovery
    // document lets sign-out run its real course. Registered after the catch-all,
    // which is what makes it win for this one URL.
    await page.route('**/oidc/.well-known/openid-configuration', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          issuer: 'http://172.16.7.25:3000/oidc',
          authorization_endpoint: 'http://172.16.7.25:3000/oidc/auth',
          token_endpoint: 'http://172.16.7.25:3000/oidc/token',
          end_session_endpoint: 'http://172.16.7.25:3000/oidc/session/end',
          jwks_uri: 'http://172.16.7.25:3000/oidc/jwks',
          response_types_supported: ['code'],
          subject_types_supported: ['public'],
          id_token_signing_alg_values_supported: ['ES384'],
          code_challenge_methods_supported: ['S256'],
          grant_types_supported: ['authorization_code', 'refresh_token'],
          scopes_supported: ['openid', 'offline_access', 'profile', 'email', 'custom_data'],
          token_endpoint_auth_methods_supported: ['none'],
        }),
      })
    );

    // Then play Logto's part and complete the round trip: accept the end-session
    // request and send the browser back to the post-sign-out URI. This is what
    // makes the test faithful — the bug only appeared on the way *back*, when
    // AuthProvider re-reads localStorage after a full page load.
    await page.route('**/oidc/session/end**', (route) => {
      ssoRequests.push(route.request().url());
      return route.fulfill({
        status: 302,
        headers: { location: 'http://localhost:5173/login' },
      });
    });

    await page.reload();
    await page.locator('.sidebar-footer .logout-btn').click();

    // 1. We land back on /login — and, crucially, stay logged out after the full
    //    reload rather than being resurrected from localStorage.
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

    const leftover = await page.evaluate(() => ({
      accessToken: localStorage.getItem('accessToken'),
      refreshToken: localStorage.getItem('refreshToken'),
      user: localStorage.getItem('user'),
      authMethod: localStorage.getItem('authMethod'),
    }));
    expect(leftover).toEqual({
      accessToken: null, refreshToken: null, user: null, authMethod: null,
    });

    // The guard must actually keep them out, not merely look logged out.
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);

    // 2. Logto's end-session really was requested, carrying postSignOutRedirectUri.
    const endSession = ssoRequests.find((url) => url.includes('/session/end'));
    expect(endSession, `no end-session request; saw: ${ssoRequests.join(', ')}`).toBeTruthy();
    expect(decodeURIComponent(endSession)).toContain('post_logout_redirect_uri=http://localhost:5173/login');
  });
});
