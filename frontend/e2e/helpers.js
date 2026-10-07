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

    if (result.status !== 429) return result;
    if (attempt >= 3) {
      // Raise rather than return. Handing the 429 body back like any other
      // response is what made this bug expensive to find: the caller went on to
      // read `.results` off `{detail: "Request was throttled…"}` and the spec
      // reported `TypeError: Cannot read properties of undefined (reading
      // 'find')`, naming neither throttling nor the endpoint. Throwing here is
      // the difference between a five-minute diagnosis and an hour.
      throw new Error(
        `API rate limit exhausted after ${attempt + 1} attempts: ${method} ${path}. `
        + 'DRF throttles per user (THROTTLE_USER, default 1000/hour) and the counter lives '
        + "in the running server's process, so restart the backend to clear it — or raise "
        + 'THROTTLE_USER for the e2e server (playwright.config.js sets it, but only when '
        + 'Playwright starts the server itself; reuseExistingServer skips it otherwise).',
      );
    }
    await new Promise(r => setTimeout(r, 1500 * (attempt + 1)));
  }
}

/**
 * Create an engagement over the API.
 *
 * Objective and scope are mandatory on the engagement endpoint — an engagement
 * is where an audit gets its bounds, so the API refuses one without both. They
 * are defaulted here rather than restated at each of the seed sites, so a spec
 * can keep talking about the behaviour it is actually testing. Pass `fields` to
 * override anything, including the two defaults.
 */
export async function createEngagement(page, fields) {
  return api(page, 'POST', '/planning/engagements/', {
    engagement_type: 'financial',
    objectives: 'Verify the control under test operates as described.',
    scope: 'The records seeded by this end-to-end spec.',
    ...fields,
  });
}

/**
 * Create a finding over the API, together with the failed procedure it must hang
 * off.
 *
 * A finding is only accepted from a procedure marked failed, and a procedure
 * needs a program — whose `engagement` is a OneToOne, so the program is reused
 * when the engagement already has one rather than created twice. Pass an
 * existing `procedure` id to hang several findings off one step, which is what
 * the specs that seed a page of findings do: it saves a request per row.
 *
 * Returns the `api()` response for the *finding*, so call sites read
 * `.status`/`.body.id` exactly as they did before.
 */
export async function createFinding(page, { engagement, procedure, ...fields }) {
  let procedureId = procedure;
  if (!procedureId) {
    const existing = await api(
      page, 'GET', `/execution/programs/?engagement=${engagement}`,
    );
    let programId = existing.body.results[0]?.id;
    if (!programId) {
      const program = await api(page, 'POST', '/execution/programs/', {
        engagement, title: `E2E Seed Program ${Date.now()}`,
      });
      programId = program.body.id;
    }
    const failed = await api(page, 'POST', '/execution/procedures/', {
      program: programId,
      step_number: '1',
      title: `E2E Failed Procedure ${Date.now()}`,
      description: 'Seeded as failed so a finding can be raised from it.',
      procedure_type: 'substantive',
      status: 'failed',
    });
    procedureId = failed.body.id;
  }
  return api(page, 'POST', '/findings/findings/', {
    ...fields,
    engagement,
    procedure: procedureId,
  });
}

/**
 * Endorse and publish a finding, as a supervisor.
 *
 * A finding is a draft until this happens, and a draft is invisible to the
 * auditee — they cannot read it, comment on it, attach evidence to it, answer it
 * or raise a CAPA against it. Specs that put a finding in front of an auditee
 * have to publish it first, which is also what the real flow does.
 *
 * Requires the caller's `page` to be signed in as a supervisor (`EEU-10003`),
 * since this is gated on APPROVE_PLANS.
 */
export async function publishFinding(page, findingId) {
  return api(page, 'POST', `/findings/findings/${findingId}/publish/`);
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
