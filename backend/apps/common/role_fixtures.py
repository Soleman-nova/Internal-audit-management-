"""Shared fixtures for the API test suites.

Every app's suite needs the same five users — one per role — and every suite
loops the same request across all five to assert the capability matrix in
``ROLE_CAPABILITIES``. Building that in one place keeps each per-app suite about
the app rather than about user creation, and means the matrix documented in
TESTING.md is asserted the same way everywhere.

Not named ``test_*``/``testing`` on purpose: Django's discovery pattern is
``test*.py``, and a helper module that gets imported as a test module is a
confusing place for an import error to surface.
"""
import itertools

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role

User = get_user_model()

# Every role, in descending order of privilege. Suites iterate this so a new
# role added to the matrix shows up as a failing assertion rather than as a
# silently untested one.
ALL_ROLES = (
    Role.ADMIN, Role.AUDIT_MANAGER, Role.SUPERVISOR, Role.AUDITOR, Role.AUDITEE,
)

# Process-wide counter for the unique columns (codes, references, numbers).
# Factories are called from setUpTestData *and* from individual tests, so the
# counter has to be wider than any one test class.
_counter = itertools.count(1)


def next_seq():
    """Next value of the process-wide uniqueness counter."""
    return next(_counter)


class RoleFixtureMixin:
    """Adds five users — one per role — plus two departments and a client.

    Rows are created in ``setUpTestData`` so they are built once per class and
    rolled back per test; these suites make a lot of requests and per-test user
    creation (five ``create_user`` password hashes) dominated the runtime.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        seq = next_seq()
        cls.department = Department.objects.create(
            name=f'Finance {seq}', code=f'FIN-{seq}',
        )
        # A second department for the read-scoping tests: "an auditee elsewhere
        # in EEU" is the case that proves scoping actually filters.
        cls.other_department = Department.objects.create(
            name=f'Operations {seq}', code=f'OPS-{seq}',
        )
        cls.users = {}
        for index, role in enumerate(ALL_ROLES, start=1):
            cls.users[role] = User.objects.create_user(
                username=f'{role}-{seq}',
                employee_id=f'T{seq}-{index}',
                email=f'{role}-{seq}@test.com',
                password='pass',
                first_name=role.replace('_', ' ').title(),
                last_name='User',
                role=role,
                department=cls.department,
            )
        cls.admin = cls.users[Role.ADMIN]
        cls.manager = cls.users[Role.AUDIT_MANAGER]
        cls.supervisor = cls.users[Role.SUPERVISOR]
        cls.auditor = cls.users[Role.AUDITOR]
        cls.auditee = cls.users[Role.AUDITEE]

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    # ── Helpers ──────────────────────────────────────────────────────────
    def as_user(self, user):
        """Point the shared client at ``user`` and hand it back."""
        self.client.force_authenticate(user=user)
        return self.client

    def make_user(self, role, department=None, **kwargs):
        """An extra user beyond the five — a second auditor, an auditee in
        another department, someone with no department at all."""
        seq = next_seq()
        defaults = {
            'username': f'{role}-extra-{seq}',
            'employee_id': f'X{seq}',
            'email': f'{role}-extra-{seq}@test.com',
            'password': 'pass',
            'first_name': role.replace('_', ' ').title(),
            'last_name': f'Extra{seq}',
            'role': role,
            'department': department,
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    def assert_status_by_role(self, expected, make_request, msg=''):
        """Run one request per role and compare status codes.

        ``expected`` maps role -> status code; ``make_request(client, role)``
        performs the call. Passing the role through lets the caller vary unique
        fields per role, which matters for create tests where five roles would
        otherwise collide on the same ``code``.

        Every role in ``ALL_ROLES`` must appear in ``expected`` — a partially
        filled table is the failure mode this whole helper exists to prevent.
        """
        missing = set(ALL_ROLES) - set(expected)
        self.assertFalse(missing, f'No expectation given for role(s): {sorted(missing)}')
        for role, code in expected.items():
            with self.subTest(role=role, case=msg):
                response = make_request(self.as_user(self.users[role]), role)
                self.assertEqual(
                    response.status_code, code,
                    f'{role}: expected {code}, got {response.status_code} '
                    f'({getattr(response, "data", None)})',
                )


# ── Domain factories ────────────────────────────────────────────────────
# Enough of the plan -> engagement -> program -> procedure -> finding -> CAPA
# chain to reach any endpoint. Each factory fills only the columns the database
# requires plus the ones the tests assert on, so a test that cares about, say,
# `due_date` sets it explicitly and reads as if it were the only thing there.

def make_universe(department=None, **kwargs):
    from apps.audit_planning.models import AuditUniverse

    seq = next_seq()
    defaults = {
        'name': f'Universe Entry {seq}',
        'code': f'UNV-{seq:05d}',
        'category': 'process',
        'risk_score': 3,
        'audit_frequency': 'Annually',
        'status': 'active',
        'department': department,
    }
    defaults.update(kwargs)
    return AuditUniverse.objects.create(**defaults)


def make_plan(created_by=None, **kwargs):
    from apps.audit_planning.models import AuditPlan

    seq = next_seq()
    defaults = {
        'title': f'Annual Audit Plan {seq}',
        'year': timezone.now().year,
        'created_by': created_by,
    }
    defaults.update(kwargs)
    return AuditPlan.objects.create(**defaults)


def make_engagement(plan=None, lead_auditor=None, **kwargs):
    from apps.audit_planning.models import AuditEngagement

    seq = next_seq()
    defaults = {
        'plan': plan or make_plan(created_by=lead_auditor),
        'title': f'Engagement {seq}',
        'engagement_number': f'ENG-{seq:05d}',
        'engagement_type': 'financial',
        'lead_auditor': lead_auditor,
    }
    defaults.update(kwargs)
    return AuditEngagement.objects.create(**defaults)


def make_program(engagement=None, prepared_by=None, **kwargs):
    from apps.audit_execution.models import AuditProgram

    seq = next_seq()
    defaults = {
        # AuditProgram.engagement is a OneToOne, so a fresh engagement per
        # program unless the caller supplies one.
        'engagement': engagement or make_engagement(lead_auditor=prepared_by),
        'title': f'Audit Program {seq}',
        'prepared_by': prepared_by,
    }
    defaults.update(kwargs)
    return AuditProgram.objects.create(**defaults)


def make_procedure(program=None, **kwargs):
    from apps.audit_execution.models import AuditProcedure

    seq = next_seq()
    defaults = {
        'program': program or make_program(),
        'step_number': str(seq),
        'title': f'Procedure {seq}',
        'description': 'Inspect the supporting documentation.',
        'procedure_type': 'substantive',
    }
    defaults.update(kwargs)
    return AuditProcedure.objects.create(**defaults)


def make_finding(engagement=None, identified_by=None, **kwargs):
    from apps.findings.models import AuditFinding

    seq = next_seq()
    defaults = {
        'engagement': engagement or make_engagement(lead_auditor=identified_by),
        'finding_number': f'FND-{seq:05d}',
        'title': f'Finding {seq}',
        'description': 'Controls over the process were not operating.',
        'severity': 'high',
        'category': 'control_deficiency',
        'status': 'open',
        'identified_by': identified_by,
    }
    defaults.update(kwargs)
    return AuditFinding.objects.create(**defaults)


def make_action(finding=None, owner=None, assigned_by=None, **kwargs):
    from apps.corrective_actions.models import CorrectiveAction

    seq = next_seq()
    defaults = {
        'finding': finding or make_finding(identified_by=assigned_by),
        'action_number': f'CAPA-{seq:05d}',
        'title': f'Corrective Action {seq}',
        'description': 'Reinstate the control and evidence its operation.',
        'recommendation': 'Document and test the control monthly.',
        'owner': owner,
        'assigned_by': assigned_by,
        'status': 'open',
        'priority': 'medium',
        'due_date': timezone.now().date() + timezone.timedelta(days=30),
    }
    defaults.update(kwargs)
    return CorrectiveAction.objects.create(**defaults)


def make_risk_assessment(department=None, assessed_by=None, **kwargs):
    from apps.risk_assessment.models import RiskAssessment

    defaults = {
        'department': department,
        'year': timezone.now().year,
        'assessment_period': 'Annual',
        'likelihood': 4,
        'impact': 4,
        'control_effectiveness': 3,
        'assessed_by': assessed_by,
    }
    defaults.update(kwargs)
    return RiskAssessment.objects.create(**defaults)


def make_self_assessment(risk_assessment=None, submitted_by=None, **kwargs):
    from apps.risk_assessment.models import SelfAssessment

    defaults = {
        'risk_assessment': risk_assessment,
        'submitted_by': submitted_by,
        'status': 'submitted',
        'likelihood_self': 3,
        'impact_self': 3,
        'control_effectiveness_self': 3,
        'justification': 'Controls are documented and operating.',
    }
    defaults.update(kwargs)
    return SelfAssessment.objects.create(**defaults)


def notification_titles(user):
    """Notification titles for ``user``, newest first — handy for assertions."""
    from apps.notifications.models import Notification

    return list(Notification.objects.filter(user=user).values_list('title', flat=True))
