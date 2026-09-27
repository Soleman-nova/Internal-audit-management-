"""Read-scoping for the auditee role, register by register.

Reads are open to every authenticated user by design — `HasCapability` allows all
safe methods unconditionally (`apps/common/permissions.py`) — so a ViewSet's
*queryset* is the only thing standing between an auditee and an org-wide register.
For most roles that is the right default. The auditee is the exception: they are
the party being assessed, so the EEU-wide view tells them things that are not
theirs to know — which entities are rated high risk and therefore audited next,
other directorates' scores, and the audit team's own working papers.

These tests pin that per register: the auditee sees their own department's rows and
none from another department, while an auditor still sees both.

They check the **list and the retrieve** deliberately. A scoped list with an
unscoped detail route is the easy half-fix to ship by accident, and it leaks the
same data one id at a time.
"""
from django.test import TestCase

from apps.accounts.models import Role
from apps.audit_execution.models import WorkingPaper
from apps.audit_planning.models import Project
from apps.reports.models import GeneratedReport

from .role_fixtures import (
    RoleFixtureMixin,
    make_engagement,
    make_plan,
    make_procedure,
    make_program,
    make_risk_assessment,
    make_universe,
)

PLANNING = '/api/planning'
EXECUTION = '/api/execution'
REPORTS = '/api/reports'
RISK = '/api/risk'


def ids_on(response):
    """Row ids from a DRF response, paginated or not."""
    data = response.data
    rows = data['results'] if isinstance(data, dict) else data
    return {row['id'] for row in rows}


