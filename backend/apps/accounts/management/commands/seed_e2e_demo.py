"""
End-to-End Demo Seed — Complete Audit Lifecycle

Creates a single, fully-completed audit engagement that touches every
workflow stage and every role so end-users can see the entire journey
from risk assessment → planning → fieldwork → findings → CAPA → report.

All statuses are "completed" so the report shows every workflow step.

Run:  python manage.py seed_e2e_demo
"""
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import User, Department, Role, AuditTrail
from apps.risk_assessment.models import RiskParameter, RiskAssessment, SelfAssessment
from apps.audit_planning.models import (
    AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember,
)
from apps.audit_execution.models import AuditProgram, AuditProcedure, WorkingPaper
from apps.findings.models import AuditFinding, FindingComment
from apps.corrective_actions.models import CorrectiveAction, ActionResponse, FollowUp
from apps.reports.models import ReportTemplate, GeneratedReport
from apps.notifications.models import Notification, SystemSetting


class Command(BaseCommand):
    help = 'Seeds a complete end-to-end audit lifecycle demo (all roles, all stages completed)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("  EEU E2E DEMO — Complete Audit Lifecycle"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

        now = timezone.now()
        current_year = now.year

        # ────────────────────────────────────────────────────────────────────
        # STAGE 0: Ensure base users & departments exist (idempotent)
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 0] Ensuring users & departments exist...")

        dept_proc, _ = Department.objects.get_or_create(
            code="PROC",
            defaults={"name": "Procurement and Logistics", "head": "Daniel Tekle"},
        )
        dept_fin, _ = Department.objects.get_or_create(
            code="FIN",
            defaults={"name": "Finance and Accounts", "head": "Abebe Kebede"},
        )

        # Ensure roles
        for name, label in Role.ROLE_CHOICES:
            Role.objects.get_or_create(
                name=name,
                defaults={"description": f"Default {label} Role", "permissions": {}},
            )

        # Users — all four workflow roles + admin
        manager, _ = User.objects.get_or_create(
            email="manager@eeu.com",
            defaults={
                "username": "manager",
                "first_name": "Martha",
                "last_name": "Hailu",
                "role": Role.AUDIT_MANAGER,
                "department": dept_fin,
                "employee_id": "EEU-10002",
            },
        )
        if not manager.has_usable_password():
            manager.set_password("user123")
            manager.save()

        supervisor, _ = User.objects.get_or_create(
            email="supervisor@eeu.com",
            defaults={
                "username": "supervisor",
                "first_name": "Bekele",
                "last_name": "Dejene",
                "role": Role.SUPERVISOR,
                "department": dept_fin,
                "employee_id": "EEU-10003",
            },
        )
        if not supervisor.has_usable_password():
            supervisor.set_password("user123")
            supervisor.save()

        auditor, _ = User.objects.get_or_create(
            email="auditor@eeu.com",
            defaults={
                "username": "auditor",
                "first_name": "Tsion",
                "last_name": "Girma",
                "role": Role.AUDITOR,
                "department": dept_fin,
                "employee_id": "EEU-10004",
            },
        )
        if not auditor.has_usable_password():
            auditor.set_password("user123")
            auditor.save()

        auditee, _ = User.objects.get_or_create(
            email="auditee@eeu.com",
            defaults={
                "username": "auditee",
                "first_name": "Kidus",
                "last_name": "Yosef",
                "role": Role.AUDITEE,
                "department": dept_proc,
                "employee_id": "EEU-10005",
            },
        )
        if not auditee.has_usable_password():
            auditee.set_password("user123")
            auditee.save()

        self.stdout.write(f"  ✓ Audit Manager : {manager.get_full_name()} ({manager.email})")
        self.stdout.write(f"  ✓ Supervisor   : {supervisor.get_full_name()} ({supervisor.email})")
        self.stdout.write(f"  ✓ Lead Auditor : {auditor.get_full_name()} ({auditor.email})")
        self.stdout.write(f"  ✓ Auditee       : {auditee.get_full_name()} ({auditee.email})")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 1: Risk Assessment & Universe Setup
        #   — Manager sets up universe, Auditee completes self-assessment,
        #     Manager finalises the risk score.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 1] Risk Assessment & Audit Universe Setup...")

        # Risk parameters (if not already present)
        risk_params_data = [
            {"name": "Financial Impact", "description": "Potential monetary loss", "weight": 0.30, "category": "financial"},
            {"name": "Operational Disruption", "description": "Interruption to services", "weight": 0.25, "category": "operational"},
            {"name": "Compliance Violations", "description": "Regulatory exposure", "weight": 0.20, "category": "compliance"},
            {"name": "Process Complexity", "description": "Control complexity", "weight": 0.15, "category": "operational"},
            {"name": "System Automation", "description": "Manual process reliance", "weight": 0.10, "category": "it"},
        ]
        for rp in risk_params_data:
            RiskParameter.objects.get_or_create(
                name=rp["name"],
                defaults=rp,
            )

        # Audit Universe entry for the procurement process
        universe, created = AuditUniverse.objects.get_or_create(
            code="E2E-PROC-01",
            defaults={
                "name": "Procurement of High-Voltage Cables & Substation Equipment",
                "category": "process",
                "department": dept_proc,
                "risk_score": 4.80,
                "audit_frequency": "Annually",
                "owner": dept_proc.head,
                "status": "active",
                "last_audited": now.date() - datetime.timedelta(days=400),
            },
        )
        if created:
            self.stdout.write(f"  ✓ Created Audit Universe: {universe.name}")

        # Risk Assessment — completed
        risk_assessment, created = RiskAssessment.objects.get_or_create(
            department=dept_proc,
            year=current_year,
            assessment_period="Annual",
            defaults={
                "audit_universe": universe,
                "likelihood": 4,
                "impact": 5,
                "control_effectiveness": 2,
                "notes": "Annual risk assessment for procurement process. High likelihood of "
                         "procurement fraud due to manual approval workflows and weak vendor "
                         "verification controls.",
                "assessed_by": manager,
                "reviewed_by": manager,
            },
        )
        if created:
            self.stdout.write(f"  ✓ Created Risk Assessment: score={risk_assessment.risk_score}, "
                              f"rating={risk_assessment.risk_rating}")

        # Auditee self-assessment — reviewed (completed)
        self_assessment, created = SelfAssessment.objects.get_or_create(
            risk_assessment=risk_assessment,
            defaults={
                "submitted_by": auditee,
                "status": "reviewed",
                "likelihood_self": 3,
                "impact_self": 4,
                "control_effectiveness_self": 3,
                "justification": "Procurement process has documented procedures but vendor "
                                "due-diligence checks are inconsistently applied across teams.",
                "mitigating_controls": "Tender Committee review for purchases above 500,000 ETB; "
                                       "dual-signature requirement for bank transfers.",
                "reviewer_notes": "Self-assessment aligns with audit team findings. Control "
                                  "effectiveness rated lower due to recent staff turnover.",
                "reviewed_by": manager,
                "reviewed_at": now - datetime.timedelta(days=30),
            },
        )
        if created:
            self.stdout.write(f"  ✓ Created Auditee Self-Assessment (status=reviewed)")

        self._log_audit(manager, "CREATE", universe, "E2E: Risk Assessment completed")
        self._log_audit(auditee, "CREATE", self_assessment, "E2E: Auditee self-assessment submitted")
        self._log_audit(manager, "APPROVE", risk_assessment, "E2E: Risk assessment reviewed & approved")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 2: Annual Plan Creation & Approval
        #   — Manager creates plan, submits, and approves it.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 2] Annual Audit Plan — Created, Submitted & Approved...")

        plan, created = AuditPlan.objects.get_or_create(
            year=current_year,
            title=f"E2E Demo — Annual Audit Plan {current_year}",
            defaults={
                "description": "Comprehensive annual audit plan covering procurement, finance, "
                               "and IT controls. This plan has been fully approved and completed.",
                "objectives": "Evaluate internal controls across procurement and finance; verify "
                              "compliance with EEU procurement regulations; identify cost "
                              "efficiencies and fraud risks.",
                "scope": "All procurement processes, vendor management, and payment cycles within "
                         "EEU Procurement and Finance departments.",
                "methodology": "COSO Internal Control Framework, risk-based sampling, substantive "
                               "testing, and data analytics.",
                "status": "completed",
                "created_by": manager,
                "approved_by": manager,
                "approved_at": now - datetime.timedelta(days=60),
                "start_date": datetime.date(current_year, 1, 1),
                "end_date": datetime.date(current_year, 12, 31),
                "total_budget_days": 120,
            },
        )
        if created:
            self.stdout.write(f"  ✓ Created Audit Plan: {plan.title} (status=completed)")

        self._log_audit(manager, "CREATE", plan, "E2E: Annual plan created")
        self._log_audit(manager, "APPROVE", plan, "E2E: Annual plan submitted & approved")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 3: Engagement Scheduling & Staffing
        #   — Manager schedules engagement, assigns lead auditor & supervisor.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 3] Engagement Scheduling & Team Assignment...")

        engagement, created = AuditEngagement.objects.get_or_create(
            engagement_number=f"E2E-ENG-{current_year}-001",
            defaults={
                "plan": plan,
                "audit_universe": universe,
                "title": "Procurement Compliance & Fraud Risk Audit",
                "engagement_type": "compliance",
                "department": dept_proc,
                "objectives": "Assess compliance of the procurement process with EEU regulations; "
                              "evaluate vendor selection controls; identify fraud risk indicators.",
                "scope": "All procurement transactions above 100,000 ETB for the current fiscal "
                         "year, including tender evaluations, vendor onboarding, and payment "
                         "approvals.",
                "status": "completed",
                "lead_auditor": auditor,
                "supervisor": supervisor,
                "planned_start": datetime.date(current_year, 3, 1),
                "planned_end": datetime.date(current_year, 5, 30),
                "actual_start": datetime.date(current_year, 3, 1),
                "actual_end": datetime.date(current_year, 5, 15),
                "planned_days": 60,
                "actual_days": 55,
                "risk_level": "critical",
            },
        )
        if created:
            self.stdout.write(f"  ✓ Created Engagement: {engagement.title} (status=completed)")

            # Team members
            AuditTeamMember.objects.get_or_create(
                engagement=engagement, user=auditor,
                defaults={"role": "lead", "allocated_days": 40, "actual_days": 38},
            )
            AuditTeamMember.objects.get_or_create(
                engagement=engagement, user=supervisor,
                defaults={"role": "supervisor", "allocated_days": 15, "actual_days": 12},
            )
            self.stdout.write("  ✓ Team assigned: Lead Auditor + Supervisor")

        self._log_audit(manager, "CREATE", engagement, "E2E: Engagement scheduled")
        self._notify(auditor, "assigned", "New Engagement Assignment",
                      f"You have been assigned as Lead Auditor for '{engagement.title}'.")
        self._notify(supervisor, "assigned", "Supervision Assignment",
                      f"You are the Supervisor for '{engagement.title}'.")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 4: Execution & Fieldwork
        #   — Auditor creates program, Supervisor approves,
        #     Auditor completes all procedures & uploads working papers.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 4] Audit Execution & Fieldwork...")

        program, created = AuditProgram.objects.get_or_create(
            engagement=engagement,
            defaults={
                "title": "Procurement Compliance Audit Program",
                "objectives": "Test the design and operating effectiveness of procurement "
                              "controls, vendor due-diligence, and payment authorization workflows.",
                "scope": "All procurement transactions Q1–Q2, vendor master data, and tender "
                         "committee minutes.",
                "status": "completed",
                "version": 1,
                "prepared_by": auditor,
                "reviewed_by": supervisor,
                "approved_by": supervisor,
                "approved_at": now - datetime.timedelta(days=45),
            },
        )
        if created:
            self.stdout.write(f"  ✓ Created Audit Program: {program.title} (status=completed)")

        self._log_audit(auditor, "CREATE", program, "E2E: Audit program created")
        self._log_audit(supervisor, "APPROVE", program, "E2E: Program submitted for review")
        self._log_audit(supervisor, "APPROVE", program, "E2E: Program approved by supervisor")
        self._notify(auditor, "approved", "Program Approved",
                      f"Your audit program for '{engagement.title}' has been approved.")

        # Procedures — all completed
        procedures_data = [
            {
                "step_number": "PROC-001",
                "title": "Review Vendor Onboarding & Due-Diligence Process",
                "description": "Obtain the vendor registration list and verify that all new "
                               "vendors completed the required due-diligence checks (business "
                               "registration, tax clearance, bank verification).",
                "procedure_type": "test_of_controls",
                "risk_area": "Vendor Fraud Risk",
                "assertion": "Completeness, Existence",
                "expected_evidence": "Vendor registration forms, due-diligence checklists, "
                                     "and approval signatures.",
                "conclusion": "3 out of 15 new vendors were onboarded without complete "
                              "due-diligence documentation. Control deficiency identified.",
            },
            {
                "step_number": "PROC-002",
                "title": "Test Tender Committee Evaluation Controls",
                "description": "Inspect tender evaluation minutes for 10 high-value procurements "
                               "to verify proper quorum, evaluation criteria, and approval.",
                "procedure_type": "substantive",
                "risk_area": "Procurement Bypass Risk",
                "assertion": "Occurrence, Authorization",
                "expected_evidence": "Tender committee minutes, evaluation scorecards, and "
                                     "approval memos.",
                "conclusion": "2 out of 10 tenders had incomplete evaluation documentation. "
                              "One tender was awarded without quorum. Finding raised.",
            },
            {
                "step_number": "PROC-003",
                "title": "Verify Payment Authorization Workflow",
                "description": "Trace 20 sample payments from invoice to bank transfer to verify "
                               "dual-signature controls and proper segregation of duties.",
                "procedure_type": "substantive",
                "risk_area": "Payment Fraud Risk",
                "assertion": "Accuracy, Authorization",
                "expected_evidence": "Invoices, payment vouchers, bank transfer confirmations, "
                                     "and approval signatures.",
                "conclusion": "All 20 sampled payments had proper dual-signature authorization. "
                              "No exceptions noted. Control operating effectively.",
            },
            {
                "step_number": "PROC-004",
                "title": "Analytical Review of Procurement Spend",
                "description": "Perform spend analytics to identify unusual patterns, duplicate "
                               "vendors, and split-purchase indicators.",
                "procedure_type": "analytical",
                "risk_area": "Split Purchase Risk",
                "assertion": "Completeness, Classification",
                "expected_evidence": "Spend data export, analytics worksheets, and exception "
                                     "reports.",
                "conclusion": "Identified 5 potential split-purchase transactions just below "
                              "the tender threshold. Finding raised for investigation.",
            },
        ]

        procedures = []
        for idx, pd in enumerate(procedures_data):
            proc, created = AuditProcedure.objects.get_or_create(
                program=program,
                step_number=pd["step_number"],
                defaults={
                    "title": pd["title"],
                    "description": pd["description"],
                    "procedure_type": pd["procedure_type"],
                    "risk_area": pd["risk_area"],
                    "assertion": pd["assertion"],
                    "expected_evidence": pd["expected_evidence"],
                    "status": "completed",
                    "assigned_to": auditor,
                    "completed_by": auditor,
                    "completed_at": now - datetime.timedelta(days=35 - idx * 3),
                    "conclusion": pd["conclusion"],
                    "order": idx + 1,
                },
            )
            procedures.append(proc)
            if created:
                self.stdout.write(f"  ✓ Procedure {pd['step_number']}: {pd['title']} (completed)")

        self._log_audit(auditor, "UPDATE", program, "E2E: All fieldwork procedures completed")

        # Working Papers — reviewed
        wp_data = [
            {"ref": "WP-A.1.1", "title": "Vendor Registration Master List", "proc": procedures[0]},
            {"ref": "WP-A.1.2", "title": "Due-Diligence Checklist Exceptions", "proc": procedures[0]},
            {"ref": "WP-B.2.1", "title": "Tender Committee Minutes — Sample", "proc": procedures[1]},
            {"ref": "WP-B.2.2", "title": "Tender Evaluation Scorecards", "proc": procedures[1]},
            {"ref": "WP-C.3.1", "title": "Payment Authorization Trace Worksheet", "proc": procedures[2]},
            {"ref": "WP-D.4.1", "title": "Spend Analytics — Exception Report", "proc": procedures[3]},
        ]
        for idx, wp in enumerate(wp_data):
            paper, created = WorkingPaper.objects.get_or_create(
                engagement=engagement,
                reference=wp["ref"],
                defaults={
                    "procedure": wp["proc"],
                    "title": wp["title"],
                    "description": f"Working paper documenting {wp['title'].lower()} for the "
                                   f"procurement compliance audit.",
                    "paper_type": "evidence",
                    "prepared_by": auditor,
                    "reviewed_by": supervisor,
                    "is_reviewed": True,
                    "review_notes": "Reviewed and accepted. Evidence sufficient to support "
                                    "audit conclusion." if idx % 2 == 0
                                    else "Reviewed with minor comments. Evidence acceptable.",
                },
            )
            if created:
                self.stdout.write(f"  ✓ Working Paper {wp['ref']}: {wp['title']} (reviewed)")

        self._log_audit(auditor, "CREATE", engagement, "E2E: Working papers uploaded")
        self._log_audit(supervisor, "APPROVE", engagement, "E2E: Working papers reviewed & accepted")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 5: Findings & Recommendations
        #   — Auditor logs findings based on fieldwork results.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 5] Findings & Recommendations...")

        findings_data = [
            {
                "number": "E2E-FIND-001",
                "title": "Incomplete Vendor Due-Diligence Documentation",
                "description": "3 out of 15 new vendors were onboarded without complete "
                               "due-diligence documentation (missing tax clearance and bank "
                               "verification letters).",
                "severity": "high",
                "category": "control_deficiency",
                "condition": "3 of 15 new vendors lack tax clearance certificates and bank "
                             "verification letters in their registration files.",
                "criteria": "EEU Procurement Manual Section 3.4 requires all vendors to submit "
                            "complete due-diligence documentation before activation.",
                "cause": "The vendor onboarding system does not enforce mandatory document "
                         "upload before activation. Procurement officers can bypass the check "
                         "manually.",
                "effect": "Risk of fictitious vendor creation and fraudulent payments to "
                          "unverified bank accounts.",
                "recommendation": "Implement system-enforced mandatory document upload in the "
                                  "ERP vendor master. Re-verify all 3 vendors and obtain "
                                  "missing documentation within 30 days.",
            },
            {
                "number": "E2E-FIND-002",
                "title": "Tender Awarded Without Committee Quorum",
                "description": "One high-value tender (1.2M ETB) was awarded without the required "
                               "quorum of 3 tender committee members — only 2 were present.",
                "severity": "critical",
                "category": "compliance",
                "condition": "Tender T-2024-015 was approved with only 2 of 3 required "
                             "committee members present, violating quorum requirements.",
                "criteria": "EEU Procurement Regulation Article 7.2 requires a minimum quorum "
                            "of 3 committee members for tenders above 500,000 ETB.",
                "cause": "Absence of a committee member was not escalated; no alternate member "
                         "was designated. The procurement officer proceeded without quorum.",
                "effect": "Potential legal challenge to the tender award; risk of biased "
                          "vendor selection without proper oversight.",
                "recommendation": "Retrospectively review and ratify the tender decision with "
                                  "a full quorum. Designate alternate committee members and "
                                  "enforce quorum checks in the tender management system.",
            },
            {
                "number": "E2E-FIND-003",
                "title": "Potential Split Purchases Below Tender Threshold",
                "description": "5 transactions to the same vendor within 2 weeks, each just "
                               "below the 100,000 ETB tender threshold, indicating possible "
                               "split purchasing to bypass competitive tendering.",
                "severity": "medium",
                "category": "fraud",
                "condition": "5 separate purchase orders to vendor V-0145, each between "
                             "95,000–99,000 ETB, issued within a 14-day period.",
                "criteria": "EEU Procurement Regulation Article 5.1 prohibits split purchasing "
                            "to circumvent tender thresholds.",
                "cause": "No automated monitoring or alert system for split-purchase detection. "
                         "Procurement officers can issue multiple POs without system-level review.",
                "effect": "Potential circumvention of competitive tendering; risk of inflated "
                          "pricing and favoritism toward specific vendors.",
                "recommendation": "Implement automated split-purchase detection in the ERP. "
                                  "Investigate the 5 transactions and recover any overpayment. "
                                  "Establish a quarterly spend analytics review.",
            },
        ]

        findings = []
        for idx, fd in enumerate(findings_data):
            finding, created = AuditFinding.objects.get_or_create(
                engagement=engagement,
                finding_number=fd["number"],
                defaults={
                    "title": fd["title"],
                    "description": fd["description"],
                    "severity": fd["severity"],
                    "category": fd["category"],
                    "condition": fd["condition"],
                    "criteria": fd["criteria"],
                    "cause": fd["cause"],
                    "effect": fd["effect"],
                    "recommendation": fd["recommendation"],
                    "status": "closed",
                    "identified_by": auditor,
                    "assigned_to": auditee,
                    "auditee": auditee,
                    "procedure": procedures[idx] if idx < len(procedures) else None,
                    "target_resolution_date": now.date() + datetime.timedelta(days=90),
                    "actual_resolution_date": now.date() - datetime.timedelta(days=5),
                    "management_response": "Management acknowledges the finding and has "
                                           "implemented corrective actions as detailed in the "
                                           "associated CAPA. All remediation steps are complete.",
                    "is_repeat": False,
                },
            )
            findings.append(finding)
            if created:
                self.stdout.write(f"  ✓ Finding {fd['number']}: {fd['title']} (closed)")

            # Finding comment from auditee
            FindingComment.objects.get_or_create(
                finding=finding,
                author=auditee,
                comment=f"Thank you for the finding. We have reviewed the recommendation and "
                        f"will implement corrective actions. Please see the associated CAPA "
                        f"for our detailed response.",
                defaults={"is_internal": False},
            )

        self._log_audit(auditor, "CREATE", engagement, "E2E: 3 audit findings logged")
        self._notify(auditee, "finding", "New Audit Finding Assigned",
                      f"You have been assigned finding {findings[0].finding_number}. "
                      "Please review and respond.")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 6: Corrective Action Plan (CAPA) Portal
        #   — Auditor spawns CAPAs, Auditee responds with progress,
        #     Supervisor verifies and closes.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 6] Corrective Actions (CAPA) — Resolved & Closed...")

        capa_data = [
            {
                "number": "E2E-CAPA-001",
                "finding": findings[0],
                "title": "Enforce Mandatory Vendor Due-Diligence Upload",
                "description": "Configure the ERP vendor master to require mandatory upload of "
                                "tax clearance and bank verification documents before vendor "
                                "activation. Re-verify the 3 non-compliant vendors.",
                "recommendation": "System change request submitted to IT. Vendor re-verification "
                                  "in progress.",
                "priority": "high",
                "due_date": now.date() + datetime.timedelta(days=30),
                "completed_date": now.date() - datetime.timedelta(days=7),
            },
            {
                "number": "E2E-CAPA-002",
                "finding": findings[1],
                "title": "Ratify Tender Decision & Designate Alternate Committee Members",
                "description": "Retrospectively ratify tender T-2024-015 with full quorum. "
                                "Designate 2 alternate tender committee members and enforce "
                                "quorum checks in the tender system.",
                "recommendation": "Tender decision ratified on {0}. Alternates designated "
                                  "and system updated.".format(
                                      (now.date() - datetime.timedelta(days=10)).isoformat()),
                "priority": "immediate",
                "due_date": now.date() + datetime.timedelta(days=15),
                "completed_date": now.date() - datetime.timedelta(days=5),
            },
            {
                "number": "E2E-CAPA-003",
                "finding": findings[2],
                "title": "Implement Split-Purchase Detection & Investigate Transactions",
                "description": "Deploy automated split-purchase monitoring in the ERP. "
                                "Investigate the 5 flagged transactions and recover any "
                                "overpayment from vendor V-0145.",
                "recommendation": "Analytics dashboard deployed. Investigation complete — "
                                  "no overpayment found. Vendor issued warning letter.",
                "priority": "medium",
                "due_date": now.date() + datetime.timedelta(days=60),
                "completed_date": now.date() - datetime.timedelta(days=3),
            },
        ]

        capas = []
        for cd in capa_data:
            capa, created = CorrectiveAction.objects.get_or_create(
                finding=cd["finding"],
                action_number=cd["number"],
                defaults={
                    "title": cd["title"],
                    "description": cd["description"],
                    "recommendation": cd["recommendation"],
                    "owner": auditee,
                    "assigned_by": auditor,
                    "status": "closed",
                    "priority": cd["priority"],
                    "due_date": cd["due_date"],
                    "completed_date": cd["completed_date"],
                    "management_response": "Corrective action fully implemented. Evidence "
                                           "documentation attached. Requesting closure verification.",
                    "follow_up_notes": "Verified by supervisor. Action confirmed complete.",
                },
            )
            capas.append(capa)
            if created:
                self.stdout.write(f"  ✓ CAPA {cd['number']}: {cd['title']} (closed)")

            # Action response from auditee
            ActionResponse.objects.get_or_create(
                corrective_action=capa,
                responder=auditee,
                response_text=f"Implementation complete. {cd['recommendation']}",
                defaults={"status_update": "resolved"},
            )

            # Follow-up — completed
            FollowUp.objects.get_or_create(
                corrective_action=capa,
                scheduled_date=cd["completed_date"],
                defaults={
                    "conducted_by": supervisor,
                    "status": "completed",
                    "notes": "Follow-up verification conducted. Corrective action confirmed "
                             "fully implemented. Evidence reviewed and accepted.",
                    "outcome": "CAPA verified and closed",
                },
            )

        self._log_audit(auditor, "CREATE", engagement, "E2E: 3 CAPAs created from findings")
        self._log_audit(auditee, "UPDATE", engagement, "E2E: Auditee submitted CAPA responses")
        self._log_audit(supervisor, "APPROVE", engagement, "E2E: Supervisor verified & closed all CAPAs")
        self._notify(auditor, "approved", "CAPA Closed",
                      "All corrective actions for the engagement have been verified and closed.")

        # ────────────────────────────────────────────────────────────────────
        # STAGE 7: Reports & Analytics
        #   — Auditor/Manager generates final report, engagement closed.
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n[Stage 7] Reports & Analytics — Final Report Generated...")

        # Report template
        template, _ = ReportTemplate.objects.get_or_create(
            name="E2E Standard Audit Report Template",
            defaults={
                "template_type": "engagement",
                "description": "Comprehensive engagement report covering background, objectives, "
                               "scope, methodology, findings, CAPA status, and executive summary.",
                "is_default": True,
                "created_by": manager,
            },
        )

        # Generated report — ready
        report, created = GeneratedReport.objects.get_or_create(
            title=f"Final Audit Report — {engagement.title}",
            defaults={
                "template": template,
                "engagement": engagement,
                "format": "pdf",
                "status": "ready",
                "parameters": {
                    "include_executive_summary": True,
                    "include_findings": True,
                    "include_capa": True,
                    "include_risk_analysis": True,
                    "include_procedures": True,
                },
                "generated_by": auditor,
            },
        )
        if created:
            self.stdout.write(f"  ✓ Generated Report: {report.title} (status=ready)")

        self._log_audit(auditor, "CREATE", report, "E2E: Final audit report generated")
        self._log_audit(manager, "APPROVE", engagement, "E2E: Engagement reviewed & closed by manager")
        self._notify(manager, "report_ready", "Audit Report Ready",
                      f"The final report for '{engagement.title}' is ready for review.")
        self._notify(auditee, "report_ready", "Audit Report Published",
                      f"The final audit report for '{engagement.title}' has been published.")

        # ────────────────────────────────────────────────────────────────────
        # System Settings
        # ────────────────────────────────────────────────────────────────────
        SystemSetting.objects.get_or_create(
            key="enable_email_alerts",
            defaults={
                "value": "True",
                "description": "Enable automated emails on corrective action status changes.",
                "updated_by": manager,
            },
        )

        # ────────────────────────────────────────────────────────────────────
        # Summary
        # ────────────────────────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("  E2E DEMO COMPLETE — Full Audit Lifecycle Seeded"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"""
  Workflow Summary:
  ─────────────────
  Stage 1: Risk Assessment      ✓ Completed (score={risk_assessment.risk_score}, rating={risk_assessment.risk_rating})
  Stage 2: Annual Plan          ✓ Approved & Completed
  Stage 3: Engagement           ✓ Scheduled & Team Assigned (status=completed)
  Stage 4: Fieldwork            ✓ Program approved, 4 procedures completed, 6 working papers reviewed
  Stage 5: Findings             ✓ 3 findings logged & closed (1 critical, 1 high, 1 medium)
  Stage 6: CAPA                 ✓ 3 corrective actions resolved & closed, 3 follow-ups completed
  Stage 7: Report               ✓ Final report generated (status=ready)

  Roles Involved:
  ──────────────
  • Audit Manager ({manager.get_full_name()}): Created plan, approved, risk assessment, closed engagement
  • Supervisor ({supervisor.get_full_name()}): Approved program, reviewed working papers, verified CAPAs
  • Lead Auditor ({auditor.get_full_name()}): Created program, completed procedures, logged findings, generated report
  • Auditee ({auditee.get_full_name()}): Self-assessment, CAPA responses, follow-up participation

  Login Credentials:
  ─────────────────
  Manager:    manager@eeu.com    / user123
  Supervisor: supervisor@eeu.com / user123
  Auditor:    auditor@eeu.com    / user123
  Auditee:    auditee@eeu.com    / user123

  Audit Trail: {AuditTrail.objects.count()} entries logged
  Notifications: {Notification.objects.count()} notifications created
""")

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _log_audit(self, user, action, instance, description=""):
        """Create an AuditTrail entry for the E2E demo."""
        ct = ContentType.objects.get_for_model(instance)
        AuditTrail.objects.create(
            user=user,
            action=action,
            model_name=instance._meta.model_name,
            object_id=str(instance.pk),
            object_repr=description or str(instance),
            changes={"e2e_demo": True, "description": description},
            ip_address="127.0.0.1",
            user_agent="E2E-Demo-Seed/1.0",
        )

    def _notify(self, user, ntype, title, message, link=""):
        """Create a Notification for the E2E demo."""
        Notification.objects.create(
            user=user,
            notification_type=ntype,
            title=title,
            message=message,
            link=link,
            is_read=False,
        )