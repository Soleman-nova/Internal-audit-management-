"""Role-by-role tests for the audit planning API.

Covers the universe register, the re-audit due list, the plan submit/approve
workflow (including the ownership gate added so an auditor cannot submit a
colleague's plan under their own name), engagement creation and status
transitions, and the auditee read scoping on the engagement calendar.
"""
import datetime

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.audit_planning.models import (
    AuditEngagement, AuditPlan, AuditTeamMember, AuditUniverse,
)
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_engagement, make_plan, make_universe,
    notification_titles, next_seq,
)
from apps.notifications.models import Notification

UNIVERSE_URL = '/api/planning/universe/'
PLANS_URL = '/api/planning/plans/'
ENGAGEMENTS_URL = '/api/planning/engagements/'


class AuditUniverseRoleAccessTest(RoleFixtureMixin, TestCase):
    """WRITE_AUDIT gates the register; reads stay open to every role."""

    def test_every_role_can_list(self):
        make_universe(department=self.department)
        self.assert_status_by_role(
            {role: 200 for role in self.users},
            lambda client, role: client.get(UNIVERSE_URL),
        )

    def test_only_write_audit_roles_can_create(self):
        def create(client, role):
            return client.post(UNIVERSE_URL, {
                'name': f'Process for {role}',
                # Unique per role: five roles POSTing the same code would fail
                # on the unique constraint rather than on the permission.
                'code': f'UNV-{role[:3].upper()}-{next_seq()}',
                'category': 'process',
                'risk_score': 3.5,
                'audit_frequency': 'Annually',
                'owner': 'Process Owner',
                'department': self.department.id,
                'status': 'active',
            })

        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, create)

    def test_only_write_audit_roles_can_update(self):
        entry = make_universe(department=self.department)
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 200,
            Role.AUDITEE: 403,
        }, lambda client, role: client.patch(
            f'{UNIVERSE_URL}{entry.id}/', {'owner': role}, format='json',
        ))

    def test_auditee_cannot_delete(self):
        entry = make_universe(department=self.department)
        response = self.as_user(self.auditee).delete(f'{UNIVERSE_URL}{entry.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(AuditUniverse.objects.filter(pk=entry.pk).exists())

    def test_crud_is_audit_logged(self):
        client = self.as_user(self.auditor)
        created = client.post(UNIVERSE_URL, {
            'name': 'Logged Process', 'code': f'UNV-LOG-{next_seq()}',
            'category': 'process', 'risk_score': 2, 'audit_frequency': 'Annually',
            'status': 'active',
        })
        entry_id = created.data['id']
        client.patch(f'{UNIVERSE_URL}{entry_id}/', {'owner': 'New Owner'}, format='json')
        client.delete(f'{UNIVERSE_URL}{entry_id}/')

        actions = list(
            AuditTrail.objects
            .filter(model_name='AuditUniverse', object_id=str(entry_id))
            .values_list('action', flat=True)
        )
        self.assertCountEqual(actions, ['CREATE', 'UPDATE', 'DELETE'])


class DueForReAuditTest(RoleFixtureMixin, TestCase):
    """``due-for-re-audit`` — the Phase 3.3 re-audit window."""

    def setUp(self):
        super().setUp()
        today = timezone.now().date()
        self.never_audited = make_universe(
            department=self.department, audit_frequency='Annually', last_audited=None,
        )
        self.overdue = make_universe(
            department=self.department, audit_frequency='Annually',
            last_audited=today - datetime.timedelta(days=400),
        )
        self.recent = make_universe(
            department=self.department, audit_frequency='Annually',
            last_audited=today - datetime.timedelta(days=30),
        )
        self.system_overdue = make_universe(
            department=self.department, category='system', audit_frequency='Quarterly',
            last_audited=today - datetime.timedelta(days=200),
        )

    def codes(self, response):
        payload = response.data
        rows = payload['results'] if isinstance(payload, dict) else payload
        return {row['code'] for row in rows}

    def test_lists_never_audited_and_lapsed_entries_only(self):
        response = self.as_user(self.auditor).get(f'{UNIVERSE_URL}due-for-re-audit/')
        self.assertEqual(response.status_code, 200)
        codes = self.codes(response)
        self.assertIn(self.never_audited.code, codes)
        self.assertIn(self.overdue.code, codes)
        self.assertNotIn(self.recent.code, codes)

    def test_inactive_entries_are_excluded(self):
        retired = make_universe(
            department=self.department, audit_frequency='Annually',
            last_audited=None, status='inactive',
        )
        response = self.as_user(self.auditor).get(f'{UNIVERSE_URL}due-for-re-audit/')
        self.assertNotIn(retired.code, self.codes(response))

    def test_as_of_shifts_the_window(self):
        """A "what if" date in the past pulls the recently audited entry out of
        scope; the same entry is due again when asked about a date far ahead."""
        client = self.as_user(self.auditor)
        past = (self.recent.last_audited + datetime.timedelta(days=1)).isoformat()
        self.assertNotIn(
            self.recent.code,
            self.codes(client.get(f'{UNIVERSE_URL}due-for-re-audit/?as_of={past}')),
        )
        future = (self.recent.last_audited + datetime.timedelta(days=800)).isoformat()
        self.assertIn(
            self.recent.code,
            self.codes(client.get(f'{UNIVERSE_URL}due-for-re-audit/?as_of={future}')),
        )

    def test_category_narrows_the_list(self):
        response = self.as_user(self.auditor).get(
            f'{UNIVERSE_URL}due-for-re-audit/?category=system'
        )
        self.assertEqual(self.codes(response), {self.system_overdue.code})

    def test_bad_as_of_date_is_a_400_not_a_500(self):
        response = self.as_user(self.auditor).get(
            f'{UNIVERSE_URL}due-for-re-audit/?as_of=not-a-date'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('YYYY-MM-DD', response.data['detail'])

    def test_response_is_paginated(self):
        response = self.as_user(self.auditor).get(f'{UNIVERSE_URL}due-for-re-audit/')
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)


class AuditPlanWorkflowTest(RoleFixtureMixin, TestCase):
    """Submit is owner-or-approver; approve needs APPROVE_PLANS."""

    def setUp(self):
        super().setUp()
        self.plan = make_plan(created_by=self.auditor)

    def submit(self, user):
        return self.as_user(user).post(f'{PLANS_URL}{self.plan.id}/submit/')

    def test_author_can_submit_and_approvers_are_notified(self):
        response = self.submit(self.auditor)
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, 'submitted')

        for approver in (self.admin, self.manager):
            self.assertTrue(
                Notification.objects.filter(
                    user=approver, notification_type='approval_needed',
                ).exists(),
                f'{approver.role} was not asked to approve',
            )
        # The submitter is not told about their own submission, and a supervisor
        # is not on the plan-approval distribution list.
        self.assertEqual(notification_titles(self.auditor), [])
        self.assertEqual(notification_titles(self.supervisor), [])

    def test_an_uninvolved_auditor_cannot_submit_someone_elses_plan(self):
        """The gate this test exists for: at the class-level WRITE_AUDIT
        permission any auditor could push a colleague's draft to the approvers
        under their own name."""
        other_auditor = self.make_user(Role.AUDITOR, department=self.department)
        response = self.submit(other_auditor)
        self.assertEqual(response.status_code, 403)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, 'draft')

    def test_approve_plans_holders_can_submit_any_plan(self):
        self.assertEqual(self.submit(self.supervisor).status_code, 200)

    def test_auditee_cannot_submit(self):
        self.assertEqual(self.submit(self.auditee).status_code, 403)

    def test_submit_is_audit_logged_with_the_status_change(self):
        self.submit(self.auditor)
        entry = AuditTrail.objects.filter(
            model_name='AuditPlan', object_id=str(self.plan.id), action='UPDATE',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes, {'status': ['draft', 'submitted']})

    def test_approve_stamps_the_approver_and_notifies_the_author(self):
        response = self.as_user(self.manager).post(f'{PLANS_URL}{self.plan.id}/approve/')
        self.assertEqual(response.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, 'approved')
        self.assertEqual(self.plan.approved_by, self.manager)
        self.assertIsNotNone(self.plan.approved_at)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='approved',
            ).exists()
        )

    def test_approve_is_gated_by_approve_plans(self):
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(f'{PLANS_URL}{self.plan.id}/approve/'))

    def test_approve_is_logged_as_an_approve_action(self):
        self.as_user(self.manager).post(f'{PLANS_URL}{self.plan.id}/approve/')
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='AuditPlan', object_id=str(self.plan.id), action='APPROVE',
            ).exists()
        )

    def test_create_records_the_author(self):
        response = self.as_user(self.auditor).post(PLANS_URL, {
            'title': 'FY Plan', 'year': timezone.now().year,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            AuditPlan.objects.get(pk=response.data['id']).created_by, self.auditor,
        )

    def test_auditee_cannot_create_a_plan(self):
        response = self.as_user(self.auditee).post(PLANS_URL, {
            'title': 'Blocked Plan', 'year': timezone.now().year,
        }, format='json')
        self.assertEqual(response.status_code, 403)


class AuditEngagementTest(RoleFixtureMixin, TestCase):
    """Engagement creation, team membership and status transitions."""

    def setUp(self):
        super().setUp()
        self.plan = make_plan(created_by=self.manager)

    def test_create_generates_a_number_and_notifies_the_team(self):
        response = self.as_user(self.manager).post(ENGAGEMENTS_URL, {
            'plan': self.plan.id,
            'title': 'Revenue Assurance Audit',
            'engagement_type': 'financial',
            'department': self.department.id,
            'lead_auditor': self.auditor.id,
            'supervisor': self.supervisor.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)

        engagement = AuditEngagement.objects.get(pk=response.data['id'])
        self.assertRegex(engagement.engagement_number, r'^ENG-\d{4}-\d{4}$')
        for member in (self.auditor, self.supervisor):
            self.assertTrue(
                Notification.objects.filter(
                    user=member, notification_type='assigned',
                ).exists(),
                f'{member.role} was not told about the assignment',
            )
        # The creator is not notified of their own assignment.
        self.assertEqual(notification_titles(self.manager), [])

    def test_client_supplied_engagement_number_is_ignored(self):
        response = self.as_user(self.manager).post(ENGAGEMENTS_URL, {
            'plan': self.plan.id, 'title': 'Spoofed Number',
            'engagement_number': 'ENG-HACKED',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.data['engagement_number'], 'ENG-HACKED')

    def test_auditee_cannot_create_an_engagement(self):
        response = self.as_user(self.auditee).post(ENGAGEMENTS_URL, {
            'plan': self.plan.id, 'title': 'Blocked Engagement',
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_add_member_notifies_the_new_member(self):
        engagement = make_engagement(plan=self.plan, lead_auditor=self.auditor)
        second = self.make_user(Role.AUDITOR, department=self.department)
        response = self.as_user(self.supervisor).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/add-member/',
            {'user': second.id, 'role': 'member', 'allocated_days': 5},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(
            AuditTeamMember.objects.filter(engagement=engagement, user=second).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=second, notification_type='assigned').exists()
        )

    def test_update_status_stamps_the_actual_dates(self):
        engagement = make_engagement(plan=self.plan, lead_auditor=self.auditor)
        client = self.as_user(self.supervisor)

        client.post(f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
                    {'status': 'in_progress'}, format='json')
        engagement.refresh_from_db()
        self.assertEqual(engagement.status, 'in_progress')
        self.assertEqual(engagement.actual_start, timezone.now().date())

        client.post(f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
                    {'status': 'completed'}, format='json')
        engagement.refresh_from_db()
        self.assertEqual(engagement.actual_end, timezone.now().date())

    def test_completing_back_fills_the_linked_universe_entry(self):
        entry = make_universe(department=self.department, last_audited=None)
        engagement = make_engagement(
            plan=self.plan, lead_auditor=self.auditor, audit_universe=entry,
        )
        self.as_user(self.supervisor).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
            {'status': 'completed'}, format='json',
        )
        entry.refresh_from_db()
        self.assertEqual(entry.last_audited, timezone.now().date())

    def test_completing_falls_back_to_the_department_universe_entry(self):
        """Engagements scheduled straight off a department, with no explicit
        universe link, must still close the re-audit loop — otherwise the
        entity looks permanently overdue."""
        low = make_universe(department=self.department, risk_score=1, last_audited=None)
        high = make_universe(department=self.department, risk_score=9, last_audited=None)
        engagement = make_engagement(
            plan=self.plan, lead_auditor=self.auditor,
            audit_universe=None, department=self.department,
        )
        self.as_user(self.supervisor).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
            {'status': 'completed'}, format='json',
        )
        low.refresh_from_db()
        high.refresh_from_db()
        # Highest risk score wins the fallback; the low-risk sibling is untouched.
        self.assertEqual(high.last_audited, timezone.now().date())
        self.assertIsNone(low.last_audited)

    def test_invalid_status_is_a_400(self):
        engagement = make_engagement(plan=self.plan, lead_auditor=self.auditor)
        response = self.as_user(self.supervisor).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
            {'status': 'nonsense'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        engagement.refresh_from_db()
        self.assertEqual(engagement.status, 'planned')

    def test_reporting_notifies_supervisors_and_managers_but_not_the_actor(self):
        engagement = make_engagement(plan=self.plan, lead_auditor=self.auditor)
        self.as_user(self.supervisor).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
            {'status': 'reporting'}, format='json',
        )
        self.assertTrue(notification_titles(self.manager))
        self.assertEqual(notification_titles(self.supervisor), [])


class AuditEngagementScopingTest(RoleFixtureMixin, TestCase):
    """Auditees read only the engagements that concern their department."""

    def setUp(self):
        super().setUp()
        self.plan = make_plan(created_by=self.manager)
        self.own_dept = make_engagement(
            plan=self.plan, lead_auditor=self.auditor, department=self.department,
        )
        self.other_dept = make_engagement(
            plan=self.plan, lead_auditor=self.auditor, department=self.other_department,
        )

    def visible_ids(self, user):
        response = self.as_user(user).get(ENGAGEMENTS_URL)
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in response.data['results']}

    def test_auditee_sees_only_their_own_department(self):
        visible = self.visible_ids(self.auditee)
        self.assertIn(self.own_dept.id, visible)
        self.assertNotIn(self.other_dept.id, visible)

    def test_auditee_without_a_department_sees_only_named_engagements(self):
        """A missing department is read as "no department scope", not as
        "every department" — the safer reading of incomplete data."""
        floating = self.make_user(Role.AUDITEE, department=None)
        self.assertEqual(self.visible_ids(floating), set())

        AuditTeamMember.objects.create(
            engagement=self.other_dept, user=floating, role='member',
        )
        self.assertEqual(self.visible_ids(floating), {self.other_dept.id})

    def test_scoping_does_not_duplicate_rows(self):
        """An auditee who is both the department representative and a named team
        member matched two OR branches; without .distinct() the row came back
        twice and the count was wrong."""
        AuditTeamMember.objects.create(
            engagement=self.own_dept, user=self.auditee, role='member',
        )
        response = self.as_user(self.auditee).get(ENGAGEMENTS_URL)
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.own_dept.id])
        self.assertEqual(response.data['count'], 1)

    def test_other_roles_see_the_whole_calendar(self):
        for user in (self.admin, self.manager, self.supervisor, self.auditor):
            with self.subTest(role=user.role):
                visible = self.visible_ids(user)
                self.assertIn(self.own_dept.id, visible)
                self.assertIn(self.other_dept.id, visible)

    def test_auditee_cannot_retrieve_another_departments_engagement(self):
        response = self.as_user(self.auditee).get(
            f'{ENGAGEMENTS_URL}{self.other_dept.id}/'
        )
        self.assertEqual(response.status_code, 404)