class AuditeeReadScopingTest(RoleFixtureMixin, TestCase):
    """One register per test, each asserting the same three things."""

    def assert_isolated(self, url, mine_id, theirs_id):
        """`mine_id` is visible to the auditee; `theirs_id` is not.

        Then the reverse control: an auditor must still see both, so this cannot
        pass by the endpoint simply being broken for everyone.
        """
        seen = ids_on(self.as_user(self.auditee).get(url))
        self.assertIn(mine_id, seen, f'auditee lost their own row from {url}')
        self.assertNotIn(theirs_id, seen, f'auditee can see another department at {url}')

        auditor_seen = ids_on(self.as_user(self.auditor).get(url))
        self.assertIn(mine_id, auditor_seen)
        self.assertIn(theirs_id, auditor_seen, f'auditor lost sight of {url}')

        # The detail route has to narrow with the list, not around it.
        self.assertEqual(
            self.as_user(self.auditee).get(f'{url}{theirs_id}/').status_code, 404,
        )

    # ── Planning ─────────────────────────────────────────────────────────

    def test_audit_universe_is_scoped(self):
        mine = make_universe(department=self.department)
        theirs = make_universe(department=self.other_department)
        self.assert_isolated(f'{PLANNING}/universe/', mine.id, theirs.id)

    def test_projects_are_scoped(self):
        mine = Project.objects.create(
            code='PRJ-MINE', name='Substation upgrade', department=self.department,
        )
        theirs = Project.objects.create(
            code='PRJ-THEIRS', name='Line extension', department=self.other_department,
        )
        self.assert_isolated(f'{PLANNING}/projects/', mine.id, theirs.id)

    def test_plans_are_scoped_through_their_engagements(self):
        """`AuditPlan` carries no department, so the scope runs through the
        engagements it contains — the only place the owning unit is recorded."""
        mine = make_plan(created_by=self.auditor)
        make_engagement(plan=mine, lead_auditor=self.auditor, department=self.department)
        theirs = make_plan(created_by=self.auditor)
        make_engagement(
            plan=theirs, lead_auditor=self.auditor, department=self.other_department,
        )
        self.assert_isolated(f'{PLANNING}/plans/', mine.id, theirs.id)

    # ── Execution ────────────────────────────────────────────────────────

    def test_programs_are_scoped(self):
        mine = make_program(
            engagement=make_engagement(lead_auditor=self.auditor, department=self.department),
            prepared_by=self.auditor,
        )
        theirs = make_program(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.other_department,
            ),
            prepared_by=self.auditor,
        )
        self.assert_isolated(f'{EXECUTION}/programs/', mine.id, theirs.id)

    def test_procedures_are_scoped(self):
        """Two hops: procedure -> program -> engagement -> department."""
        mine = make_procedure(program=make_program(
            engagement=make_engagement(lead_auditor=self.auditor, department=self.department),
        ))
        theirs = make_procedure(program=make_program(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.other_department,
            ),
        ))
        self.assert_isolated(f'{EXECUTION}/procedures/', mine.id, theirs.id)

    def test_working_papers_are_scoped(self):
        """The most sensitive register: the documented basis for the findings
        against the auditee, covering engagements they may not be part of."""
        mine = WorkingPaper.objects.create(
            engagement=make_engagement(lead_auditor=self.auditor, department=self.department),
            reference='WP-MINE', title='Reconciliation', prepared_by=self.auditor,
        )
        theirs = WorkingPaper.objects.create(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.other_department,
            ),
            reference='WP-THEIRS', title='Fixed asset count', prepared_by=self.auditor,
        )
        self.assert_isolated(f'{EXECUTION}/working-papers/', mine.id, theirs.id)

    # ── Reports & risk ───────────────────────────────────────────────────

    def test_generated_reports_are_scoped(self):
        mine = GeneratedReport.objects.create(
            title='Mine', format='pdf', generated_by=self.auditor,
            engagement=make_engagement(lead_auditor=self.auditor, department=self.department),
        )
        theirs = GeneratedReport.objects.create(
            title='Theirs', format='pdf', generated_by=self.auditor,
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.other_department,
            ),
        )
        self.assert_isolated(f'{REPORTS}/generated/', mine.id, theirs.id)

    def test_risk_assessments_are_scoped(self):
        mine = make_risk_assessment(department=self.department, assessed_by=self.auditor)
        theirs = make_risk_assessment(department=self.other_department, assessed_by=self.auditor)
        self.assert_isolated(f'{RISK}/assessments/', mine.id, theirs.id)

    # ── The edges of the rule ────────────────────────────────────────────

    def test_an_auditee_with_no_department_sees_no_org_wide_rows(self):
        """The `AuditeeScopeMixin` fallback, department half.

        With no department there is no department clause to match on, and
        `AuditUniverse` names no individual — so the register comes back empty
        rather than fully visible. The other reading of a missing department,
        "no restriction", turns a data gap into a disclosure, which is why the
        mixin returns `none()` instead of the unfiltered queryset.
        """
        landless = self.make_user(Role.AUDITEE, department=None)
        make_universe(department=self.department)

        response = self.as_user(landless).get(f'{PLANNING}/universe/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ids_on(response), set())

    def test_a_named_auditee_keeps_their_own_rows_without_a_department(self):
        """The fallback's other half: the *personal* branch still applies, so work
        an auditee is named on stays reachable with no department at all."""
        landless = self.make_user(Role.AUDITEE, department=None)
        mine = WorkingPaper.objects.create(
            engagement=make_engagement(lead_auditor=self.auditor, department=None),
            reference='WP-LANDLESS', title='Mine', prepared_by=landless,
        )
        seen = ids_on(self.as_user(landless).get(f'{EXECUTION}/working-papers/'))
        self.assertIn(mine.id, seen)

    def test_an_org_wide_report_is_invisible_to_an_auditee(self):
        """`GeneratedReport.engagement` is nullable. A report with no engagement
        matches neither branch of the scope, so an EEU-wide report stays with the
        audit team rather than reaching every auditee."""
        org_wide = GeneratedReport.objects.create(
            title='EEU-wide summary', format='pdf', generated_by=self.auditor,
            engagement=None,
        )
        seen = ids_on(self.as_user(self.auditee).get(f'{REPORTS}/generated/'))
        self.assertNotIn(org_wide.id, seen)
