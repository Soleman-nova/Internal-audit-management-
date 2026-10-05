"""Role-by-role tests for the findings API.

Covers finding-number generation, assignment notifications, the auditee's own
workflow (comment, evidence, management response, dispute — the actions a plain
WRITE_AUDIT gate used to lock them out of), the publication gate that keeps an
unendorsed finding away from the auditee entirely, the resolve/close/reopen
lifecycle, the read scoping that keeps one department's findings out of another's
register, and the slim list payload that reports counts where the detail view
nests collections.
"""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_engagement, make_failed_procedure, make_finding,
    make_procedure, notification_titles,
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
        # A finding is raised from the procedure that failed, so every create on
        # this endpoint needs one.
        self.failed_procedure = make_failed_procedure(engagement=self.engagement)

    def payload(self, **kwargs):
        data = {
            'engagement': self.engagement.id,
            'procedure': self.failed_procedure.id,
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

    def test_only_the_audit_team_hears_about_a_new_finding(self):
        """Creation notifies the audit side, and stops there.

        The auditee used to be told as well, which announced a finding before
        anyone had reviewed it — and on the common shape where the assigned
        contact *is* the auditee, announced it straight to them. A finding is a
        draft until a supervisor publishes it, and publishing is what brings the
        auditee in; `test_publishing_notifies_the_auditee` covers that half.
        """
        self.as_user(self.auditor).post(FINDINGS_URL, self.payload(
            assigned_to=self.supervisor.id, auditee=self.auditee.id,
        ), format='json')
        self.assertTrue(
            Notification.objects.filter(
                user=self.supervisor, notification_type='finding',
            ).exists(),
            'the audit team was not told about the finding',
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.auditee, notification_type='finding',
            ).exists(),
            'the auditee was told about a finding nobody has published',
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


class FindingProcedureLinkageTest(RoleFixtureMixin, TestCase):
    """A finding is always raised from the procedure that failed.

    The execution-linkage rule: procedures belong to a program, and a finding
    belongs to a procedure that actually ran and found the control wanting.
    Without the parent link a finding is an assertion with no test behind it —
    nothing on the record says which piece of fieldwork produced it.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        self.failed = make_failed_procedure(engagement=self.engagement)

    def payload(self, **kwargs):
        data = {
            'engagement': self.engagement.id,
            'title': 'Segregation of duties not enforced',
            'description': 'The same user both raised and approved the payment.',
            'severity': 'high',
            'category': 'control_deficiency',
        }
        data.update(kwargs)
        return data

    def test_a_finding_without_a_procedure_is_refused(self):
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('procedure', response.data)

    def test_only_a_failed_procedure_can_raise_a_finding(self):
        """A completed step means the control held, so it raises nothing."""
        for status in ('pending', 'in_progress', 'completed', 'not_applicable'):
            with self.subTest(status=status):
                procedure = make_procedure(
                    program=self.failed.program, status=status,
                )
                response = self.as_user(self.auditor).post(
                    FINDINGS_URL,
                    self.payload(procedure=procedure.id), format='json',
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn('procedure', response.data)

    def test_a_procedure_from_another_engagement_is_refused(self):
        other_engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        foreign = make_failed_procedure(engagement=other_engagement)
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(procedure=foreign.id), format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('procedure', response.data)

    def test_a_failed_procedure_of_this_engagement_is_accepted(self):
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(procedure=self.failed.id), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        finding = AuditFinding.objects.get(pk=response.data['id'])
        self.assertEqual(finding.procedure_id, self.failed.id)
        self.assertEqual(finding.engagement_id, self.engagement.id)


class FindingPublishTest(RoleFixtureMixin, TestCase):
    """The supervisor endorses a finding before the auditee ever sees it.

    A finding is the audit team's own draft until a reviewer agrees it stands up.
    Publishing is what starts the auditee's response clock.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        self.finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            auditee=self.auditee, status='draft',
        )

    def publish(self, user):
        return self.as_user(user).post(f'{FINDINGS_URL}{self.finding.id}/publish/')

    def test_publish_is_gated_on_approve_plans(self):
        """The auditor who raised the finding cannot also endorse it."""
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            f'{FINDINGS_URL}{make_finding(
                engagement=self.engagement, identified_by=self.auditor,
                auditee=self.auditee, status="draft",
            ).id}/publish/',
        ))

    def test_publishing_moves_the_finding_to_awaiting_the_auditee(self):
        response = self.publish(self.supervisor)
        self.assertEqual(response.status_code, 200, response.data)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, AuditFinding.AWAITING_AUDITEE)

    def test_publishing_notifies_the_auditee(self):
        self.publish(self.supervisor)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='finding',
            ).exists(),
        )

    def test_publishing_does_not_notify_the_publisher(self):
        self.publish(self.supervisor)
        self.assertEqual(notification_titles(self.supervisor), [])

    def test_publishing_twice_is_refused(self):
        self.assertEqual(self.publish(self.supervisor).status_code, 200)
        self.assertEqual(self.publish(self.supervisor).status_code, 400)

    def test_a_settled_finding_cannot_be_published(self):
        for status in ('closed', 'resolved'):
            with self.subTest(status=status):
                settled = make_finding(
                    engagement=self.engagement, identified_by=self.auditor,
                    status=status,
                )
                response = self.as_user(self.supervisor).post(
                    f'{FINDINGS_URL}{settled.id}/publish/',
                )
                self.assertEqual(response.status_code, 400, response.data)

    def test_responding_to_a_published_finding_moves_it_on(self):
        """The auditee's answer is the event that ends "awaiting response"."""
        self.publish(self.supervisor)
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{self.finding.id}/respond/',
            {'management_response': 'Accounts were revoked on 12 August.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'in_progress')

    def test_a_finding_not_awaiting_a_response_keeps_its_status(self):
        """Revising a live finding's text is not a lifecycle move.

        Its own finding rather than the shared one: `setUp` now hands out a draft,
        which the auditee cannot reach at all, and `awaiting_auditee_response`
        would move on respond by design. `in_progress` is the published state
        where answering is a revision rather than an event.
        """
        live = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            auditee=self.auditee, status='in_progress',
        )
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{live.id}/respond/',
            {'management_response': 'First cut of the response.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        live.refresh_from_db()
        self.assertEqual(live.status, 'in_progress')

    def test_an_auditee_can_dispute_a_published_finding(self):
        self.publish(self.supervisor)
        response = self.as_user(self.auditee).post(f'{FINDINGS_URL}{self.finding.id}/dispute/')
        self.assertEqual(response.status_code, 200, response.data)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'disputed')

    def test_publishing_is_audit_logged(self):
        self.publish(self.supervisor)
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='AuditFinding', object_id=str(self.finding.id),
                action='UPDATE',
            ).exists(),
        )


