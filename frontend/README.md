# Frontend — EEU Internal Audit Management System

React 19 + Vite 8 single-page application for the [EEU Internal Audit Management System](../README.md). It talks to the Django REST API in [`../backend`](../backend).

Start with the [root README](../README.md) for the full stack, API reference and deployment notes, and the [user manual](../USER_MANUAL.md) for what the screens do.

## Scripts

```bash
npm install
npm run dev       # dev server with HMR on http://localhost:5173
npm run build     # production bundle into dist/
npm run preview   # serve the built bundle locally
npm run lint      # eslint — see "Known limitations" in the root README; not currently clean
```

There is no JS test runner installed; UI behaviour is covered by the manual walkthrough in [../TESTING.md](../TESTING.md).

## Configuration

Copy [.env.example](.env.example) to `.env`. The only variable is `VITE_API_BASE_URL` — the API base URL **including** the `/api` prefix.

Vite inlines it at build time, so it must be set before `npm run build`; a production build without it is pinned to `localhost:8000`. The client resolves the base URL in this order: the value saved in the in-app Settings modal (localStorage) → `VITE_API_BASE_URL` → `http://localhost:8000/api`.

## Layout

```
src/
├── api/                 axios client + one module per domain
│   ├── apiClient.js     JWT interceptors, shared silent refresh, session helpers
│   └── paginated.js     helper for the API's {count, next, previous, results} shape
├── components/
│   ├── layout/          AppLayout — sidebar, header, Settings and Help modals
│   ├── ui/              DataTable, Modal, Badge, FormField, OrgUnitSelect, …
│   └── EEUOrgChart.jsx  organizational chart used by the dashboard selector
├── context/             AuthContext, I18nContext (EN/AM), ToastContext
├── hooks/
│   ├── usePermissions.js  mirrors the server capability matrix for UI gating only
│   └── useOrgUnits.js
├── pages/               one directory per module; every page is lazy-loaded
├── utils/validation.js
├── App.jsx              routes, ProtectedRoute, CapabilityRoute
└── App.css, index.css
```

## Notes

- **Permissions here are cosmetic.** `usePermissions` hides buttons and guards routes; the server is the only enforcement. Never rely on it for security.
- **Pages are lazy-loaded** so an auditee never downloads the user-management or audit-trail chunks.
- **Deploying:** serve `dist/` as static files with SPA fallback — any unknown path must return `index.html`, since routing is client-side.
