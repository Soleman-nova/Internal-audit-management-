// TESTING.md §6 — cross-cutting checks, run across roles: language switch,
// dark mode, the help modal, and session persistence.
import { test, expect } from '@playwright/test';
import { login } from './helpers.js';

const SETTINGS_BTN = 'button[title="System Settings"]';
const HELP_BTN = 'button[title="Help & Support"]';
const SAVE_BTN = '[role="dialog"] form button[type="submit"]';

// Toasts float over the header with pointer-events and cover the action
// buttons until they clear (success/info auto-dismiss; assertive error toasts
// linger). Dismiss any visible toast first, then click normally.
async function dismissToasts(page) {
  for (;;) {
    const close = page.locator('div[class*="pointer-events-auto"] button').first();
    if ((await close.count()) === 0) break;
    try {
      await close.click({ timeout: 3000 });
    } catch {
      break;
    }
  }
}

async function openSettings(page) {
  await dismissToasts(page);
  await page.locator(SETTINGS_BTN).click();
}

test('EN ⇄ AM language switch relabels the sidebar', async ({ page }) => {
  await login(page, 'EEU-10004', 'user123');
  await page.goto('/dashboard');

  // The radio inputs are sr-only with an overlay preview on top; clicking the
  // label card is what a user does and it reliably flips the radio.
  await openSettings(page);
  await page.locator('.app-modal-lang-card').filter({ hasText: 'Amharic' }).click();
  await page.locator(SAVE_BTN).click();
  await expect(page.locator('.sidebar-nav')).toContainText('ዳሽቦርድ', { timeout: 20_000 });

  // Restore English.
  await openSettings(page);
  await page.locator('.app-modal-lang-card').filter({ hasText: 'English' }).click();
  await page.locator(SAVE_BTN).click();
  await expect(page.locator('.sidebar-nav')).toContainText('Dashboard');
});

test('dark mode is applied to the document', async ({ page }) => {
  await login(page, 'EEU-10002', 'user123');
  await page.goto('/dashboard');
  await expect(page.locator('body')).toHaveAttribute('data-theme', 'light');

  await openSettings(page);
  await page.locator('.app-modal-theme-card').filter({ hasText: 'Dark Mode' }).click();
  await page.locator(SAVE_BTN).click();
  await expect(page.locator('body')).toHaveAttribute('data-theme', 'dark');

  await openSettings(page);
  await page.locator('.app-modal-theme-card').filter({ hasText: 'Light Mode' }).click();
  await page.locator(SAVE_BTN).click();
  await expect(page.locator('body')).toHaveAttribute('data-theme', 'light');
});

test('the help modal opens with the role checklists', async ({ page }) => {
  await login(page, 'EEU-10005', 'user123');
  await page.goto('/dashboard');
  await dismissToasts(page);
  await page.locator(HELP_BTN).click();
  await expect(page.getByRole('button', { name: 'Roles Overview' })).toBeVisible();
});

test('a reload keeps the session alive', async ({ page }) => {
  await login(page, 'EEU-10005', 'user123');
  await page.goto('/dashboard');
  await page.reload();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.locator('.sidebar-nav')).toBeVisible();
});