class FindingUpdateTest(RoleFixtureMixin, TestCase):
    """Re-assignment notifies only the people who are newly on the hook."""

    def setUp(self):
        super().setUp()
        # `in_progress` rather than the fixture default: these tests edit and
        # transition the finding, and resolving needs a state the lifecycle
        # allows out of — `awaiting_auditee_response` only moves on a response.
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
            assigned_to=self.supervisor,
            status='in_progress',
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
        self.assertEqual(self.finding.status, 'in_progress')

    def test_status_change_is_logged_with_the_transition(self):
        self.as_user(self.auditor).post(f'{self.url}resolve/')
        entry = AuditTrail.objects.filter(
            model_name='AuditFinding', object_id=str(self.finding.id), action='UPDATE',
        ).first()
        self.assertEqual(entry.changes, {'status': ['in_progress', 'resolved']})

    def test_auditee_cannot_edit_a_finding_about_them(self):
        response = self.as_user(self.auditee).patch(
            self.url, {'severity': 'low'}, format='json',
        )
        self.assertEqual(response.status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-evidence-test-'))
class FindingResponseTest(RoleFixtureMixin, TestCase):
    """The auditee's side of the conversation: comments, evidence, and their own
    management response.

    All of these inherited the class-level WRITE_AUDIT gate, so the person being
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

    def respond_as(self, user, text='Management accepts the finding and will act.'):
        return self.as_user(user).post(
            f'{FINDINGS_URL}{self.finding.id}/respond/',
            {'management_response': text}, format='json',
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

    # ── Management response ──────────────────────────────────────────────
    # `management_response` is the auditee's own formal position and it feeds the
    # audit report, but the viewset's class-level CanWriteAudit gate meant only
    # the audit team could write it — so the auditor typed the auditee's answer
    # on their behalf. `respond` is the fourth involved-party action.

    def test_named_auditee_can_record_a_management_response(self):
        response = self.respond_as(self.auditee)
        self.assertEqual(response.status_code, 200, response.data)
        self.finding.refresh_from_db()
        self.assertEqual(
            self.finding.management_response,
            'Management accepts the finding and will act.',
        )

    def test_responding_again_replaces_the_previous_wording(self):
        """The auditee revises their position while the finding is open; there
        is no second field, so the endpoint is both create and update."""
        self.respond_as(self.auditee, 'First draft of our position.')
        self.respond_as(self.auditee, 'Revised: the control has been reinstated.')
        self.finding.refresh_from_db()
        self.assertEqual(
            self.finding.management_response,
            'Revised: the control has been reinstated.',
        )

    def test_the_response_does_not_move_the_finding_status(self):
        """Responding is not a lifecycle event — `dispute` is the action for
        disagreement, and status belongs to the audit team's transitions.

        On a finding that is *not* awaiting a response, which is the only case
        where that holds: answering a published finding is what ends
        `awaiting_auditee_response`, and that is asserted separately.
        """
        live = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            assigned_to=self.supervisor, auditee=self.auditee,
            status='in_progress',
        )
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{live.id}/respond/',
            {'management_response': 'Management accepts the finding and will act.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        live.refresh_from_db()
        self.assertEqual(live.status, 'in_progress')

    def test_an_uninvolved_auditee_in_the_same_department_cannot_respond(self):
        response = self.respond_as(self.bystander)
        self.assertEqual(response.status_code, 403)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.management_response, '')

    def test_an_auditee_elsewhere_cannot_respond(self):
        self.assertEqual(self.respond_as(self.outsider).status_code, 404)

    def test_capability_holders_can_record_a_response_on_any_finding(self):
        """An auditor recording a response received by phone or letter is
        legitimate, so the capability branch of the gate stays open."""
        self.assertEqual(self.respond_as(self.auditor).status_code, 200)
        self.assertEqual(self.respond_as(self.manager).status_code, 200)

    def test_a_blank_response_is_refused(self):
        for text in ('', '   \n  '):
            with self.subTest(text=repr(text)):
                response = self.respond_as(self.auditee, text)
                self.assertEqual(response.status_code, 400)
                self.finding.refresh_from_db()
                self.assertEqual(self.finding.management_response, '')

    def test_the_response_is_audit_logged_against_the_finding(self):
        self.respond_as(self.auditee)
        entry = AuditTrail.objects.filter(
            model_name='AuditFinding', object_id=str(self.finding.id),
        ).first()
        self.assertIn('Management response recorded', entry.object_repr)
        self.assertIn('management_response', entry.changes)

    def test_the_response_notifies_the_audit_team_but_not_the_responder(self):
        self.respond_as(self.auditee)
        for recipient in (self.auditor, self.supervisor):
            self.assertTrue(
                Notification.objects.filter(
                    user=recipient, notification_type='finding',
                ).exists(),
                f'{recipient.role} was not told about the management response',
            )
        self.assertEqual(notification_titles(self.auditee), [])

    def test_a_closed_finding_no_longer_accepts_a_response(self):
        self.finding.status = 'closed'
        self.finding.save(update_fields=['status'])
        response = self.respond_as(self.auditee)
        self.assertEqual(response.status_code, 400)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.management_response, '')

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
        # `in_progress`, because this class is about resolve / close / reopen /
        # dispute and `awaiting_auditee_response` — the fixture's default, being
        # the state a freshly published finding sits in — only moves on a response.
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
            assigned_to=self.supervisor,
            auditee=self.auditee,
            status='in_progress',
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
            {'status': ['in_progress', 'resolved']},
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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-publish-gate-test-'))
class FindingPublicationGateTest(RoleFixtureMixin, TestCase):
    """A finding is invisible and inert to its auditee until it is published.

    The supervisor's `publish` action existed and was correctly gated, but the
    auditee scope had no status filter — so the review it represents was
    decorative. The auditee could read the finding, comment on it, attach evidence
    to it, answer it and dispute it from the moment it was typed, and the approval
    step that was supposed to precede all of that had nothing to gate.

    Every path is asserted twice: refused before publication, and reachable after
    it. Without the second half these would pass if the endpoints were simply
    broken for auditees.
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
        self.draft = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            assigned_to=self.auditee, auditee=self.auditee, status='draft',
        )

    def publish(self):
        response = self.as_user(self.supervisor).post(
            f'{FINDINGS_URL}{self.draft.id}/publish/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.draft.refresh_from_db()

    def test_a_draft_is_absent_from_the_list_and_the_detail_route(self):
        response = self.as_user(self.auditee).get(FINDINGS_URL)
        self.assertNotIn(self.draft.id, {row['id'] for row in response.data['results']})
        self.assertEqual(
            self.as_user(self.auditee).get(f'{FINDINGS_URL}{self.draft.id}/').status_code,
            404,
        )

    def test_a_legacy_open_finding_is_hidden_too(self):
        """`open` is pre-publication as well.

        Nothing creates it any more, but rows raised before this rule did, and
        the publish action has always accepted it as a thing to publish *from*.
        Treating it as visible because nothing writes it would leave the gate
        open to any row an admin or a management command puts there.
        """
        legacy = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            assigned_to=self.auditee, auditee=self.auditee, status='open',
        )
        self.assertEqual(
            self.as_user(self.auditee).get(f'{FINDINGS_URL}{legacy.id}/').status_code,
            404,
        )

    def test_the_auditee_actions_are_refused_on_a_draft(self):
        """404, not 403 — `get_object()` cannot find it, so it is not disclosed
        that the finding exists at all."""
        client = self.as_user(self.auditee)
        evidence = Evidence.objects.create(
            finding=self.draft, title='Premature',
            file=SimpleUploadedFile('early.txt', b'x', content_type='text/plain'),
            uploaded_by=self.auditor,
        )
        for label, response in (
            ('retrieve', client.get(f'{FINDINGS_URL}{self.draft.id}/')),
            ('respond', client.post(
                f'{FINDINGS_URL}{self.draft.id}/respond/',
                {'management_response': 'Answering something unpublished.'},
                format='json',
            )),
            ('dispute', client.post(f'{FINDINGS_URL}{self.draft.id}/dispute/')),
            ('comment', client.post(
                f'{FINDINGS_URL}{self.draft.id}/add-comment/',
                {'comment': 'Commenting on something unpublished.'}, format='json',
            )),
            ('evidence', client.get(f'{EVIDENCE_URL}{evidence.id}/download/')),
        ):
            with self.subTest(action=label):
                self.assertEqual(response.status_code, 404, response.data)

        # Nothing landed on the way through.
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.management_response, '')
        self.assertEqual(self.draft.status, 'draft')
        self.assertFalse(FindingComment.objects.filter(finding=self.draft).exists())

    def test_a_capa_cannot_be_proposed_for_a_draft(self):
        """The create gate reads the finding in the payload rather than an object,
        so it does not inherit the queryset's filter and asserts it separately."""
        response = self.as_user(self.auditee).post('/api/corrective/actions/', {
            'finding': self.draft.id,
            'title': 'Premature remediation plan',
            'description': 'Answering a finding nobody has published.',
            'recommendation': 'Wait for the supervisor.',
            'due_date': timezone.now().date() + timezone.timedelta(days=30),
        }, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(
            CorrectiveAction.objects.filter(finding=self.draft).exists(),
        )

    def test_publishing_opens_every_one_of_them(self):
        """The reverse control. Each refusal above has to become reachable, or
        these tests would be satisfied by an endpoint that is broken outright."""
        self.publish()

        self.assertEqual(
            self.as_user(self.auditee).get(f'{FINDINGS_URL}{self.draft.id}/').status_code,
            200,
        )
        listing = self.as_user(self.auditee).get(FINDINGS_URL)
        self.assertIn(
            self.draft.id, {row['id'] for row in listing.data['results']},
        )
        self.assertEqual(
            self.as_user(self.auditee).post(
                f'{FINDINGS_URL}{self.draft.id}/add-comment/',
                {'comment': 'We have corrected the postings.'}, format='json',
            ).status_code,
            201,
        )
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{self.draft.id}/respond/',
            {'management_response': 'Management accepts the finding.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_the_audit_team_still_sees_the_draft(self):
        """The gate is on the auditee, not on the register."""
        for user in (self.admin, self.manager, self.supervisor, self.auditor):
            with self.subTest(role=user.role):
                response = self.as_user(user).get(f'{FINDINGS_URL}{self.draft.id}/')
                self.assertEqual(response.status_code, 200, response.data)


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


class FindingProvenanceAndOverdueTest(RoleFixtureMixin, TestCase):
    """The two facts a finding cannot be read without, derived rather than stored.

    `procedure_label` and `is_overdue` both existed as columns on other models and
    as nothing here: the fieldwork a finding came from, and whether it is past its
    own target date. Neither was written anywhere a page could show it, so a
    register row said what had been found and nothing about where it came from or
    how late it was.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(lead_auditor=self.auditor)
        self.procedure = make_failed_procedure(
            engagement=self.engagement, step_number='3.1',
            title='Agree disbursements to the ledger',
        )

    def detail(self, finding):
        return self.as_user(self.auditor).get(
            f'{FINDINGS_URL}{finding.id}/'
        ).data

    # ── Which fieldwork produced this ──────────────────────────────────────
    def test_the_source_procedure_is_named(self):
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            procedure=self.procedure,
        )
        label = self.detail(finding)['procedure_label']
        self.assertEqual(label, '3.1. Agree disbursements to the ledger')

    def test_a_row_with_no_parent_procedure_says_so_with_a_null(self):
        """Not a placeholder string: a page can tell "none recorded" from a name,
        which matters because the linkage rule post-dates these rows."""
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor, procedure=None,
        )
        self.assertIsNone(self.detail(finding)['procedure_label'])

    def test_the_label_is_on_the_list_row_too(self):
        """The register's split-pane list is where an auditor reads the column."""
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            procedure=self.procedure,
        )
        response = self.as_user(self.auditor).get(FINDINGS_URL)
        row = next(r for r in response.data['results'] if r['id'] == finding.id)
        self.assertEqual(row['procedure_label'], '3.1. Agree disbursements to the ledger')

    # ── Whether it is late ─────────────────────────────────────────────────
    def yesterday(self):
        return timezone.now().date() - timezone.timedelta(days=1)

    def test_a_past_target_date_is_overdue(self):
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            procedure=self.procedure, target_resolution_date=self.yesterday(),
        )
        self.assertTrue(self.detail(finding)['is_overdue'])

    def test_due_today_is_not_overdue(self):
        """Same boundary as the CAPA overdue list: the day itself is still the
        deadline, and flagging it early teaches people to ignore the flag."""
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            procedure=self.procedure, target_resolution_date=timezone.now().date(),
        )
        self.assertFalse(self.detail(finding)['is_overdue'])

    def test_a_settled_finding_is_never_overdue(self):
        """Resolved late is still late, but it is not *late* — it is done, and
        flagging it invites someone to chase work that has been closed out."""
        for status in ('resolved', 'closed'):
            with self.subTest(status=status):
                finding = make_finding(
                    engagement=self.engagement, identified_by=self.auditor,
                    procedure=self.procedure, status=status,
                    target_resolution_date=self.yesterday(),
                )
                self.assertFalse(self.detail(finding)['is_overdue'])

    def test_no_target_date_is_not_a_deadline(self):
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            procedure=self.procedure, target_resolution_date=None,
        )
        self.assertFalse(self.detail(finding)['is_overdue'])

    def test_a_disputed_finding_past_its_date_is_still_overdue(self):
        """A dispute is not an answer: the finding is unsettled, so it is late."""
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            procedure=self.procedure, status='disputed',
            target_resolution_date=self.yesterday(),
        )
        self.assertTrue(self.detail(finding)['is_overdue'])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-finding-auditee-test-'))
