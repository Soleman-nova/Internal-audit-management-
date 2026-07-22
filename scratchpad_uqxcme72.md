# EEU Internal Audit Management System — Role-Based Workflow Guide

This document details the step-by-step end-to-end journey for each user role in the EEU Internal Audit Management System, from configuration to audit closure.

---

## 👥 Roles Overview
* **Super Admin (`admin`)**: Responsible for user management, system configuration, access control, and auditing security logs.
* **Audit Manager (`audit_manager`)**: Drives the annual audit cycle, manages the Audit Universe, creates and approves Annual Plans, and initiates/schedules Engagements.
* **Audit Supervisor (`supervisor`)**: Reviews audit programs, reviews fieldwork working papers, and coordinates the execution.
* **Auditor / Lead Auditor (`auditor`)**: Designs audit program procedures, conducts fieldwork (checklists and workpapers), logs findings, and drafts final reports.
* **Auditee (`auditee`)**: Represents audited departments, completes risk self-assessments, and owns corrective actions (CAPA) execution and updates.

---

## 🔄 End-to-End Workflow Stages

### Stage 1: Risk Assessment & Universe Setup
* **Auditor/Manager**: Adds operational entities, processes, and IT systems to the **Audit Universe** (Planning Page).
* **Auditee**: Completes self-assessments on risk parameters (Risk Page).
* **Manager**: Configures weights/parameters and views the **Risk Heat Map (5x5)** to rank entities by priority.

### Stage 2: Annual Plan Creation & Submission
* **Manager**: Creates an **Annual Audit Plan** (Title, Budget Days, Start/End dates).
* **Manager**: Maps universe items to the plan.
* **Manager**: Submits the plan for review and approves it (changes status to `approved`/`active`).

### Stage 3: Engagement Scheduling & Staffing
* **Manager**: Schedules **Audit Engagements** under an approved plan (assigning lead auditors, supervisors, and allocating days).

### Stage 4: Execution & Fieldwork
* **Auditor**: Creates an **Audit Program** (objectives, scope) and defines individual **Fieldwork Procedures** (step numbers, procedure types, assertions).
* **Supervisor**: Reviews and approves the Audit Program.
* **Auditor**: Updates status of each procedure (`In Progress` -> `Completed`) and uploads files to the **Working Papers Registry** as evidence.
* **Supervisor**: Reviews uploaded working papers and adds review notes/sign-off.

### Stage 5: Findings & Recommendations
* **Auditor**: Records **Findings** related to control deficiencies, IT security issues, or compliance exceptions (logs criteria, condition, cause, effect, and recommendation).
* **Auditor**: Submits findings for management review (sets status to `open`).

### Stage 6: Corrective Action Plan (CAPA) Portal
* **Auditor**: Spawns **CAPAs** linked to approved findings.
* **Auditee**: Logs in to the portal, responds to assigned CAPAs, uploads progress updates, and sets status to `In Progress` or `Resolved`.
* **Auditor/Supervisor**: Verifies remediation evidence and closes the CAPA.

### Stage 7: Reports & Analytics
* **Auditor/Manager**: Generates standard draft reports based on findings.
* **Manager**: Marks the entire engagement as completed.

---

## 📋 Detailed Step-by-Step Task List by Role

### 1. 🔑 Super Admin Workflow
* [ ] **Step 1.1**: Log in as administrator using `admin@eeu.com`.
* [ ] **Step 1.2**: Access **User Management** in the sidebar.
* [ ] **Step 1.3**: Add new users (name, email, role, department, employee ID) and activate or deactivate existing accounts.
* [ ] **Step 1.4**: Check **Audit Trail** in the sidebar to review system logs (user logins, page access, actions, and timestamps).

### 2. 📈 Audit Manager Workflow
* [ ] **Step 2.1**: Log in as manager using `manager@eeu.com`.
* [ ] **Step 2.2**: Manage the **Audit Universe** (add systems, projects, or processes with their associated department, category, and initial risk score).
* [ ] **Step 2.3**: Open the **Risk Assessment** tab to define risk weights (financial weight, complexity weight, etc.) and view the dynamic **5x5 Risk Heat Map**.
* [ ] **Step 2.4**: Create a new **Annual Audit Plan** (providing year, budget, dates, and objective).
* [ ] **Step 2.5**: Submit the plan for approval, and mark it as `Approved`.
* [ ] **Step 2.6**: Schedule individual **Audit Engagements** under that plan (mapping them to universe nodes, selecting risk level, planned dates, and assigning a Lead Auditor & Supervisor).
* [ ] **Step 2.7**: Access the **Reports** section to compile, review, and lock final audit reports.

### 3. 🛡️ Audit Supervisor Workflow
* [ ] **Step 3.1**: Log in as supervisor using `supervisor@eeu.com`.
* [ ] **Step 3.2**: Open **Audit Execution** and review the defined audit program structure (Objectives & Scope) for the engagement.
* [ ] **Step 3.3**: Click "Approve Program" to sign off and transition the program from `draft` to `approved`.
* [ ] **Step 3.4**: Monitor active fieldwork status of assigned auditors.
* [ ] **Step 3.5**: Inspect uploaded working papers in the **Working Papers Registry** and post supervisor review notes or approve the workpaper.

### 4. ✍️ Auditor / Lead Auditor Workflow
* [ ] **Step 4.1**: Log in as auditor using `auditor@eeu.com`.
* [ ] **Step 4.2**: Navigate to **Audit Execution** and select the active engagement.
* [ ] **Step 4.3**: Create/define the **Audit Program** if it does not exist.
* [ ] **Step 4.4**: Add specific **Fieldwork Procedures** under the program.
* [ ] **Step 4.5**: Perform tests, transition procedures status (`Pending` -> `In Progress` -> `Completed`), and upload evidence files in the **Upload Working Paper** card.
* [ ] **Step 4.6**: Navigate to the **Findings Registry** and click **Log Finding** to capture control deficiencies (categorize severity, describe condition, criteria, root cause, effect, and write recommendation).
* [ ] **Step 4.7**: Navigate to **Corrective Actions** and create/spawn CAPA tasks linked to findings.
* [ ] **Step 4.8**: Access the **Reports & Analytics** tab to generate standard draft report summaries.

### 5. 🏢 Auditee Workflow
* [ ] **Step 5.1**: Log in as auditee using `auditee@eeu.com`.
* [ ] **Step 5.2**: Go to **Risk Assessment** -> **Self Assessment** to respond to operational risk surveys.
* [ ] **Step 5.3**: Open the **Corrective Actions** portal.
* [ ] **Step 5.4**: Locate CAPAs assigned to their department, click **Respond**, type progress/remediation notes, update the status, and upload implementation documents.
