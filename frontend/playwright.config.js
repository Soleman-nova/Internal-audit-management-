import { defineConfig } from '@playwright/test';

const FRONTEND = 'http://localhost:5173';

export default defineConfig({
  testDir: './e2e',
  // One worker: every spec mutates the same seeded database, so the run must
  // be strictly sequential. Parallel projects would race on unique codes.
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: FRONTEND,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      // Django's API is all POST/authed; /admin/login/ is a plain 200 GET that
      // proves the backend is listening without needing credentials.
      // Playwright spawns this through cmd.exe on Windows, which treats the `/`
      // in a forward-slash executable path as a switch delimiter and reports
      // "'venv' is not recognized". The backslashes are required here even
      // though every other path in the repo is written with forward slashes.
      command: 'cd ../backend && venv\\Scripts\\python.exe manage.py runserver 8000',
      url: 'http://localhost:8000/admin/login/',
      reuseExistingServer: true,
      timeout: 60_000,
      env: { PYTHONUTF8: '1' },
    },
    {
      command: 'npm run dev',
      url: FRONTEND,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
  projects: [
    // Signs in as every role once, through the real login page, and saves the
    // resulting localStorage (accessToken/refreshToken/user) as storage state.
    // Specs reuse it, so a failure inside a spec means the feature broke — not
    // the login. It also exercises step 0 of the walkthrough as a side effect.
    { name: 'setup', testMatch: /auth\.setup\.js/ },

    { name: 'login', testMatch: /login\.spec\.js/, dependencies: ['setup'] },
    {
      name: 'admin',
      testMatch: /admin\.spec\.js/,
      dependencies: ['setup'],
      use: { storageState: 'e2e/.auth/admin.json' },
    },
    {
      name: 'manager',
      testMatch: /manager\.spec\.js/,
      dependencies: ['setup'],
      use: { storageState: 'e2e/.auth/manager.json' },
    },
    {
      name: 'supervisor',
      testMatch: /supervisor\.spec\.js/,
      dependencies: ['setup'],
      use: { storageState: 'e2e/.auth/supervisor.json' },
    },
    {
      name: 'auditor',
      testMatch: /auditor\.spec\.js/,
      dependencies: ['setup'],
      use: { storageState: 'e2e/.auth/auditor.json' },
    },
    {
      name: 'auditee',
      testMatch: /auditee\.spec\.js/,
      dependencies: ['setup'],
      use: { storageState: 'e2e/.auth/auditee.json' },
    },
    {
      name: 'cross-cutting',
      testMatch: /cross-cutting\.spec\.js/,
      dependencies: ['setup'],
    },
  ],
});
