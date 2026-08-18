"""Role-by-role tests for the audit execution API.

Covers program submit/approve gating, procedure CRUD audit logging and the
``complete`` action (which the UI used to fake), and working-paper upload,
review, download and deletion.
"""
import shutil
import tempfile

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import AuditTrail, Role
from apps.audit_execution.models import AuditProcedure, AuditProgram, WorkingPaper
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_engagement, make_procedure, make_program,
    notification_titles,
)
from apps.notifications.models import Notification

PROGRAMS_URL = '/api/execution/programs/'
PROCEDURES_URL = '/api/execution/procedures/'
PAPERS_URL = '/api/execution/working-papers/'


class AuditProgramRoleAccessTest(RoleFixtureMixin, TestCase):
    """WRITE_AUDIT gates program authoring; reads stay open."""

    def test_every_role_can_list(self):
        make_program(prepared_by=self.auditor)
        self.assert_status_by_role(
            {role: 200 for role in self.users},
            lambda client, role: client.get(PROGRAMS_URL),
        )

    def test_only_write_audit_roles_can_create(self):
        # AuditProgram.engagement is a OneToOne, so each role needs its own.
        engagements = {
            role: make_engagement(lead_auditor=self.auditor) for role in self.users
        }
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(PROGRAMS_URL, {
            'engagement': engagements[role].id,
            'title': f'Program by {role}',
            'objectives': 'Test the key controls.',
        }, format='json'))

    def test_create_records_the_preparer(self):
        response = self.as_user(self.auditor).post(PROGRAMS_URL, {
            'engagement': make_engagement(lead_auditor=self.auditor).id,
            'title': 'Fieldwork Program',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            AuditProgram.objects.get(pk=response.data['id']).prepared_by, self.auditor,
        )

    def test_default_ordering_keeps_pagination_stable(self):
        """Without an explicit ordering the queryset came back in whatever order
        the database chose, so paginating it could repeat or skip rows."""
        for _ in range(3):
            make_program(prepared_by=self.auditor)
        response = self.as_user(self.auditor).get(PROGRAMS_URL)
        timestamps = [row['created_at'] for row in response.data['results']]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))


class AuditProgramSubmitTest(RoleFixtureMixin, TestCase):
    """``submit`` belongs to the people who own the work, plus approvers."""

    def setUp(self):
        super().setUp()
        self.lead = self.make_user(Role.AUDITOR, department=self.department)
        self.engagement = make_engagement(lead_auditor=self.lead)
        self.program = make_program(
            engagement=self.engagement, prepared_by=self.auditor,
        )
        self.url = f'{PROGRAMS_URL}{self.program.id}/submit/'

    def test_preparer_can_submit_and_reviewers_are_notified(self):
        response = self.as_user(self.auditor).post(self.url)
        self.assertEqual(response.status_code, 200)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'submitted')
        for reviewer in (self.manager, self.supervisor):
            self.assertTrue(
                Notification.objects.filter(
                    user=reviewer, notification_type='approval_needed',
                ).exists(),
                f'{reviewer.role} was not asked to review',
            )
        self.assertEqual(notification_titles(self.auditor), [])

    def test_engagement_lead_can_submit(self):
        """The dotted field path in the permission — ``engagement.lead_auditor``
        — is what lets the lead submit a program a colleague drafted."""
        self.assertEqual(self.as_user(self.lead).post(self.url).status_code, 200)

    def test_an_uninvolved_auditor_cannot_submit(self):
        stranger = self.make_user(Role.AUDITOR, department=self.department)
        self.assertEqual(self.as_user(stranger).post(self.url).status_code, 403)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'draft')

    def test_approve_plans_holders_can_submit_any_program(self):
        self.assertEqual(self.as_user(self.supervisor).post(self.url).status_code, 200)

    def test_auditee_cannot_submit(self):
        self.assertEqual(self.as_user(self.auditee).post(self.url).status_code, 403)

    def test_submit_is_audit_logged_with_the_status_change(self):
        self.as_user(self.auditor).post(self.url)
        entry = AuditTrail.objects.filter(
            model_name='AuditProgram', object_id=str(self.program.id), action='UPDATE',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes, {'status': ['draft', 'submitted']})


class AuditProgramApproveTest(RoleFixtureMixin, TestCase):
    """``approve`` needs APPROVE_PLANS — an auditor cannot sign off fieldwork."""

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(lead_auditor=self.auditor)
        self.program = make_program(
            engagement=self.engagement, prepared_by=self.auditor, status='submitted',
        )
        self.url = f'{PROGRAMS_URL}{self.program.id}/approve/'

    def test_approval_stamps_the_reviewer_and_notifies_the_lead(self):
        response = self.as_user(self.supervisor).post(self.url)
        self.assertEqual(response.status_code, 200)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'approved')
        self.assertEqual(self.program.approved_by, self.supervisor)
        self.assertEqual(self.program.reviewed_by, self.supervisor)
        self.assertIsNotNone(self.program.approved_at)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='approved',
            ).exists()
        )

    def test_gated_by_approve_plans(self):
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(self.url))

    def test_approval_is_logged_as_an_approve_action(self):
        self.as_user(self.manager).post(self.url)
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='AuditProgram', object_id=str(self.program.id),
                action='APPROVE',
            ).exists()
        )


