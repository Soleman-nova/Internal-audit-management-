"""Role-by-role tests for the findings API.

Covers finding-number generation, assignment notifications, the auditee's own
workflow (comment, evidence, dispute — the actions a plain WRITE_AUDIT gate used
to lock them out of), the resolve/close/reopen lifecycle, and the read scoping
that keeps one department's findings out of another's register.
"""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_engagement, make_finding, notification_titles,
)
from apps.findings.models import AuditFinding, Evidence, FindingComment
from apps.notifications.models import Notification

FINDINGS_URL = '/api/findings/findings/'
EVIDENCE_URL = '/api/findings/evidence/'


class FindingCreateTest(RoleFixtureMixin, TestCase):
    """Creation is WRITE_AUDIT; the number is the server's to assign."""

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )

    def payload(self, **kwargs):
        data = {
            'engagement': self.engagement.id,
            'title': 'Unapproved journal entries',
            'description': 'Twelve journals were posted without review.',
            'severity': 'high',
            'category': 'control_deficiency',
        }
        data.update(kwargs)
        return data

    def test_only_write_audit_roles_can_log_a_finding(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            FINDINGS_URL, self.payload(title=f'Finding by {role}'), format='json',
        ))

    def test_server_assigns_the_finding_number_and_the_identifier(self):
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        finding = AuditFinding.objects.get(pk=response.data['id'])
        self.assertRegex(finding.finding_number, r'^FND-\d{5}$')
        self.assertEqual(finding.identified_by, self.auditor)

    def test_client_supplied_finding_number_is_overwritten(self):
        """The findings page used to send ``FIND-<timestamp>``; the server
        overwrites it, so the number the user saw in the form was never the
        number the record ended up with."""
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(finding_number='FIND-9999'), format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertRegex(response.data['finding_number'], r'^FND-\d{5}$')

    def test_assignee_and_auditee_are_notified_but_not_the_author(self):
        self.as_user(self.auditor).post(FINDINGS_URL, self.payload(
            assigned_to=self.supervisor.id, auditee=self.auditee.id,
        ), format='json')
        for recipient in (self.supervisor, self.auditee):
            self.assertTrue(
                Notification.objects.filter(
                    user=recipient, notification_type='finding',
                ).exists(),
                f'{recipient.role} was not notified',
            )
        self.assertEqual(notification_titles(self.auditor), [])

    def test_creation_is_audit_logged(self):
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(), format='json',
        )
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='AuditFinding', object_id=str(response.data['id']),
                action='CREATE',
            ).exists()
        )