class FindingAuditeeResolutionTest(RoleFixtureMixin, TestCase):
    """A finding raised through the register must have someone to answer it.

    The register's create form sends no auditee, `AuditEngagement` had no field to
    inherit one from, and so every finding raised through the UI landed with
    `auditee = NULL` and `assigned_to = NULL`. Nothing failed loudly — the auditee
    scope falls back to `engagement.department`, so the finding still appeared in
    the right department's register — but the object-level gate on respond /
    add-comment / upload-evidence / dispute matches against those two fields, so
    all four 403'd, and `publish` drew its notification recipients from the same
    two NULLs and told nobody. The finding was visible to exactly the people who
    could not act on it.

    The E2E fixtures hid this by naming the auditee by hand at the call site;
    these tests drive the payload shape the *form* actually sends.
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
            supervisor=self.supervisor, auditee=self.auditee,
        )
        self.failed_procedure = make_failed_procedure(engagement=self.engagement)

    def payload(self, **kwargs):
        """What FindingsPage.handleCreateFinding posts: no auditee, no assignee."""
        data = {
            'engagement': self.engagement.id,
            'procedure': self.failed_procedure.id,
            'title': 'Stock issue vouchers unreconciled',
            'description': 'No reconciliation for two months.',
            'severity': 'medium',
            'category': 'operational',
            'recommendation': 'Resume the monthly count.',
        }
        data.update(kwargs)
        return data

    def create(self, **kwargs):
        response = self.as_user(self.auditor).post(
            FINDINGS_URL, self.payload(**kwargs), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return AuditFinding.objects.get(pk=response.data['id'])

    def bare_engagement_finding(self, title):
        """One created against an engagement that names no representative."""
        bare = make_engagement(lead_auditor=self.auditor, department=self.department)
        procedure = make_failed_procedure(engagement=bare)
        response = self.as_user(self.auditor).post(
            FINDINGS_URL,
            {'engagement': bare.id, 'procedure': procedure.id, 'title': title,
             'description': 'Seeded against an engagement with no representative.',
             'severity': 'low', 'category': 'other',
             'recommendation': 'Name a representative.'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return AuditFinding.objects.get(pk=response.data['id'])

    def test_a_new_finding_inherits_the_engagements_auditee(self):
        self.assertEqual(self.create().auditee, self.auditee)

    def test_an_explicit_auditee_wins_over_the_engagements(self):
        other = self.make_user(Role.AUDITEE, department=self.department)
        self.assertEqual(self.create(auditee=other.id).auditee, other)

    def test_an_engagement_without_an_auditee_does_not_break_creation(self):
        """No honest value to inherit, so it stays blank rather than failing or
        inventing an addressee. The engagement form warns about this."""
        self.assertIsNone(
            self.bare_engagement_finding('No representative named').auditee,
        )

    def test_the_inherited_auditee_can_answer_the_finding(self):
        """The dead end itself, end to end: raise it the way the form does,
        endorse it, and confirm the auditee can then act on it.

        All four of these 403'd before the engagement named an auditee — the
        finding was readable and inert.
        """
        finding = self.create()
        published = self.as_user(self.supervisor).post(
            f'{FINDINGS_URL}{finding.id}/publish/',
        )
        self.assertEqual(published.status_code, 200, published.data)

        client = self.as_user(self.auditee)
        self.assertEqual(
            client.post(f'{FINDINGS_URL}{finding.id}/add-comment/',
                        {'comment': 'We have reinstituted the count.'},
                        format='json').status_code,
            201,
        )
        self.assertEqual(
            client.post(f'{FINDINGS_URL}{finding.id}/respond/',
                        {'management_response': 'Count resumed.'},
                        format='json').status_code,
            200,
        )
        self.assertEqual(
            client.post(f'{FINDINGS_URL}{finding.id}/upload-evidence/',
                        {'title': 'Count sheet', 'evidence_type': 'document',
                         'file': SimpleUploadedFile('count.txt', b'counted',
                                                    content_type='text/plain')},
                        format='multipart').status_code,
            201,
        )
        self.assertEqual(
            client.post(f'{FINDINGS_URL}{finding.id}/dispute/').status_code,
            200,
        )

    def test_a_fresh_finding_reads_as_pending_supervisor_review(self):
        """The value stays `draft`; only the label moved. It names the queue the
        finding is sitting in — the supervisor's — rather than the raiser's."""
        finding = self.create()
        self.assertEqual(finding.status, 'draft')
        self.assertEqual(finding.get_status_display(), 'Pending Supervisor Review')

    # ── Who is told ──────────────────────────────────────────────────────

    def test_raising_a_finding_asks_the_engagements_supervisor_to_review_it(self):
        self.create()
        self.assertTrue(
            Notification.objects.filter(
                user=self.supervisor, notification_type='approval_needed',
            ).exists(),
            f'the reviewer was never told: {notification_titles(self.supervisor)}',
        )

    def test_the_reviewer_falls_back_to_the_approvers_when_none_is_named(self):
        """An engagement with no supervisor is an unassigned review, not an
        unreviewable one — `publish` is gated on the capability, so someone can
        still act. Leaving them untold would be the same dead end one level up."""
        self.bare_engagement_finding('Nobody assigned to review')
        # The fixture's supervisor and manager both hold APPROVE_PLANS; the raiser
        # is an auditor, who does not.
        for reviewer in (self.supervisor, self.manager):
            self.assertTrue(
                Notification.objects.filter(
                    user=reviewer, notification_type='approval_needed',
                ).exists(),
                f'{reviewer.role} holds APPROVE_PLANS but was not told',
            )

    def test_the_raiser_is_not_told_to_review_their_own_finding(self):
        """A supervisor may log a finding themselves; the capability is theirs."""
        self.as_user(self.supervisor).post(
            FINDINGS_URL, self.payload(title='Raised by the reviewer'), format='json',
        )
        self.assertEqual(
            Notification.objects.filter(
                user=self.supervisor, notification_type='approval_needed',
            ).count(),
            0,
        )

    def test_publishing_notifies_the_inherited_auditee(self):
        finding = self.create()
        Notification.objects.all().delete()
        self.as_user(self.supervisor).post(f'{FINDINGS_URL}{finding.id}/publish/')
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='finding',
            ).exists(),
            'the person the finding is addressed to was not told it was published',
        )

    def test_publishing_still_notifies_an_engagement_level_auditee(self):
        """Rows stamped before the inheritance existed carry no auditee of their
        own. The engagement's is the next best addressee, and the department's
        auditees the last resort — publishing must not be able to mean
        "published into the void"."""
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor, status='draft',
        )
        self.assertIsNone(finding.auditee)
        Notification.objects.all().delete()
        self.as_user(self.supervisor).post(f'{FINDINGS_URL}{finding.id}/publish/')
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='finding',
            ).exists(),
            'an unaddressed finding was published and nobody was told',
        )
