# Live Demo Walkthrough — One Case, Every Role

This is the script for a live, end-to-end demonstration of the EEU Internal Audit
Management System. A single demo case — **Distribution Transformer Procurement &
Stock Control** — is seeded up to a checkpoint, and the presenter then walks the
room through the rest of the workflow live, role by role, until a final report is
generated and downloaded.

**What the audience should take away:** who does what at each stage, how statuses
and reference numbers are assigned by the server, how approvals gate the flow, and
how the auditee interacts through findings and CAPAs.

---

## 1. The case at a glance

| Stage | Who | State when demo starts |
|---|---|---|
| Audit Universe entity | Audit Manager | **pre-seeded** (code `DEMO-PROC-01`) |
| Risk assessment + self-assessment | Manager / Auditee | **pre-seeded**, reviewed |
| Annual plan | Audit Manager | **pre-seeded**, approved |
| Engagement + team | Audit Manager | **pre-seeded**, `fieldwork`, lead + supervisor assigned |
| Program & procedures | Auditor | **live** — auditor builds them |
| Program approval / workpaper review | Supervisor | **live** |
| Findings | Auditor | **live** |
| Finding response & evidence | Auditee | **live** |
| CAPA | Auditor → Auditee → Supervisor | **live** |
| Report | Auditor / Manager | **live** — generate + download |

Everything pre-seeded is still *shown* on screen and narrated; nothing after the
checkpoint exists until the presenter performs it. That is what makes the demo
show the workflow rather than a finished result.

---

## 2. Setup (do before the audience arrives)