class FindingUpdateTest(RoleFixtureMixin, TestCase):
    """Re-assignment notifies only the people who are newly on the hook."""

    def setUp(self):
        super().setUp()
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
            assigned_to=self.supervisor,
        )
        self.url = f'{FINDINGS_URL}{self.finding.id}/'

    def test_reassignment_notifies_the_new_assignee_only(self):
        newcomer = self.make_user(Role.AUDITOR, department=self.department)
        response = self.as_user(self.auditor).patch(
            self.url, {'assigned_to': newcomer.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(
                user=newcomer, notification_type='assigned',
            ).exists()
        )
        # The previous assignee is not re-notified about a finding they lost.
        self.assertEqual(notification_titles(self.supervisor), [])

    def test_editing_other_fields_notifies_nobody(self):
        self.as_user(self.auditor).patch(
            self.url, {'recommendation': 'Introduce a review step.'}, format='json',
        )
        self.assertEqual(notification_titles(self.supervisor), [])

    def test_status_change_is_logged_with_the_transition(self):
        self.as_user(self.auditor).patch(
            self.url, {'status': 'in_progress'}, format='json',
        )
        entry = AuditTrail.objects.filter(
            model_name='AuditFinding', object_id=str(self.finding.id), action='UPDATE',
        ).first()
        self.assertEqual(entry.changes, {'status': ['open', 'in_progress']})

    def test_auditee_cannot_edit_a_finding_about_them(self):
        response = self.as_user(self.auditee).patch(
            self.url, {'severity': 'low'}, format='json',
        )
        self.assertEqual(response.status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-evidence-test-'))
class FindingResponseTest(RoleFixtureMixin, TestCase):
    """The auditee's side of the conversation: comments and evidence.

    Both actions inherited the class-level WRITE_AUDIT gate, so the person being
    asked to respond to a finding got a 403 on their own record — they could
    only reject it.
    """

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        self.finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            assigned_to=self.supervisor, auditee=self.auditee,
        )
        # Same department as the engagement, so the finding is *readable*, but
        # not named on it — the object check is the only thing stopping them.
        self.bystander = self.make_user(Role.AUDITEE, department=self.department)
        # A different department entirely: the finding is not even visible.
        self.outsider = self.make_user(Role.AUDITEE, department=self.other_department)

    def comment_as(self, user, text='We have corrected the postings.'):
        return self.as_user(user).post(
            f'{FINDINGS_URL}{self.finding.id}/add-comment/',
            {'comment': text}, format='json',
        )

    def upload_as(self, user):
        return self.as_user(user).post(
            f'{FINDINGS_URL}{self.finding.id}/upload-evidence/',
            {
                'title': 'Signed authorisation log',
                'evidence_type': 'document',
                'file': SimpleUploadedFile('log.txt', b'signed', content_type='text/plain'),
            },
            format='multipart',
        )

    def test_named_auditee_can_comment(self):
        """The URL carries the finding, so the client sends only the text —
        requiring ``finding`` in the payload made every comment a 400."""
        response = self.comment_as(self.auditee)
        self.assertEqual(response.status_code, 201, response.data)
        comment = FindingComment.objects.get(pk=response.data['id'])
        self.assertEqual(comment.finding, self.finding)
        self.assertEqual(comment.author, self.auditee)

    def test_comment_pulls_in_the_rest_of_the_thread(self):
        self.comment_as(self.auditee)
        for recipient in (self.auditor, self.supervisor):
            self.assertTrue(
                Notification.objects.filter(
                    user=recipient, notification_type='comment',
                ).exists(),
                f'{recipient.role} was not told about the reply',
            )
        self.assertEqual(notification_titles(self.auditee), [])

    def test_comment_is_audit_logged_against_the_finding(self):
        self.comment_as(self.auditee)
        entry = AuditTrail.objects.filter(
            model_name='AuditFinding', object_id=str(self.finding.id),
        ).first()
        self.assertIn('Comment added', entry.object_repr)

    def test_capability_holders_can_comment_on_any_finding(self):
        self.assertEqual(self.comment_as(self.auditor).status_code, 201)
        self.assertEqual(self.comment_as(self.manager).status_code, 201)

    def test_an_uninvolved_auditee_in_the_same_department_is_refused(self):
        response = self.comment_as(self.bystander)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FindingComment.objects.filter(author=self.bystander).exists())

    def test_an_auditee_elsewhere_cannot_even_see_the_finding(self):
        self.assertEqual(self.comment_as(self.outsider).status_code, 404)

    def test_named_auditee_can_upload_evidence(self):
        response = self.upload_as(self.auditee)
        self.assertEqual(response.status_code, 201, response.data)
        evidence = Evidence.objects.get(pk=response.data['id'])
        self.assertEqual(evidence.finding, self.finding)
        self.assertEqual(evidence.uploaded_by, self.auditee)
        self.assertTrue(evidence.file)

    def test_evidence_upload_notifies_the_auditor_who_raised_it(self):
        self.upload_as(self.auditee)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='finding',
            ).exists()
        )

    def test_an_uninvolved_auditee_cannot_upload_evidence(self):
        self.assertEqual(self.upload_as(self.bystander).status_code, 403)


