# EEU Internal Audit Management System — Enhancement Plan

**Date:** 2026-07-31
**Basis:** Full backend, frontend, and cross-cutting exploration of the current codebase.
**Nature:** This is a prioritized menu, not an all-or-nothing commitment. Phases are ordered so that
foundational fixes (security, shared infrastructure) come before the features that build on them.

---

## How to read this

Each item lists **Why** (the concrete gap found in the code), **What** (the change), and a rough
**Effort** (S = <½ day, M = ~1–2 days, L = multi-day). Security/correctness items are called out first
because several are genuine holes, not just polish.

---

## Phase 0 — Bugs & quick wins (cheap, do first)

| # | Item | Why | Effort |
|---|------|-----|--------|
| 0.1 | Fix `generate-pdf` shortcut action | `reports/views.py` `generate-pdf` creates a `GeneratedReport` with `status='ready'` but **saves no file**, so a later `export` finds nothing. Either save the file or drop the shortcut and reuse the real generator. | S |
| 0.2 | Fix seed data risk-param categories | `seed_data.py` seeds `RiskParameter.category` as `"impact"`/`"likelihood"`, which aren't valid `CATEGORY_CHOICES`; `get_category_display()` misbehaves. | S |
| 0.3 | Seed a `RiskAssessment` | None is seeded, so the report "Risk Analysis" section renders empty on demo data. | S |
| 0.4 | Rename `backend/test_planning_api.py` → `smoke_planning_api.py` | It's a live-HTTP script, not a `TestCase`; the runner collects it and it errors on Windows console emoji. Removes noise from `manage.py test`. | S |
| 0.5 | Notification badge shows a dot, not a count | `AppLayout.jsx` shows a red dot; surfacing the actual `unreadCount` is a one-line UX win. | S |

---

## Phase 1 — Security & authorization (critical)

The single biggest risk: **there is no server-side role enforcement.** Global default is
`IsAuthenticated` and every ViewSet only re-declares that. Consequences found in code:

- Any authenticated user (including `auditee`) can **create/update/delete users**, **approve plans**,
  **close/delete findings**, and **read the full audit trail**.
- `reset-password` (`accounts/views.py`) lets **any authenticated user reset any other user's password** —
  no role or ownership check.

| # | Item | What | Effort |
|---|------|------|--------|
| 1.1 | Role-based permission classes | Add `apps/common/permissions.py` with `IsAdmin`, `IsAuditManagerOrAdmin`, `IsAuditorOrAbove`, `ReadOnlyOrRole`, and object-level ownership checks. Define a role→capability matrix once. | M |
| 1.2 | Apply RBAC to every ViewSet/action | Gate writes: plan approve/submit → manager/admin; user CRUD + reset-password → admin; finding close → auditor+; etc. Keep reads broad but scope auditee data (generalize the existing `corrective_actions` pattern). | M |
| 1.3 | Enforce password validators on API | `UserCreateSerializer`, `reset_password`, `ChangePasswordView` only check `len>=8` and never call Django's configured `validate_password`. Wire the validators in. | S |
| 1.4 | Ops hardening | `DEBUG=True` default, committed `SECRET_KEY` and `.env`, weak seeded passwords. Move secrets to env-only, add `.env` to `.gitignore`, guard media `static()` behind `DEBUG`, parameterize `CORS`/`ALLOWED_HOSTS`. | M |

> Note: 1.1–1.2 must land **with** the frontend route guards (Phase 4.4) — the UI currently hides some
> nav links but leaves routes and actions reachable by URL/console.

---

## Phase 2 — Workflow completeness & automation

### 2A. Time-based automation (currently entirely absent)

Everything is request-driven. `CorrectiveAction` has a required `due_date`, an `overdue` status value,
an `/overdue` endpoint, and an `is_overdue` serializer field — but **nothing ever sets `status='overdue'`**,
and the `action_due` / `action_overdue` / `follow_up` notification types are **defined but never emitted**.
`celery` is in requirements but there's no Celery app; no email is ever sent.

| # | Item | What | Effort |
|---|------|------|--------|
| 2.1 | Overdue detection job | Management command `flag_overdue_actions` that transitions past-due CAPAs to `overdue` (respecting `extended_due_date`) and emits `action_overdue` notifications. Runnable via cron/Task Scheduler now; Celery-beat later. | M |
| 2.2 | Due-soon reminders | Same job emits `action_due` for items due within N days; `follow_up` reminders for scheduled follow-ups. | S |
| 2.3 | Email delivery | Wire the configured (console) `EMAIL_BACKEND` into the notification service as an optional channel gated by the existing `enable_email_alerts` SystemSetting; set `FollowUp.email_sent`. | M |
| 2.4 | (Optional) Celery app | If real async is wanted, add `core/celery.py` + beat schedule so 2.1–2.3 run automatically. Otherwise cron the management command. | M |

### 2B. Notification coverage gaps

Centralized `notify`/`notify_roles` helpers exist and are clean. Missing emitters:

- **audit_execution**: program submit/approve, procedure complete, working-paper review — **zero** notifications.
- **Engagement `update-status`** (entering reporting/completed) — none.
- **Finding** status changes other than close (resolved/disputed) — none.
- **SelfAssessment** submission — no notification to reviewer.

| # | Item | What | Effort |
|---|------|------|--------|
| 2.5 | Fill notification emitters | Add `notify(...)` at the above mutation points, mirroring the plan submit/approve reference pattern. | M |

### 2C. Missing workflow transitions