```bash
# Terminal 1 — backend (set PYTHONUTF8 first on Windows: export PYTHONUTF8=1)
cd backend
python manage.py migrate
python manage.py seed_org_structure && python manage.py seed_eeu_audit_structure
python manage.py seed_service_centers && python manage.py seed_hq_org_units
python manage.py seed_data
python manage.py seed_demo_case --to engagement    # ← the demo case, at the checkpoint
python manage.py runserver

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

**Login is by Employee ID** (not email):

| Role | Employee ID | Password |
|---|---|---|
| System Admin | `EEU-10001` | `admin123` |
| Audit Manager | `EEU-10002` | `user123` |
| Supervisor | `EEU-10003` | `user123` |
| Lead Auditor | `EEU-10004` | `user123` |
| Auditee | `EEU-10005` | `user123` |

**Reset between runs:** `python manage.py seed_demo_case --to engagement` deletes
the previous DEMO case first, so re-running it resets the demonstration. To wipe
everything else as well, run `python manage.py reset_business_data --no-input`
first, then the seed steps above.

> **`--to` checkpoints** — `seed_demo_case` can stop earlier:
> - `--to universe` seeds only the entity; you then create risk → plan →
>   engagement live.
> - `--to plan` also seeds the risk assessment and approved plan; you schedule
>   the engagement live.
> - `--to engagement` (default) is the setup above.

---

## 3. The flow to narrate before the live part

Log in as each role below, open the screen, and spend one line explaining what the
room is looking at. Keep this to ~3 minutes.

### 3.1 System Admin — `EEU-10001`
Sidebar shows **User Management** and **Audit Trail**.
- **User Management**: point at the five demo accounts (one per role) — each role
  is what controls what the user can do.
- **Audit Trail**: show the `DEMO:` entries already logged by the seed command.

### 3.2 Audit Manager — `EEU-10002`
Sidebar has **no** User Management — the route guard blocks `/users`.
- **Planning → Audit Universe**: the demo entity `DEMO-PROC-01` is listed with
  its risk score. Mention the server assigns `FND-…`/`CAPA-…` reference numbers
  later.
- **Planning → Annual Audit Plans**: `DEMO Annual Audit Plan 2026` shows
  **APPROVED**.
- **Planning → Engagements**: `DEMO-ENG-2026-001` is `fieldwork`, with lead
  auditor and supervisor named. The status dropdown here is how an engagement
  moves through stages.
- **Risk Assessment**: the assessment exists with a computed score; the auditee's
  self-assessment is `reviewed`.

> To show **entity creation live** instead of narrated, run
> `seed_demo_case --to universe` in setup and have the manager create the entity
> here using **Add Entity** (the walkthrough in §4.2 gives the field values).

---

## 4. Live walkthrough — role by role

Every step below has the exact text to paste into the form. **Refresh after any
mutation** once in a while — the refresh-after-action checks are what separate
this demo from a green-toast illusion.

### 4.1 Lead Auditor — `EEU-10004` — program, procedures, fieldwork

1. Log in → **Audit Execution**.
2. Engagement selector → choose `DEMO-ENG-2026-001 — Distribution Transformer
   Procurement & Stock Control Audit`. No program exists yet.
3. **Create Audit Program**:
   - Title: `Transformer Procurement Audit Program`
   - Objectives: `Test procurement controls, stores inward inspection, stock recording, and issue-to-site authorization.`
   - Scope: `All transformer purchase orders above 100,000 ETB, tenders, inward inspection, and store issue vouchers.`
4. **Add Procedure** — create three:
   - Step `1.0` · Test of Controls · **Vendor & Tender Compliance Review** —
     `Verify tender committee quorum, evaluation criteria, and vendor registration for 10 sampled purchase orders.`
   - Step `2.0` · Substantive · **Inward Inspection & Stores Receipt Tracing** —
     `Trace 15 transformers from goods-received note to store bin card and inspect inspection reports.`
   - Step `3.0` · Analytical · **Stock Issue & Reconciliation Analytics** —
     `Compare store issue vouchers to bin-card balances and flag unexplained write-offs.`
5. Set procedure **1.0** to `in_progress`, then **2.0** to `completed` (this
   stamps `completed_by`/`completed_at` and notifies the engagement lead).
6. **Submit for Review** on the program header. The badge flips to **SUBMITTED**.

### 4.2 Supervisor — `EEU-10003` — approve program, review workpaper

1. Log in → **Audit Execution** → the same engagement.
2. The program shows **SUBMITTED** → **Review & Approve** → type a review note
   (`Program scope is adequate. Proceed with fieldwork.`) → **Approve Program**.
   The badge flips to **APPROVED**; the auditor is notified.
3. Back on the Auditor's side (or stay here if you prefer — the supervisor can
   review too): upload a working paper from **Audit Execution**:
   - Reference: `WP-2.1` · Title: `Inward Inspection Report Sample` → choose any
     file → **Upload Working Paper**.
4. As **Supervisor**, click the review icon on the paper, add
   `Evidence supports the conclusion. Accepted.` → **Mark as Reviewed**. The
   paper now shows the REVIEWED badge.

### 4.3 Lead Auditor — `EEU-10004` — log findings

1. Log in → **Findings Registry** → select the demo engagement → **Log Finding**.
2. Create two findings (paste the values below, one per modal):

   **Finding A — high**
   - Title: `Inward Inspection Reports Missing for 3 of 15 Transformers`
   - Severity: `High` · Category: `Control Deficiency`
   - Description: `Three transformer deliveries were received and booked to store without a completed inward inspection report.`
   - Condition: `3 of 15 sampled goods-received notes have no signed inspection report on file.`
   - Criteria: `EEU Stores Procedure Section 6.2 requires inspection sign-off before goods are booked into the ledger.`
   - Cause: `Receiving staff shortcut inspection when deliveries arrive late in the day.`
   - Effect: `Substandard or damaged transformers can enter the store and be issued to site undetected.`
   - Recommendation: `Enforce inspection sign-off before store booking and re-inspect the three units.`

   **Finding B — medium**
   - Title: `Store Issue Vouchers Not Reconciled to Bin Cards`
   - Severity: `Medium` · Category: `Operational Weakness`
   - Description: `Monthly stock reconciliation is not performed, so bin-card balances cannot be relied upon.`
   - Condition: `No reconciliation between issue vouchers and bin cards for the last two months.`
   - Criteria: `EEU Stores Procedure Section 4.1 requires monthly reconciliation signed by the storekeeper.`
   - Cause: `No dedicated stores clerk since the warehouse transferred units.`
   - Effect: `Stock losses or miscounts can go undetected until the annual count.`
   - Recommendation: `Resume monthly reconciliation and have the regional finance officer sign off each log.`

   The server numbers them `FND-2026-0001` / `0002` — the form does not invent
   numbers.

3. Open Finding A (double-click) → the detail page. Mention this is where the
   auditee will respond next.

### 4.4 Auditee — `EEU-10005` — respond with evidence

1. Log in. The bell should show a notification about the new finding; the
   dashboard's **My Work** lists it.
2. **Findings Registry** → the demo engagement → Finding A → open it.
   Because the engagement's department is the auditee's department, the auditee
   sees it.
3. Add a **comment**: `We have re-inspected all three units and completed the missing reports.`
4. **Upload evidence** (any file, e.g. a scan or text file titled
   `Inspection sign-off log`).
5. Note the auditee has no Resolve/Close buttons here — those belong to the audit
   team.

### 4.5 Lead Auditor — `EEU-10004` — spawn CAPAs

1. Log in → **Corrective Actions** → **Spawn & Assign CAPA**.
2. For Finding A:
   - Link to Audit Finding: `FND-2026-0001 …`
   - Title: `Re-inspect units and enforce inspection sign-off before booking`
   - Description: `Complete inspection reports for the three outstanding units and require inspection sign-off before store booking.`
   - Recommendation: `Update the stores procedure and train receiving staff.`
   - Assign Owner: `Kidus Yosef` · Priority: `High` · Due Date: today + 14 days
3. Repeat for Finding B:
   - Title: `Restore monthly bin-card reconciliation`
   - Description: `Resume monthly stock reconciliation and sign-off by the regional finance officer.`
   - Recommendation: `Assign a responsible clerk and document the reconciliation cycle.`
   - Assign Owner: `Kidus Yosef` · Priority: `Medium` · Due Date: today + 30 days
4. The numbers come from the server: `CAPA-2026-0001` / `0002`.

### 4.6 Auditee — `EEU-10005` — CAPA responses

1. Log in → **Corrective Actions** → the two CAPAs are listed under **Open /
   In Progress**.
2. CAPA-0001 → **Respond**:
   - Progress Status: `Resolved / Actioned`
   - Notes: `All three units re-inspected and signed off. Stores procedure updated; receiving staff trained.`
   - Upload an implementation document (any file).
3. CAPA-0002 → **Respond**:
   - Progress Status: `In Progress`
   - Notes: `Reconciliation restarted; first monthly log prepared, pending regional finance sign-off.`
4. There is no **Verify & Schedule Follow-up** button for the auditee — the owner
   cannot sign off their own remediation.

### 4.7 Supervisor — `EEU-10003` — verify and close

1. Log in → **Corrective Actions**.
2. CAPA-0002 → **Verify & Schedule Follow-up** (on the CAPA detail page):
   schedule a follow-up a week out; the owner is notified.
3. Back on the list, open **CAPA-0001** → verify the response and mark it closed.
4. **Findings Registry** → Finding A → **Resolve** then **Close** (an auditee is
   403 here — only the audit team closes). This is the moment the engagement can
   eventually be marked `completed`.

### 4.8 Lead Auditor / Manager — generate and download the report

1. Log in as **Auditor** (or Manager) → **Reports & Analytics** → **Compile
   Report**.
2. Title: `Final Audit Report — Distribution Transformer Procurement & Stock Control`
3. Engagement: the demo engagement · Template: `EEU Standard Audit Report
   Template` · Format: `PDF`.
4. The row appears as **GENERATING**, then flips to **READY** on its own (the page
   polls — no refresh needed).
5. **Download** → a real PDF opens, named from the title.
6. Optional flourish: generate an **Excel** and a **Word** version of the same
   report and download both.

### 4.9 Cross-cutting (as time permits)

- **Dashboard** as each role: KPIs and charts rescope; the auditee's dashboard
  shows **My Work** (findings, CAPAs, self-assessments).
- **Bell**: click every notification — each lands on the specific record, never
  the dashboard.
- **EN ⇄ AM** toggle and light/dark toggle on a couple of pages.

---

## 5. Expected outcomes to point out

- Reference numbers (`ENG-…`, `FND-…`, `CAPA-…`) are assigned by the server,
  year-scoped, and never collide.
- Statuses move only through the permitted path (`draft → submitted → approved`,
  `planned → fieldwork → …`), enforced on the backend, not just hidden in the UI.
- The auditee holds no capabilities; every action they can take is an
  object-level check on records naming them or their department.
- Report generation is asynchronous: `generating → ready`, and the download is
  gated through an authenticated endpoint.

## 6. Troubleshooting

- **UnicodeEncodeError in the seed command** — export `PYTHONUTF8=1` first
  (Windows).
- **Throttled 429s during a long demo** — the authenticated API throttle is
  1000/hour; restarting `manage.py runserver` resets the in-memory counter.
- **Report stuck on GENERATING** — the worker is a background thread in the same
  process; if the server restarted mid-compile the row stays `generating`. Delete
  the row or regenerate.
- **Demo rows persist across sessions** — that is deliberate; re-run
  `seed_demo_case --to engagement` to reset the case, or
  `reset_business_data --no-input` to empty every business table first.
