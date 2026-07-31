import os
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import User, Department, Role
from apps.risk_assessment.models import RiskParameter, RiskAssessment
from apps.audit_planning.models import AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember
from apps.audit_execution.models import AuditProgram, AuditProcedure
from apps.findings.models import AuditFinding
from apps.corrective_actions.models import CorrectiveAction
from apps.reports.models import ReportTemplate
from apps.notifications.models import SystemSetting

class Command(BaseCommand):
    help = 'Seeds initial demo data for EEU Internal Audit Management System'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding data...")

        # 1. Create Departments
        depts_data = [
            {"name": "Finance and Accounts", "code": "FIN", "head": "Abebe Kebede"},
            {"name": "Information Technology", "code": "IT", "head": "Sarah Mohammed"},
            {"name": "Procurement and Logistics", "code": "PROC", "head": "Daniel Tekle"},
            {"name": "Human Resources", "code": "HR", "head": "Tigist Assefa"},
            {"name": "Power Distribution", "code": "DIST", "head": "Dawit Tesfaye"},
        ]
        depts = {}
        for d in depts_data:
            dept, created = Department.objects.get_or_create(
                code=d["code"],
                defaults={"name": d["name"], "head": d["head"], "description": f"EEU {d['name']} Department"}
            )
            depts[d["code"]] = dept
            if created:
                self.stdout.write(f"Created Department: {dept.name}")

        # 2. Create Roles (django DB roles if they aren't created by signals or already there)
        for name, label in Role.ROLE_CHOICES:
            role, created = Role.objects.get_or_create(
                name=name,
                defaults={"description": f"Default {label} Role", "permissions": {}}
            )

        # 3. Create Users
        users_data = [
            {
                "email": "admin@eeu.com",
                "username": "admin",
                "first_name": "Anteneh",
                "last_name": "Getachew",
                "role": Role.ADMIN,
                "department": depts["IT"],
                "employee_id": "EEU-10001",
            },
            {
                "email": "manager@eeu.com",
                "username": "manager",
                "first_name": "Martha",
                "last_name": "Hailu",
                "role": Role.AUDIT_MANAGER,
                "department": depts["FIN"],
                "employee_id": "EEU-10002",
            },
            {
                "email": "supervisor@eeu.com",
                "username": "supervisor",
                "first_name": "Bekele",
                "last_name": "Dejene",
                "role": Role.SUPERVISOR,
                "department": depts["FIN"],
                "employee_id": "EEU-10003",
            },
            {
                "email": "auditor@eeu.com",
                "username": "auditor",
                "first_name": "Tsion",
                "last_name": "Girma",
                "role": Role.AUDITOR,
                "department": depts["FIN"],
                "employee_id": "EEU-10004",
            },
            {
                "email": "auditee@eeu.com",
                "username": "auditee",
                "first_name": "Kidus",
                "last_name": "Yosef",
                "role": Role.AUDITEE,
                "department": depts["PROC"],
                "employee_id": "EEU-10005",
            },
        ]

        users = {}
        for u in users_data:
            user = User.objects.filter(email=u["email"]).first()
            if not user:
                user = User.objects.create_user(
                    email=u["email"],
                    username=u["username"],
                    first_name=u["first_name"],
                    last_name=u["last_name"],
                    role=u["role"],
                    department=u["department"],
                    employee_id=u["employee_id"],
                )
                user.set_password("admin123" if u["role"] == Role.ADMIN else "user123")
                user.save()
                self.stdout.write(f"Created User: {user.email}")
            users[u["role"]] = user

        # Make admin superuser
        admin_user = users[Role.ADMIN]
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.save()

        # 4. Create Risk Parameters
        risk_params = [
            {"name": "Financial Impact", "description": "Potential direct or indirect monetary loss to EEU", "weight": 0.3, "category": "financial"},
            {"name": "Operational Disruption", "description": "Degree of interruption to power supply or utility services", "weight": 0.25, "category": "operational"},
            {"name": "Compliance Violations", "description": "Exposure to regulatory penalties or audits exceptions", "weight": 0.2, "category": "compliance"},
            {"name": "Process Complexity", "description": "Internal controls complexity and number of actors", "weight": 0.15, "category": "operational"},
            {"name": "System Automation", "description": "Lack of automated reconciliation or reliance on manual work", "weight": 0.1, "category": "it"},
        ]
        for rp in risk_params:
            RiskParameter.objects.get_or_create(
                name=rp["name"],
                defaults={"description": rp["description"], "weight": rp["weight"], "category": rp["category"]}
            )

        # 4b. Create a Risk Assessment (so report "Risk Analysis" isn't empty on demo data).
        # risk_score / risk_rating / residual_risk are computed in RiskAssessment.save().
        ra, ra_created = RiskAssessment.objects.get_or_create(
            department=depts["FIN"],
            year=datetime.datetime.now().year,
            assessment_period="Annual",
            defaults={
                "likelihood": 4,
                "impact": 4,
                "control_effectiveness": 3,
                "notes": "Baseline annual risk assessment for financial systems and controls.",
                "assessed_by": users[Role.AUDIT_MANAGER],
            },
        )
        if ra_created:
            self.stdout.write(f"Created Risk Assessment: {ra}")

        # 5. Create Audit Universe
        universe_data = [
            {"name": "ERP Financials and Accounts Payable", "code": "UNIV-FIN-01", "category": "system", "dept": depts["FIN"], "risk": 4.25, "freq": "Annually"},
            {"name": "High Voltage Grid Procurement Project", "code": "UNIV-PROC-02", "category": "project", "dept": depts["PROC"], "risk": 4.80, "freq": "Annually"},
            {"name": "Billing and Customer Information System", "code": "UNIV-DIST-03", "category": "system", "dept": depts["DIST"], "risk": 4.60, "freq": "Annually"},
            {"name": "Human Resources Payroll Administration", "code": "UNIV-HR-04", "category": "process", "dept": depts["HR"], "risk": 3.10, "freq": "Bi-annually"},
            {"name": "Substation Security Controls", "code": "UNIV-DIST-05", "category": "department", "dept": depts["DIST"], "risk": 2.80, "freq": "Tri-annually"},
        ]
        universe = []
        for uni in universe_data:
            entry, created = AuditUniverse.objects.get_or_create(
                code=uni["code"],
                defaults={
                    "name": uni["name"],
                    "category": uni["category"],
                    "department": uni["dept"],
                    "risk_score": uni["risk"],
                    "audit_frequency": uni["freq"],
                    "owner": uni["dept"].head,
                    "status": "active"
                }
            )
            universe.append(entry)
            if created:
                self.stdout.write(f"Created Universe item: {entry.name}")

        # 6. Create Audit Plan
        current_year = datetime.datetime.now().year
        plan = AuditPlan.objects.filter(year=current_year, title__startswith="EEU Annual Audit Plan").first()
        if not plan:
            plan = AuditPlan.objects.create(
                year=current_year,
                title=f"EEU Annual Audit Plan {current_year}",
                description=f"Annual risk-based audit plan focusing on financial automation, critical utility procurement, and customer billing controls.",
                objectives="To evaluate internal controls, confirm compliance with energy regulations, and identify operational cost efficiencies.",
                scope="All departments, power distribution grids, and information systems belonging to EEU.",
                methodology="COSO Internal Control Framework, risk-based sampling, and remote data analytics.",
                status="approved",
                created_by=users[Role.AUDIT_MANAGER],
                approved_by=users[Role.AUDIT_MANAGER],
                approved_at=timezone.now(),
                start_date=datetime.date(current_year, 1, 1),
                end_date=datetime.date(current_year, 12, 31),
                total_budget_days=180
            )
            self.stdout.write(f"Created Audit Plan: {plan.title}")

        # 7. Create Engagements
        eng_data = [
            {
                "title": "ERP System Security and Financial Controls Audit",
                "number": f"ENG-{current_year}-001",
                "type": "it",
                "dept": depts["IT"],
                "universe": universe[0],
                "status": "in_progress",
                "risk": "high",
            },
            {
                "title": "Procurement of High-Voltage Cables & Substation Equipments",
                "number": f"ENG-{current_year}-002",
                "type": "compliance",
                "dept": depts["PROC"],
                "universe": universe[1],
                "status": "fieldwork",
                "risk": "critical",
            },
            {
                "title": "Billing System Revenue Reconciliation Audit",
                "number": f"ENG-{current_year}-003",
                "type": "operational",
                "dept": depts["DIST"],
                "universe": universe[2],
                "status": "planned",
                "risk": "high",
            }
        ]

        engagements = []
        for ed in eng_data:
            eng, created = AuditEngagement.objects.get_or_create(
                engagement_number=ed["number"],
                defaults={
                    "plan": plan,
                    "audit_universe": ed["universe"],
                    "title": ed["title"],
                    "engagement_type": ed["type"],
                    "department": ed["dept"],
                    "status": ed["status"],
                    "lead_auditor": users[Role.AUDITOR],
                    "supervisor": users[Role.SUPERVISOR],
                    "planned_start": datetime.date(current_year, 4, 1),
                    "planned_end": datetime.date(current_year, 7, 30),
                    "planned_days": 45,
                    "risk_level": ed["risk"],
                }
            )
            engagements.append(eng)
            if created:
                self.stdout.write(f"Created Engagement: {eng.title}")
                # Assign team members
                AuditTeamMember.objects.get_or_create(engagement=eng, user=users[Role.AUDITOR], defaults={"role": "lead", "allocated_days": 30})
                AuditTeamMember.objects.get_or_create(engagement=eng, user=users[Role.SUPERVISOR], defaults={"role": "supervisor", "allocated_days": 15})

        # 8. Create Audit Program and Procedures for the IT security audit
        prog, created = AuditProgram.objects.get_or_create(
            engagement=engagements[0],
            defaults={
                "title": "ERP Security Program",
                "objectives": "Program to audit access controls, change management, and user permissions segregation of duties (SoD) inside the main ERP database.",
                "scope": "All modules of the Oracle ERP system at EEU HQ including database permissions.",
                "status": "approved",
                "prepared_by": users[Role.AUDITOR],
                "reviewed_by": users[Role.SUPERVISOR],
                "approved_by": users[Role.SUPERVISOR],
                "approved_at": timezone.now(),
            }
        )
        if created:
            self.stdout.write(f"Created Audit Program for ERP")
            
            # Procedures
            proc1 = AuditProcedure.objects.create(
                program=prog,
                step_number="PROC-001",
                title="Review Segregation of Duties (SoD) matrix",
                description="Obtain the current user-role matrix and check if any accounts have conflicting privileges (e.g. initiating and approving payments).",
                status="completed",
                completed_by=users[Role.AUDITOR],
                completed_at=timezone.now() - datetime.timedelta(days=5),
                order=1
            )
            proc2 = AuditProcedure.objects.create(
                program=prog,
                step_number="PROC-002",
                title="Audit Database login attempts & password strength settings",
                description="Inspect the core ERP database parameters for locked accounts, brute-force security, and minimum password entropy.",
                status="in_progress",
                completed_by=None,
                order=2
            )
            proc3 = AuditProcedure.objects.create(
                program=prog,
                step_number="PROC-003",
                title="Inspect ERP Backup and Disaster Recovery (DR) verification logs",
                description="Verify that weekly restoration tests are conducted and documented for offsite data recovery procedures.",
                status="pending",
                order=3
            )

        # 9. Create a Sample Audit Finding
        finding, created = AuditFinding.objects.get_or_create(
            engagement=engagements[0],
            finding_number="FIND-001",
            defaults={
                "title": "Unauthorized Segregation of Duties Violations in ERP Accounts Payable",
                "description": "It was discovered that three senior database admins possess both payment creation and approval rights, violating basic internal checks.",
                "severity": "high",
                "criteria": "EEU IT Security Policy Article 4.2 states that developers and DBAs must not hold administrative business transactions access.",
                "condition": "Accounts department personnel and DBAs share administrative roles that override transaction blocks.",
                "effect": "Increased risk of fraudulent payments being injected directly into the database without manager check-offs.",
                "cause": "Absence of a quarterly system role review and lack of dynamic workflow blocks at the application tier.",
                "status": "draft",
                "identified_by": users[Role.AUDITOR],
            }
        )
        if created:
            self.stdout.write(f"Created Finding: {finding.title}")
            
            # Create corrective action
            CorrectiveAction.objects.create(
                finding=finding,
                action_number="CAPA-001",
                title="Segregate Admin and Transactional Privileges",
                description="Ensure DBA accounts are restricted to schema management and database maintenance. Remove transactional posting roles from admins.",
                recommendation="Perform an absolute segregation of system admin privileges; remove transactional payment authorization from DBAs immediately.",
                owner=users[Role.AUDITEE],  # Auditee owner
                due_date=datetime.date(current_year, 9, 30),
                status="open",
            )

        # 10. System settings and templates
        ReportTemplate.objects.get_or_create(
            name="EEU Standard Audit Report Template",
            defaults={
                "template_type": "engagement",
                "description": "Default multi-page executive audit report format including background, executive summary, risk analysis, findings table, and CAPA.",
                "is_default": True
            }
        )
        SystemSetting.objects.get_or_create(
            key="enable_email_alerts",
            defaults={"value": "True", "description": "Enable automated emails on corrective actions status changes."}
        )

        self.stdout.write(self.style.SUCCESS("Demo database successfully seeded!"))
