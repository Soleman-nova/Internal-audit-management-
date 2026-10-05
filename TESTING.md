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
| `accounts` | 125 | org-unit tree + pagination, service-center seed, directorate-scoped dashboard, `ProfileView` self-service edits |
| `audit_planning` | 74 | universe CRUD, `due-for-re-audit`, plan submit/approve, engagement numbering, the auditee representative round-tripping, `update-status` back-filling `last_audited`, engagement read scoping, and the lifecycle fields (`status`, `actual_start`/`actual_end`, approver) being read-only so the completion guard is the only way to close an engagement |
| `audit_execution` | 57 | program submit/approve, `complete` and `reopen` (and the refusal to close a program whose steps have no outcome), procedure CRUD audit logging, the `complete` action, the announcement of a failed step, completion percent that counts every finished outcome, working-paper upload/review/download/delete |
| `findings` | 101 | `FND-#####`, assignment notifications, the publication gate (`publish`, and the auditee's total exclusion before it), the auditee's inheritance of the engagement's representative and the resulting end-to-end unblock, the reviewer notification on create, the auditee comment/evidence workspace, resolve/close/dispute/reopen, read scoping, the named source procedure, and the derived overdue flag |
| `corrective_actions` | 100 | `CAPA-#####`, the auditee's proposal and the lead auditor's sign-off, the refusal to link an action to a finding no supervisor has endorsed, the transitions an ordinary edit may **not** make (`pending_approval` in either direction, `overdue`, `not_implemented`, and out of a terminal status), `add-response` and the split between the statuses an owner may report and the ones the audit side records, `verify-and-close` as the auditor's single act of verification and closure, the ownership gate on `schedule-followup`, paginated `overdue` and its due-date boundary, `summary`, both scoping branches |
| `risk_assessment` | 79 | risk-parameter gate, score computation and universe propagation, `heatmap`/`summary`, the self-assessment lock-down |
| `reports` | 53 | template gate, async generation contract, a real compile of all three formats, the failure path, `export`, six-month `analytics` buckets, and the disclosure of material held back because its finding is unendorsed |
| `common` | 47 | the capability matrix itself, a cross-app RBAC sweep, and the `PREFIX-YYYY-NNNN` sequence — including coexistence with the hand-numbered seed rows that are longer than any generated number |
| `notifications` | 16 | `notify`/`notify_roles`, unread count, settings gate |

Shared fixtures live in [role_fixtures.py](backend/apps/common/role_fixtures.py): `RoleFixtureMixin` builds all five users plus two departments once per class, and `assert_status_by_role` runs one request per role against an expectation table. That table **must** name every role — a partially filled one fails rather than silently skipping a role.

Two conventions worth knowing when reading a failure:

- **403 vs 404 is deliberate.** A 403 means the record is visible but the caller is not named on it. A 404 means read scoping hid the row entirely, so `get_object` never reached the object check. Both are asserted explicitly; neither is papered over with `assertIn(status, (403, 404))`.
- **Report generation is threaded.** `enqueue_report_generation` starts a raw thread, so tests either patch it or call `_generate_report_task` / `generate_report_file` synchronously. A real thread would touch the test database outside the transaction the test case rolls back.

### Clearing the database

`reset_business_data` empties the transactional tables without touching accounts — `manage.py flush` cannot be used because it would take `User` and `Role` with it.

```bash
cd backend
python manage.py reset_business_data --dry-run    # report counts, delete nothing
python manage.py reset_business_data              # type `wipe` to confirm
```

**Deleted:** audit universe, plans, engagements, team members, risk assessments and self-assessments, programs, procedures, working papers, findings, evidence, finding comments, CAPAs, action responses, follow-ups, generated reports, notifications, and the audit trail.

**Kept:** users, roles, departments (the whole org tree), report templates, system settings, projects, and risk parameters.

The command does not reset PK sequences and does not need to: reference numbers come from the highest numeric `PREFIX-YYYY-` row in [reference_numbers.py](backend/apps/common/reference_numbers.py), so `FND-<year>-0001` starts at 0001 again once the tables are empty. It leaves `media/` alone by default — files are not rows — and reports how many uploads it orphaned; pass `--purge-files` to remove those four directories as well.

Every run ends with a verification pass, also available standalone as `--verify`. It asserts the business tables are empty, the kept tables are unchanged, every role still has an active user, an active admin remains, the capability matrix covers every role, and the org tree still has a root. It exits non-zero on failure, so it can gate a script.

After a wipe, **do not re-run `seed_data` / `seed_e2e_demo`** unless you want the demo lifecycle back — they only add. The five demo accounts the Playwright suite signs in as live in `User` and survive the wipe, so §3 still works on an otherwise empty database.

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
| Create CAPA | ✅ | ✅ | ✅ | ✅ | own finding only |
| Approve a CAPA plan | ✅ | ✅ | ✅ | own only | ❌ |
| Respond to CAPA | ✅ | ✅ | ✅ | ✅ | own department, progress statuses only |
| Schedule CAPA follow-up | ✅ | ✅ | ✅ | own only | ❌ |
| Verify & close a CAPA | ✅ | ✅ | ✅ | own only | ❌ |
| Generate report | ✅ | ✅ | ✅ | ✅ | ❌ |
| Report templates (write) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Read analytics | ✅ | ✅ | ✅ | ✅ | ✅ |
| Read scoping | all | all | all | all | own dept + own records |

"own only" means the object check in `InvolvedPartyOrCapability` applies: an auditor may submit a plan or program they authored, or one whose engagement they lead, but not a colleague's.

### What auditee scoping actually filters

| Endpoint | An auditee sees |
|---|---|
| `/api/findings/findings/` | **only published findings** (never `draft`/`open`), and within those only where they are the auditee or assignee, plus findings on an engagement in their department |
| `/api/findings/evidence/` | evidence attached to those findings — inherits the publication filter, or the file and its title would disclose the finding |
| `/api/planning/engagements/` | engagements for their department, plus any they are named on |
| `/api/corrective/actions/` | every CAPA owned by someone in their department (owner-only if they have no department), minus any raised against an unpublished finding |
| `/api/risk/self-assessments/` | **only their own submission** — so does an auditor, since scoping here is by APPROVE_PLANS, not role |

The publication filter is the other half of the auditee's scope: a finding nobody has endorsed is not theirs to see, and the filter lives on the querysets rather than on each action, so `respond`, `dispute`, `add-comment` and `upload-evidence` all refuse it with a 404 rather than each needing its own status check. `CanProposeCorrectiveAction` is the exception — it reads the finding id out of the request body instead of resolving an object, so it repeats the filter by hand.

A user with no department falls back to records naming them personally. This is asserted in every scoping suite, because it is the branch a demo database never exercises.

---

## 3. Manual role walkthrough

### Setup

```bash
cd backend
# On Windows, set PYTHONUTF8=1 first (bash): export PYTHONUTF8=1
# seed_e2e_demo prints a ✓ its summary; the default cp1252 console cannot encode it
# and the command dies part-way with a UnicodeEncodeError otherwise.
python manage.py migrate
python manage.py seed_org_structure && python manage.py seed_eeu_audit_structure
python manage.py seed_service_centers && python manage.py seed_hq_org_units
python manage.py seed_data && python manage.py seed_e2e_demo
python manage.py flag_overdue_actions      # populates the overdue CAPA tab
python manage.py runserver
```

For a **live, role-by-role presentation** — starting at entity creation and ending at a generated report — run `seed_demo_case` instead of the fully-completed `seed_e2e_demo`. It seeds one case up to a checkpoint and leaves the rest to be performed live (fieldwork → findings → CAPA → report); the walkthrough is [DEMO.md](DEMO.md). `seed_e2e_demo` still seeds its completed lifecycle alongside, so both can coexist on a demo database.

```bash
cd frontend && npm install && npm run dev
```

**Login is by Employee ID, not email.** `LoginSerializer` takes `employee_id`.

| Role | Employee ID | Password |
|---|---|---|
| System Admin | `EEU-10001` | `admin123` |
| Audit Manager | `EEU-10002` | `user123` |
| Supervisor | `EEU-10003` | `user123` |
| Lead Auditor | `EEU-10004` | `user123` |
| Auditee | `EEU-10005` | `user123` |

`EEU-10001` is created by `seed_data` only. The other four exist after either seed command.

**An executable version of this walkthrough now exists.** `frontend/e2e/` is a Playwright suite that performs one real UI login per role, then drives every section below through the browser — including the refresh-after-mutation checks that a backend test cannot catch. Run it with:

```bash
# terminal 1 — backend (restart it if you have run the suite before, so the
# 1000/hour authenticated throttle resets)
cd backend && export PYTHONUTF8=1 && python manage.py runserver

# terminal 2
cd frontend && npx playwright install chromium && npx playwright test
```

The tables below remain the human-readable spec; the Playwright suite is its automated execution.

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
| 2.11 | Planning → Engagements → schedule one under the plan, assigning lead auditor + supervisor | Engagement number is assigned as `ENG-YYYY-NNNN` **by the server**; lead and supervisor are notified | |
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
| 3.9 | CAPA → open an action whose evidence has been filed → **Verify & Close CAPA** | 200; a completed follow-up record is written, the action and its finding both go to `closed`, and the owner is notified. Verifying and closing are one route, so there is no way to close one without recording the verification. A PATCH to `closed` by an auditor who is neither this action's nor an approver returns 403 | |
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
| 4.9a | With a step still *Pending*, click **Complete Fieldwork** | Refused, naming the steps with no recorded outcome, and the status does not move. A `PATCH {"status":"completed"}` used to bypass this entirely — and *Completed* is what locks every procedure control | |
| 4.9b | Give every step an outcome, then **Complete Fieldwork** | → `completed`, engagement lead notified. *Failed* and *Not Applicable* count as outcomes; a step that failed is what raises a finding | |
| 4.9c | **Reopen Fieldwork** | → `approved`, and the procedure controls come back | |
| 4.9d | `PATCH /api/execution/programs/{id}/` with `{"status":"approved","approved_by":…}` | 200 and **nothing changes** — those fields are read-only. The only way to approve is `approve/`, which gates on APPROVE_PLANS and stamps the approver | |
| 4.10 | Upload a working paper with a file | Created with you as preparer; the file is downloadable | |
| 4.11 | Try to review your own working paper | Blocked — review needs APPROVE_PLANS | |
| 4.12 | Findings → **Log Finding** (failed procedure, severity, condition, criteria, cause, effect, recommendation) | Created as **Pending Supervisor Review** (the stored value stays `draft`). The number is `FND-YYYY-NNNN` **assigned by the server** — the form no longer invents a `FIND-####` the record never gets. The form asks for no auditee: the finding is addressed to the **engagement's auditee representative** and inherits it. It is invisible and inert to the auditee until published (see 4.23) | |
| 4.12a | Log a finding on an engagement whose **auditee representative is blank** | Created with `auditee: null` and no error — there is no honest value to inherit. The engagement row shows `—` for the representative, and the finding will be readable by the department but unanswerable until one is set (see 4.12b for the consequence) | |
| 4.12b | On the engagement, set the auditee representative, then log a finding | The finding carries that user in its `auditee` field, and the auditee's own actions on it are authorized by that field rather than by the department fallback | |
| 4.13 | Assignee and auditee check their bell after logging a finding | Only the **audit team** was notified. The auditee was not — a finding nobody has endorsed should not be announced to the party it concerns, and on the common shape where the assigned contact *is* the auditee it went straight to them. The **engagement's supervisor** is told it awaits review (`approval_needed`), and when the engagement names no supervisor every active `APPROVE_PLANS` holder is told instead | |
| 4.14 | Open the finding's detail page → add a comment | Comment appears in the thread; the rest of the thread is notified | |
| 4.15 | Detail page → upload evidence | Evidence listed and downloadable | |
| 4.16 | Detail page → **Resolve** | Status → `resolved` with a resolution date | |
| 4.17 | With more than 20 findings in the register, deep-link straight to the 25th finding's detail page | It renders. It used to say "Finding not found" — the page fetched page 1 of the list and searched it client-side | |
| 4.18 | CAPA → create an action from that finding (owner, priority, due date) | Number is `CAPA-YYYY-NNNN` from the server; the owner is notified with the due date in the message. An audit-raised action starts `open` — it needs no sign-off | |
| 4.18a | CAPA → **Spawn CAPA Task** → open the finding picker, with a finding of your own still awaiting supervisor review | It is **not listed**, and a hint under the picker says why rather than the list quietly coming up short. Posting the link by hand is a 400 naming the finding and its state. Only a *new* link is refused: an action that already carries an unendorsed finding — one raised while this hole was open — stays editable, so correcting its title does not fail | |
| 4.19 | Reports → generate a draft report | Generates and downloads | |
| 4.19a | Generate a report for an engagement holding an action against an unendorsed finding | Section 5 does not print the action — a corrective action is only as distributable as the finding it answers — and **says so**: *"Not included in this report: 1 corrective action whose finding has not yet been endorsed for publication."* Section 4 does the same for the finding itself. *"No corrective actions have been assigned for findings in this engagement"* is now printed only when that is literally true. **4.18a closed the route that used to create this state by hand**, so the walkthrough cannot produce it any more: it is covered by the reports tests, and survives for rows that predate the gate | |
| 4.19b | Publish that finding (4.24), then generate the report again | The action and the finding both appear, with no withheld note. Words it as *"Not shown above: …"* instead when the section has rows **and** withheld siblings — a half-published engagement is one report, not two | |
| 4.20 | Try to approve a plan | Blocked (403) | |
| 4.21 | Given a plan the auditee proposed (step 5.14), open it → **Approve Plan** | Status → `open` with `approved_by`/`approved_at` stamped; the auditee is notified. Re-approving is a 400 — the transition is one-shot | |
| 4.22 | Given a plan proposed by an auditee but routed to a colleague (the engagement's lead auditor), try to approve it | Blocked (403). The gate is the *raiser-or-approver*, not every auditor — see `schedule-followup` for the same shape | |
| 4.23 | Take the draft from 4.12, log in as the auditee before publishing | The finding is **absent from their register and 404s on its detail route**, the kanban drops the pre-publication columns, and the list reads *"Nothing has been published to you yet."* Comment, evidence, respond and dispute all 404 too, and proposing a CAPA against it is refused | |
| 4.24 | You (supervisor) → open the draft → **Publish to Auditee** | Status → `awaiting_auditee_response`; the auditee named on the finding — inherited from the engagement — is notified. Only now do 4.14–4.16 and 5.7+ work for them. Publishing twice is a 400, and a `resolved`/`closed` finding cannot be published at all. On a finding that names nobody (4.12a), the engagement's representative is notified instead, and failing that the department's auditees — publishing can never notify no one | |
| 4.24a | As the auditee named on the engagement, answer a finding you did **not** have to be named on individually (4.12b) | Comment, evidence, respond and dispute all succeed. This is the regression the inheritance exists for: before it, the same finding was visible to this user (the register falls back to the engagement's department) and 403 on every one of the four, because the object-level check had no auditee to match | |
| 4.24b | As a **different** auditee in the same department, try the same four actions | Still 403. The department fallback is a *read* convenience — writing stays with the named representative, and the register is what tells you which of the two you are looking at | |
| 4.25 | Once the auditee has filed evidence (5.13b) → **Verify & Close CAPA** → set the date and findings | 200. A completed follow-up record is written, the action → `closed` with a completion date, and the finding behind it → `closed`. The owner is notified | |
| 4.26 | Open one of your colleague's CAPAs → **Verify & Close CAPA**, and separately `PATCH` it to `closed` | Both blocked (403). The action is scoped to its own auditor, and the status PATCH — which used to be gated on `WRITE_AUDIT` alone — no longer offers the same decision by a side door |
| 4.27 | Open a finding → read **Source procedure**, and follow the link | The fieldwork step is **named** (`3.1. Agree disbursements to the ledger`), not an id, and the link lands on the execution board with that step highlighted. Until this existed the link was in the database and nowhere a reader could follow it — a finding was an assertion with nothing behind it |
| 4.27a | Back on Execution → look at a failed step that already has a finding against it | A badge says how many. Before it, a failed step with a finding looked exactly like one nobody had written up, and **Log Finding** on it opened a form that would accept a duplicate |
| 4.27b | On a published finding with no action, click **Spawn CAPA Task linked to Finding** | The follow-up form opens by itself, already pointed at *this* finding with its title, description and recommendation carried across. The button is absent while the finding is unendorsed, and the section says why |
| 4.27c | Create the action, then reopen the finding | It is listed under **Corrective Actions** with its owner, due date and status, and links to the action. The count also shows in the register's split view |
| 4.27d | Set a finding's target resolution date in the past and reload | An **Overdue** badge, derived live from the date — no scheduled job involved. Not shown once the finding is resolved or closed, and not shown for a finding due *today* |
| 4.28 | In the register's split view, click **Open full finding record** | Reaches the finding's own page. Previously the only way there was a double-click on a list row, which is not discoverable | |

---

### 5. Auditee — `EEU-10005`

This is the role most worth walking end to end: it holds no capabilities at all, so everything it *can* do runs through object-level checks, and everything it *sees* runs through queryset scoping.

| # | Step | Expected | Result |
|---|---|---|---|
| 5.1 | Log in | Dashboard shows a **My Work** section: findings assigned to you, CAPAs you own, self-assessments awaiting you. Findings nobody has published are **not** on it — this queue is your work, and an unendorsed finding is not yet yours | |
| 5.2 | Sidebar | No User Management, no Audit Trail | |
| 5.3 | Risk → Self Assessment → submit one (likelihood, impact, control effectiveness, justification) | 201. The parent assessment is flagged as self-assessed **server-side** — you hold no WRITE_AUDIT, so a client-side PATCH would 403 and make a successful submission look failed | |
| 5.4 | Risk → Self Assessments list | **Only your own submission.** Another auditee's is not listed | |
| 5.5 | Try to edit your submission | Allowed while it is `submitted` | |
| 5.6 | After a manager reviews it (step 2.7), try to edit it again | Blocked (403) — a reviewed submission is closed to edits | |
| 5.7 | Findings register | Only **published** findings, and within those only ones naming you or on an engagement in your department. Another department's findings are absent. A finding nobody has endorsed is absent too, and its detail route 404s — see 4.23 | |
| 5.7a | Findings register on a fresh database | *"Nothing has been published to you yet."* Every finding starts as a draft, so an empty register is the normal state, not a fault |
| 5.8 | Open a finding assigned to you → add a comment | 201. **This used to be a 403** — the action inherited a WRITE_AUDIT gate, so the person being asked to respond to a finding could not | |
| 5.9 | Same finding → upload evidence | 201, and the auditor who raised it is notified | |
| 5.10 | Same finding → **Dispute** | Status → `disputed`; the auditor is notified | |
| 5.11 | Same finding → look for Resolve / Close / Reopen | Not offered, and a direct POST returns 403 | |
| 5.12 | CAPA list | Only your department's actions — and none raised against a finding you cannot see, or the action's own title would disclose it | |
| 5.13 | Open a CAPA you own → **Respond** with notes, a status update, and an evidence file | 201; the status moves; the auditor who raised it is notified. The status list offers only *In Progress*, *Partially Resolved* and *Evidence Submitted / Pending Verification* — an owner reports progress, not outcomes | |
| 5.13a | Same form, but post `status_update: closed` (or `resolved`) directly | **403**, and nothing is written: no action response, no status change, and the finding behind the action is untouched. This route cascades to the finding, so before the status list was narrowed an auditee closed their own remediation *and* settled the finding about them, in a single request | |
| 5.13b | Set **Evidence Submitted / Pending Verification** with the evidence attached | 201. This is the handoff — the claim is yours to make; the conclusion is the auditor's | |
| 5.13c | On a plan that is still `pending_approval`, try to respond | **400**, and the form is not offered. Reporting progress would move the action out of `pending_approval`, the only state **Approve Plan** accepts — so the sign-off became unreachable and the plan approved itself. The status posted is a legitimate one for an owner; it is the stage that is wrong | |
| 5.14 | CAPA → **Formulate Remediation Plan**, pick a finding about you, fill in the plan and a due date | Created as `CAPA-YYYY-NNNN`, owned by you, status `pending_approval`. **This used to be a 403 at creation** — the class-level WRITE_AUDIT gate meant the audit team wrote your plan for you, so the approval step that follows had nothing of yours to approve. There is no owner picker: the server assigns the proposal to its author | |
| 5.15 | Look at the plan you just proposed | Owned by you and awaiting approval. You cannot PATCH it — status included, which is what stops a proposal being closed, and the finding behind it settled, in one request | |
| 5.16 | Open your proposal → look for Approve Plan, or POST to its `/approve/` | Not offered, and 403. The plan is routed to the engagement's lead auditor, not back to you | |
| 5.16a | As an auditor, `PATCH` the action with `{"status":"open"}` while it is `pending_approval` | **400**, and nothing changes. `approve/` is the only route out of that stage: it asks who may sign the plan off and stamps who did and when. Before this the PATCH was accepted, so any auditor could open a plan awaiting their own approval with no approver recorded | |
| 5.16b | `PATCH` an open action with `{"status":"overdue"}` or `{"status":"not_implemented"}` | **400**. `overdue` is derived from the due date by the nightly job, and `not_implemented` is recorded beside the follow-up visit that justifies calling a remedy a failure — neither is an edit | |
| 5.16c | `PATCH` a **closed** action back to `in_progress` | **400**. There is no reopen route, and the edit would have carried the reopening back to the finding behind it | |
| 5.16d | `PATCH` progress statuses (`in_progress`, `partially_resolved`, `evidence_submitted`) as an auditor who is neither the assigner nor an approver | **200** — the guard is about reserved transitions, not about writes in general | |
| 5.17 | Same CAPA → look for Verify & Close CAPA, or POST to its `/verify-and-close/` | Not offered, and 403 — the owner cannot sign off their own remediation. Verify & close is one action: it records the follow-up that proves the check happened and closes the action and its finding together | |
| 5.18 | Anywhere → look for create/edit buttons on universe, plans, engagements, programs, procedures, findings | All hidden | |
| 5.19 | Direct POST to `/api/corrective/actions/` naming a finding from **another directorate**, or one that is still unpublished | 403 — the create gate reads the finding, and mirrors the same scope the register uses, publication included |
| 5.20 | Direct POST to `/api/findings/findings/` (browser console or curl with your token) | 403 | |
| 5.21 | `GET /api/risk/self-assessments/<another user's id>/` | 404 — scoping hides the row rather than admitting it exists | |
| 5.22 | `PATCH /api/risk/self-assessments/<your id>/ {"status": "reviewed"}` | 200, **but the status stays `submitted`** and no reviewer is stamped. This was a privilege-escalation route around the review gate | |
| 5.23 | Reports → try to generate a report | Blocked (403) | |

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
| 7.5 | `POST /api/findings/findings/` with your own `finding_number` | Ignored; the server's `FND-YYYY-NNNN` wins | |
| 7.6 | `PATCH /api/findings/findings/<id>/ {"identified_by": <other user>}` | Ignored — read-only | |
| 7.7 | `GET /api/reports/generated/<id>/export/` on a row still `generating` | 400, not an empty file | |
| 7.8 | `GET /api/auth/audit-trail/` as an auditor | 403 — the trail requires the capability even to read | |

---

### 8. Org structure, regions & service centres

These cover the newer organisational-unit work (commit `414a79b`) that the earlier sections predate. Login as any role with a department (the audit manager works) and sign in with the language set to English first, then repeat the Amharic steps with the language set to Amharic.

| # | Step | Expected | Result |
|---|---|---|---|
| 8.1 | Dashboard → the EEU org chart | The executive/corporate/audit tree renders; expanding a node shows its children; clicking a directorate rescopes the KPIs and charts | |
| 8.2 | Dashboard → directorate selector | FPA, TA, ITA and PP appear; choosing one rescopes every card, not just a label | |
| 8.3 | Planning → Audit Universe → Add → Department picker | The cascading picker shows three steps: chief office → region → service centre. Step one lists Executive Office, Internal Audit and Chief Offices groups; step two lists every region; step three lists the service centres of the chosen region | |
| 8.4 | Pick a region at step two only | Saving records the region as the department — stopping early is legitimate | |
| 8.5 | Pick a service centre at step three | Saving records the service centre | |
| 8.6 | Settings → System → language → Amharic, then repeat 8.1–8.5 | Amharic names from `org_units_am.json` / `service_centers_am.json` are shown in the picker and org chart; no raw keys leak | |
| 8.7 | Admin → Users → Add → Department picker | Same three-step picker; the saved unit shows as the user's department | |

---

## 4. Known limitations

- **Report generation runs on a raw thread**, not a task queue. It is enough for a single-worker deployment: if the process restarts mid-compile the row stays `generating` with no retry. Swap `enqueue_report_generation` for a Celery task if durability matters.
- **`departments/tree` is deliberately unpaginated** — the cascading picker needs the whole tree in one response. Every other list endpoint is paginated.
- **`generate_report_file` has no branch for an unknown format.** The three known formats are covered; an unrecognised one would leave the row on `generating` rather than `failed`.
- **Nothing asserts PDF *layout*.** The findings table's title column used to paint over the Severity column, because a plain string in a reportlab `Table` is drawn with `canvas.drawString`, which neither wraps nor clips. The fix wraps every cell in a `Paragraph`, and `apps.reports.tests` now asserts the *text* — the table cell is proven to draw a markup-bearing title intact rather than eating it as a tag. What is **not** asserted is where the text lands: no PDF-reading library is installed (`pypdf`/`pdfminer` are absent from `requirements.txt`), so the tests inflate and read the raw content streams and cannot see geometry. Column widths, wrapping and any future layout regression still have to be checked by eye on a generated PDF. Word and Excel are covered properly — those files parse, so their cell wrapping and column widths are asserted.
- **`login.spec.js` 0.1 is the suite's flakiest test.** It signs five roles in and out in one test, so it holds the most timing surface; it failed once in a full run (a 90s click timeout on a demo button) and did not reproduce in six consecutive repeats or in isolation (10.4s against the 90s limit). Treat a red 0.1 as a flake first — but re-run it rather than assuming, since the same test would also be the first to notice a login regression.
- **`risk.spec.js` deliberately does not cover the adopt-the-auditee's-figures flow.** Reaching that dialog needs a submitted self-assessment, and its parent accepts only one (a `OneToOne`) — so the test would have to claim the seeded assessment, flip its `is_self_assessment` flag and put it back; creating an assessment instead propagates a score onto an audit-universe row, so tidying up would rewrite seeded risk scores. The semantics are covered by seven backend tests in `AdoptedSourceTest`, and the control's rendering by the i18n bare-key walk.
- **No frontend *unit* tests.** The project still has no JS unit-test runner. UI behaviour is now covered by the Playwright suite in `frontend/e2e/` (§3), which drives the real browser as each role — the refresh-after-mutation checks are exactly the class of defect backend tests cannot catch.
- **The in-app Help modal's role checklists still reference email logins** (`admin@eeu.com` and similar). Authentication is by Employee ID; [USER_MANUAL.md](USER_MANUAL.md) is correct and the modal text has not been updated.
- **Repeated E2E runs against one long-lived backend can trip the authenticated throttle** (1000/hour). A single `npx playwright test` run makes a few hundred requests, so one run is fine; restarting `manage.py runserver` resets the in-memory throttle cache before a re-run. The suite also retries a 429 once with a short backoff.

