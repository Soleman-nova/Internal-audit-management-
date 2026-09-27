import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // Playwright specs and the e2e planner script are Node programs, not browser
    // ones, so `process` and `Buffer` are real there — ESLint reporting them as
    // `no-undef` was a config gap, not a defect, and a `no-undef` nobody can act
    // on is how a lint gate gets ignored. `globals.browser` stays in the mix
    // because the same files pass callbacks into `page.evaluate`, which execute
    // in the page and legitimately use `localStorage` and `fetch`.
    files: ['e2e/**/*.js', 'e2e-planner.js'],
    languageOptions: {
      globals: { ...globals.node, ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
])
