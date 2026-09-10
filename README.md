# EEU Internal Audit Management System

Internal audit lifecycle management for the **Ethiopian Electric Utility (EEU)**. The system carries an audit from risk assessment through annual planning, engagement execution, findings, corrective actions and reporting — with role-based access control enforced server-side and a bilingual (English / አማርኛ) interface.

A Django REST API backend and a React single-page frontend, in one repository.

```
Risk assessment → Annual plan → Engagement → Program & procedures
    → Working papers → Findings → Corrective actions → Report
```

**Status:** pre-1.0, actively developed. No `LICENSE` file is present, so no license is granted — treat the code as EEU-internal until the organization publishes licensing terms.

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Roles and permissions](#roles-and-permissions)
- [Management commands](#management-commands)
- [Testing](#testing)
- [Deployment](#deployment)
- [Known limitations](#known-limitations)
- [Documentation](#documentation)

---

## Features

| Module | What it does |
|---|---|
| **Dashboard** | KPI cards (engagements, findings, overdue actions, compliance score), a directorate selector that rescopes every number, six-month execution chart, open-findings distribution, five-quarter compliance trend, and a **My Work** queue of the signed-in user's own findings, CAPAs and pending self-assessments. |
| **Audit Planning** | The audit universe (departments, processes, IT systems, projects, subsidiaries, regulatory areas) with re-audit frequency tracking; annual plans that submit and approve through a status workflow, including directorate plans rolling into an EEU consolidated master plan; engagements with server-assigned numbers and audit teams. |
| **Audit Execution** | Audit programs with a prepare → submit → approve cycle; procedures across six procedure types with assignment and completion sign-off; working papers with upload, supervisory review and permission-gated download. |
| **Findings Registry** | Findings recorded in the standard condition / criteria / cause / effect / recommendation structure, across five severities and eight categories, with evidence attachments, a comment thread, management responses, repeat-finding linkage, and a resolve / close / dispute / reopen lifecycle. |
| **Risk Assessment** | A 5×5 likelihood × impact matrix with weighted risk parameters, scores and ratings computed server-side and propagated back onto the audit universe; auditee self-assessments with a manager review step. |
| **Corrective Actions (CAPA)** | Actions raised from findings with owners, priorities and due dates; owner responses with evidence; supervisory verification and scheduled follow-ups; automatic overdue flagging and due-soon reminders. |
| **Reports & Analytics** | Report templates plus asynchronous generation to **PDF, Excel and Word**; generated reports move from `generating` to `ready` without a page refresh; analytics endpoint with six-month rolling buckets. |
| **User Management** | Administrator-only user provisioning, activation/deactivation and password resets. |
| **Audit Trail** | Every create, update, delete, login, export and approval recorded with user, object, field-level changes, IP address and user agent. Reading it requires a capability of its own. |
| **Notifications** | Ten notification types delivered in-app, with a polling unread badge and deep links to the specific record. |
| **Platform** | JWT authentication with silent refresh, English/Amharic switching, light and dark themes, a configurable API endpoint, and pagination, filtering, search and ordering on every list endpoint. |

---

## Tech stack

**Backend** — Python 3.13. Pinned in [backend/requirements.txt](backend/requirements.txt), which documents why each pin exists.

| Package | Version | Role |
|---|---|---|
| `django` | 6.0.5 | Web framework |
| `djangorestframework` | 3.17.1 | REST API |
| `djangorestframework-simplejwt` | 5.5.1 | JWT auth, rotation and blacklisting |
| `django-cors-headers` | 4.9.0 | Browser access control |
| `django-filter` | 25.2 | List filtering |
| `python-decouple` | 3.8 | Env-driven settings |
| `psycopg2-binary` | 2.9.12 | PostgreSQL driver (optional branch) |
| `Pillow` | 12.2.0 | Image validation |
| `reportlab` / `openpyxl` / `python-docx` | 4.5.1 / 3.1.5 / 1.2.0 | PDF / Excel / Word rendering |
| `django-import-export` | 4.4.1 | Admin bulk import & export |
| `celery` | 5.6.3 | Pinned as the intended replacement for the report thread — **not wired up** |

**Frontend** — Node 20+. See [frontend/package.json](frontend/package.json).

| Package | Version | Role |
|---|---|---|
| `react` / `react-dom` | 19.2 | UI |
| `vite` | 8.0 | Dev server and build |
| `react-router-dom` | 7.15 | Routing, lazy-loaded pages |
| `axios` | 1.16 | HTTP client with the auth interceptor |
| `tailwindcss` + `@tailwindcss/vite` | 4.3 | Styling |
| `recharts` | 3.8 | Dashboard charts |
| `lucide-react` | 1.16 | Icons |
| `eslint` | 10.3 | Linting |

---

## Repository layout

```
.
├── backend/
│   ├── core/                     Django project: settings, root urls, wsgi/asgi
│   ├── apps/
│   │   ├── accounts/             User (login by employee_id), Department, Role,
│   │   │                         AuditTrail, dashboard stats
│   │   ├── audit_planning/       AuditUniverse, AuditPlan, AuditEngagement,
│   │   │                         AuditTeamMember
│   │   ├── audit_execution/      AuditProgram, AuditProcedure, WorkingPaper
│   │   ├── findings/             AuditFinding, Evidence, FindingComment
│   │   ├── risk_assessment/      RiskParameter, RiskAssessment, SelfAssessment
│   │   ├── corrective_actions/   CorrectiveAction, ActionResponse, FollowUp
│   │   ├── reports/              ReportTemplate, GeneratedReport, jobs.py
│   │   ├── notifications/        Notification, SystemSetting, services.py
│   │   └── common/               RBAC matrix, pagination, validators,
│   │                             reference numbers, audit logging, test fixtures
│   ├── media/                    Uploads (gitignored, never served in production)
│   ├── logs/                     Rotating audit_system.log (gitignored)
│   ├── manage.py
│   ├── requirements.txt
│   └── .env.example              Annotated backend configuration reference
├── frontend/
│   ├── src/
│   │   ├── api/                  axios client + one module per domain
│   │   ├── components/layout/    AppLayout: sidebar, header, Settings, Help
│   │   ├── components/ui/        DataTable, Modal, Badge, FormField, …
│   │   ├── components/           EEUOrgChart
│   │   ├── context/              AuthContext, I18nContext, ToastContext
│   │   ├── hooks/                usePermissions, useOrgUnits
│   │   ├── pages/                auth, dashboard, planning, execution,
│   │   │                         findings, risk, followup, reports, admin
│   │   ├── utils/                validation
│   │   ├── App.jsx               Routes + route guards
│   │   └── App.css, index.css    Live stylesheets
│   ├── package.json
│   └── .env.example              Annotated frontend configuration reference
├── css/styles.css                Legacy stylesheet — not used by the React app
├── README.md                     This file
├── USER_MANUAL.md               End-user guide and administrator runbook
├── TESTING.md                    Automated test map + manual role walkthrough
└── ENHANCEMENT_PLAN.md           Roadmap notes
```

---

## Quick start

**Prerequisites:** Python 3.13, Node 20+, Git. SQLite is the default database, so nothing else is needed to get running.

### 1. Backend

```bash
git clone <repository-url>
cd "EEU Internal Audit Management System/backend"

python -m venv venv
source venv/Scripts/activate      # Windows (Git Bash);  venv\Scripts\activate on cmd
# source venv/bin/activate        # macOS / Linux

pip install -r requirements.txt
cp .env.example .env              # defaults work as-is for development

python manage.py migrate
python manage.py runserver        # http://localhost:8000
```

### 2. Demo data

Run the seeders in this order — later ones expect the organizational units the earlier ones create:

```bash
python manage.py seed_org_structure        # executive + corporate units
python manage.py seed_eeu_audit_structure  # IAEO and the four audit directorates
python manage.py seed_service_centers      # regions and customer service centers
python manage.py seed_hq_org_units         # detailed head-office units under the chief offices
python manage.py seed_data                 # demo users, universe, plan, engagements
python manage.py seed_e2e_demo             # a full worked example end to end
python manage.py flag_overdue_actions      # populates the overdue CAPA tab
```

> **On Windows, set `PYTHONUTF8=1` first.** `seed_e2e_demo` prints a `✓` in its summary, which the default `cp1252` console cannot encode — the command dies part-way with `UnicodeEncodeError: 'charmap' codec can't encode character '✓'`. Run `set PYTHONUTF8=1` (cmd), `$env:PYTHONUTF8=1` (PowerShell), or `export PYTHONUTF8=1` (bash) before the seed chain. Verified: the chain completes cleanly with it set and fails without it.

### 3. Frontend

```bash
cd ../frontend
npm install
cp .env.example .env
npm run dev                       # http://localhost:5173
```

### 4. Sign in

> **Login is by Employee ID, not email.** The login serializer authenticates on `employee_id`; `USERNAME_FIELD` on the user model is `employee_id`. Email is stored for notifications only.

| Role | Employee ID | Password |
|---|---|---|
| System Admin | `EEU-10001` | `admin123` |
| Audit Manager | `EEU-10002` | `user123` |
| Supervisor | `EEU-10003` | `user123` |
| Lead Auditor | `EEU-10004` | `user123` |
| Auditee | `EEU-10005` | `user123` |

`EEU-10001` is created by `seed_data` only; the other four exist after either seed command. These are development credentials — change or remove them before any real deployment.

> **The login page's one-click "Audit Manager" button does not work on a freshly seeded database.** It submits `User1234`, but every seeder sets the non-admin passwords to `user123` ([seed_data.py:107](backend/apps/accounts/management/commands/seed_data.py#L107), [seed_e2e_demo.py:74](backend/apps/accounts/management/commands/seed_e2e_demo.py#L74)). Type `EEU-10002` / `user123` into the form instead, or fix the constant in [LoginPage.jsx:13](frontend/src/pages/auth/LoginPage.jsx#L13). The other four buttons are correct. `TESTING.md` carries the same stale `User1234`.

To create your own administrator instead:

```bash
python manage.py createsuperuser   # prompts for an employee ID, not a username
```

---

## Configuration

Every deployment value is read through `python-decouple`'s `config()` in [backend/core/settings.py](backend/core/settings.py). The two `.env.example` files are the authoritative, annotated reference:

- [backend/.env.example](backend/.env.example) — copy to `backend/.env`
- [frontend/.env.example](frontend/.env.example) — copy to `frontend/.env`

Neither `.env` is committed (both are gitignored). The variables that actually change between environments:

| Variable | Where | Notes |
|---|---|---|
| `SECRET_KEY` | backend | Has an insecure default **only while `DEBUG=True`**. Required when `DEBUG=False` — the process refuses to start without it rather than running with a published key. |
| `DEBUG` | backend | `False` activates the whole `SECURE_*` block and stops Django serving media. |
| `ALLOWED_HOSTS` | backend | Comma-separated, no spaces. Must include the deployment hostname. |
| `USE_SQLITE` | backend | `True` uses `backend/db.sqlite3`. `False` switches to the PostgreSQL branch and the `DB_*` variables. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | backend | Ignored while `USE_SQLITE=True`. |
| `CORS_ALLOWED_ORIGINS` | backend | Origins the browser may call the API from, scheme included, no trailing slash. Must list wherever the built frontend is served. A missing entry shows up as every browser request failing while `curl` works fine. Also used as `CSRF_TRUSTED_ORIGINS` when `DEBUG=False`. |
| `EMAIL_BACKEND` + `EMAIL_HOST*` | backend | Console backend by default (mail prints to the server log). Switch to SMTP to actually deliver reminders. |
| `THROTTLE_LOGIN` | backend | Default `30/min`. Tighter than the anonymous rate so it still blunts credential stuffing, but loose enough that the one-click demo logins and e2e runs do not trip it. |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` / `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | backend | Default 60 minutes / 7 days. |
| `LOG_LEVEL` | backend | Handlers write to the console and to a rotating `backend/logs/audit_system.log` (5 MB × 5). |
| `VITE_API_BASE_URL` | frontend | Base URL of the API **including** `/api`. Inlined at build time. Without it a production build is pinned to `localhost:8000`. |

The frontend resolves its API base URL in this order: the value saved in the in-app Settings modal (localStorage) → `VITE_API_BASE_URL` → `http://localhost:8000/api`.

Timezone is fixed at `Africa/Addis_Ababa`.

---

## API reference

All endpoints live under `/api/`. Authenticate with `Authorization: Bearer <access token>` from `POST /api/auth/login/`.

**Conventions**

- **Pagination** — every list endpoint returns `{count, next, previous, results}` at 20 rows per page; `?page=` and `?page_size=` are honoured ([apps/common/pagination.py](backend/apps/common/pagination.py)). The single exception is `departments/tree/`, which is deliberately unpaginated because the cascading picker needs the whole tree in one response.
- **Filtering** — `DjangoFilterBackend`, `SearchFilter` (`?search=`) and `OrderingFilter` (`?ordering=`) are enabled globally; each viewset declares its own `filterset_fields`.
- **Throttling** — anonymous 60/min, authenticated 1000/hour, login 30/min.
- **Files** — uploads are validated by extension allowlist and size cap (documents 10 MB, images 2 MB) in [apps/common/validators.py](backend/apps/common/validators.py). Media is not served directly in production; evidence, working papers and reports are fetched through their permission-gated `download` / `export` actions.
- **Reference numbers** — `finding_number`, `engagement_number` and `action_number` are assigned by the server as `FND-YYYY-NNNN`, `ENG-YYYY-NNNN` and `CAPA-YYYY-NNNN`. A client-supplied value is ignored ([apps/common/reference_numbers.py](backend/apps/common/reference_numbers.py)).
- **403 vs 404** — a `403` means the record is visible but you are not named on it; a `404` means read scoping hid the row entirely. The distinction is deliberate and asserted by tests.

### Mount points

| Prefix | App |
|---|---|
| `/admin/` | Django admin |
| `/api/auth/` | `accounts` |
| `/api/planning/` | `audit_planning` |
| `/api/execution/` | `audit_execution` |
| `/api/findings/` | `findings` |
| `/api/risk/` | `risk_assessment` |
| `/api/corrective/` | `corrective_actions` |
| `/api/reports/` | `reports` |
| `/api/notifications/` | `notifications` |

### Authentication and accounts — `/api/auth/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `POST` | `login/` | — | Body `{employee_id, password}`. Throttled at 30/min. Returns `access`, `refresh`, `user`. |
| `POST` | `logout/` | authenticated | Body `{refresh}`. Blacklists the refresh token. |
| `POST` | `token/refresh/` | — | Body `{refresh}`. Rotates and returns a new pair. |
| `POST` | `change-password/` | authenticated | Body `{current_password, new_password}`. |
| `GET` `PATCH` | `profile/` | authenticated | Self-service profile edit. |
| `GET` | `dashboard/stats/` | authenticated | `?directorate=<department id>` rescopes every KPI and chart. |
| `GET` `POST` `PATCH` `DELETE` | `users/` `users/{id}/` | `manage_users` | Filter `role`, `department`, `is_active`; search employee ID, email, name. |
| `GET` | `users/me/` | `manage_users` | The requesting user's record. |
| `POST` | `users/{id}/activate/` · `users/{id}/deactivate/` | `manage_users` | Toggles `is_active`. |
| `POST` | `users/{id}/reset-password/` | `manage_users` | Sets a new password for another user. |
| `GET` | `departments/` | authenticated | Filter `unit_type`, `directorate_type`, `parent`, `is_active`. |
| `POST` `PATCH` `DELETE` | `departments/` | `write_audit` | |
| `GET` | `departments/tree/` | authenticated | Whole hierarchy, unpaginated. |
| `GET` | `audit-trail/` | `view_audit_trail` | Read-only, **including reads**. Filter `?model_name=` and `?user=` (django-filter exact); `?action=` matches case-insensitively; `?search=` covers the object representation and the acting user's email and name. The User Management page's Security Audit Log panel calls this with `model_name=User`. |

### Planning — `/api/planning/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `universe/` | authenticated | Filter `category`, `status`, `department`, `directorate`. |
| `POST` `PATCH` `DELETE` | `universe/` | `write_audit` | |
| `GET` | `universe/due-for-re-audit/` | authenticated | `?as_of=YYYY-MM-DD`; a bad date returns 400. |
| `GET` | `plans/` | authenticated | Filter `status`, `year`, `directorate`, `plan_scope`. |
| `POST` `PATCH` `DELETE` | `plans/` | `write_audit` | Created as `draft`. |
| `POST` | `plans/{id}/submit/` | `write_audit`, or the plan's own author | → `submitted`; notifies approvers, not you. |
| `POST` | `plans/{id}/approve/` | `approve_plans` | → `approved`; stamps `approved_by`/`approved_at`, notifies the author, logs an `APPROVE`. |
| `GET` | `engagements/` | authenticated | Filter `status`, `engagement_type`, `plan`, `department`, `directorate`, `risk_level`. Read-scoped for auditees. |
| `POST` `PATCH` `DELETE` | `engagements/` | `write_audit` | Number assigned server-side as `ENG-YYYY-NNNN`. |
| `POST` | `engagements/{id}/add-member/` | `write_audit` | |
| `POST` | `engagements/{id}/update-status/` | `write_audit` | Completion back-fills the universe entry's `last_audited`. |

### Execution — `/api/execution/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `programs/` | authenticated | Filter `status`, `engagement`. |
| `POST` `PATCH` `DELETE` | `programs/` | `write_audit` | Created as `draft`, preparer recorded. |
| `POST` | `programs/{id}/submit/` | `write_audit`, or the preparer / engagement lead | → `submitted`; notifies the supervisor. |
| `POST` | `programs/{id}/approve/` | `approve_plans` | → `approved`; notifies the preparer. |
| `GET` | `procedures/` | authenticated | Filter `status`, `program`, `procedure_type`, `assigned_to`. |
| `POST` `PATCH` `DELETE` | `procedures/` | `write_audit` | |
| `POST` | `procedures/{id}/complete/` | `write_audit` | Stamps `completed_by`/`completed_at`, notifies the engagement lead. |
| `GET` | `working-papers/` | authenticated | Filter `engagement`, `paper_type`, `is_reviewed`, `procedure`. |
| `POST` `PATCH` `DELETE` | `working-papers/` | `write_audit` | File validated on upload. |
| `POST` | `working-papers/{id}/review/` | `approve_plans` | Sets `is_reviewed`, notifies the preparer. |
| `GET` | `working-papers/{id}/download/` | authenticated | Serves the file with its original name and content type. |

### Findings — `/api/findings/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `findings/` | authenticated | Filter `severity`, `status`, `category`, `engagement`, `is_repeat`. Read-scoped for auditees. |
| `POST` `PATCH` `DELETE` | `findings/` | `write_audit` | Number assigned server-side as `FND-YYYY-NNNN`; `identified_by` is read-only. |
| `POST` | `findings/{id}/add-comment/` | the finding's auditee or assignee, or `write_audit` | Notifies the rest of the thread. |
| `POST` | `findings/{id}/upload-evidence/` | the finding's auditee or assignee, or `write_audit` | |
| `POST` | `findings/{id}/respond/` | the finding's auditee or assignee, or `write_audit` | Management response. |
| `POST` | `findings/{id}/dispute/` | the finding's auditee or assignee, or `write_audit` | → `disputed`. |
| `POST` | `findings/{id}/resolve/` | `close_findings` | → `resolved`, with a resolution date. |
| `POST` | `findings/{id}/close/` | `close_findings` | → `closed`. Only `closed` counts towards the compliance score. |
| `POST` | `findings/{id}/reopen/` | `close_findings` | |
| `GET` | `evidence/` | authenticated | Filter `finding`, `evidence_type`. Scoped to visible findings. |
| `POST` `DELETE` | `evidence/` | `write_audit` | |
| `GET` | `evidence/{id}/download/` | authenticated | |

### Risk — `/api/risk/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `parameters/` | authenticated | Filter `category`, `is_active`. |
| `POST` `PATCH` `DELETE` | `parameters/` | `manage_settings` | Weights feed the score uplift. |
| `GET` | `assessments/` | authenticated | Ordered by descending risk score. |
| `POST` `PATCH` `DELETE` | `assessments/` | `write_audit` | Score, rating and residual risk are computed server-side and propagated to the linked universe entry. |
| `GET` | `assessments/heatmap/` | authenticated | 5×5 grid; year filter. |
| `GET` | `assessments/summary/` | authenticated | |
| `GET` | `self-assessments/` | authenticated | Filter `status`, `submitted_by`. Everyone without `approve_plans` sees **only their own** — auditors included. |
| `POST` `PATCH` | `self-assessments/` | authenticated | Editable while `submitted`; a reviewed submission is closed to edits. `status` cannot be self-set to `reviewed`. |
| `POST` | `self-assessments/{id}/review/` | `approve_plans` | → `reviewed`; stamps the reviewer and notifies the submitter. |

### Corrective actions — `/api/corrective/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `actions/` | authenticated | Filter `status`, `priority`, `finding`, `owner`. Auditees see their department's actions. |
| `POST` `PATCH` `DELETE` | `actions/` | `write_audit` | Number assigned server-side as `CAPA-YYYY-NNNN`. |
| `POST` | `actions/{id}/add-response/` | the action's owner, or `write_audit` | Notes, status update and an optional evidence file. |
| `POST` | `actions/{id}/schedule-followup/` | `approve_plans`, or the raiser | Owners cannot sign off their own remediation. |
| `GET` | `actions/overdue/` | authenticated | Paginated. Derived from the due date, so correct before `flag_overdue_actions` has ever run. Due *today* is not overdue. |
| `GET` | `actions/summary/` | authenticated | |

### Reports — `/api/reports/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `templates/` | authenticated | Filter `template_type`, `is_default`. |
| `POST` `PATCH` `DELETE` | `templates/` | `manage_settings` | |
| `GET` | `generated/` | authenticated | Filter `format`, `status`, `engagement`. |
| `POST` | `generated/` | `write_audit` | Returns immediately with `status: generating`. |
| `POST` | `generated/generate-pdf/` · `generated/generate-excel/` | `write_audit` | |
| `GET` | `generated/{id}/export/` | authenticated | Downloads the file. Returns 400 while the row is still `generating`. |
| `GET` | `generated/analytics/` | authenticated | `monthly_findings` covers exactly six consecutive calendar months. |

### Notifications — `/api/notifications/`

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `/` | authenticated | The caller's own notifications, newest first. |
| `POST` | `{id}/mark-read/` | authenticated | |
| `POST` | `mark-all-read/` | authenticated | |
| `GET` | `unread-count/` | authenticated | `{unread: n}`. Polled by the header bell. |
| `GET` | `settings/` | `manage_settings` | System key/value settings. |
| `POST` `PATCH` `DELETE` | `settings/` | `manage_settings` | |

---

## Roles and permissions

Authorization is capability-based. `ROLE_CAPABILITIES` in [backend/apps/common/permissions.py](backend/apps/common/permissions.py) is the **server-side source of truth**; [frontend/src/hooks/usePermissions.js](frontend/src/hooks/usePermissions.js) mirrors the same matrix to hide buttons and guard routes, and never substitutes for the server check.

| Capability | admin | audit_manager | supervisor | auditor | auditee |
|---|:---:|:---:|:---:|:---:|:---:|
| `manage_users` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `manage_settings` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `approve_plans` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `write_audit` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `close_findings` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `view_audit_trail` | ✅ | ✅ | ✅ | ❌ | ❌ |

Three permission classes consume that matrix:

- **`HasCapability`** subclasses (`CanManageUsers`, `CanManageSettings`, `CanWriteAudit`) — reads open to any authenticated user, writes require the capability.
- **`CanViewAuditTrail`** — the trail is sensitive enough that even `GET` requires the capability.
- **`RequiresCapability.for_(...)`** — gates one specific action, reads included.
- **`InvolvedPartyOrCapability.for_(...)`** — allows capability holders *or* the users named on the object itself, via (optionally dotted) field paths. This is what lets an auditee, who holds no capabilities at all, comment on their own finding and respond to their own CAPA without being granted `write_audit` everywhere.

**Auditee read scoping.** An auditee sees findings naming them plus every finding on an engagement in their department; engagements for their department; CAPAs owned by anyone in their department; and only their own self-assessment. A user with no department falls back to records naming them personally.

The feature-level matrix — 23 rows, every cell asserted by a test — is in [TESTING.md §2](TESTING.md#2-role--capability-matrix). [USER_MANUAL.md](USER_MANUAL.md) covers the same ground in task language.

---

## Management commands

Run from `backend/` with the virtualenv active.

| Command | Purpose | When |
|---|---|---|
| `seed_org_structure` | Executive and corporate organizational units | Once, first |
| `seed_eeu_audit_structure` | IAEO plus the FPA, TA, ITA and PP directorates | Once, after the above |
| `seed_service_centers` | EEU regions and their customer service centers. Amharic names are applied from `data/service_centers_am.json` (`--amharic-file` to override; that export covers 445 of the 582 centers) | Once, after the above |
| `seed_hq_org_units` | The detailed head-office units (CO Treasury, CO Budget, SCADA/DMS, …) under the existing chief offices; merges onto, never duplicates, the seeded units. Amharic names are applied from `data/org_units_am.json` (`--amharic-file` to override) | Once, after the above |
| `seed_data` | Demo users (`EEU-10001`–`EEU-10005`), risk parameters, universe entries, an approved annual plan, engagements, a program with procedures, one finding and one CAPA, a report template | Development only |
| `seed_e2e_demo` | A worked example spanning the whole lifecycle | Development only |
| `flag_overdue_actions` | Flips past-due CAPAs to `overdue` and sends due-soon reminders (`DUE_SOON_DAYS = 3`, override with `--days`). Idempotent, and honours `extended_due_date` over `due_date` | **Daily, scheduled** |
| `fail_stuck_reports` | Moves reports stranded on `generating` to `failed` — the recovery path when a process restarts mid-compile | **Periodically, scheduled** |
| `reassign_legacy_department_users` | Moves users off retired departments onto the current org tree | One-off migration |
| `retire_legacy_departments` | Deactivates superseded departments after reassignment | One-off migration, after the above |

Two standalone scripts are run with `python`, not `manage.py`: `backend/seed_risk_data.py` and `backend/smoke_planning_api.py`.

Scheduling examples are in the [administrator runbook](USER_MANUAL.md#scheduled-jobs).

---

## Testing

```bash
cd backend
python manage.py test                              # 334 tests, ~7 min
python manage.py test apps.findings -v 2           # one app
python manage.py check
python manage.py makemigrations --check --dry-run   # no model drift
```

```bash
cd frontend
npm run lint
npm run build
```

Tests run against a throwaway SQLite database and redirect `MEDIA_ROOT` to a temp directory, so neither `db.sqlite3` nor `media/` is touched and no seed data is needed. Shared fixtures in [backend/apps/common/role_fixtures.py](backend/apps/common/role_fixtures.py) build all five roles once per class; `assert_status_by_role` runs one request per role against an expectation table that **must** name every role, so a partially filled table fails rather than silently skipping a role.

A passing run still prints a `GeneratedReport.DoesNotExist` traceback. That is expected: `test_a_missing_report_does_not_crash_the_worker` deletes a report out from under the background task to prove the worker survives it, and the handler in [backend/apps/reports/jobs.py](backend/apps/reports/jobs.py) logs the exception on the way past. Trust the final `OK`, not the traceback.

Coverage by app, the full role matrix, and a manual browser walkthrough for each of the five roles are in [TESTING.md](TESTING.md). The walkthrough exists because a handler that mutates local state and shows a success toast without calling the API passes every backend test ever written — only a refresh catches it.

---

## Deployment

1. **Configure.** Set `DEBUG=False` and a fresh `SECRET_KEY`; add the hostname to `ALLOWED_HOSTS` and the frontend origin to `CORS_ALLOWED_ORIGINS`. Point `VITE_API_BASE_URL` at the public API URL — it is inlined at build time, so it must be set *before* `npm run build`.
2. **Verify.** `python manage.py check --deploy` must report no issues. This is the acceptance test for the whole `SECURE_*` block, which activates only when `DEBUG=False`: HTTPS redirect, HSTS, secure cookies, `X-Frame-Options` and the rest.
3. **Database.** `python manage.py migrate`. For PostgreSQL, set `USE_SQLITE=False` and the `DB_*` variables.
4. **Static and media.** `python manage.py collectstatic`. Serve `staticfiles/` from the web server. Do **not** expose `media/` — files are reached through authenticated `download` actions, and Django stops serving media entirely when `DEBUG=False`.
5. **Frontend.** `npm run build`, then serve `frontend/dist/` as static files with SPA fallback (any unknown path returns `index.html`, since routing is client-side).
6. **Reverse proxy.** `SECURE_PROXY_SSL_HEADER` is already set, which is what keeps `SECURE_SSL_REDIRECT` from becoming an infinite redirect loop behind a TLS-terminating proxy. Start `SECURE_HSTS_SECONDS` small (e.g. `3600`) while confirming certificates — browsers remember HSTS per host and a long max-age set by mistake cannot be recalled.
7. **Schedule** `flag_overdue_actions` daily and `fail_stuck_reports` periodically. See the [runbook](USER_MANUAL.md#scheduled-jobs).
8. **Email.** Switch `EMAIL_BACKEND` to SMTP and fill in the host credentials, or reminders will only ever print to the server log.
9. **Credentials.** Remove or change the seeded demo accounts. Do not run `seed_data` or `seed_e2e_demo` against production.

---

## Known limitations

- **Report generation runs on a raw daemon thread**, not a task queue ([apps/reports/jobs.py](backend/apps/reports/jobs.py)). Adequate for a single-worker deployment, but if the process restarts mid-compile the row stays `generating` with no retry — `fail_stuck_reports` is the manual recovery. `celery` is pinned as the intended replacement; no broker is configured and no task is defined.
- **`generate_report_file` has no branch for an unknown format.** The three known formats are covered; an unrecognised one would leave the row on `generating` rather than `failed`.
- **`departments/tree` is deliberately unpaginated** — the cascading picker needs the whole tree in one response. Every other list endpoint is paginated.
- **No frontend unit tests.** There is no JS test runner installed; UI behaviour is covered by the manual walkthrough in `TESTING.md` instead.
- **`npm run lint` is not clean.** The current tree reports around 120 problems — mostly unused variables and `react-hooks/exhaustive-deps` warnings across `src/pages/**` and `src/utils/validation.js`. `npm run build` succeeds, so none of them break the bundle, but do not expect a green lint run until they are worked through.
- **Two seeding papercuts on Windows**, both verified against a scratch database: `seed_e2e_demo` crashes on a `cp1252` console unless `PYTHONUTF8=1` is set, and the login page's Audit Manager demo button carries a password no seeder assigns. Both are described in [Quick start](#4-sign-in).
- **The in-app Help modal's role checklists still reference email logins** (`admin@eeu.com` and similar). Authentication is by Employee ID. [USER_MANUAL.md](USER_MANUAL.md) is correct; the modal text has not been updated.

---

## Documentation

| Document | For |
|---|---|
| [USER_MANUAL.md](USER_MANUAL.md) | End users, role by role, plus the administrator runbook |
| [TESTING.md](TESTING.md) | Test coverage map, role × capability matrix, manual walkthrough |
| [ENHANCEMENT_PLAN.md](ENHANCEMENT_PLAN.md) | Roadmap notes |
| [backend/.env.example](backend/.env.example) · [frontend/.env.example](frontend/.env.example) | Annotated configuration reference |

Support: `audit.support@eeu.gov.et`
