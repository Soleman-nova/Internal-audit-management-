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

    // Everything below hinges on this: logout only takes the Logto path while
    // `authMethod` is still 'logto'. It is cleared by `clearSession()`, which the
    // 401 interceptor now calls — so assert the premise here rather than letting a
    // downgrade surface sixty lines later as an unexplained "no end-session
    // request", which reads like a flaky test rather than a state change.
    expect(await page.evaluate(() => localStorage.getItem('authMethod'))).toBe('logto');

    // Marks this document so the wait below can tell it from the one the
    // end-session redirect lands on.
    await page.evaluate(() => {
      window.__preSignOutDoc = true;
    });

    await page.locator('.sidebar-footer .logout-btn').click();

    // 1. That Logto's *own* session was ended — the half a sign-out clearing only
    //    our tokens would fail, and what keeps the next "Sign in with Logto" from
    //    completing silently with no credential prompt.
    //
    //    Polled, and deliberately *not* gated on the URL. The URL is no longer a
    //    proxy for "the round trip finished": the route guard leaves a protected
    //    page as a router push the moment the session is cleared, so it becomes
    //    /login while the SDK is still resolving its discovery document. Asserting
    //    the URL first and reading this array after was a race with the very thing
    //    being asserted — it cost ~12% of runs, with the sign-out in fact working
    //    (the page console showed `signOut` resolving in 4 of the 5 failures).
    await expect.poll(
      () => ssoRequests.find((url) => url.includes('/oidc/session/end')) ?? null,
      { timeout: 15_000, message: "logout never reached Logto's end-session endpoint" },
    ).not.toBeNull();
    const endSession = ssoRequests.find((url) => url.includes('/oidc/session/end'));
    expect(endSession).toContain('post_logout_redirect_uri=');

    // 2. We land back on /login — and, crucially, stay logged out after the full
    //    reload rather than being resurrected from localStorage.
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

    // The end-session 302 sends the browser to a fresh /login document. Wait for
    // it to replace this one before reading storage, or the read can land in a
    // context that is being destroyed mid-navigation (`page.evaluate: Execution
    // context was destroyed`), which is a third way this test was flaky.
    await page.waitForFunction(() => !window.__preSignOutDoc);

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
  });

  // 3. This assertion was removed once as "racy, cause unknown" and is back now
  //    that the cause is known — it was the app's bug, not the test's flakiness.
  //
  //    What it looked like: the end-session assertion failed on roughly 10-40% of
  //    runs, always with an empty request log, while every other assertion in this
  //    test passed every time.
  //
  //    What it was. `logout()` clears the session *before* handing off to the SDK
  //    (deliberately — an unreachable Logto must still leave you signed out). The
  //    app stays mounted while that happens, so its in-flight requests go out with
  //    no access token and come back 401 in a burst. The interceptor reads a 401 as
  //    "the session is over" and answers it with `clearSession()` plus a *hard
  //    navigation* to /login — and that navigation raced the SDK's own navigation
  //    to /oidc/session/end. Both end on /login, so the sign-out looked correct
  //    either way; what was lost was Logto's session, silently left alive. When the
  //    interceptor won, it also cancelled the in-flight discovery fetch, which is
  //    why the request log came back empty, and why the failure looked like the
  //    SDK never starting.
  //
  //    Measured, not inferred: instrumenting localStorage/fetch/click ordering in
  //    the page put the failures at 4/40 runs, every one of them with the
  //    interceptor's redirect landing ~50-60ms after the click and ~25-35ms after
  //    the discovery fetch started. Disabling only that redirect took the same
  //    run to 0/40. The fix (`beginSignOut` in apiClient.js) makes the interceptor
  //    stand down while a sign-out is in progress, so it no longer competes for the
  //    navigation. The premise assertion above still holds: the 401s were never
  //    downgrading `authMethod`.
  //
  //    Verified the other way too: with the new guard deleted, 3 of 50 runs fail
  //    here again with the original `requests seen: []`; with it, 0 of 40 do.

  test('0.6 an expired session still reaches /login after a failed Logto sign-out', async ({ page }) => {
    // The regression test for the guard's *reset*, which is the half of the fix
    // that is easy to lose and silent when it breaks.
    //
    // `beginSignOut` suppresses the 401 interceptor's redirect. If it were never
    // cleared, it would keep suppressing it — but only until the next page load,
    // since it is module state. The dangerous case is therefore the sign-out that
    // does NOT cause a page load: when Logto is unreachable, `signOut` never
    // navigates, and the user reaches /login through the router instead. Live in
    // the same document, the guard would still be set, and the *next* session's
    // expiry would clear the tokens with no redirect — the exact stranded-user
    // state 3.2 was fixed to prevent.
    await login(page, 'EEU-10002', 'user123');
    await page.evaluate(() => localStorage.setItem('authMethod', 'logto'));

    // Logto unreachable: no discovery document, so `signOut` throws before it can
    // navigate anywhere. This also pins the other half of the fix — that logout
    // does not *depend* on a 401 to get the user off the page. The guard suppresses
    // the interceptor's redirect here, so the route guard has to be what moves
    // them; when it read localStorage without subscribing to the auth context it
    // did not, and the user was left standing on the page they had just signed
    // out of.
    await page.route('**/oidc/**', (route) => route.abort());
    await page.locator('.sidebar-footer .logout-btn').click();
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

    // Marks that everything from here on shares one document, so the premise
    // above can be asserted rather than assumed.
    await page.evaluate(() => {
      window.__sameDocument = true;
    });

    // Sign back in *without a page load* — this is the whole point of the test,
    // and `helpers.login` cannot be used here because it starts with
    // `page.goto('/login')`, which reloads the document and resets the very module
    // state under test. Driving the form directly keeps us in the same document,
    // which is the only situation in which a stale guard can do harm.
    await page.locator('#login-employee-id').fill('EEU-10002');
    await page.locator('#login-password').fill('user123');
    await page.locator('#login-submit-btn').click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
    // Premise: no reload happened, so module state really did survive.
    expect(await page.evaluate(() => window.__sameDocument)).toBe(true);

    // Now expire the session in the SPA, with no page load to reset anything.
    // An unreadable token counts as *not* expired (see `isTokenExpired`), so the
    // app renders and its requests 401; the refresh then fails on the same
    // garbage, which is the "session is over" branch the interceptor redirects on.
    await page.evaluate(() => {
      window.__survivedNav = true;
      localStorage.setItem('accessToken', 'expired.junk.token');
      localStorage.setItem('refreshToken', 'expired.junk.token');
    });

    // Opening another page makes the app fire a request that will 401. This click is
    // best-effort, not the mechanism: the dashboard already polls notifications every
    // 30 s, so the redirect arrives on its own. Racing it is what made this flaky —
    // when the poll won, the navigation detached the nav item mid-click and the click
    // timed out at 90 s waiting for an element that would never come back. Both routes
    // end at /login with a cleared session, which is what the assertions below check.
    await page.locator('.sidebar-nav').getByText('Audit Planning')
      .click({ timeout: 5_000 })
      .catch(() => {});

    // Longer than the poll interval, so the poll can be the trigger.
    await expect(page).toHaveURL(/\/login/, { timeout: 40_000 });
    // A *full page load* is the point here, and it is what distinguishes this from
    // the assertion above: nothing has cleared the auth context, so the route guard
    // has not re-rendered and the interceptor's own redirect is the only thing that
    // can have moved us. If the guard were still suppressing it, we would be sitting
    // on /planning with no way out.
    expect(await page.evaluate(() => window.__survivedNav)).toBeUndefined();
  });
});
