# Testing the EEU Internal Audit Management System

Two layers, and they cover different things:

- **Automated** — Django API tests, one suite per app, every gate asserted for all five roles. This is what proves the permission matrix and the notification/audit-log side effects. Run it on every change.
- **Manual** — the role walkthrough in [§3](#3-manual-role-walkthrough). This is what proves the *browser* reaches those endpoints. A handler that mutates local state and shows a green toast without calling the API passes every backend test ever written; only a refresh catches it. Several of the bugs this checklist was written for were exactly that shape, which is why the walkthrough asks you to refresh.

---

## 1. Automated tests

```bash
cd backend
python manage.py test                                   # everything
python manage.py test apps.findings -v 2                # one app
python manage.py test apps.findings.tests.FindingScopingTest   # one class
python manage.py check
python manage.py makemigrations --check --dry-run        # no model drift
```

```bash
cd frontend
npm run lint
npm run build
```

Tests use SQLite in a throwaway database, so no seed data is needed and nothing touches `db.sqlite3`. File-handling suites redirect `MEDIA_ROOT` to a temp directory and remove it in `tearDownClass`, so `media/` stays clean.

### Coverage by app

| App | Tests | What it pins down |
|---|---|---|
| `accounts` | 51 | org-unit tree + pagination, service-center seed, directorate-scoped dashboard, `ProfileView` self-service edits |
| `audit_planning` | 35 | universe CRUD, `due-for-re-audit`, plan submit/approve, engagement numbering, `update-status` back-filling `last_audited`, engagement read scoping |
| `audit_execution` | 30 | program submit/approve, procedure CRUD audit logging, `complete`, working-paper upload/review/download/delete |
| `findings` | 32 | `FND-#####`, assignment notifications, the auditee comment/evidence workspace, resolve/close/dispute/reopen, read scoping |
| `corrective_actions` | 27 | `CAPA-#####`, `add-response`, `schedule-followup` gating, paginated `overdue` and its due-date boundary, `summary`, both scoping branches |
| `risk_assessment` | 32 | risk-parameter gate, score computation and universe propagation, `heatmap`/`summary`, the self-assessment lock-down |
| `reports` | 28 | template gate, async generation contract, a real compile of all three formats, the failure path, `export`, six-month `analytics` buckets |
| `common` | — | the capability matrix itself, plus a cross-app RBAC sweep |
| `notifications` | — | `notify`/`notify_roles`, unread count, settings gate |

Shared fixtures live in [role_fixtures.py](backend/apps/common/role_fixtures.py): `RoleFixtureMixin` builds all five users plus two departments once per class, and `assert_status_by_role` runs one request per role against an expectation table. That table **must** name every role — a partially filled one fails rather than silently skipping a role.

Two conventions worth knowing when reading a failure:

- **403 vs 404 is deliberate.** A 403 means the record is visible but the caller is not named on it. A 404 means read scoping hid the row entirely, so `get_object` never reached the object check. Both are asserted explicitly; neither is papered over with `assertIn(status, (403, 404))`.
- **Report generation is threaded.** `enqueue_report_generation` starts a raw thread, so tests either patch it or call `_generate_report_task` / `generate_report_file` synchronously. A real thread would touch the test database outside the transaction the test case rolls back.

---

## 2. Role × capability matrix

The server-side source of truth is `ROLE_CAPABILITIES` in [permissions.py](backend/apps/common/permissions.py); the frontend mirrors it in [usePermissions.js](frontend/src/hooks/usePermissions.js) for UI gating only. Every row below is asserted by a test.

| Feature | admin | audit_manager | supervisor | auditor | auditee |
|---|:---:|:---:|:---:|:---:|:---:|
| Create/edit users | ✅ | ❌ | ❌ | ❌ | ❌ |
| View audit trail | ✅ | ✅ | ✅ | ❌ | ❌ |
| System settings | ✅ | ✅ | ❌ | ❌ | ❌ |
| Risk parameters (write) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Risk assessment (write) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Submit self-assessment | ✅ | ✅ | ✅ | ✅ | ✅ |
| Review self-assessment | ✅ | ✅ | ✅ | ❌ | ❌ |
| Universe / plan / engagement (write) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Approve plan | ✅ | ✅ | ✅ | ❌ | ❌ |
| Submit plan / program | ✅ | ✅ | ✅ | own only | ❌ |
| Program + procedures (write) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Approve program / review working paper | ✅ | ✅ | ✅ | ❌ | ❌ |
| Log finding | ✅ | ✅ | ✅ | ✅ | ❌ |
| Comment / upload evidence on a finding | ✅ | ✅ | ✅ | ✅ | own finding only |
| Resolve / close / reopen finding | ✅ | ✅ | ✅ | ✅ | ❌ |
| Dispute finding | ✅ | ✅ | ✅ | ✅ | own finding only |
| Create CAPA | ✅ | ✅ | ✅ | ✅ | ❌ |
| Respond to CAPA | ✅ | ✅ | ✅ | ✅ | own department |
| Schedule CAPA follow-up | ✅ | ✅ | ✅ | own only | ❌ |
| Generate report | ✅ | ✅ | ✅ | ✅ | ❌ |
| Report templates (write) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Read analytics | ✅ | ✅ | ✅ | ✅ | ✅ |
| Read scoping | all | all | all | all | own dept + own records |

"own only" means the object check in `InvolvedPartyOrCapability` applies: an auditor may submit a plan or program they authored, or one whose engagement they lead, but not a colleague's.

### What auditee scoping actually filters

| Endpoint | An auditee sees |
|---|---|
| `/api/findings/findings/` | findings where they are the auditee or assignee, plus every finding on an engagement in their department |
| `/api/findings/evidence/` | evidence attached to those findings |
| `/api/planning/engagements/` | engagements for their department, plus any they are named on |
| `/api/corrective/actions/` | every CAPA owned by someone in their department (owner-only if they have no department) |
| `/api/risk/self-assessments/` | **only their own submission** — so does an auditor, since scoping here is by APPROVE_PLANS, not role |

A user with no department falls back to records naming them personally. This is asserted in every scoping suite, because it is the branch a demo database never exercises.

---

## 3. Manual role walkthrough

### Setup

```bash
cd backend
python manage.py migrate
python manage.py seed_org_structure && python manage.py seed_eeu_audit_structure
python manage.py seed_service_centers
python manage.py seed_data && python manage.py seed_e2e_demo
python manage.py flag_overdue_actions      # populates the overdue CAPA tab
python manage.py runserver
```

```bash
cd frontend && npm install && npm run dev
```

**Login is by Employee ID, not email.** `LoginSerializer` takes `employee_id`.

| Role | Employee ID | Password |
|---|---|---|
| System Admin | `EEU-10001` | `admin123` |
| Audit Manager | `EEU-10002` | `User1234` |
| Supervisor | `EEU-10003` | `user123` |
| Lead Auditor | `EEU-10004` | `user123` |
| Auditee | `EEU-10005` | `user123` |

`EEU-10001` is created by `seed_data` only. The other four exist after either seed command.

Fill in the **Result** column as ✅ / ❌ and note the actual behaviour when it differs.

---

### 0. Login page

| # | Step | Expected | Result |
|---|---|---|---|
| 0.1 | Click each of the five one-click demo buttons in turn | All five authenticate and land on the dashboard. **Audit Manager is the one to watch** — it used to send the wrong password and always failed | |
| 0.2 | Log in with a wrong password | Inline error, no redirect, no token stored | |
| 0.3 | Log in normally, then reload the page | Still authenticated — the refresh token survives a reload | |

---

### 1. System Admin — `EEU-10001`

| # | Step | Expected | Result |
|---|---|---|---|
| 1.1 | Log in | Dashboard renders; sidebar shows **User Management** and **Audit Trail** | |
| 1.2 | User Management → create one user per role (name, email, role, department, employee ID) | All five created and listed | |
| 1.3 | Deactivate a user, then reactivate them | Status badge flips both ways; the deactivated user cannot log in | |
| 1.4 | Reset a user's password | Success, and the new password works on the login page | |
| 1.5 | Audit Trail → read the log | Your own actions from 1.2–1.4 appear with user, action, model, timestamp and IP | |
| 1.6 | Audit Trail → page past the first 20 rows | Page 2 loads different rows, none repeated | |
| 1.7 | Settings modal → System tab → change a setting and save | 200, value persists after reopening the modal | |
| 1.8 | Settings modal → Profile tab → change your first name and phone, save | 200 and the header name updates. **Previously a 404 for every role** | |
| 1.9 | Visit `/planning`, `/execution`, `/findings`, `/risk`, `/capa`, `/reports` | All reachable | |
| 1.10 | Dashboard → switch the directorate selector | Every KPI and chart rescopes, not just the label | |

---

### 2. Audit Manager — `EEU-10002`

| # | Step | Expected | Result |
|---|---|---|---|
| 2.1 | Log in | Dashboard renders; **User Management is absent** from the sidebar | |
| 2.2 | Navigate directly to `/users` | Blocked by the route guard — no user list is rendered | |
| 2.3 | Planning → Audit Universe → add an entry (department, category, risk score, frequency) | Created and listed | |
| 2.4 | Risk → Parameters → add a parameter with a weight | 201. Supervisor and below get 403 here (step 3.8) | |
| 2.5 | Risk → create an assessment (likelihood, impact, control effectiveness) | Score and rating are computed **server-side**; the linked universe entry's risk score updates to match | |
| 2.6 | Risk → Heat Map | The 5×5 grid places your assessment at the right cell; the year filter changes what is shown | |
| 2.7 | Risk → Self-Assessments → open a submitted one → Review with comments | Status → `reviewed`, reviewer and timestamp stamped, and the submitter gets a notification. Must go through the **Review** action, not a status dropdown | |
| 2.8 | Planning → create an Annual Audit Plan | Created as `draft` | |
| 2.9 | Submit the plan | Status → `submitted`; approvers are notified, and you are not notified about your own submission | |
| 2.10 | Approve the plan | Status → `approved`, with `approved_by`/`approved_at` stamped; the author is notified; the audit trail records an APPROVE | |
| 2.11 | Planning → Engagements → schedule one under the plan, assigning lead auditor + supervisor | Engagement number is assigned as `ENG-#####` **by the server**; lead and supervisor are notified | |
| 2.12 | Engagements → add a team member | Member appears on the engagement | |
| 2.13 | Reports → generate a PDF report for that engagement | Row appears as `GENERATING`, then flips to `READY` **without a manual refresh** | |
| 2.14 | Download the ready report | A valid PDF, named from the report title. Check the URL: no `localhost:8000`, and the JWT is attached | |
| 2.15 | Generate an **Excel** report and download it | Opens in a spreadsheet app as `.xlsx`. **This whole path used to crash** — Excel and Word died with `UnboundLocalError` before writing a byte, leaving the row stuck on `GENERATING` | |
| 2.16 | Generate a **Word** report and download it | Opens as `.docx` | |
| 2.17 | Reports → Templates → create a template | 201. Supervisor and below get 403 here | |

---

### 3. Supervisor — `EEU-10003`

| # | Step | Expected | Result |
|---|---|---|---|
| 3.1 | Log in | Sidebar shows Audit Trail but **not** User Management | |
| 3.2 | Navigate directly to `/users` | Blocked | |
| 3.3 | Execution → select the engagement → review the program's objectives and scope | Program renders | |
| 3.4 | Click **Approve Fieldwork** | 200, status → `approved`, reviewer stamped, the preparer is notified. **This button used to 404** — it called `approve-fieldwork/` when the route is `approve/` | |
| 3.5 | Working Papers → open an uploaded paper → add review notes and sign off | `is_reviewed` set, reviewer stamped, preparer notified | |
| 3.6 | Working Papers → download a paper | Correct file, correct filename, correct content type | |
| 3.7 | Findings → open a finding → **Close** | Status → `closed` with a resolution date; the auditor who raised it is notified | |
| 3.8 | Risk → try to add a risk parameter | Blocked — the button is hidden, and a direct POST returns 403 | |
| 3.9 | CAPA → open an action → **Verify & Schedule Follow-up** | Follow-up created, owner notified | |
| 3.10 | Reports → try to create a template | Blocked (403) | |

---

### 4. Lead Auditor — `EEU-10004`

| # | Step | Expected | Result |
|---|---|---|---|
| 4.1 | Log in | Sidebar shows **no Audit Trail** and no User Management | |
| 4.2 | Navigate directly to `/audit-trail` | Blocked | |
| 4.3 | Execution → select the active engagement → create the Audit Program | Created as `draft`, with you recorded as preparer | |
| 4.4 | Add three fieldwork procedures | All three listed | |
| 4.5 | Edit a procedure's title | The change persists. It used to POST a **duplicate** instead of patching — so check the list length did not grow | |
| 4.6 | Delete a procedure, then **refresh the page** | It stays deleted. Before the fix the handler only mutated local state and showed a success toast, so a refresh brought it back | |
| 4.7 | Change a procedure's status to In Progress, then **refresh** | The status persists | |
| 4.8 | Set a procedure to Completed | `completed_by`/`completed_at` stamped, the conclusion preserved, and the engagement lead notified | |
| 4.9 | Click **Submit for Review** on the program | 200, status → `submitted`, supervisor notified. **This button used to 404** — it called `submit-for-review/` when the route is `submit/` | |
| 4.10 | Upload a working paper with a file | Created with you as preparer; the file is downloadable | |
| 4.11 | Try to review your own working paper | Blocked — review needs APPROVE_PLANS | |
| 4.12 | Findings → **Log Finding** (severity, condition, criteria, cause, effect, recommendation, assignee, auditee) | Created. The number is `FND-#####` **assigned by the server** — the form no longer invents a `FIND-####` the record never gets | |
| 4.13 | Assignee and auditee check their bell | Both were notified; you were not notified about your own finding | |
| 4.14 | Open the finding's detail page → add a comment | Comment appears in the thread; the rest of the thread is notified | |
| 4.15 | Detail page → upload evidence | Evidence listed and downloadable | |
| 4.16 | Detail page → **Resolve** | Status → `resolved` with a resolution date | |
| 4.17 | With more than 20 findings in the register, deep-link straight to the 25th finding's detail page | It renders. It used to say "Finding not found" — the page fetched page 1 of the list and searched it client-side | |
| 4.18 | CAPA → create an action from that finding (owner, priority, due date) | Number is `CAPA-#####` from the server; the owner is notified with the due date in the message | |
| 4.19 | Reports → generate a draft report | Generates and downloads | |
| 4.20 | Try to approve a plan | Blocked (403) | |

---

### 5. Auditee — `EEU-10005`

This is the role most worth walking end to end: it holds no capabilities at all, so everything it *can* do runs through object-level checks, and everything it *sees* runs through queryset scoping.

| # | Step | Expected | Result |
|---|---|---|---|
| 5.1 | Log in | Dashboard shows a **My Work** section: findings assigned to you, CAPAs you own, self-assessments awaiting you | |
| 5.2 | Sidebar | No User Management, no Audit Trail | |
| 5.3 | Risk → Self Assessment → submit one (likelihood, impact, control effectiveness, justification) | 201. The parent assessment is flagged as self-assessed **server-side** — you hold no WRITE_AUDIT, so a client-side PATCH would 403 and make a successful submission look failed | |
| 5.4 | Risk → Self Assessments list | **Only your own submission.** Another auditee's is not listed | |
| 5.5 | Try to edit your submission | Allowed while it is `submitted` | |
| 5.6 | After a manager reviews it (step 2.7), try to edit it again | Blocked (403) — a reviewed submission is closed to edits | |
| 5.7 | Findings register | Only findings naming you, or on an engagement in your department. Another department's findings are absent | |
| 5.8 | Open a finding assigned to you → add a comment | 201. **This used to be a 403** — the action inherited a WRITE_AUDIT gate, so the person being asked to respond to a finding could not | |
| 5.9 | Same finding → upload evidence | 201, and the auditor who raised it is notified | |
| 5.10 | Same finding → **Dispute** | Status → `disputed`; the auditor is notified | |
| 5.11 | Same finding → look for Resolve / Close / Reopen | Not offered, and a direct POST returns 403 | |
| 5.12 | CAPA list | Only your department's actions | |
| 5.13 | Open a CAPA you own → **Respond** with notes, a status update, and an evidence file | 201; the status moves; the auditor who raised it is notified | |
| 5.14 | Same CAPA → look for Verify & Schedule Follow-up | Not offered — the owner cannot sign off their own remediation | |
| 5.15 | Anywhere → look for create/edit buttons on universe, plans, engagements, programs, procedures, findings, CAPAs | All hidden | |
| 5.16 | Direct POST to `/api/findings/findings/` (browser console or curl with your token) | 403 | |
| 5.17 | `GET /api/risk/self-assessments/<another user's id>/` | 404 — scoping hides the row rather than admitting it exists | |
| 5.18 | `PATCH /api/risk/self-assessments/<your id>/ {"status": "reviewed"}` | 200, **but the status stays `submitted`** and no reviewer is stamped. This was a privilege-escalation route around the review gate | |
| 5.19 | Reports → try to generate a report | Blocked (403) | |

---

### 6. Cross-cutting — repeat as every role

| # | Step | Expected | Result |
|---|---|---|---|
| 6.1 | Open the bell dropdown and click **every** notification | Each lands on the specific record — never the dashboard. All eight backend link shapes used to miss the router and fall through to the `*` catch-all | |
| 6.2 | Check the unread badge before and after reading one | Count decrements without a reload | |
| 6.3 | Toggle EN ⇄ AM on every page | No raw keys leak (e.g. `overdueCapas`, `selectAuditEngagement`) | |
| 6.4 | Toggle light ⇄ dark on every page | No unreadable text, no missing borders | |
| 6.5 | Resize to a narrow window on every page | Sidebar collapses; tables scroll rather than overflow | |
| 6.6 | Settings → Profile → change your name | 200 and the header updates | |
| 6.7 | Change your password, log out, log in with the new one | Works; the old password is refused | |
| 6.8 | Log out | Redirected to login, and the refresh token is blacklisted — the back button does not restore the session | |
| 6.9 | Leave the tab idle past the access-token lifetime, then act | The refresh happens transparently; no spurious logout | |
| 6.10 | Page past row 20 on the findings, CAPA and universe tables | Page 2 loads different rows | |

---

### 7. Endpoint checks worth running directly

Some of these are hard to see through the UI. Use the browser console with your token, or curl.

| # | Check | Expected | Result |
|---|---|---|---|
| 7.1 | `GET /api/reports/generated/analytics/` | `monthly_findings` has exactly six consecutive calendar months with `%b %Y` labels. February must be present and no month repeated — the old 30-day stepping skipped February and double-counted 31-day months | |
| 7.2 | `GET /api/corrective/actions/overdue/` | A paginated `{count, results}`, and `?page_size=1` returns one row with the full count. It also has to be correct **before** `flag_overdue_actions` has ever run, since it derives from the due date | |
| 7.3 | `GET /api/corrective/actions/overdue/` with an action due **today** | Today is not overdue; yesterday is | |
| 7.4 | `GET /api/planning/universe/due-for-re-audit/?as_of=2030-01-01` | Everything lapsed is listed; `?as_of=not-a-date` returns 400 mentioning `YYYY-MM-DD` | |
| 7.5 | `POST /api/findings/findings/` with your own `finding_number` | Ignored; the server's `FND-#####` wins | |
| 7.6 | `PATCH /api/findings/findings/<id>/ {"identified_by": <other user>}` | Ignored — read-only | |
| 7.7 | `GET /api/reports/generated/<id>/export/` on a row still `generating` | 400, not an empty file | |
| 7.8 | `GET /api/auth/audit-trail/` as an auditor | 403 — the trail requires the capability even to read | |

---

## 4. Known limitations

- **Report generation runs on a raw thread**, not a task queue. It is enough for a single-worker deployment: if the process restarts mid-compile the row stays `generating` with no retry. Swap `enqueue_report_generation` for a Celery task if durability matters.
- **`departments/tree` is deliberately unpaginated** — the cascading picker needs the whole tree in one response. Every other list endpoint is paginated.
- **`generate_report_file` has no branch for an unknown format.** The three known formats are covered; an unrecognised one would leave the row on `generating` rather than `failed`.
- **No frontend unit tests.** UI behaviour is covered by the walkthrough above, deliberately — the project has no JS test runner installed, and adding one was out of scope.