State machines exist but some states are unreachable via the API:

- **Findings**: `close` hard-jumps to `closed`; `resolved` / `disputed` / `in_progress` have **no transition endpoints**.
- **SelfAssessment**: `reviewed` status exists but there's no review/approve endpoint.
- **AuditProgram**: `reviewed_by` is never populated.

| # | Item | What | Effort |
|---|------|------|--------|
| 2.6 | Add transition endpoints | `finding/{id}/resolve`, `/dispute`, `/reopen`; `self-assessment/{id}/review`; populate `reviewed_by` on program review. Each: status change + AuditTrail + notify. | M |

### 2D. AuditTrail consistency

~40 near-identical `AuditTrail.objects.create(...)` blocks, copy-pasted. Coverage holes:
audit_execution (0), risk_assessment (0), notifications (0), SystemSetting changes (0). `changes` and
`user_agent` fields are always empty.

| # | Item | What | Effort |
|---|------|------|--------|
| 2.7 | Reusable audit-trail mixin | `AuditTrailMixin` (or DRF-level hook) that logs create/update/delete uniformly, captures `user_agent`, and records a `changes` diff. Backfill the un-covered apps. | M |

---

## Phase 3 — Domain data integrity

The risk pipeline is disconnected and the audit-universe loop never closes.

| # | Item | Why | Effort |
|---|------|-----|--------|
| 3.1 | Connect risk to the universe | `RiskAssessment` links to `Department`, not `AuditUniverse` (contradicting its own docstring). Add the FK and propagate the computed `risk_score` into `AuditUniverse.risk_score` instead of it being hand-entered. | M |
| 3.2 | Activate `RiskParameter` weights | The weighted `RiskParameter` model is dead config; scoring is hardcoded `likelihood*impact`. Either use the weights in scoring or remove the model to stop implying a feature that isn't there. | M |
| 3.3 | Close the re-audit loop | On engagement completion, update `AuditUniverse.last_audited`; add a "due for re-audit" flag/endpoint driven by `audit_frequency`. | M |
| 3.4 | Async report generation | Report generation runs **synchronously** inside the request and blocks the worker; the `generating` status is therefore never really observed. Move to the Celery task from 2.4 (or a threaded job) and let the frontend poll the existing status. | M |

---

## Phase 4 — Frontend foundation (unblocks everything else)

| # | Item | Why | Effort |
|---|------|-----|--------|
| 4.1 | Global auth/user context | Current user is re-parsed from `localStorage` in 4+ places; profile/theme/language changes don't propagate without reload. Add a single `AuthContext` (+ reactive theme/lang). | M |
| 4.2 | Shared component library | Modals/tables/badges/spinners/empty-states are copy-pasted across 9 pages (two different modal systems). Extract `<Modal>`, `<DataTable>`, `<Badge>`, `<Spinner>`, `<EmptyState>`, `<FormField>`, and a `<Toast>` provider. | L |
| 4.3 | API-group modules | Only `authApi`/`notificationApi` exist; every other endpoint is an inline string duplicated across pages. Add `planningApi`, `executionApi`, `findingsApi`, `riskApi`, `capaApi`, `reportsApi`, `usersApi`. | M |
| 4.4 | Route-level RBAC + `usePermissions` | Routes are unguarded (URL bypasses hidden nav); role groupings differ per page. Add role-gated routes and one shared permission helper matching the Phase 1 backend matrix. | M |
| 4.5 | Consistent error/empty/loading UX | Reads swallow errors silently (`console.error`); writes show raw `alert(JSON.stringify(...))`. Replace with toasts + inline banners + consistent empty/loading states. | M |

---

## Phase 5 — Frontend feature completeness

| # | Item | Why | Effort |
|---|------|-----|--------|
| 5.1 | Real dashboard | All four charts and the "Recent System Activity" feed are hardcoded; compliance score is faked at `92.4`. Wire charts to `/reports/generated/analytics/` and the activity feed to `/auth/audit-trail/`; add a per-user "my work" summary. | M |
| 5.2 | Table pagination/filter/sort | Only Audit Trail paginates; other lists render a single `results` array and silently truncate large datasets to page 1. Add server-side paging/sort/filter via the shared `<DataTable>`. | M |
| 5.3 | Form validation | Essentially just `required` today. Add field-level errors, cross-field checks (e.g. plan start<end), and format checks. | M |
| 5.4 | Detail routes / deep-linking | Flat routing means no `/findings/:id` etc.; records are selected via in-page state, so nothing is bookmarkable. Add detail routes. | M |
| 5.5 | Extend i18n to page content | Amharic exists but covers only nav/settings chrome (~35 keys); ~95% of visible text is hardcoded English and language changes don't reach pages. Propagate lang via context and translate page strings. | L |

---

## Suggested sequencing

1. **Phase 0** (quick wins/bugs) — immediate, low risk.
2. **Phase 1** (security) + **Phase 4.4** (route guards) together — close the authorization holes end-to-end.
3. **Phase 2** (workflow + automation) — the highest *functional* value; makes the system actively useful (reminders, overdue, full notifications).
4. **Phase 4.1–4.3, 4.5** (frontend foundation) — pay down duplication before adding features.
5. **Phase 3** (domain integrity) and **Phase 5** (feature polish) — in either order, by priority.

## Explicitly out of scope until asked
- Multi-engagement / plan-level reporting.
- Real-time (WebSocket) notifications (current 30s poll is adequate).
- Postgres migration (SQLite works; the Postgres path already exists in settings).
