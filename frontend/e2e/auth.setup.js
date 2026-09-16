// One real UI login per role, saved as storage state for the role projects.
// This is TESTING.md step 0 executed as a side effect: if a demo credential or
// the login flow itself breaks, every role project fails on setup.
import { test as setup } from '@playwright/test';
import { login } from './helpers.js';

const ROLES = [
  { name: 'admin', employeeId: 'EEU-10001', password: 'admin123' },
  { name: 'manager', employeeId: 'EEU-10002', password: 'user123' },
  { name: 'supervisor', employeeId: 'EEU-10003', password: 'user123' },
  { name: 'auditor', employeeId: 'EEU-10004', password: 'user123' },
  { name: 'auditee', employeeId: 'EEU-10005', password: 'user123' },
];

for (const role of ROLES) {
  setup(`authenticate ${role.name}`, async ({ page }) => {
    await login(page, role.employeeId, role.password);
    await page.context().storageState({ path: `e2e/.auth/${role.name}.json` });
  });
}
