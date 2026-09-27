// i18n integrity: the two ways a translation can silently go wrong.
//
// 1. `t()` returns the key itself when the key is missing from the dictionary, so a
//    typo or an unadded key renders as a bare camelCase token — in text or in a
//    `title`/`placeholder`/`aria-label`. Walk every page plus the Help and Settings
//    dialogs and assert none appears. This is the check that would have caught
//    `title={t('clickForDetails') || '...'}`, which rendered the literal key.
//
// 2. New keys are added to the `en` block only — `t()` falls back to English for a
//    key the active language lacks, which keeps one source of truth. Everything
//    else in the suite runs in English, so without this a key that only resolved
//    because `lang` was 'en' would look fine everywhere but a real Amharic session.
//
// Cheap and deterministic: no data setup, no assertions about layout.
import { test, expect } from '@playwright/test';

const PAGES = [
  '/dashboard', '/planning', '/execution', '/findings', '/risk',
  '/capa', '/reports', '/users', '/audit-trail',
];

/** Text that looks like a dictionary key rather than prose: word-word all one run. */
const KEYLIKE = /\b[a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+\b/;

const bareKeys = async (page, where) => {
  const found = await page.evaluate((pattern) => {
    const re = new RegExp(pattern, 'g');
    const ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];
    const out = [];
    // Text nodes *and* user-facing attributes. Attributes matter: a `title` that
    // read `{t('clickForDetails') || 'Click to view details'}` rendered the bare
    // key, because `t()` returns the key rather than undefined — and a
    // text-nodes-only walk does not see it.
    const collect = (s) => {
      const m = s.trim().match(re);
      if (m) out.push(m.join(', '));
    };
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      // Transient toast stack — excluded for the same reason the fingerprint
      // excludes it, and because one sitting over a button breaks the click below.
      if (n.parentElement && n.parentElement.closest('[aria-live]')) continue;
      collect(n.textContent);
    }
    for (const el of document.body.querySelectorAll('*')) {
      for (const a of ATTRS) {
        if (el.hasAttribute(a)) collect(el.getAttribute(a));
      }
    }
    return [...new Set(out)];
  }, KEYLIKE.source);
  return found.map((k) => `${where}: ${k}`);
};

test('no screen renders a bare dictionary key', async ({ page }) => {
  const offenders = [];

  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    offenders.push(...(await bareKeys(page, path)));
  }

  // The dialogs the fingerprint does not open: Help (with its roles / lifecycle /
  // checklist tabs) and Settings — where most of AppLayout's strings live.
  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  // Clear any toast that would intercept the click below. Its text is excluded
  // above regardless; this is only so the click can land.
  await page.evaluate(() => document.querySelectorAll('[aria-live]').forEach((el) => el.remove()));
  const help = page.getByRole('button', { name: /help/i }).first();
  if (await help.count()) {
    await help.click();
    for (const tab of [/role/i, /stage|lifecycle/i, /checklist|task/i]) {
      const b = page.getByRole('button', { name: tab }).first();
      if (await b.count()) {
        await b.click();
        offenders.push(...(await bareKeys(page, `help:${tab}`)));
      }
    }
    await page.keyboard.press('Escape');
  }
  const settings = page.getByRole('button', { name: /settings/i }).first();
  if (await settings.count()) {
    await settings.click();
    offenders.push(...(await bareKeys(page, 'settings')));
    const tabs = page.locator('.app-modal-nav-btn');
    for (let i = 0; i < (await tabs.count()); i += 1) {
      await tabs.nth(i).click();
      offenders.push(...(await bareKeys(page, `settings#${i}`)));
    }
    await page.keyboard.press('Escape');
  }

  console.log('bare-key findings:', JSON.stringify(offenders, null, 1));
  expect(offenders, `untranslated keys rendered on screen: ${offenders.join(' | ')}`).toEqual([]);
});

test('switching to Amharic falls back to English rather than breaking', async ({ page }) => {
  // Every new key from the extraction is `en`-only by design, and `t()` falls back
  // to English for a missing key. Nothing else exercises that path — the whole
  // suite runs in English — so a key that resolved only because `lang` was 'en'
  // would look fine everywhere except in a real Amharic session.
  const offenders = [];

  for (const path of PAGES) {
    await page.goto(path);
    await page.evaluate(() => localStorage.setItem('language', 'am'));
    await page.reload();
    await page.waitForLoadState('networkidle');

    // The chrome really is Amharic (so we know the language took effect and this
    // is not just the English path again), and nothing renders a bare key.
    const text = await page.evaluate(() => document.body.innerText);
    if (!/[ሀ-፿]/.test(text)) {
      offenders.push(`${path}: no Amharic script rendered — the language switch did not take`);
    }
    offenders.push(...(await bareKeys(page, `${path}(am)`)));
  }

  console.log('amharic-mode findings:', JSON.stringify(offenders, null, 1));
  expect(offenders, `problems in Amharic mode: ${offenders.join(' | ')}`).toEqual([]);
});
