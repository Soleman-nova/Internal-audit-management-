"""
Demo Case Seed — one audit case, checkpointed so the workflow can be shown live.

Why this exists
---------------
``seed_e2e_demo`` seeds a single lifecycle with every stage already marked
``completed``/``closed`` — a finished case, nothing left to do. This command
seeds the SAME single case up to a chosen checkpoint and stops, so a presenter
can walk an end-user through the workflow live, role by role, from entity
creation through to report generation:

    Stage 0  Admin       → users, audit trail            (config + case support)
    Stage 1  Manager     → entity in the Audit Universe  (pre-seeded, narrated)
    Stage 2  Manager/    → risk assessment + auditee self-assessment
             Auditee                                        (pre-seeded, narrated)
    Stage 3  Manager     → annual plan approved          (pre-seeded, narrated)
    Stage 4  Manager     → engagement + team assigned    (pre-seeded, narrated)
    --------------------------------------------------------- checkpoint ------
    Stage 5  Auditor     → program, procedures, fieldwork          ⬅ live
    Stage 6  Supervisor  → approve program, review working papers  ⬅ live
    Stage 7  Auditor     → log findings                            ⬅ live
    Stage 8  Auditee     → respond, comment, upload evidence       ⬅ live
    Stage 9  Auditor     → spawn CAPAs                             ⬅ live
    Stage 10 Auditee     → CAPA responses                          ⬅ live
    Stage 11 Supervisor  → verify & close CAPAs                    ⬅ live
    Stage 12 Auditor/    → generate + download report              ⬅ live
             Manager

Checkpoints (--to)
------------------
    universe    — supporting config + the demo entity in the Audit Universe.
                  Presenter creates risk → plan → engagement → … live.
    plan        — … + risk assessment (auditee self-assessment reviewed) and an
                  approved annual plan. Presenter schedules the engagement live.
    engagement  — DEFAULT. … + the engagement scheduled with lead auditor and
                  supervisor assigned. Presenter performs fieldwork → findings →
                  CAPA → report live. This is the recommended demo setup.

Re-runnable: every row belonging to the DEMO case (codes/numbers/titles prefixed
``DEMO-`` / ``DEMO ``) is removed first, so the command can be run again to
reset a demonstration without wiping the rest of the database.

Run:  python manage.py seed_demo_case              # checkpoint: engagement
      python manage.py seed_demo_case --to plan    # stop after plan approval
      python manage.py seed_demo_case --to universe
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
from apps.findings.models import AuditFinding
from apps.corrective_actions.models import CorrectiveAction
from apps.reports.models import ReportTemplate, GeneratedReport
from apps.notifications.models import Notification, SystemSetting

CHECKPOINTS = ('universe', 'plan', 'engagement')


class Command(BaseCommand):
    help = ('Seeds a single DEMO audit case up to a chosen checkpoint so the '
            'audit workflow can be demonstrated live, role by role.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            choices=CHECKPOINTS,
            default='engagement',
            help='How far to seed the case before stopping (default: engagement).',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 70))
        self.stdout.write(self.style.MIGRATE_HEADING('  EEU DEMO CASE — checkpoint seed'))
        self.stdout.write(self.style.MIGRATE_HEADING('=' * 70))

        self._cleanup_demo_case()
        self.stdout.write(self.style.NOTICE('  ✓ removed any previous DEMO case'))

        now = timezone.now()
        current_year = now.year

        # ── Stage 0: users, departments, roles, config ─────────────────────
        self.stdout.write('\n[Stage 0] Ensuring users, departments & config exist...')
        dept_proc, _ = Department.objects.get_or_create(
            code='PROC',
            defaults={
                'name': 'Procurement and Logistics',
                'name_am': 'ግዢ እና ሎጂስቲክስ',
                'head': 'Daniel Tekle',
            },
        )
        dept_fin, _ = Department.objects.get_or_create(
            code='FIN',
            defaults={
                'name': 'Finance and Accounts',
                'name_am': 'ፋይናንስ እና ሒሳብ',
                'head': 'Abebe Kebede',
            },
        )
        for name, label in Role.ROLE_CHOICES:
            Role.objects.get_or_create(
                name=name,
                defaults={'description': f'Default {label} Role', 'permissions': {}},
            )

        manager = self._ensure_user(
            email='manager@eeu.com', username='manager', first_name='Martha',
            last_name='Hailu', role=Role.AUDIT_MANAGER, department=dept_fin,
            employee_id='EEU-10002',
        )
        supervisor = self._ensure_user(
            email='supervisor@eeu.com', username='supervisor', first_name='Bekele',
            last_name='Dejene', role=Role.SUPERVISOR, department=dept_fin,
            employee_id='EEU-10003',
        )
        auditor = self._ensure_user(
            email='auditor@eeu.com', username='auditor', first_name='Tsion',
            last_name='Girma', role=Role.AUDITOR, department=dept_fin,
            employee_id='EEU-10004',
        )
        auditee = self._ensure_user(
            email='auditee@eeu.com', username='auditee', first_name='Kidus',
            last_name='Yosef', role=Role.AUDITEE, department=dept_proc,
            employee_id='EEU-10005',
        )
        self.stdout.write(
            '  ✓ Manager / Supervisor / Auditor / Auditee ready '
            '(passwords user123; admin admin123)'
        )

        for rp in (
            {'name': 'Financial Impact', 'description': 'Potential monetary loss', 'weight': 0.30, 'category': 'financial'},
            {'name': 'Operational Disruption', 'description': 'Interruption to services', 'weight': 0.25, 'category': 'operational'},
            {'name': 'Compliance Violations', 'description': 'Regulatory exposure', 'weight': 0.20, 'category': 'compliance'},
            {'name': 'Process Complexity', 'description': 'Control complexity', 'weight': 0.15, 'category': 'operational'},
            {'name': 'System Automation', 'description': 'Manual process reliance', 'weight': 0.10, 'category': 'it'},
        ):
            RiskParameter.objects.get_or_create(name=rp['name'], defaults=rp)

        template, _ = ReportTemplate.objects.get_or_create(
            name='EEU Standard Audit Report Template',
            defaults={
                'template_type': 'engagement',
                'description': 'Default multi-page executive audit report format '
                               'including background, executive summary, risk '
                               'analysis, findings table, and CAPA.',
                'is_default': True,
            },
        )
        SystemSetting.objects.get_or_create(
            key='enable_email_alerts',
            defaults={'value': 'True', 'description': 'Enable automated emails '
                      'on corrective action status changes.'},
        )

        # ── Stage 1: entity in the Audit Universe ──────────────────────────
        self.stdout.write('\n[Stage 1] Audit Universe entity (pre-seeded)...')
        universe, created = AuditUniverse.objects.get_or_create(
            code='DEMO-PROC-01',
            defaults={
                'name': 'Distribution Transformer Procurement & Stock Control',
                'category': 'process',
                'department': dept_proc,
                'description': 'End-to-end procurement of distribution transformers, '
                               'inward inspection, warehousing, and issue-to-site '
                               'stock control across EEU stores.',
                'risk_score': 4.60,
                'audit_frequency': 'Annually',
                'owner': dept_proc.head,
                'status': 'active',
                'last_audited': now.date() - datetime.timedelta(days=400),
            },
        )
        self._log_audit(manager, 'CREATE', universe, 'DEMO: entity added to the Audit Universe')

        if options['to'] == 'universe':
            self._summary(options['to'], universe=universe)
            return

        # ── Stage 2: risk assessment + auditee self-assessment ─────────────
        self.stdout.write('\n[Stage 2] Risk assessment & self-assessment (pre-seeded)...')
        risk_assessment, _ = RiskAssessment.objects.get_or_create(
            department=dept_proc,
            year=current_year,
            assessment_period='Annual',
            defaults={
                'audit_universe': universe,
                'likelihood': 4,
                'impact': 5,
                'control_effectiveness': 2,
                'notes': 'Annual risk assessment for transformer procurement. High '
                         'likelihood of stock-loss and contract-bypass given manual '
                         'stores records and weak vendor vetting.',
                'assessed_by': manager,
                'reviewed_by': manager,
            },
        )
        SelfAssessment.objects.get_or_create(
            risk_assessment=risk_assessment,
            defaults={
                'submitted_by': auditee,
                'status': 'reviewed',
                'likelihood_self': 3,
                'impact_self': 4,
                'control_effectiveness_self': 3,
                'justification': 'Procurement has documented procedures but stores '
                                 'issuing is paper-based and vendor checks vary by team.',
                'mitigating_controls': 'Tender committee review above 500,000 ETB; '
                                       'dual-signature on store release vouchers.',
                'reviewer_notes': 'Self-assessment aligns with the audit team view. '
                                  'Control effectiveness rated lower after recent '
                                  'warehouse staff turnover.',
                'reviewed_by': manager,
                'reviewed_at': now - datetime.timedelta(days=25),
            },
        )
        self._log_audit(manager, 'CREATE', risk_assessment, 'DEMO: risk assessment finalised')
        self._log_audit(auditee, 'CREATE', risk_assessment, 'DEMO: auditee self-assessment submitted')
        self._log_audit(manager, 'APPROVE', risk_assessment, 'DEMO: self-assessment reviewed')

        # ── Stage 3: annual plan created, submitted and approved ────────────
        self.stdout.write('\n[Stage 3] Annual audit plan (approved, pre-seeded)...')
        plan, _ = AuditPlan.objects.get_or_create(
            year=current_year,
            title=f'DEMO Annual Audit Plan {current_year}',
            defaults={
                'description': 'Annual risk-based plan covering transformer '
                               'procurement, stock control, and finance. Fully '
                               'approved ahead of the demonstration.',
                'objectives': 'Evaluate procurement and stock controls; verify '
                              'compliance with EEU stores regulations; identify '
                              'loss and fraud risks.',
                'scope': 'Transformer procurement, inward inspection, warehouse '
                         'stock and issue-to-site within EEU stores.',
                'methodology': 'COSO Internal Control Framework, risk-based '
                               'sampling, and substantive testing.',
                'status': 'approved',
                'created_by': manager,
                'approved_by': manager,
                'approved_at': now - datetime.timedelta(days=40),
                'start_date': datetime.date(current_year, 1, 1),
                'end_date': datetime.date(current_year, 12, 31),
                'total_budget_days': 90,
            },
        )
        self._log_audit(manager, 'CREATE', plan, 'DEMO: annual plan created & submitted')
        self._log_audit(manager, 'APPROVE', plan, 'DEMO: annual plan approved')

        if options['to'] == 'plan':
            self._summary(options['to'], universe=universe, plan=plan,
                          risk_assessment=risk_assessment)
            return

        # ── Stage 4: engagement scheduled and staffed ───────────────────────
        self.stdout.write('\n[Stage 4] Engagement & team (pre-seeded)...')
        engagement, _ = AuditEngagement.objects.get_or_create(
            engagement_number=f'DEMO-ENG-{current_year}-001',
            defaults={
                'plan': plan,
                'audit_universe': universe,
                'title': 'Distribution Transformer Procurement & Stock Control Audit',
                'engagement_type': 'compliance',
                'department': dept_proc,
                'objectives': 'Assess procurement compliance, stores inward '
                              'inspection, stock recording, and issue controls.',
                'scope': 'All transformer purchase orders above 100,000 ETB for the '
                         'current fiscal year, including tenders, inward '
                         'inspection, and store issue vouchers.',
                'status': 'fieldwork',
                'lead_auditor': auditor,
                'supervisor': supervisor,
                'planned_start': datetime.date(current_year, 3, 1),
                'planned_end': datetime.date(current_year, 5, 30),
                'planned_days': 60,
                'risk_level': 'critical',
            },
        )
        AuditTeamMember.objects.get_or_create(
            engagement=engagement, user=auditor,
            defaults={'role': 'lead', 'allocated_days': 40},
        )
        AuditTeamMember.objects.get_or_create(
            engagement=engagement, user=supervisor,
            defaults={'role': 'supervisor', 'allocated_days': 15},
        )
        self._log_audit(manager, 'CREATE', engagement, 'DEMO: engagement scheduled & staffed')
        self._notify(auditor, 'assigned', '[DEMO] Engagement Assignment',
                     f'You are the Lead Auditor for "{engagement.title}".')
        self._notify(supervisor, 'assigned', '[DEMO] Supervision Assignment',
                     f'You are the Supervisor for "{engagement.title}".')

        self._summary(options['to'], universe=universe, plan=plan,
                      risk_assessment=risk_assessment, engagement=engagement)

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _cleanup_demo_case(self):
        """Remove any rows belonging to a previous DEMO case, leaves-first."""
        demo_engs = AuditEngagement.objects.filter(
            engagement_number__startswith='DEMO-')
        demo_eng_ids = list(demo_engs.values_list('id', flat=True))
        demo_univs = AuditUniverse.objects.filter(code__startswith='DEMO-')
        demo_univ_ids = list(demo_univs.values_list('id', flat=True))
        demo_plans = AuditPlan.objects.filter(title__startswith='DEMO ')

        CorrectiveAction.objects.filter(finding__engagement_id__in=demo_eng_ids).delete()
        AuditFinding.objects.filter(engagement_id__in=demo_eng_ids).delete()
        WorkingPaper.objects.filter(engagement_id__in=demo_eng_ids).delete()
        AuditProcedure.objects.filter(program__engagement_id__in=demo_eng_ids).delete()
        AuditProgram.objects.filter(engagement_id__in=demo_eng_ids).delete()
        GeneratedReport.objects.filter(engagement_id__in=demo_eng_ids).delete()
        AuditTeamMember.objects.filter(engagement_id__in=demo_eng_ids).delete()
        demo_engs.delete()
        demo_plans.delete()
        RiskAssessment.objects.filter(audit_universe_id__in=demo_univ_ids).delete()
        demo_univs.delete()
        Notification.objects.filter(title__startswith='[DEMO]').delete()
        AuditTrail.objects.filter(changes__demo_case=True).delete()

    @staticmethod
    def _ensure_user(email, username, first_name, last_name, role, department,
                     employee_id):
        """Create the demo user, or re-pin an existing one.

        ``get_or_create`` alone is not enough: the legacy department tree was
        retired at some point and existing demo accounts may hold
        ``department=NULL``, which hides every department-scoped record (the
        auditee's view of the demo engagement relies on being in PROC).
        """
        user, _ = User.objects.update_or_create(
            email=email,
            defaults={
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'role': role,
                'department': department,
                'employee_id': employee_id,
                'is_active': True,
            },
        )
        if not user.has_usable_password():
            user.set_password('admin123' if role == Role.ADMIN else 'user123')
            user.save()
        return user

    def _log_audit(self, user, action, instance, description=''):
        ct = ContentType.objects.get_for_model(instance)
        AuditTrail.objects.create(
            user=user,
            action=action,
            model_name=instance._meta.model_name,
            object_id=str(instance.pk),
            object_repr=description or str(instance),
            changes={'demo_case': True, 'description': description},
            ip_address='127.0.0.1',
            user_agent='Demo-Case-Seed/1.0',
        )

    def _notify(self, user, ntype, title, message, link=''):
        Notification.objects.create(
            user=user,
            notification_type=ntype,
            title=title,
            message=message,
            link=link,
            is_read=False,
        )

    def _summary(self, checkpoint, universe=None, plan=None,
                 risk_assessment=None, engagement=None):
        now = timezone.now()
        current_year = now.year
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('  DEMO CASE READY — checkpoint: ' + checkpoint))
        self.stdout.write('=' * 70)

        lines = [
            'Pre-seeded:',
            f'  • Entity in Audit Universe: {universe.name} ({universe.code})'
            if universe else '',
            f'  • Risk assessment: score {risk_assessment.risk_score}, '
            f'rating {risk_assessment.risk_rating} (self-assessment reviewed)'
            if risk_assessment else '',
            f'  • Annual plan: {plan.title} (approved)' if plan else '',
            f'  • Engagement: {engagement.engagement_number} — {engagement.title} '
            f'(status={engagement.status}, lead + supervisor assigned)'
            if engagement else '',
        ]
        self.stdout.write('\n'.join(line for line in lines if line))

        todo = {
            'universe': 'Create the risk assessment → annual plan → engagement, '
                        'then continue from the fieldwork stage.',
            'plan': 'Schedule the engagement and assign the team, then continue '
                    'from the fieldwork stage.',
            'engagement': 'Continue live: auditor builds the program & procedures, '
                          'supervisor approves, findings, CAPA, and report.',
        }[checkpoint]
        self.stdout.write(f'\nNext ({todo})')

        self.stdout.write(self.style.NOTICE(
            '\nSee DEMO.md for the full role-by-role walkthrough.'
        ))
