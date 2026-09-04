# EEU Internal Audit Management System — User Manual

For auditors, supervisors, audit managers, auditees and system administrators of the **Ethiopian Electric Utility**.

This manual describes what each screen does, who may use it, and what happens after you act. Developer and API documentation is in [README.md](README.md); test coverage and the browser walkthrough are in [TESTING.md](TESTING.md).

---

## Contents

**Getting started**
1. [What this system does](#1-what-this-system-does)
2. [Signing in](#2-signing-in)
3. [Finding your way around](#3-finding-your-way-around)
4. [Settings](#4-settings)

**The modules**

5. [Dashboard](#5-dashboard)
6. [Audit Planning](#6-audit-planning)
7. [Audit Execution](#7-audit-execution)
8. [Findings Registry](#8-findings-registry)
9. [Risk Assessment](#9-risk-assessment)
10. [Corrective Actions (CAPA)](#10-corrective-actions-capa)
11. [Reports & Analytics](#11-reports--analytics)
12. [User Management](#12-user-management)
13. [Audit Trail](#13-audit-trail)

**Reference**

14. [Your role, step by step](#14-your-role-step-by-step)
15. [Notifications](#15-notifications)
16. [Administrator runbook](#16-administrator-runbook)
17. [Troubleshooting](#17-troubleshooting)
18. [Glossary](#18-glossary)
19. [Support](#19-support)

---

## 1. What this system does

The system carries an internal audit from the first risk assessment to the final report, keeping every step, every document and every decision in one place.

### The audit lifecycle

| Stage | Who drives it | What happens |
|---|---|---|
| **1. Risk assessment & universe setup** | Audit manager, auditor, auditee | Auditable entities are registered in the **audit universe**. Auditees complete risk self-assessments. Managers score risk on a 5×5 heat map and rank what to audit first. |
| **2. Annual plan** | Audit manager | The year's audit plan is drafted with objectives, scope, budget and schedule, then submitted for approval. Directorate plans roll up into an EEU consolidated master plan. |
| **3. Engagement scheduling** | Audit manager | Individual audits are scheduled under an approved plan and staffed with a lead auditor, a supervisor and team members. |
| **4. Execution & fieldwork** | Auditor, supervisor | The auditor builds the audit program and its procedures. The supervisor approves it. The auditor works the procedures and uploads working papers. The supervisor reviews and signs them off. |
| **5. Findings** | Auditor | Deficiencies are logged with condition, criteria, cause, effect and a recommendation, with evidence attached. |
| **6. Corrective actions (CAPA)** | Auditor, auditee, supervisor | Findings spawn corrective actions with owners and due dates. Owners report progress with evidence. Supervisors verify and schedule follow-ups. |
| **7. Reports & analytics** | Auditor, audit manager | Reports are compiled to PDF, Excel or Word, and the engagement is closed. |

### The five roles

| Role | Who they are | What they do here |
|---|---|---|
| **Administrator** (`admin`) | IT / system owner | Creates and manages user accounts, configures the system, reads the security audit trail. |
| **Audit Manager** (`audit_manager`) | Head of the audit function | Owns the audit universe and the annual plan, approves plans and programs, reviews self-assessments, configures risk parameters and report templates. |
| **Audit Supervisor** (`supervisor`) | Reviewer of fieldwork | Approves audit programs, reviews working papers, closes findings, verifies corrective actions. |
| **Auditor / Lead Auditor** (`auditor`) | Fieldwork | Designs procedures, performs testing, uploads working papers, logs findings, raises corrective actions, drafts reports. |
| **Auditee** (`auditee`) | Audited department representative | Completes risk self-assessments, responds to findings that concern them, and owns the remediation of corrective actions. |

Permissions are enforced by the server, not by the interface. Buttons you may not use are hidden, but the real check happens on every request — a hidden button cannot be worked around by calling the API directly.

---

## 2. Signing in

### Log in with your Employee ID

> **You log in with your Employee ID, not your email address.** Employee IDs follow the pattern `EEU-#####`. Your email address is stored for notifications only and will not sign you in.

1. Open the application (ask your administrator for the address).
2. Enter your **Employee ID** and **password**.
3. Select **Sign In**.

On a demonstration or training system, the login page also shows five one-click role buttons that fill in and submit a demo account for you.

| Role | Employee ID | Password |
|---|---|---|
| System Admin | `EEU-10001` | `admin123` |
| Audit Manager | `EEU-10002` | `user123` |
| Supervisor | `EEU-10003` | `user123` |
| Lead Auditor | `EEU-10004` | `user123` |
| Auditee | `EEU-10005` | `user123` |

These accounts exist only where demo data has been seeded. They are not present on a properly configured production system.

> **Known issue:** the one-click **Audit Manager** button submits the wrong password and fails with "Invalid Employee ID or password". Type `EEU-10002` / `user123` into the form by hand. The other four buttons work.

### Passwords

Passwords must be at least 8 characters and are additionally checked against Django's standard validators: not too similar to your own name or Employee ID, not a commonly used password, and not entirely numeric. Change yours from **Settings → Change Password**.

### Your session

- You stay signed in for **7 days** of inactivity before you must log in again.
- Behind the scenes your access credential is renewed every hour automatically. You will not be logged out mid-task, and leaving a tab idle over lunch is safe — the next thing you click renews the session silently.
- **Log out** invalidates the session on the server. The browser Back button will not restore it.
- Reloading the page keeps you signed in.

### Failed logins

The login endpoint accepts **5 attempts per minute**. Exceeding that returns a "too many requests" error for a short period. This is a deliberate protection against password guessing — wait a minute and try again.

If your account has been deactivated by an administrator, your password will be rejected even though it is correct. Contact your administrator.

---

## 3. Finding your way around

### The sidebar

The left sidebar is your main navigation. Everyone sees seven destinations:

| Destination | What it is |
|---|---|
| **Dashboard** | Your KPIs, charts, and your own outstanding work |
| **Audit Planning** | Audit universe, annual plans, engagements |
| **Audit Execution** | Programs, procedures, working papers |
| **Findings Registry** | All findings you are entitled to see |
| **Risk Assessment** | Risk matrix, heat map, self-assessments |
| **Corrective Actions** | CAPA tracking and follow-up |
| **Reports & Analytics** | Report templates and generated reports |

Two more appear only for the roles that hold the matching capability:

- **User Management** — administrators only.
- **Audit Trail** — administrators, audit managers and supervisors.

If a destination is not in your sidebar, typing its address directly will not open it either; you will be returned to the Dashboard.

### The header

| Control | What it does |
|---|---|
| **Menu / hamburger** | Collapses and expands the sidebar. |
| **Notification bell** | Shows a badge with your unread count, refreshed automatically about every 30 seconds. Open it to see your notifications; select one to jump straight to the record it refers to. |
| **Help** | Opens the **Workflow & Support Center**: a roles overview, the seven-stage lifecycle, and per-role task checklists you can tick off. Your ticks are remembered in your own browser. |
| **Settings** | Language, theme, password and profile — see below. |
| **Log out** | Ends your session. |

### Smaller screens

Below roughly 900 pixels wide, the sidebar becomes a drawer that slides over the page and closes itself as soon as you pick a destination. Wide tables scroll sideways rather than overflowing the page.

### Keyboard users

A **Skip to content** link is the first focusable element on every page, so you can jump past the sidebar's 7–11 links straight into the page body.

> **Note on the Help modal:** its role checklists still tell you to sign in with an email address such as `admin@eeu.com`. That text is out of date. Log in with your Employee ID, as described in [section 2](#2-signing-in).

---

## 4. Settings

Open **Settings** from the header. There are three tabs.

### General

| Setting | Notes |
|---|---|
| **API endpoint** | The address of the server this browser talks to. Changing it takes effect immediately — no reload needed. Only change it if your administrator tells you to. |
| **Language** | English or አማርኛ (Amharic). Applies across the whole interface; organizational units display their Amharic names where those have been entered. |
| **Theme** | Light or dark. |

Your language, theme and endpoint choices are remembered in this browser and survive logging out.

### Change Password

Enter your current password, then the new one twice. A strength meter fills as the new password gets longer — **weak** below 8 characters, **fair** at 8, **good** at 10, **strong** at 12 or more. Length is only part of it; the server also applies the validators described in [section 2](#2-signing-in).

After changing your password, your old one stops working immediately.

### Profile

| Field | Editable |
|---|---|
| Employee ID | No — set by your administrator |
| Department | No |
| Role | No |
| Account status | No |
| First name | Yes |
| Last name | Yes |

Saving updates the name shown in the header straight away. To change your department or role, ask an administrator.

---

## 5. Dashboard

**Purpose:** a single view of where the audit function stands, and of what is waiting for *you*.
**Who can use it:** everyone.

### The KPI cards

| Card | How it is calculated |
|---|---|
| **Total / Active engagements** | Every engagement in scope; "active" counts those with status *In Progress*. |
| **Total / Open findings** | Every finding in scope; "open" counts status *Open*. |
| **Critical / High findings** | Open findings at those severities. |
| **Open actions** | Corrective actions still at *Open* or *In Progress*. |
| **Overdue actions** | Open or in-progress actions whose due date has passed. |
| **Active plans** | Annual plans with status *Active*. |
| **Compliance score** | **Closed** findings as a percentage of all findings. |

**Why the compliance score only counts *closed* findings.** A finding marked *Resolved* records a claim that remediation happened, and the audit team sets that itself. *Closed* is the state a finding reaches once that claim has been **verified** by someone holding the close-findings capability. If both counted, a directorate could read as 100% compliant with nothing actually verified. Where there are no findings at all, the score reads 100%.

### The directorate selector

The org-chart selector at the top rescopes the whole dashboard to one audit directorate — engagements, findings, corrective actions, plans, every KPI and every chart. Leaving it on the consolidated view gives you the EEU-wide picture.

**One panel deliberately ignores it: My Work.** Your own outstanding tasks do not belong to a directorate you happen to be browsing, so they are always your real tasks.

### My Work

Up to five rows in each of three lists:

- Findings assigned to you that still need something from you. A finding leaves this list once it reaches *Resolved* — at that point the ball is with the reviewer, even though it does not yet count towards the compliance score.
- Corrective actions you own that are still open.
- Self-assessments awaiting your submission.

Select any row to open the record.

### The charts

| Chart | Shows |
|---|---|
| **Engagement execution** | The last six calendar months of engagement activity. |
| **Open findings by severity** | A distribution of *open* findings only, so it always sums to the Open Findings card above it. |
| **Compliance trend** | Five quarters of cumulative compliance. |
| **Engagements by status** | The current spread across planned, in progress, fieldwork, reporting, completed and cancelled. |

---

## 6. Audit Planning

**Purpose:** decide what will be audited, and when.
**Who can use it:** everyone can read. Creating and editing requires an audit role (auditor and above). Approving a plan requires supervisor and above. Auditees see only engagements for their own department, plus any they are named on.

The page has three tabs.

### Audit Universe

The catalogue of everything that *could* be audited.

| Field | Notes |
|---|---|
| Name, Code | Code must be unique. |
| Category | Department, Business Process, IT System, Project, Subsidiary, or Regulatory Area. |
| Department / Directorate | Which unit owns the entity, and which audit directorate is responsible. |
| Risk score | Kept up to date automatically by the Risk Assessment module — see [section 9](#9-risk-assessment). |
| Audit frequency | Drives re-audit reminders: monthly, quarterly, semi-annually (or bi-annually), annually (or yearly), biennially, tri-annually. |
| Last audited | Filled in automatically when an engagement covering the entity completes. |
| Status | Active, Inactive, or Under Review. |

**Due for re-audit.** An entity is due when its last audit is older than its frequency allows. An entity that has **never** been audited is always due. If the frequency field is blank or unrecognised, no reminder is produced — so fill it in.

Entries are listed with the highest risk score first, which is the order the annual plan should follow.

**To add an entity:** open the Audit Universe tab → **Add Entry** → complete the fields → save.

### Annual Plans

| Field | Notes |
|---|---|
| Title, Year | |
| Plan scope | **Directorate Plan** or **EEU Consolidated Master Plan**. A directorate plan can name a consolidated plan as its parent, so the master plan aggregates them. |
| Directorate | Which audit directorate owns the plan. |
| Objectives, Scope, Methodology, Description | Free text. |
| Budget, dates | |

**Status flow:** `Draft → Submitted → Approved → Active → Completed`, with `Cancelled` available throughout.

**To move a plan forward:**

1. Create it. It starts as **Draft**.
2. Select **Submit**. Status becomes *Submitted* and everyone who can approve is notified. You are not notified about your own submission.
   - An auditor may submit a plan **they authored**, but not a colleague's.
3. Someone with approval rights selects **Approve**. Status becomes *Approved*, the approver and timestamp are stamped on the record, the author is notified, and an `APPROVE` entry is written to the audit trail.

### Engagements

An individual audit, scheduled under a plan.

| Field | Notes |
|---|---|
| Engagement number | **Assigned by the server** as `ENG-YYYY-NNNN`. Do not invent one. |
| Title | |
| Engagement type | Financial Audit · Performance Audit · Technical & Engineering Audit (substations, distribution grids, loss reduction, transmission) · Information Technology Audit (ERP, CIS billing, cybersecurity, infrastructure) · Planning & Special Review Audit. |
| Plan, Audit universe entry | Which plan it belongs to and which entity it covers. |
| Department, Directorate | |
| Lead auditor, Supervisor | Both are notified when the engagement is created. |
| Risk level, dates, budgeted hours | |

**Status flow:** `Planned → In Progress → Fieldwork → Reporting → Completed`, with `Cancelled` available. Use **Update Status** rather than editing the field directly — completing an engagement this way also back-fills the *Last audited* date on the linked audit universe entry, which is what keeps re-audit reminders honest.

**Audit team.** Use **Add Member** to add people as Lead Auditor, Team Member, Supervisor or Subject Matter Expert, with allocated and actual days.

---

## 7. Audit Execution

**Purpose:** run the fieldwork and keep the evidence.
**Who can use it:** everyone can read. Creating and editing requires an audit role. Approving a program and reviewing working papers require supervisor and above.

### Audit Program

One program per engagement, setting out objectives and scope.

**Status flow:** `Draft → Submitted for Review → Approved → Active → Completed`.

1. The auditor creates the program against the engagement. It starts as **Draft** with the auditor recorded as preparer.
2. The auditor adds procedures (below).
3. The auditor selects **Submit for Review**. Status becomes *Submitted* and the supervisor is notified.
   - Without approval rights, you may submit only a program you prepared, or one whose engagement you lead.
4. The supervisor selects **Approve Fieldwork**. Status becomes *Approved*, the reviewer is stamped, and the preparer is notified.

### Procedures

The individual test steps.

| Field | Notes |
|---|---|
| Step number, Title, Description | |
| Procedure type | Test of Controls · Substantive Testing · Analytical Procedures · Inquiry · Observation · Inspection & Re-performance. |
| Risk area | |
| Assigned to | |
| Status | Pending · In Progress · Completed · Not Applicable. |
| Conclusion | Recorded when you complete the step. |

Procedures are listed in step order. Editing a procedure updates it in place; deleting removes it permanently — both are saved to the server immediately, so a page refresh will show exactly what you left.

**To complete a procedure:** open it → **Complete** → record your conclusion. Your name and the time are stamped on the record and the engagement's lead auditor is notified.

### Working Papers

The evidence file for the engagement.

| Field | Notes |
|---|---|
| Reference, Title, Description | |
| Paper type | Planning Document · Audit Program · Evidence · Work Paper · Correspondence · Report · Other. |
| Engagement, Procedure | The procedure link is optional. |
| File | Up to **10 MB**. Accepted: PDF, Word, Excel, PowerPoint, text, CSV, RTF, ODT, ODS, images (PNG, JPG, GIF, BMP, TIFF, WebP) and archives (ZIP, 7z). |

**To upload:** Working Papers → **Upload** → give it a reference and title, choose the file, save. You are recorded as the preparer.

**To review one (supervisor and above):** open the paper → add review notes → sign off. The paper is marked reviewed, you are stamped as reviewer, and the preparer is notified. You cannot review your own paper — review requires approval rights that the preparer's role may not include.

**To download:** use the **Download** action on the paper. Files are never exposed as plain web addresses; every download is permission-checked, and you get the original filename and file type back.

---

## 8. Findings Registry

**Purpose:** record deficiencies, get them remediated, and prove it happened.
**Who can use it:** everyone can read what they are entitled to see. Logging and editing findings requires an audit role. Resolving, closing and reopening require the close-findings capability (auditor and above). Auditees can comment, attach evidence, respond and dispute — but only on findings that name them.

### The finding structure

Findings use the standard internal-audit form:

| Field | Means |
|---|---|
| **Condition** | What you found. |
| **Criteria** | The standard, policy or regulation it should have met. |
| **Cause** | Why the gap exists. |
| **Effect** | The consequence or exposure. |
| **Recommendation** | What should be done about it. |

| Other field | Notes |
|---|---|
| Finding number | **Assigned by the server** as `FND-YYYY-NNNN`. Anything you type is ignored. |
| Severity | Critical · High · Medium · Low · Informational. |
| Category | Control Deficiency · Compliance Issue · Fraud Risk · Operational Weakness · Financial Misstatement · IT/Security Issue · Governance Issue · Other. |
| Engagement, Procedure | Which audit produced it. |
| Assigned to | The person responsible for progressing it. |
| Auditee | The department representative it concerns. |
| Target resolution date | |
| Repeat finding | Tick it and link the previous finding when the issue has recurred. |
| Management response | Recorded by the auditee via **Respond**. |
| Identified by | Set from your account and cannot be changed afterwards. |

### Logging a finding

Findings Registry → **Log Finding** → complete the fields → save. The assignee and the auditee are both notified; you are not notified about your own finding.

### The finding detail page

Open any finding to reach its workspace: the full 4C record, the comment thread, the evidence list, and the action buttons your role allows. Deep links work — a link to a specific finding opens it directly, no matter how many findings are in the register.

- **Add comment** — visible to the thread; everyone else on it is notified.
- **Upload evidence** — same limits as working papers. Evidence is typed as Document, Screenshot, Spreadsheet, Photo, Video or Other, and is downloadable through a permission-checked action.
- **Respond** — the auditee's management response.

### Status lifecycle

```
Draft → Open → In Progress → Resolved → Closed
                    ↕                      │
                Disputed  ←────────────────┘  (Reopen)
```

| Action | Who | Effect |
|---|---|---|
| **Resolve** | Auditor and above | → *Resolved*, with a resolution date. Records that remediation is claimed. |
| **Close** | Auditor and above | → *Closed*. This is the verified state, and the **only** one that counts towards the compliance score. |
| **Dispute** | The named auditee or assignee, or an auditor and above | → *Disputed*. The auditor who raised the finding is notified. |
| **Reopen** | Auditor and above | Returns a closed or resolved finding to an active state. |

An auditee is not offered Resolve, Close or Reopen, and a direct request to those endpoints is refused.

### Filtering and searching

Filter by severity, status, category, engagement and repeat flag; search titles, descriptions, finding numbers and recommendations; order by date, severity, status or target resolution date. Lists show 20 rows per page.

---

## 9. Risk Assessment

**Purpose:** score risk consistently, so the annual plan audits the right things first.
**Who can use it:** everyone can read. Creating assessments requires an audit role. **Risk parameters** require audit-manager level. Reviewing a self-assessment requires supervisor and above. Any user can submit a self-assessment.

The page has two tabs.

### Matrix

Create an assessment against a department or audit universe entry:

| Input | Scale |
|---|---|
| **Likelihood** | 1–5 |
| **Impact** | 1–5 |
| **Control effectiveness** | 1–5 (1 = ineffective, 5 = highly effective) |
| Year, Notes | |

**Scores are computed by the server, not by you.** The formula:

1. **Base score** = likelihood × impact (1–25).
2. **Weighted uplift** — the total weight of all *active* risk parameters raises the base score by 20% per unit of weight, capped at **+30%**. The result is capped at 25. With no active parameters, the base score is used unchanged.
3. **Rating band** — 1–4 **Low**, 5–9 **Medium**, 10–16 **High**, above 16 **Critical**.
4. **Residual risk** = score × (1 − (control effectiveness − 1) × 0.2). Control effectiveness 1 leaves 100% of the inherent risk; 5 reduces it to 20%.

The computed score is then **pushed onto the linked audit universe entry**, so the planning list reorders itself automatically. If the assessment names only a department, the highest-scoring active universe entry for that department is updated instead. Deleting an assessment re-propagates the next most recent one, so the universe never keeps a score from a deleted record.

**Heat map.** The 5×5 grid plots every assessment at its likelihood/impact cell, filterable by year. Use it to see concentration, not just individual scores.

**Risk parameters** (audit manager and above) let you define weighted factors across six categories — Financial Impact, Operational Impact, Compliance/Legal, Reputational, Strategic, IT/Technology. Only *active* parameters affect scoring. Because every active parameter contributes to the uplift on **every** assessment, add them deliberately: the effect is organization-wide, and the +30% cap means past a total weight of 1.5 further parameters change nothing.

### Self-Assessment

How an audited department states its own view of its risk.

| Field | Notes |
|---|---|
| Likelihood / Impact / Control effectiveness | 1–5, the department's own judgement. |
| Justification | Required. |
| Mitigating controls | Optional. |
| Status | Pending → Submitted → Reviewed. |

**As an auditee:**

1. Risk Assessment → **Self Assessment** → complete and submit. The parent assessment is flagged as self-assessed by the server.
2. You may keep editing while the status is **Submitted**.
3. Once a manager has reviewed it, it is **locked** — further edits are refused. If something needs changing after review, ask the reviewer.

**You see only your own submission.** So does an auditor: visibility here is governed by approval rights, not by role name, so anyone without them sees only what they submitted themselves.

**As a reviewer (supervisor and above):** open a submitted assessment and use the **Review** action, adding reviewer notes. The status becomes *Reviewed*, you are stamped as reviewer with a timestamp, and the submitter is notified. Use the Review action — setting the status field directly does not perform a review and will not be accepted as one.

---

## 10. Corrective Actions (CAPA)

**Purpose:** track remediation from commitment to verified completion.
**Who can use it:** everyone can read what they are entitled to see; auditees see every action owned by someone in their department. Creating actions requires an audit role. Responding is open to the action's owner. Verifying and scheduling follow-ups requires supervisor level, or the person who raised the action.

### The four tabs

| Tab | Shows |
|---|---|
| **All** | Everything in scope. |
| **Open** | Open and In Progress. |
| **Resolved** | Resolved and Closed. |
| **Overdue** | Past the due date. |

### Fields

| Field | Notes |
|---|---|
| Action number | **Assigned by the server** as `CAPA-YYYY-NNNN`. |
| Finding | The finding this remediates. |
| Title, Description, Recommendation | |
| Owner | Who must do the work. Notified on creation, with the due date in the message. |
| Assigned by | Set from your account. |
| Priority | Immediate · High · Medium · Low. |
| Due date | |
| Extended due date | Set this to grant an extension. Overdue checks use it in place of the original date — so extending a deadline stops the reminders, and the original date is still on the record. |
| Status | Open · In Progress · Partially Resolved · Resolved · Overdue · Not Implemented · Closed. |

### Raising an action

From the finding, or from Corrective Actions → **New Action**. Choose the owner, priority and due date. The owner is notified immediately.

### Responding as the owner

Open the action → **Respond** → add progress notes, set a new status, and attach evidence if you have it. The status moves, and the auditor who raised the action is notified.

Owners are **not** offered *Verify & Schedule Follow-up* — you cannot sign off your own remediation.

### Verifying as a supervisor

Open the action → **Verify & Schedule Follow-up** → set the follow-up date and notes. A follow-up record is created (Scheduled → Completed / Cancelled) and the owner is notified.

### Overdue handling

The **Overdue** tab is derived live from the due date, so it is correct even before any scheduled job has run. An action due **today** is not overdue; one due yesterday is.

Separately, a daily job (`flag_overdue_actions`) sets the status of past-due actions to *Overdue* and sends reminders for actions due within 3 days. If nobody has scheduled that job, the tab still works but statuses will not update themselves and no reminder emails go out — see the [runbook](#scheduled-jobs).

---

## 11. Reports & Analytics

**Purpose:** produce the audit report and the numbers behind it.
**Who can use it:** everyone can read and download. Generating requires an audit role. Managing **templates** requires audit-manager level.

### Templates

Seven template types: Engagement Report · Findings Summary · Management Report · Board Report · Follow-up Report · Risk Assessment Report · KPI Dashboard Report. One can be marked as the default. A template may carry an uploaded document.

### Generating a report

1. Reports & Analytics → **Generate Report**.
2. Give it a **title**, pick the **engagement** and the **template**, and choose the format: **PDF**, **Excel** or **Word**.
3. Submit. The report appears in the archive immediately with status **Generating**.
4. It flips to **Ready** on its own — the page checks every few seconds while anything is generating, so **do not refresh**. On failure the status becomes **Failed** with an error message, and you are notified either way.

### Downloading

Use the download action on a *Ready* row. You get the file named from the report title. Attempting to download a row that is still generating returns an error rather than an empty file — wait for *Ready*.

### Analytics

The analytics view reports findings over exactly six consecutive calendar months, labelled by month and year. Every month in the window appears once, including February.

---

## 12. User Management

**Purpose:** provision and manage accounts.
**Who can use it:** administrators only. The sidebar entry is hidden for everyone else, and the page cannot be reached by typing its address.

### Creating a user

**Add User**, then provide:

| Field | Notes |
|---|---|
| **Employee ID** | This is what the person signs in with. Must be unique. Use the `EEU-#####` convention. |
| First name, Last name | |
| Email | For notifications. **Not** a login credential. |
| Role | Administrator · Audit Manager · Audit Supervisor · Auditor · Auditee. This determines everything the account can do. |
| Department | Drives what auditees can see, and the directorate scoping on the dashboard. Assign it — an auditee with no department falls back to seeing only records naming them personally, which is usually not what you want. |
| Password | Communicate it out of band and have the user change it at first login. |
| Phone, Position | Optional. |

### Managing accounts

- **Deactivate** — the account stays on the system with its history intact but cannot log in. This is the correct way to handle someone leaving; deleting a user would break the records that reference them.
- **Activate** — restores access.
- **Reset password** — sets a new password for a user who has lost theirs.

Filter by role, department and active status; search by Employee ID, email or name.

Every action here is written to the audit trail with your name against it.

### Security Audit Log

The card at the bottom of this page is a scoped view of the same Audit Trail table described in §13, filtered to **account and sign-in events only** — sign-ins, sign-outs, account creation, edits, activation, deactivation and password resets or changes. It lists the ten most recent entries, newest first. Treat it as a glance while you administer accounts, not as a search tool.

- For the full history — with search, IP address, role and every kind of action — open the **Audit Trail** page (§13). It reads the same records; the two are not separate logs.
- **View full trail** jumps straight there from this card.

---

## 13. Audit Trail

**Purpose:** an accountability record of who did what.
**Who can use it:** administrators, audit managers and supervisors. **Reading it requires the capability** — the trail is sensitive enough that even viewing is gated, so an auditor requesting it is refused.

### What is recorded

| Field | |
|---|---|
| User | Who acted. |
| Action | Create · Update · Delete · View · Login · Logout · Export · Approve · Reject. |
| Model and object | What was acted on. |
| Changes | The field-level detail of an update. |
| Timestamp | |
| IP address, User agent | Where the request came from. |

Newest first, 25 rows per page. Filter by model, user or action. The **Security Audit Log** card in §12 reads this same table filtered to account events — the two views are one log, not two.

Entries are written as a side effect of real work throughout the system — approvals, user administration, procedure edits, exports — so the trail reflects activity rather than being maintained by hand.

---

## 14. Your role, step by step

Practical starting sequences. Each assumes you have signed in with your Employee ID.

### Administrator

1. **Settings → Profile** — confirm your own details, then **Change Password**.
2. **User Management** — create one account per person, with the correct role *and department*.
3. Confirm each new user can log in, then have them change their password.
4. **Settings → General** — check the API endpoint is right for your environment.
5. Configure system settings and, with the audit manager, the risk parameters.
6. **Audit Trail** — read it periodically. Look for failed access attempts and unexpected deletes.
7. Confirm the two [scheduled jobs](#scheduled-jobs) are running.
8. Deactivate accounts as people leave. Do not delete them.

### Audit Manager

1. **Planning → Audit Universe** — register every auditable entity with a category, owning department, directorate and audit frequency.
2. **Risk → Risk Parameters** — define the weighted factors your methodology uses. Remember the +30% cap and that these apply organization-wide.
3. Ask auditees to complete **self-assessments**, then **Review** each submission with notes.
4. **Risk → Matrix** — record assessments. Check the **Heat Map** and confirm the universe risk scores have updated.
5. **Planning → Annual Plans** — draft the year's plan with objectives, scope, methodology, budget and schedule. Decide whether it is a directorate plan or the consolidated master.
6. **Submit**, then **Approve** it.
7. **Planning → Engagements** — schedule audits under the plan, naming a lead auditor and a supervisor, and add team members with allocated days.
8. **Reports → Templates** — create the templates your reports will use.
9. Track progress on the **Dashboard**, using the directorate selector.

### Audit Supervisor

1. **Dashboard → My Work** — see what is waiting on you.
2. **Execution** — open the engagement's program, read its objectives and scope, and **Approve Fieldwork** when it is sound.
3. **Execution → Working Papers** — open each uploaded paper, add review notes and sign off. Download the file if you need to check it.
4. **Findings** — review findings and **Close** the ones whose remediation you have verified. Only closing counts towards compliance, so do not close on a promise.
5. **CAPA** — open completed actions and **Verify & Schedule Follow-up**.
6. **Risk → Self Assessments** — **Review** submissions.
7. **Audit Trail** — available to you if you need to trace a change.

Risk parameters and report templates are not yours to change; ask the audit manager.

### Auditor / Lead Auditor

1. **Dashboard → My Work** — your assigned findings, owned actions, pending self-assessments.
2. **Execution** — select your active engagement and create the **Audit Program** with objectives and scope. It starts as Draft with you as preparer.
3. Add **procedures** — step number, title, description, type, risk area, assignee.
4. **Submit for Review** and wait for the supervisor's approval.
5. Work the procedures: move each to *In Progress*, then **Complete** it with a conclusion. The engagement lead is notified.
6. Upload **working papers** as you go, with a reference and title. Someone with review rights signs them off — not you.
7. **Findings → Log Finding** — record condition, criteria, cause, effect and recommendation; set severity, category, assignee and auditee. The number is assigned by the server.
8. On the finding's detail page, add comments, attach evidence, and **Resolve** when remediation is done. Closing is usually the supervisor's call.
9. **CAPA** — raise actions from findings with an owner, priority and due date.
10. **Reports** — generate the engagement report.

Approving plans and programs is not yours; that is the supervisor and audit manager.

### Auditee

Your role holds no system-wide permissions on purpose. What you can do, you can do on the records that concern **you**.

1. **Dashboard → My Work** — findings assigned to you, corrective actions you own, self-assessments awaiting you.
2. **Risk → Self Assessment** — submit your department's own view: likelihood, impact, control effectiveness and a justification. Edit it freely until a manager reviews it; after that it locks.
3. **Findings** — you see findings that name you, plus findings on engagements in your department. For each one:
   - **Add a comment** to ask a question or explain context.
   - **Upload evidence** — the auditor who raised the finding is notified.
   - **Respond** with the management response.
   - **Dispute** it if you disagree with the facts. The auditor is notified and the finding is flagged, not deleted.
4. **CAPA** — you see your department's actions. On one you own, **Respond** with progress notes, a status update and evidence.
5. You will not see create or edit buttons on the audit universe, plans, engagements, programs, procedures, findings or CAPAs, and you cannot resolve, close or verify anything — including your own remediation. That separation is what makes the record credible.

---

## 15. Notifications

The bell in the header refreshes about every 30 seconds. Select a notification to open the record it refers to; select **Mark all read** to clear the badge.

| Type | Sent when |
|---|---|
| **New Finding** | A finding is logged naming you as assignee or auditee. |
| **Assigned to You** | You are made lead auditor or supervisor on an engagement, assigned a procedure, or given ownership of a corrective action. |
| **Approval Needed** | A plan or program is submitted and you can approve it. |
| **Approved** | Your plan or program is approved. |
| **Rejected** | Something you submitted is sent back. |
| **Action Due** | A corrective action you own is due within 3 days. |
| **Action Overdue** | A corrective action you own has passed its due date. |
| **Follow-up Due** | A verification follow-up has been scheduled on your action. |
| **Report Ready** | A report you generated has finished — or failed. |
| **System** | Administrative and system-level messages. |

You are never notified about your own actions — submitting your own plan or logging your own finding does not notify you.

Notification delivery never blocks the work that triggered it: if the notification cannot be created, the approval, upload or status change still succeeds.

---

## 16. Administrator runbook

Commands run from the `backend/` directory with the virtual environment active. Installation and deployment steps are in the [README](README.md#deployment).

### First-time setup

1. Configure `backend/.env` from [backend/.env.example](backend/.env.example) and `frontend/.env` from [frontend/.env.example](frontend/.env.example).
2. `python manage.py migrate`
3. Seed the organizational structure, **in this order** — each step expects the units created by the one before:
   ```bash
   python manage.py seed_org_structure        # executive + corporate units
   python manage.py seed_eeu_audit_structure  # IAEO and the four audit directorates
   python manage.py seed_service_centers      # regions and customer service centers
   ```
4. `python manage.py createsuperuser` — prompts for an **Employee ID**, not a username.
5. Create real user accounts through **User Management** in the application.
6. Set up the [scheduled jobs](#scheduled-jobs).
7. Verify: `python manage.py check --deploy` must report no issues once `DEBUG=False`.

**Do not run `seed_data` or `seed_e2e_demo` on a production system.** They create the demo accounts `EEU-10001`–`EEU-10005` with published passwords. They are for development and training environments only.

**On Windows, export `PYTHONUTF8=1` before any seed command.** `seed_e2e_demo` prints a tick character in its summary, and the default `cp1252` console cannot encode it — the command aborts mid-run with `UnicodeEncodeError`. `set PYTHONUTF8=1` in cmd, `$env:PYTHONUTF8=1` in PowerShell.

### Organizational structure

Departments carry **two** hierarchies, distinguished by unit type:

| Unit type | Used for |
|---|---|
| `EXECUTIVE` | Executive offices |
| `CORPORATE` | Corporate departments and chief offices |
| `REGION` | EEU regions |
| `SERVICE_CENTER` | Customer service centers, beneath a region |
| `AUDIT` | The internal audit function itself |

Audit units are further identified by directorate: **IAEO** (Internal Audit Executive Office), **FPA** (Financial & Performance Audit), **TA** (Technical Audit), **ITA** (Information Technology Audit), **PP** (Planning & Performance), and Other.

Each department has an optional parent, an Amharic name (shown when the interface language is Amharic), a head title, and a staff count. The cascading department → region → service-center picker and the org chart both read the whole tree in one request, which is why that one endpoint is not paginated.

Two one-off migration commands exist for reorganizations, and must be run in this order:

```bash
python manage.py reassign_legacy_department_users   # move users onto the current tree
python manage.py retire_legacy_departments          # then deactivate the old units
```

### System settings and risk parameters

**System settings** are key/value pairs, editable by administrators and audit managers through the application. They are audited like anything else.

**Risk parameters** are the weighted factors behind every risk score. Two things to keep in mind:

- Only **active** parameters count.
- Every active parameter affects **every** assessment. The uplift is 20% per unit of total weight, capped at +30%, so once the active weights total 1.5 adding more changes nothing. Changing weights does not retroactively rescore existing assessments — those recompute when they are next saved.

### Scheduled jobs

Two commands are meant to run on a schedule. Nothing schedules them for you.

| Command | Frequency | What it does |
|---|---|---|
| `flag_overdue_actions` | Daily | Sets past-due corrective actions to *Overdue* and sends due-soon reminders for actions due within 3 days (`--days N` to change the window). Uses the extended due date when one is set. Safe to run repeatedly — it will not send the same reminder twice. |
| `fail_stuck_reports` | Every few hours | Moves reports stranded on *Generating* to *Failed*. Needed because report generation runs in-process: if the server restarts mid-compile, the row would otherwise sit at *Generating* forever. |

**Windows Task Scheduler**

Create a Basic Task running daily at 08:00, with:

- Program: `C:\path\to\backend\venv\Scripts\python.exe`
- Arguments: `manage.py flag_overdue_actions`
- Start in: `C:\path\to\backend`

Repeat for `fail_stuck_reports` on a several-hour repeat.

**cron**

```cron
0 8 * * *    cd /path/to/backend && /path/to/venv/bin/python manage.py flag_overdue_actions
0 */4 * * *  cd /path/to/backend && /path/to/venv/bin/python manage.py fail_stuck_reports
```

Check the outcome in `backend/logs/audit_system.log`.

### Email

Out of the box, `EMAIL_BACKEND` is the console backend: mail is printed to the server log rather than sent. In-app notifications work regardless, but **email reminders will not reach anyone** until you switch to SMTP in `backend/.env` and fill in `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL`. `FRONTEND_URL` is what the links inside those emails point at.

### Backups

Back up both of these together — a database without its files is not a restorable audit record:

| What | Where |
|---|---|
| Database | `backend/db.sqlite3`, or `pg_dump` for PostgreSQL |
| Uploaded files | `backend/media/` — evidence, working papers, generated reports, templates |

Test a restore before you need one.

### Logs

`backend/logs/audit_system.log` rotates at 5 MB and keeps 5 files. Set the verbosity with `LOG_LEVEL` in `backend/.env`. Unhandled request errors are always logged regardless of that setting, so raising the level to `WARNING` still preserves server-error tracebacks.

The application-level **Audit Trail** is separate, lives in the database, and is read in the application — not from these files.

### Routine checks

| Frequency | Check |
|---|---|
| Daily | The overdue-actions job ran; no reports stuck on *Generating*. |
| Weekly | Audit trail reviewed for unexpected access or deletions; backup completed. |
| Monthly | Deactivate accounts for departed staff; confirm roles and departments are still right. |
| Per release | `python manage.py test` and `python manage.py check --deploy` both clean. |

---

## 17. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| **"Invalid credentials" with a password you know is right** | You are entering an email address. Login is by **Employee ID**. | Use your `EEU-#####` ID. If that fails too, your account may be deactivated — ask an administrator. |
| **The one-click *Audit Manager* demo button is rejected** | The button submits `User1234`; the seeders set that account's password to `user123`. | Type `EEU-10002` / `user123` into the form instead. |
| **`seed_e2e_demo` aborts with `UnicodeEncodeError: 'charmap' codec can't encode character`** | A Windows console using `cp1252` cannot print the tick character in the command's summary. | Set `PYTHONUTF8=1` and re-run. See the [runbook](#first-time-setup). |
| **Login rejected with a "too many requests" error** | The 5-attempts-per-minute throttle. | Wait a minute. If it persists, someone may be guessing against your ID — tell your administrator. |
| **Everything fails in the browser, but the server is clearly up** | The frontend's origin is missing from `CORS_ALLOWED_ORIGINS`. A tell-tale sign: `curl` against the API works fine while the browser shows network errors on every request. | Add the exact origin (scheme included, no trailing slash) to `CORS_ALLOWED_ORIGINS` in `backend/.env` and restart. |
| **A deployed frontend tries to reach `localhost:8000`** | `VITE_API_BASE_URL` was not set at build time. It is inlined during `npm run build`, not read at runtime. | Set it in `frontend/.env` and rebuild. As a per-browser workaround, set the endpoint in **Settings → General**. |
| **A report is stuck on *Generating*** | The server process restarted mid-compile. Generation runs in-process with no retry. | Run `python manage.py fail_stuck_reports`, then generate again. Schedule that command so it self-heals. |
| **"Not found" on a record a colleague can see** | Read scoping hid the row — usually you are an auditee and the record belongs to another department. | Expected behaviour. If you should have access, you probably need a different department or role. |
| **"Permission denied" on a record you can see** | The record is visible to you, but you are not named on it and your role lacks the capability. | Ask the person named on the record, or someone with the capability, to act. |
| **A file upload is rejected** | The extension is not on the allowlist, or the file is over the limit (10 MB for documents, 2 MB for images). | Convert to an accepted format, or split or compress the file. |
| **Overdue actions never change status; no reminder emails** | `flag_overdue_actions` is not scheduled, and/or email is still on the console backend. | Schedule the job and configure SMTP. See the [runbook](#scheduled-jobs). |
| **A saved change reappears after refreshing** | The change did not reach the server. | Retry and watch for an error message. Report it — a success message with no saved change is a bug worth filing. |
| **Amharic text shows raw labels like `overdueCapas`** | A missing translation entry. | Report the page and label; the interface still works in English. |
| **Blank page after deployment, and any address other than the home page 404s** | The static host is not falling back to `index.html`. Routing is client-side. | Configure SPA fallback so unknown paths return `index.html`. |
| **A universe entry never appears as due for re-audit** | Its audit frequency is blank or not a recognised value. | Set it to monthly, quarterly, semi-annually, annually, biennially or tri-annually. |
| **Server will not start after setting `DEBUG=False`** | `SECRET_KEY` is required once `DEBUG` is off — there is no fallback, by design. | Set a fresh `SECRET_KEY` in `backend/.env`. Generate one with `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`. |

---

## 18. Glossary

### Audit terms

| Term | Meaning |
|---|---|
| **Audit universe** | The catalogue of everything that could be audited — departments, processes, systems, projects, subsidiaries, regulatory areas. The starting point for annual planning. |
| **Annual audit plan** | The year's programme of audits, approved before work begins. |
| **Engagement** | One individual audit, scheduled under a plan and staffed with a team. |
| **Audit program** | The document setting out an engagement's objectives, scope and test steps. |
| **Procedure** | A single test step within a program. |
| **Working paper** | The documented evidence of work performed, retained for review. |
| **Finding** | A documented deficiency, expressed as condition, criteria, cause, effect and recommendation. |
| **Condition / Criteria / Cause / Effect** | What was found / what should have been / why the gap exists / what it costs or risks. |
| **Repeat finding** | An issue that has recurred, linked back to the earlier finding. |
| **CAPA** | Corrective and Preventive Action — the remediation commitment arising from a finding, with an owner and a due date. |
| **Follow-up** | The scheduled verification that a corrective action actually worked. |
| **Inherent risk** | Risk before controls are considered: likelihood × impact. |
| **Control effectiveness** | How well existing controls mitigate a risk, rated 1 (ineffective) to 5 (highly effective). |
| **Residual risk** | Risk remaining after controls: the score reduced in proportion to control effectiveness. |
| **Heat map** | The 5×5 likelihood-by-impact grid used to compare and prioritise risks. |
| **Self-assessment** | The audited department's own statement of its risk, reviewed by the audit function. |
| **Compliance score** | Verified closure rate: closed findings as a percentage of all findings. |

### EEU terms

| Term | Meaning |
|---|---|
| **EEU** | Ethiopian Electric Utility. |
| **IAEO** | Internal Audit Executive Office — the head of the internal audit function. |
| **FPA** | Financial & Performance Audit Directorate. |
| **TA** | Technical Audit Directorate — substations, distribution grids, loss reduction, transmission. |
| **ITA** | Information Technology Audit Directorate — ERP, CIS billing, cybersecurity, infrastructure. |
| **PP** | Planning & Performance Directorate. |
| **Region** | An EEU regional operating unit. |
| **Customer Service Center (CSC)** | A customer-facing service point beneath a region. |
| **Directorate** | An audit directorate. The dashboard's directorate selector rescopes every figure to one of them. |

### System terms

| Term | Meaning |
|---|---|
| **Employee ID** | Your login identifier, in the form `EEU-#####`. |
| **Capability** | A named permission (manage users, manage settings, approve plans, write audit, close findings, view audit trail) granted by your role. |
| **Read scoping** | The filtering that limits which records a role can see at all — as distinct from what it may change. |
| **Reference number** | A server-assigned identifier: `FND-YYYY-NNNN` for findings, `ENG-YYYY-NNNN` for engagements, `CAPA-YYYY-NNNN` for corrective actions. |
| **Audit trail** | The system's own record of who did what, when, and from where. |

---

## 19. Support

**IT Help Desk:** `audit.support@eeu.gov.et`

When reporting a problem, include: your Employee ID and role, the page you were on, what you expected, what happened, any error message word for word, and the record's reference number if there is one.

| Also see | |
|---|---|
| [README.md](README.md) | Installation, configuration, API reference, deployment |
| [TESTING.md](TESTING.md) | Test coverage, the full role × capability matrix, browser walkthrough |
| **Help** in the header | The in-app workflow overview and role checklists |
