"""Role-by-role tests for the findings API.

Covers finding-number generation, assignment notifications, the auditee's own
workflow (comment, evidence, dispute — the actions a plain WRITE_AUDIT gate used
to lock them out of), the resolve/close/reopen lifecycle, the read scoping that
keeps one department's findings out of another's register, and the slim list
payload that reports counts where the detail view nests collections.
"""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_engagement, make_finding, notification_titles,
)
from apps.common.validators import MAX_DOCUMENT_SIZE
from apps.corrective_actions.models import CorrectiveAction
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
        self.assertRegex(finding.finding_number, r'^FND-\d{4}-\d{4}$')
        self.assertEqual(finding.identified_by, self.auditor)

    def test_client_supplied_finding_number_is_overwritten(self):
        """The findings page used to send ``FIND-<timestamp>``; the server
        overwrites it, so the number the user saw in the form was never the
        number the record ended up with."""
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(finding_number='FIND-9999'), format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertRegex(response.data['finding_number'], r'^FND-\d{4}-\d{4}$')

    def test_numbers_are_sequential_and_never_collide(self):
        """The old generator was five random digits against a unique column.

        A repeat was an IntegrityError, i.e. a 500 that discarded everything the
        auditor had typed — and on a 100,000-value namespace that is ordinary
        birthday math, not a remote edge case.
        """
        client = self.as_user(self.auditor)
        numbers = []
        for i in range(25):
            response = client.post(
                FINDINGS_URL, self.payload(title=f'Finding {i}'), format='json',
            )
            self.assertEqual(response.status_code, 201, response.data)
            numbers.append(response.data['finding_number'])
        self.assertEqual(len(set(numbers)), 25)
        year = timezone.now().year
        self.assertEqual(numbers[0], f'FND-{year}-0001')
        self.assertEqual(numbers[-1], f'FND-{year}-0025')

    def test_a_number_taken_by_a_concurrent_create_is_retried(self):
        """Two writers racing for the same sequence must not surface a 500."""
        year = timezone.now().year
        make_finding(engagement=self.engagement, finding_number=f'FND-{year}-0001')
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['finding_number'], f'FND-{year}-0002')

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

    def test_status_cannot_be_changed_through_a_plain_patch(self):
        """`status` is read-only on the serializer.

        A writable status let any WRITE_AUDIT holder close a finding with a
        PATCH, skipping the CLOSE_FINDINGS gate on the `close` action, the
        `actual_resolution_date` stamp, the transition check, the audit-trail
        entry, and the notification to whoever raised it.
        """
        response = self.as_user(self.auditor).patch(
            self.url, {'status': 'closed'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'open')

    def test_status_change_is_logged_with_the_transition(self):
        self.as_user(self.auditor).post(f'{self.url}resolve/')
        entry = AuditTrail.objects.filter(
            model_name='AuditFinding', object_id=str(self.finding.id), action='UPDATE',
        ).first()
        self.assertEqual(entry.changes, {'status': ['open', 'resolved']})

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

    def test_file_url_points_at_the_gated_endpoint_not_media(self):
        """`file_url` used to be an absolute MEDIA_URL, which served audit
        evidence to anyone holding the link with no token — and 404'd under
        DEBUG=False, where `static()` does not mount MEDIA_URL at all."""
        response = self.upload_as(self.auditee)
        url = response.data['file_url']
        self.assertNotIn('/media/', url)
        self.assertIn(f'/evidence/{response.data["id"]}/download/', url)

    def test_download_returns_the_bytes_to_an_involved_party(self):
        evidence_id = self.upload_as(self.auditee).data['id']
        response = self.as_user(self.auditee).get(f'{EVIDENCE_URL}{evidence_id}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'signed')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_download_requires_authentication(self):
        from rest_framework.test import APIClient

        evidence_id = self.upload_as(self.auditee).data['id']
        response = APIClient().get(f'{EVIDENCE_URL}{evidence_id}/download/')
        self.assertEqual(response.status_code, 401)

    def test_an_auditee_elsewhere_cannot_download_the_evidence(self):
        """The scoped queryset is the authorization: `get_object()` cannot find
        an attachment on a finding outside the caller's department."""
        evidence_id = self.upload_as(self.auditee).data['id']
        response = self.as_user(self.outsider).get(f'{EVIDENCE_URL}{evidence_id}/download/')
        self.assertEqual(response.status_code, 404)

    def test_uploader_cannot_be_reassigned_through_a_patch(self):
        evidence_id = self.upload_as(self.auditee).data['id']
        response = self.as_user(self.auditor).patch(
            f'{EVIDENCE_URL}{evidence_id}/',
            {'uploaded_by': self.supervisor.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Evidence.objects.get(pk=evidence_id).uploaded_by, self.auditee)

    # ── Upload validation ────────────────────────────────────────────────
    # Evidence.file was a bare FileField, and `upload-evidence` is reachable by
    # the named auditee by design. See apps/common/validators.py.

    def upload_file(self, name, body=b'x', content_type='text/plain'):
        return self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{self.finding.id}/upload-evidence/',
            {
                'title': 'Attachment',
                'evidence_type': 'document',
                'file': SimpleUploadedFile(name, body, content_type=content_type),
            },
            format='multipart',
        )

    def test_an_executable_cannot_be_stored_as_evidence(self):
        response = self.upload_file('payload.exe', b'MZ\x90\x00')
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)
        self.assertFalse(Evidence.objects.filter(title='Attachment').exists())

    def test_an_oversized_file_is_refused(self):
        """10 MB is the cap; the request must not be spooled into the media
        directory and then rejected — nothing is saved on a 400."""
        oversized = b'0' * (MAX_DOCUMENT_SIZE + 1)
        response = self.upload_file('dump.pdf', oversized, 'application/pdf')
        self.assertEqual(response.status_code, 400)
        self.assertIn('limit is 10.0 MB', str(response.data['file']))
        self.assertFalse(Evidence.objects.filter(title='Attachment').exists())

    def test_the_ordinary_formats_still_upload(self):
        for name in ('ledger.pdf', 'sample.xlsx', 'scan.jpg'):
            with self.subTest(name=name):
                self.assertEqual(self.upload_file(name).status_code, 201)

    def test_a_file_large_enough_to_spool_to_disk_still_uploads(self):
        """Above FILE_UPLOAD_MAX_MEMORY_SIZE Django hands the view a
        ``TemporaryUploadedFile`` wrapping an open file handle. The route used to
        call ``request.data.copy()``, which on a multipart QueryDict is a
        *deepcopy* — and that handle cannot be pickled, so every scan-sized
        upload was a 500. See apps/common/request_utils.py.
        """
        spooled = settings.FILE_UPLOAD_MAX_MEMORY_SIZE + 1024
        self.assertLess(spooled, MAX_DOCUMENT_SIZE, 'must be valid, just not in memory')
        response = self.upload_file('scan.pdf', b'0' * spooled, 'application/pdf')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Evidence.objects.get(title='Attachment').file.size, spooled)

    def test_a_multi_valued_field_is_not_passed_through_as_a_list(self):
        """``with_parent`` replaced ``request.data.copy()``, and the obvious
        spelling — ``{**querydict}`` — reads the MultiValueDict's internal lists
        rather than the last value per key, which would send the serializer
        ``['document']`` instead of ``'document'``."""
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{self.finding.id}/upload-evidence/',
            {
                'title': 'Attachment',
                # A form that renders the field twice, or a client that retries
                # an append — either way the parser keeps both values.
                'evidence_type': ['photo', 'document'],
                'file': SimpleUploadedFile('ledger.pdf', b'x'),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Evidence.objects.get(title='Attachment').evidence_type, 'document')

    def test_validation_runs_on_the_plain_evidence_endpoint_too(self):
        """``upload-evidence`` is the path the UI uses, but POST /evidence/ is
        routed and writable, so the field-level validator has to cover both."""
        response = self.as_user(self.auditor).post(
            EVIDENCE_URL,
            {
                'finding': self.finding.id,
                'title': 'Direct',
                'evidence_type': 'document',
                'file': SimpleUploadedFile('script.sh', b'#!/bin/sh'),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)


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

    def _reset_status(self):
        """Put the finding back to `open` between roles.

        These tests assert *who* may call the action, so every role has to face
        the same starting state. Without the reset the first role's success
        leaves the finding resolved, and the transition guard then rejects the
        next four with a 400 — a pass/fail that says nothing about permissions.
        """
        self.finding.status = 'open'
        self.finding.actual_resolution_date = None
        self.finding.save(update_fields=['status', 'actual_resolution_date'])

    def test_resolve_is_gated_by_close_findings(self):
        def resolve(client, role):
            self._reset_status()
            return client.post(f'{self.base}resolve/')

        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 200,
            Role.AUDITEE: 403,
        }, resolve)

    def test_close_is_gated_by_close_findings(self):
        def close(client, role):
            self._reset_status()
            return client.post(f'{self.base}close/')

        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 200,
            Role.AUDITEE: 403,
        }, close)

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

    def test_an_illegal_transition_is_rejected(self):
        """Each action used to assign unconditionally, so a closed finding could
        be closed twice — writing an audit entry and firing a notification for a
        transition that never happened."""
        self.as_user(self.supervisor).post(f'{self.base}close/')
        Notification.objects.all().delete()
        response = self.as_user(self.supervisor).post(f'{self.base}close/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(notification_titles(self.auditor), [])

    def test_dispute_clears_a_stale_resolution_date(self):
        """`reopen` always cleared the date; `dispute` did not, so an unresolved
        finding kept a resolution date — and that date feeds the analytics."""
        self.as_user(self.supervisor).post(f'{self.base}resolve/')
        self.finding.refresh_from_db()
        self.assertIsNotNone(self.finding.actual_resolution_date)
        response = self.as_user(self.auditee).post(f'{self.base}dispute/')
        self.assertEqual(response.status_code, 200, response.data)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'disputed')
        self.assertIsNone(self.finding.actual_resolution_date)


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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-findings-list-test-'))
class FindingListPayloadTest(RoleFixtureMixin, TestCase):
    """The register returns counts; only the detail view nests the collections.

    The list used to embed every evidence record and every comment on every row.
    ``prefetch_related`` kept the query count flat so it never read as an N+1,
    but the payload was unbounded — megabytes to render a table that shows none
    of it.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        self.finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
        )
        for i in range(3):
            Evidence.objects.create(
                finding=self.finding, title=f'Evidence {i}',
                file=SimpleUploadedFile(f'e{i}.txt', b'x', content_type='text/plain'),
                uploaded_by=self.auditor,
            )
        for i in range(2):
            FindingComment.objects.create(
                finding=self.finding, comment=f'Comment {i}', author=self.auditor,
            )
        CorrectiveAction.objects.create(
            finding=self.finding, title='Reconcile the ledger',
            description='x', recommendation='y', owner=self.auditee,
            assigned_by=self.auditor, action_number='CAPA-2026-9001',
            due_date=timezone.now().date(),
        )

    def list_row(self):
        response = self.as_user(self.auditor).get(FINDINGS_URL)
        self.assertEqual(response.status_code, 200)
        return next(r for r in response.data['results'] if r['id'] == self.finding.id)

    def test_the_list_reports_counts_instead_of_nesting_the_collections(self):
        row = self.list_row()
        self.assertNotIn('evidence', row)
        self.assertNotIn('comments', row)
        self.assertEqual(row['evidence_count'], 3)
        self.assertEqual(row['comments_count'], 2)
        self.assertEqual(row['corrective_actions_count'], 1)

    def test_the_three_counts_do_not_inflate_each_other(self):
        """Three joins against the same rows multiply: without ``distinct=True``
        each count comes back as the product of the other two — here 3/2/1 would
        read 6/6/6."""
        row = self.list_row()
        self.assertEqual(
            [row['evidence_count'], row['comments_count'], row['corrective_actions_count']],
            [3, 2, 1],
        )

    def test_retrieve_still_returns_the_full_record(self):
        """Only `list` is slimmed — the detail page must not need a second round
        of requests to show evidence and comments."""
        response = self.as_user(self.auditor).get(f'{FINDINGS_URL}{self.finding.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['evidence']), 3)
        self.assertEqual(len(response.data['comments']), 2)

    def test_the_fields_the_follow_up_page_prefills_from_are_still_there(self):
        """FollowUpPage builds a new CAPA out of the finding picked in its
        dropdown, reading title/description/recommendation straight off this
        list rather than fetching the finding again."""
        row = self.list_row()
        for field in ('title', 'description', 'recommendation', 'finding_number',
                      'severity', 'status', 'target_resolution_date'):
            self.assertIn(field, row, f'{field} is read by a list consumer')

    def test_the_query_count_is_flat_as_rows_are_added(self):
        """The annotations replaced a prefetch of every evidence row and every
        comment on the page. That has to stay one query for the page — a
        per-row ``.count()`` would grow with the register."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = self.as_user(self.auditor)
        with CaptureQueriesContext(connection) as first:
            client.get(FINDINGS_URL)

        for i in range(8):
            extra = make_finding(engagement=self.engagement, identified_by=self.auditor)
            FindingComment.objects.create(
                finding=extra, comment=f'Another {i}', author=self.auditor,
            )
        with CaptureQueriesContext(connection) as second:
            client.get(FINDINGS_URL)

        self.assertEqual(
            len(second.captured_queries), len(first.captured_queries),
            'query count grew with the number of findings',
        )