class AuditProcedureTest(RoleFixtureMixin, TestCase):
    """Procedure CRUD is real and audit-logged; ``complete`` returns the record."""

    def setUp(self):
        super().setUp()
        self.lead = self.make_user(Role.AUDITOR, department=self.department)
        self.engagement = make_engagement(lead_auditor=self.lead)
        self.program = make_program(engagement=self.engagement, prepared_by=self.auditor)

    def create_payload(self, **kwargs):
        payload = {
            'program': self.program.id,
            'step_number': '1',
            'title': 'Vouch a sample of disbursements',
            'description': 'Agree 25 payments to supporting documentation.',
            'procedure_type': 'substantive',
        }
        payload.update(kwargs)
        return payload

    def test_only_write_audit_roles_can_create(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            PROCEDURES_URL, self.create_payload(step_number=role), format='json',
        ))

    def test_crud_is_audit_logged(self):
        """The UI's delete and status-change handlers used to mutate local state
        and show a success toast without calling the API at all; these three log
        entries are what proves the writes now reach the server."""
        client = self.as_user(self.auditor)
        created = client.post(PROCEDURES_URL, self.create_payload(), format='json')
        procedure_id = created.data['id']

        updated = client.patch(
            f'{PROCEDURES_URL}{procedure_id}/',
            {'title': 'Vouch a larger sample'}, format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            AuditProcedure.objects.get(pk=procedure_id).title, 'Vouch a larger sample',
        )

        deleted = client.delete(f'{PROCEDURES_URL}{procedure_id}/')
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(AuditProcedure.objects.filter(pk=procedure_id).exists())

        actions = list(
            AuditTrail.objects
            .filter(model_name='AuditProcedure', object_id=str(procedure_id))
            .values_list('action', flat=True)
        )
        self.assertCountEqual(actions, ['CREATE', 'UPDATE', 'DELETE'])

    def test_status_change_through_patch_records_the_transition(self):
        procedure = make_procedure(program=self.program)
        self.as_user(self.auditor).patch(
            f'{PROCEDURES_URL}{procedure.id}/', {'status': 'in_progress'}, format='json',
        )
        entry = AuditTrail.objects.filter(
            model_name='AuditProcedure', object_id=str(procedure.id), action='UPDATE',
        ).first()
        self.assertEqual(entry.changes, {'status': ['pending', 'in_progress']})

    def test_complete_stamps_the_finisher_and_returns_the_record(self):
        procedure = make_procedure(program=self.program)
        response = self.as_user(self.auditor).post(
            f'{PROCEDURES_URL}{procedure.id}/complete/',
            {'conclusion': 'No exceptions noted.'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        # The serialized record, not just a message — the client merges
        # completed_by/completed_at into its row without a second round trip.
        self.assertEqual(response.data['id'], procedure.id)
        self.assertEqual(response.data['status'], 'completed')
        self.assertEqual(response.data['completed_by'], self.auditor.id)

        procedure.refresh_from_db()
        self.assertEqual(procedure.completed_by, self.auditor)
        self.assertIsNotNone(procedure.completed_at)
        self.assertEqual(procedure.conclusion, 'No exceptions noted.')

    def test_complete_without_a_body_keeps_the_written_conclusion(self):
        """Completing from the status dropdown sends no body. Blanking the
        conclusion there would quietly destroy fieldwork evidence."""
        procedure = make_procedure(
            program=self.program, conclusion='Tested 25 items, no exceptions.',
        )
        response = self.as_user(self.auditor).post(
            f'{PROCEDURES_URL}{procedure.id}/complete/'
        )
        self.assertEqual(response.status_code, 200)
        procedure.refresh_from_db()
        self.assertEqual(procedure.status, 'completed')
        self.assertEqual(procedure.conclusion, 'Tested 25 items, no exceptions.')

    def test_complete_with_an_empty_conclusion_clears_it_deliberately(self):
        procedure = make_procedure(program=self.program, conclusion='Draft note.')
        self.as_user(self.auditor).post(
            f'{PROCEDURES_URL}{procedure.id}/complete/',
            {'conclusion': ''}, format='json',
        )
        procedure.refresh_from_db()
        self.assertEqual(procedure.conclusion, '')

    def test_complete_notifies_the_engagement_lead(self):
        procedure = make_procedure(program=self.program)
        self.as_user(self.auditor).post(f'{PROCEDURES_URL}{procedure.id}/complete/')
        self.assertTrue(
            Notification.objects.filter(user=self.lead, notification_type='system').exists()
        )

    def test_complete_does_not_notify_the_lead_about_their_own_work(self):
        procedure = make_procedure(program=self.program)
        self.as_user(self.lead).post(f'{PROCEDURES_URL}{procedure.id}/complete/')
        self.assertEqual(notification_titles(self.lead), [])

    def test_auditee_cannot_complete_a_procedure(self):
        procedure = make_procedure(program=self.program)
        response = self.as_user(self.auditee).post(
            f'{PROCEDURES_URL}{procedure.id}/complete/'
        )
        self.assertEqual(response.status_code, 403)
        procedure.refresh_from_db()
        self.assertEqual(procedure.status, 'pending')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-wp-test-'))
class WorkingPaperTest(RoleFixtureMixin, TestCase):
    """Upload, review, download and delete — including the file on disk."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(lead_auditor=self.auditor)

    def upload(self, user, name='sample.txt', body=b'reconciliation evidence'):
        return self.as_user(user).post(PAPERS_URL, {
            'engagement': self.engagement.id,
            'reference': 'WP-1.1',
            'title': 'Bank reconciliation',
            'paper_type': 'workpaper',
            'file': SimpleUploadedFile(name, body, content_type='text/plain'),
        }, format='multipart')

    def test_upload_records_the_preparer(self):
        response = self.upload(self.auditor)
        self.assertEqual(response.status_code, 201, response.data)
        paper = WorkingPaper.objects.get(pk=response.data['id'])
        self.assertEqual(paper.prepared_by, self.auditor)
        self.assertTrue(paper.file)

    def test_auditee_cannot_upload(self):
        self.assertEqual(self.upload(self.auditee).status_code, 403)

    def test_review_is_gated_by_approve_plans(self):
        paper = WorkingPaper.objects.create(
            engagement=self.engagement, reference='WP-2.1',
            title='Payroll sample', prepared_by=self.auditor,
        )
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            f'{PAPERS_URL}{paper.id}/review/', {'review_notes': role}, format='json',
        ))

    def test_review_stamps_the_reviewer_and_notifies_the_preparer(self):
        paper = WorkingPaper.objects.create(
            engagement=self.engagement, reference='WP-3.1',
            title='Fixed asset count', prepared_by=self.auditor,
        )
        response = self.as_user(self.supervisor).post(
            f'{PAPERS_URL}{paper.id}/review/',
            {'review_notes': 'Cross-referenced to the ledger.'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        paper.refresh_from_db()
        self.assertTrue(paper.is_reviewed)
        self.assertEqual(paper.reviewed_by, self.supervisor)
        self.assertEqual(paper.review_notes, 'Cross-referenced to the ledger.')
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='approved',
            ).exists()
        )

    def test_download_sends_the_real_content_type_and_filename(self):
        paper_id = self.upload(self.auditor, name='recon.txt').data['id']
        response = self.as_user(self.auditee).get(f'{PAPERS_URL}{paper_id}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('attachment; filename="', response['Content-Disposition'])
        self.assertIn('recon', response['Content-Disposition'])
        self.assertEqual(response.content, b'reconciliation evidence')

    def test_download_without_a_file_is_a_400(self):
        paper = WorkingPaper.objects.create(
            engagement=self.engagement, reference='WP-4.1',
            title='Placeholder', prepared_by=self.auditor,
        )
        response = self.as_user(self.auditor).get(f'{PAPERS_URL}{paper.id}/download/')
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_the_file_from_storage(self):
        """A deleted working paper must not leave its evidence file behind in
        media/ — the record is gone but the document would still be servable."""
        paper_id = self.upload(self.auditor, name='to-delete.txt').data['id']
        stored_name = WorkingPaper.objects.get(pk=paper_id).file.name
        self.assertTrue(default_storage.exists(stored_name))

        response = self.as_user(self.auditor).delete(f'{PAPERS_URL}{paper_id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WorkingPaper.objects.filter(pk=paper_id).exists())
        self.assertFalse(default_storage.exists(stored_name))
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='WorkingPaper', object_id=str(paper_id), action='DELETE',
            ).exists()
        )

    def test_delete_without_a_file_still_removes_the_record(self):
        paper = WorkingPaper.objects.create(
            engagement=self.engagement, reference='WP-5.1',
            title='No attachment', prepared_by=self.auditor,
        )
        response = self.as_user(self.auditor).delete(f'{PAPERS_URL}{paper.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WorkingPaper.objects.filter(pk=paper.pk).exists())
