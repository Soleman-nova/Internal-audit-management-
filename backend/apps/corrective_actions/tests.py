"""Role-by-role tests for the corrective-action (CAPA) API.

Covers CAPA numbering and owner notification, the owner's right to respond to
their own action, the ownership gate on ``schedule-followup``, the paginated
``overdue`` list and its due-date boundary, ``summary`` counts, and both
branches of the auditee read scoping.
"""
import datetime
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_action, make_engagement, make_finding,
    notification_titles,
)
from apps.corrective_actions.models import ActionResponse, CorrectiveAction, FollowUp
from apps.notifications.models import Notification

ACTIONS_URL = '/api/corrective/actions/'


class CorrectiveActionCreateTest(RoleFixtureMixin, TestCase):
    """Creation is WRITE_AUDIT; the number and the assigner are the server's."""

    def setUp(self):
        super().setUp()
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
        )

    def payload(self, **kwargs):
        data = {
            'finding': self.finding.id,
            'title': 'Reinstate the authorisation control',
            'description': 'Require dual approval on journal entries.',
            'recommendation': 'Configure the ERP approval workflow.',
            'owner': self.auditee.id,
            'priority': 'high',
            'due_date': (timezone.now().date() + datetime.timedelta(days=30)).isoformat(),
        }
        data.update(kwargs)
        return data

    def test_only_write_audit_roles_can_raise_a_capa(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            ACTIONS_URL, self.payload(title=f'CAPA by {role}'), format='json',
        ))

    def test_server_assigns_the_number_and_the_assigner(self):
        response = self.as_user(self.auditor).post(
            ACTIONS_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        action = CorrectiveAction.objects.get(pk=response.data['id'])
        self.assertRegex(action.action_number, r'^CAPA-\d{4}-\d{4}$')
        self.assertEqual(action.assigned_by, self.auditor)

    def test_owner_is_notified_with_the_due_date(self):
        self.as_user(self.auditor).post(ACTIONS_URL, self.payload(), format='json')
        notification = Notification.objects.filter(
            user=self.auditee, notification_type='assigned',
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('due', notification.message)
        self.assertEqual(notification_titles(self.auditor), [])

    def test_reassignment_notifies_the_new_owner_only(self):
        action = make_action(
            finding=self.finding, owner=self.auditee, assigned_by=self.auditor,
        )
        newcomer = self.make_user(Role.AUDITEE, department=self.department)
        response = self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action.id}/', {'owner': newcomer.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(
                user=newcomer, notification_type='assigned',
            ).exists()
        )
        self.assertEqual(notification_titles(self.auditee), [])

    def test_crud_is_audit_logged(self):
        client = self.as_user(self.auditor)
        created = client.post(ACTIONS_URL, self.payload(), format='json')
        action_id = created.data['id']
        client.patch(f'{ACTIONS_URL}{action_id}/', {'status': 'in_progress'}, format='json')
        client.delete(f'{ACTIONS_URL}{action_id}/')

        entries = list(
            AuditTrail.objects
            .filter(model_name='CorrectiveAction', object_id=str(action_id))
            .order_by('timestamp')
        )
        self.assertCountEqual(
            [e.action for e in entries], ['CREATE', 'UPDATE', 'DELETE'],
        )
        update = next(e for e in entries if e.action == 'UPDATE')
        self.assertEqual(update.changes, {'status': ['open', 'in_progress']})


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-capa-test-'))
class AddResponseTest(RoleFixtureMixin, TestCase):
    """The owner answers for their own action — including auditees."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.action = make_action(owner=self.auditee, assigned_by=self.auditor)
        self.url = f'{ACTIONS_URL}{self.action.id}/add-response/'

    def respond_as(self, user, status_update='in_progress', with_file=False,
                   filename='proof.txt'):
        data = {
            'response_text': 'Workflow configured; awaiting the next cycle.',
            'status_update': status_update,
        }
        if with_file:
            data['evidence_file'] = SimpleUploadedFile(
                filename, b'configuration export', content_type='text/plain',
            )
            return self.as_user(user).post(self.url, data, format='multipart')
        return self.as_user(user).post(self.url, data, format='json')

    def test_owner_can_respond_and_the_status_moves(self):
        response = self.respond_as(self.auditee)
        self.assertEqual(response.status_code, 201, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'in_progress')
        self.assertEqual(
            ActionResponse.objects.get(pk=response.data['id']).responder, self.auditee,
        )

    def test_owner_can_attach_evidence_to_their_response(self):
        response = self.respond_as(self.auditee, with_file=True)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(ActionResponse.objects.get(pk=response.data['id']).evidence_file)

    def test_an_executable_cannot_be_attached_to_a_response(self):
        """The auditee-reachable upload path on this app. ActionResponse.evidence_file
        was a bare FileField — see apps/common/validators.py."""
        response = self.respond_as(self.auditee, with_file=True, filename='macro.exe')
        self.assertEqual(response.status_code, 400)
        self.assertIn('evidence_file', response.data)
        self.assertFalse(ActionResponse.objects.exists())
        # The action's status must not move on a rejected response either.
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    def test_response_notifies_the_auditor_who_raised_it(self):
        self.respond_as(self.auditee)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='follow_up',
            ).exists()
        )

    def test_status_change_is_audit_logged(self):
        self.respond_as(self.auditee, status_update='resolved')
        entry = AuditTrail.objects.filter(
            model_name='CorrectiveAction', object_id=str(self.action.id),
        ).first()
        self.assertEqual(entry.changes, {'status': ['open', 'resolved']})

    def test_capability_holders_can_respond_on_any_action(self):
        self.assertEqual(self.respond_as(self.supervisor).status_code, 201)

    def test_an_auditee_elsewhere_cannot_see_or_answer_the_action(self):
        outsider = self.make_user(Role.AUDITEE, department=self.other_department)
        self.assertEqual(self.respond_as(outsider).status_code, 404)


class ScheduleFollowupTest(RoleFixtureMixin, TestCase):
    """Verification belongs to whoever raised the action, plus approvers."""

    def setUp(self):
        super().setUp()
        self.action = make_action(owner=self.auditee, assigned_by=self.auditor)
        self.url = f'{ACTIONS_URL}{self.action.id}/schedule-followup/'

    def schedule_as(self, user):
        return self.as_user(user).post(self.url, {
            'scheduled_date': (
                timezone.now().date() + datetime.timedelta(days=14)
            ).isoformat(),
            'notes': 'Re-test the approval workflow.',
        }, format='json')

    def test_the_auditor_who_raised_it_can_schedule(self):
        response = self.schedule_as(self.auditor)
        self.assertEqual(response.status_code, 201, response.data)
        follow_up = FollowUp.objects.get(pk=response.data['id'])
        self.assertEqual(follow_up.corrective_action, self.action)
        self.assertEqual(follow_up.conducted_by, self.auditor)

    def test_an_uninvolved_auditor_cannot_sign_off_a_colleagues_capa(self):
        stranger = self.make_user(Role.AUDITOR, department=self.department)
        self.assertEqual(self.schedule_as(stranger).status_code, 403)
        self.assertFalse(FollowUp.objects.filter(corrective_action=self.action).exists())

    def test_approve_plans_holders_verify_across_engagements(self):
        self.assertEqual(self.schedule_as(self.supervisor).status_code, 201)

    def test_the_owner_cannot_verify_their_own_action(self):
        """The auditee may respond, but signing the verification off would let
        them close the loop on themselves."""
        self.assertEqual(self.schedule_as(self.auditee).status_code, 403)

    def test_the_owner_is_notified_that_a_follow_up_is_coming(self):
        self.schedule_as(self.auditor)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='follow_up',
            ).exists()
        )


class OverdueEndpointTest(RoleFixtureMixin, TestCase):
    """``overdue`` is derived from the due date, and paginated."""

    def setUp(self):
        super().setUp()
        today = timezone.now().date()
        self.yesterday = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today - datetime.timedelta(days=1), status='open',
        )
        # Due today is not yet overdue — the boundary the endpoint has to get
        # right, since `due_date__lt=today` and `<= today` differ by one day of
        # somebody's grace period.
        self.today = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today, status='open',
        )
        self.settled = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today - datetime.timedelta(days=10), status='resolved',
        )
        self.in_progress = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today - datetime.timedelta(days=5), status='in_progress',
        )

    def overdue_ids(self, user, query=''):
        response = self.as_user(user).get(f'{ACTIONS_URL}overdue/{query}')
        self.assertEqual(response.status_code, 200)
        return response.data, {row['id'] for row in response.data['results']}

    def test_lists_lapsed_open_and_in_progress_actions_only(self):
        _, ids = self.overdue_ids(self.auditor)
        self.assertIn(self.yesterday.id, ids)
        self.assertIn(self.in_progress.id, ids)
        self.assertNotIn(self.today.id, ids)
        self.assertNotIn(self.settled.id, ids)

    def test_the_response_is_paginated(self):
        """An audit backlog runs to hundreds of rows; dumping the whole queryset
        is what this endpoint used to do."""
        payload, _ = self.overdue_ids(self.auditor)
        self.assertIn('count', payload)
        self.assertIn('results', payload)

    def test_page_size_is_honoured(self):
        payload, _ = self.overdue_ids(self.auditor, '?page_size=1')
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['count'], 2)

    def test_the_status_flag_is_not_required(self):
        """Derived from due_date rather than status='overdue', so the tab is
        correct even before flag_overdue_actions has ever run."""
        self.assertEqual(
            CorrectiveAction.objects.filter(status='overdue').count(), 0,
        )
        _, ids = self.overdue_ids(self.auditor)
        self.assertEqual(len(ids), 2)

    def test_an_auditee_sees_only_their_own_overdue_actions(self):
        elsewhere = self.make_user(Role.AUDITEE, department=self.other_department)
        theirs = make_action(
            owner=elsewhere, assigned_by=self.auditor,
            due_date=timezone.now().date() - datetime.timedelta(days=3), status='open',
        )
        _, ids = self.overdue_ids(self.auditee)
        self.assertNotIn(theirs.id, ids)


class SummaryEndpointTest(RoleFixtureMixin, TestCase):
    """``summary`` — the follow-up page's KPI row."""

    def setUp(self):
        super().setUp()
        today = timezone.now().date()
        make_action(owner=self.auditee, assigned_by=self.auditor, status='open',
                    due_date=today + datetime.timedelta(days=5), priority='high')
        make_action(owner=self.auditee, assigned_by=self.auditor, status='in_progress',
                    due_date=today - datetime.timedelta(days=2), priority='high')
        make_action(owner=self.auditee, assigned_by=self.auditor, status='resolved',
                    due_date=today - datetime.timedelta(days=20), priority='low')

    def test_counts_by_status_and_priority(self):
        response = self.as_user(self.auditor).get(f'{ACTIONS_URL}summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 3)
        self.assertEqual(response.data['open'], 1)
        self.assertEqual(response.data['in_progress'], 1)
        self.assertEqual(response.data['resolved'], 1)
        # Only the in_progress action is both lapsed and unsettled.
        self.assertEqual(response.data['overdue'], 1)
        by_priority = {row['priority']: row['count'] for row in response.data['by_priority']}
        self.assertEqual(by_priority, {'high': 2, 'low': 1})

    def test_the_summary_respects_auditee_scoping(self):
        response = self.as_user(
            self.make_user(Role.AUDITEE, department=self.other_department)
        ).get(f'{ACTIONS_URL}summary/')
        self.assertEqual(response.data['total'], 0)


class CorrectiveActionScopingTest(RoleFixtureMixin, TestCase):
    """Both branches of the auditee scope: by department, then by owner."""

    def setUp(self):
        super().setUp()
        self.colleague = self.make_user(Role.AUDITEE, department=self.department)
        self.elsewhere = self.make_user(Role.AUDITEE, department=self.other_department)
        self.mine = make_action(owner=self.auditee, assigned_by=self.auditor)
        self.colleagues = make_action(owner=self.colleague, assigned_by=self.auditor)
        self.theirs = make_action(owner=self.elsewhere, assigned_by=self.auditor)

    def visible_ids(self, user):
        response = self.as_user(user).get(ACTIONS_URL)
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in response.data['results']}

    def test_auditee_sees_their_whole_department(self):
        """Deliberately department-wide, not owner-only: a department
        representative follows up on their unit's commitments, not only the ones
        with their own name on them."""
        visible = self.visible_ids(self.auditee)
        self.assertIn(self.mine.id, visible)
        self.assertIn(self.colleagues.id, visible)
        self.assertNotIn(self.theirs.id, visible)

    def test_auditee_without_a_department_falls_back_to_their_own_actions(self):
        floating = self.make_user(Role.AUDITEE, department=None)
        self.assertEqual(self.visible_ids(floating), set())
        mine = make_action(owner=floating, assigned_by=self.auditor)
        self.assertEqual(self.visible_ids(floating), {mine.id})

    def test_other_roles_see_every_action(self):
        for user in (self.admin, self.manager, self.supervisor, self.auditor):
            with self.subTest(role=user.role):
                visible = self.visible_ids(user)
                self.assertIn(self.mine.id, visible)
                self.assertIn(self.theirs.id, visible)

    def test_retrieving_an_out_of_scope_action_is_a_404(self):
        response = self.as_user(self.auditee).get(f'{ACTIONS_URL}{self.theirs.id}/')
        self.assertEqual(response.status_code, 404)
