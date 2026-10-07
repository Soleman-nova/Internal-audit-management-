// TESTING.md §2 — Audit Manager. The risk register's scoring policy.
//
// Why this exists: `/risk` had one assertion anywhere in the suite (a heading and
// a 403 in supervisor.spec.js), while the page now carries the scoring policy —
// the weights, the uplift derived from them, whether stored scores still match the
// active policy, and the choice of whose figures a score is based on. A page can
// lose all of that and still pass everything else, which is the same gap that let
// the planning-page split hide.
//
// What it deliberately does NOT do: drive the adopt-the-auditee's-figures flow.
// Reaching that dialog needs a submitted self-assessment, and its parent only
// accepts one (it is a OneToOne) — so the test would have to claim the seeded
// assessment, flip its `is_self_assessment` flag and put it back. Creating an
// assessment is worse: saving one propagates its score onto an audit-universe row,
// so a test that tidies up afterwards would rewrite seeded risk scores. The
// semantics are covered by seven backend tests in `AdoptedSourceTest`, and the
// control's rendering by the i18n bare-key walk; the gap is documented here rather
// than papered over with an assertion that cannot fail.
import { test, expect } from '@playwright/test';
import { api } from './helpers.js';

const PROBE = 'E2E Policy Probe';

/** Remove the probe parameter so the global policy is left as we found it. */
async function removeProbe(page) {
  const found = await api(page, 'GET', `/risk/parameters/?search=${encodeURIComponent(PROBE)}`);
  for (const p of found.body.results ?? []) {
    await api(page, 'DELETE', `/risk/parameters/${p.id}/`);
  }
}

test.describe('risk scoring policy', () => {
  test.afterEach(async ({ page }) => {
    // The parameter set is global and every stored score depends on it, so the
    // probe must not outlive the test — otherwise later specs score against a
    // policy this test invented. Deleting it restores the policy and the recompute
    // re-freezes the register against the restored one (scores are a pure function
    // of the inputs and the policy, so this returns them to their original values).
    await removeProbe(page);
    await api(page, 'POST', '/risk/assessments/recompute/');
  });

  test('the policy in force is shown and follows the parameters', async ({ page }) => {
    await removeProbe(page);
    await page.goto('/risk');
    await expect(page.locator('.risk-view')).toContainText('Parameter policy');

    // The uplift is derived from the weights, so it is the number that proves the
    // banner is reading the live policy rather than a hardcoded string.
    await expect(page.locator('.risk-view')).toContainText(/Uplift \+\d+%/);
    const count = page.locator('.risk-view').getByText(/\d+ active parameter/);
    const before = parseInt((await count.first().innerText()).match(/(\d+)/)[1], 10);

    // Adding a parameter changes the policy every stored score was computed under.
    const created = await api(page, 'POST', '/risk/parameters/', {
      name: PROBE, category: 'it', description: 'Added by the E2E suite.', weight: '0.4',
    });
    expect(created.status).toBe(201);

    await page.reload();
    await expect(page.locator('.risk-view')).toContainText(new RegExp(`${before + 1} active parameter`));
  });

  test('the register shows inherent and residual risk, and offers no recompute when consistent', async ({ page }) => {
    // The register is seeded; every other spec on this page relies on that too.
    const existing = await api(page, 'GET', '/risk/assessments/?page_size=1');
    expect(existing.body.count).toBeGreaterThan(0);

    await page.goto('/risk');
    // Both figures, because "control effectiveness" is an input whose only output
    // is the residual score — before this it was computed and rendered nowhere.
    await expect(page.locator('.risk-view').getByText(/Inherent: /).first()).toBeVisible();
    await expect(page.locator('.risk-view').getByText(/Residual: /).first()).toBeVisible();

    // Nothing is stale, so no row advertises an older policy and the banner offers
    // no button. Recompute rewrites the whole register, so it must not be offered
    // when there is nothing to do.
    await expect(page.locator('.risk-view')).not.toContainText('Older policy');

    // And from a real client the operation is idempotent: a consistent register
    // updates nothing.
    const res = await api(page, 'POST', '/risk/assessments/recompute/');
    expect(res.status).toBe(200);
    expect(res.body.updated).toBe(0);
  });
});