class FindingLifecycleTest(RoleFixtureMixin, TestCase):
    """resolve / close / dispute / reopen and the dates they move."""

    def setUp(self):
        super().setUp()
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
            assigned_to=self.supervisor,
            auditee=self.auditee,
        )
        self.base = f'{FINDINGS_URL}{self.finding.id}/'

    def test_resolve_sets_the_resolution_date_and_notifies_the_auditor(self):
        response = self.as_user(self.supervisor).post(f'{self.base}resolve/')
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'resolved')
        self.assertEqual(self.finding.actual_resolution_date, timezone.now().date())
        self.assertTrue(notification_titles(self.auditor))

    def test_resolve_is_gated_by_close_findings(self):
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 200,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(f'{self.base}resolve/'))

    def test_close_is_gated_by_close_findings(self):
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 200,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(f'{self.base}close/'))

    def test_close_stamps_the_resolution_date(self):
        self.as_user(self.supervisor).post(f'{self.base}close/')
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'closed')
        self.assertEqual(self.finding.actual_resolution_date, timezone.now().date())

    def test_reopen_clears_the_resolution_date_and_notifies_the_assignee(self):
        self.as_user(self.supervisor).post(f'{self.base}close/')
        response = self.as_user(self.manager).post(f'{self.base}reopen/')
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'in_progress')
        self.assertIsNone(self.finding.actual_resolution_date)
        self.assertTrue(notification_titles(self.supervisor))

    def test_reopen_is_gated_by_close_findings(self):
        self.assertEqual(
            self.as_user(self.auditee).post(f'{self.base}reopen/').status_code, 403,
        )

    def test_named_auditee_can_dispute(self):
        """Dispute is the one lifecycle action that belongs to the auditee."""
        response = self.as_user(self.auditee).post(f'{self.base}dispute/')
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'disputed')
        self.assertTrue(notification_titles(self.auditor))

    def test_an_uninvolved_auditee_cannot_dispute(self):
        bystander = self.make_user(Role.AUDITEE, department=self.department)
        self.assertEqual(
            self.as_user(bystander).post(f'{self.base}dispute/').status_code, 403,
        )

    def test_every_transition_is_audit_logged(self):
        self.as_user(self.supervisor).post(f'{self.base}resolve/')
        self.as_user(self.supervisor).post(f'{self.base}close/')
        self.as_user(self.supervisor).post(f'{self.base}reopen/')
        changes = list(
            AuditTrail.objects
            .filter(model_name='AuditFinding', object_id=str(self.finding.id))
            .order_by('timestamp')
            .values_list('changes', flat=True)
        )
        self.assertEqual(changes, [
            {'status': ['open', 'resolved']},
            {'status': ['resolved', 'closed']},
            {'status': ['closed', 'in_progress']},
        ])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-scope-test-'))
class FindingScopingTest(RoleFixtureMixin, TestCase):
    """An auditee reads the findings that concern them, not EEU's register."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        own_engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        other_engagement = make_engagement(
            lead_auditor=self.auditor, department=self.other_department,
        )
        self.own_dept = make_finding(
            engagement=own_engagement, identified_by=self.auditor,
        )
        self.other_dept = make_finding(
            engagement=other_engagement, identified_by=self.auditor,
        )
        # Named on a finding outside their department — assignment beats scope.
        self.named_elsewhere = make_finding(
            engagement=other_engagement, identified_by=self.auditor, auditee=self.auditee,
        )

    def visible_ids(self, user, url=FINDINGS_URL):
        response = self.as_user(user).get(url)
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in response.data['results']}

    def test_auditee_sees_own_department_and_own_assignments(self):
        visible = self.visible_ids(self.auditee)
        self.assertIn(self.own_dept.id, visible)
        self.assertIn(self.named_elsewhere.id, visible)
        self.assertNotIn(self.other_dept.id, visible)

    def test_auditee_without_a_department_sees_only_their_own_findings(self):
        floating = self.make_user(Role.AUDITEE, department=None)
        self.assertEqual(self.visible_ids(floating), set())
        mine = make_finding(
            engagement=self.other_dept.engagement,
            identified_by=self.auditor, assigned_to=floating,
        )
        self.assertEqual(self.visible_ids(floating), {mine.id})

    def test_other_roles_see_the_whole_register(self):
        for user in (self.admin, self.manager, self.supervisor, self.auditor):
            with self.subTest(role=user.role):
                visible = self.visible_ids(user)
                self.assertIn(self.own_dept.id, visible)
                self.assertIn(self.other_dept.id, visible)

    def test_retrieving_an_out_of_scope_finding_is_a_404(self):
        response = self.as_user(self.auditee).get(f'{FINDINGS_URL}{self.other_dept.id}/')
        self.assertEqual(response.status_code, 404)

    def test_evidence_inherits_the_findings_visibility(self):
        mine = Evidence.objects.create(
            finding=self.own_dept, title='Our reconciliation',
            file=SimpleUploadedFile('mine.txt', b'x', content_type='text/plain'),
            uploaded_by=self.auditor,
        )
        theirs = Evidence.objects.create(
            finding=self.other_dept, title='Another department',
            file=SimpleUploadedFile('theirs.txt', b'x', content_type='text/plain'),
            uploaded_by=self.auditor,
        )
        visible = self.visible_ids(self.auditee, EVIDENCE_URL)
        self.assertIn(mine.id, visible)
        self.assertNotIn(theirs.id, visible)
