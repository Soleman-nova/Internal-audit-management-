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
    RoleFixtureMixin, make_engagement, make_finding, make_procedure, make_program,
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
        # 404 rather than 403: a program on an engagement outside their own
        # department is no longer in the auditee's queryset, so `get_object()`
        # refuses before the capability check is ever reached. The denial is the
        # same, and 404 discloses less — it does not confirm the record exists.
        self.assertEqual(self.as_user(self.auditee).post(self.url).status_code, 404)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'draft')

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

    def test_a_program_cannot_be_approved_by_writing_the_field(self):
        """The side door `approve` was built to be the only way through.

        `approve` gates on APPROVE_PLANS, stamps who signed off and when, writes an
        APPROVE entry to the trail and notifies the preparer. A PATCH carrying
        `status` did none of that, so an auditor could approve their own fieldwork
        program — and attribute the approval to a chosen user — leaving the record
        indistinguishable from one the gate actually passed.
        """
        response = self.as_user(self.auditor).patch(
            f'{PROGRAMS_URL}{self.program.id}/',
            {'status': 'approved', 'approved_by': self.manager.id,
             'approved_at': '2026-01-01T00:00:00Z'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'submitted')
        self.assertIsNone(self.program.approved_by)
        self.assertIsNone(self.program.approved_at)

    def test_program_content_edits_still_work(self):
        """The positive control: only the lifecycle fields were closed off."""
        response = self.as_user(self.auditor).patch(
            f'{PROGRAMS_URL}{self.program.id}/',
            {'title': 'Revised fieldwork program'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.program.refresh_from_db()
        self.assertEqual(self.program.title, 'Revised fieldwork program')


class ProgramCompletionPercentTest(RoleFixtureMixin, TestCase):
    """A program's progress counts every step that reached an outcome.

    `failed` and `not_applicable` are fieldwork *results*, not unfinished work:
    one of them is the very thing that produces a finding. Counting `completed`
    alone left a program whose tests legitimately failed permanently short of
    100%, so the board read as "still working" long after the fieldwork ended.
    """

    def setUp(self):
        super().setUp()
        self.program = make_program(prepared_by=self.auditor)

    def percent(self):
        return self.as_user(self.auditor).get(
            f'{PROGRAMS_URL}{self.program.id}/'
        ).data['completion_percent']

    def test_no_steps_reads_as_zero(self):
        self.assertEqual(self.percent(), 0)

    def test_a_pending_step_is_not_progress(self):
        make_procedure(program=self.program, status='pending')
        make_procedure(program=self.program, status='in_progress')
        self.assertEqual(self.percent(), 0)

    def test_failed_and_not_applicable_are_finished_work(self):
        make_procedure(program=self.program, status='completed')
        make_procedure(program=self.program, status='failed')
        make_procedure(program=self.program, status='not_applicable')
        make_procedure(program=self.program, status='pending')
        self.assertEqual(self.percent(), 75)

    def test_a_program_whose_steps_all_failed_still_reaches_full(self):
        """The regression this fixes, stated as its own case.

        A failed test is not an unfinished one. Reading it as unfinished meant the
        auditor got no signal that the fieldwork was done — only that something,
        somewhere, was still outstanding.
        """
        make_procedure(program=self.program, status=AuditProcedure.FAILED)
        make_procedure(program=self.program, status=AuditProcedure.FAILED)
        self.assertEqual(self.percent(), 100)


class ProgramCompletionTest(RoleFixtureMixin, TestCase):
    """`complete` is the only route to `completed`, and it checks the fieldwork.

    `status` is read-only on the serializer, so without this route a program could
    not be closed at all — and with the PATCH open it could be closed by anyone,
    unchecked, which is worse: the execution board locks every procedure control
    on `completed`, so a half-finished program closed that way read as finished
    and immutable.
    """

    def setUp(self):
        super().setUp()
        self.lead = self.make_user(Role.AUDITOR, department=self.department)
        self.engagement = make_engagement(lead_auditor=self.lead)
        self.program = make_program(
            engagement=self.engagement, prepared_by=self.auditor, status='approved',
        )
        self.url = f'{PROGRAMS_URL}{self.program.id}/complete/'

    def mark(self, status, step='1'):
        return make_procedure(program=self.program, status=status, step_number=step)

    def test_a_step_still_pending_blocks_it_and_writes_nothing(self):
        self.mark('completed', '1')
        self.mark('pending', '2')

        response = self.as_user(self.auditor).post(self.url)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('1 procedure(s)', response.data['detail'])
        self.assertIn('2', response.data['detail'])
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'approved')

    def test_in_progress_also_blocks(self):
        self.mark('in_progress')
        response = self.as_user(self.auditor).post(self.url)
        self.assertEqual(response.status_code, 400, response.data)

    def test_failed_and_inapplicable_steps_let_it_close(self):
        """Both are fieldwork outcomes. One of them is what raises a finding."""
        self.mark(AuditProcedure.FAILED, '1')
        self.mark('not_applicable', '2')
        self.mark('completed', '3')

        response = self.as_user(self.auditor).post(self.url)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'completed')
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'completed')

    def test_a_program_with_no_procedures_closes(self):
        """Nothing outstanding is nothing outstanding — an empty program is a
        legitimate state, and refusing to close it would strand it forever."""
        self.assertEqual(self.as_user(self.auditor).post(self.url).status_code, 200)

    def test_the_refusal_elides_long_lists(self):
        for n in range(12):
            self.mark('pending', str(n))
        response = self.as_user(self.auditor).post(self.url)
        self.assertEqual(response.status_code, 400)
        # Twelve named would be unreadable; the count carries the rest.
        self.assertIn('12 procedure(s)', response.data['detail'])
        self.assertIn('…', response.data['detail'])

    def test_completion_notifies_the_lead(self):
        self.mark('completed')
        self.as_user(self.auditor).post(self.url)
        self.assertTrue(Notification.objects.filter(user=self.lead).exists())

    def test_the_lead_is_not_told_about_their_own_closure(self):
        self.mark('completed')
        self.as_user(self.lead).post(self.url)
        self.assertEqual(notification_titles(self.lead), [])

    def test_it_is_audit_logged_with_the_status_change(self):
        self.mark('completed')
        self.as_user(self.auditor).post(self.url)
        entry = AuditTrail.objects.filter(
            model_name='AuditProgram', object_id=str(self.program.id), action='UPDATE',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes, {'status': ['approved', 'completed']})

    def test_an_auditee_cannot_complete_a_program(self):
        self.mark('completed')
        self.assertEqual(self.as_user(self.auditee).post(self.url).status_code, 403)

    # ── reopen ─────────────────────────────────────────────────────────────
    def test_a_completed_program_can_be_reopened(self):
        self.mark('completed')
        self.as_user(self.auditor).post(self.url)

        response = self.as_user(self.auditor).post(
            f'{PROGRAMS_URL}{self.program.id}/reopen/'
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'approved')

    def test_reopen_refuses_a_program_that_is_not_completed(self):
        response = self.as_user(self.auditor).post(
            f'{PROGRAMS_URL}{self.program.id}/reopen/'
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.program.refresh_from_db()
        self.assertEqual(self.program.status, 'approved')


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

    def test_an_executable_cannot_be_attached_as_a_working_paper(self):
        """WorkingPaper.file was a bare FileField. See apps/common/validators.py."""
        response = self.upload(self.auditor, name='tool.exe', body=b'MZ\x90\x00')
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)
        self.assertFalse(WorkingPaper.objects.filter(reference='WP-1.1').exists())

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
        response = self.as_user(self.auditor).get(f'{PAPERS_URL}{paper_id}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('attachment; filename="', response['Content-Disposition'])
        self.assertIn('recon', response['Content-Disposition'])
        self.assertEqual(response.content, b'reconciliation evidence')

    def test_auditee_cannot_download_a_working_paper(self):
        """Working papers are the audit team's own evidence, so the auditee
        scoping has to reach the download action, not just the list.

        The file is streamed through the API specifically so /media/ is not an
        open side door; a scoped list with an unscoped download would be the same
        leak by another route.
        """
        paper_id = self.upload(self.auditor, name='recon.txt').data['id']
        response = self.as_user(self.auditee).get(f'{PAPERS_URL}{paper_id}/download/')
        self.assertEqual(response.status_code, 404)

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


class ProcedureFailureIsAnnouncedTest(RoleFixtureMixin, TestCase):
    """A failed step is told to the engagement lead, like a completed one.

    `complete` announced its outcome; nothing announced the other end of fieldwork.
    That is the asymmetry that mattered: a step that passed needs nobody's
    attention, while a step that failed is the trigger event for raising a finding,
    and the lead had to notice a finding appear in a different register to learn
    their own test had failed.
    """

    def setUp(self):
        super().setUp()
        self.lead = self.make_user(Role.AUDITOR, department=self.department)
        self.engagement = make_engagement(lead_auditor=self.lead)
        self.program = make_program(
            engagement=self.engagement, prepared_by=self.auditor,
        )

    def mark_failed(self, procedure, user):
        return self.as_user(user).patch(
            f'{PROCEDURES_URL}{procedure.id}/', {'status': AuditProcedure.FAILED},
            format='json',
        )

    def test_marking_a_step_failed_notifies_the_lead(self):
        procedure = make_procedure(program=self.program)
        self.mark_failed(procedure, self.auditor)
        titles = notification_titles(self.lead)
        self.assertEqual(len(titles), 1, titles)
        self.assertIn(procedure.title, titles[0])

    def test_ruling_a_step_inapplicable_also_notifies(self):
        """The other terminal outcome a lead needs to hear about.

        A step ruled inapplicable is off the board without being answered, so it
        never produces a finding — and never appears on any completion count the
        lead is looking at either.
        """
        procedure = make_procedure(program=self.program)
        self.as_user(self.auditor).patch(
            f'{PROCEDURES_URL}{procedure.id}/', {'status': 'not_applicable'},
            format='json',
        )
        self.assertTrue(notification_titles(self.lead))

    def test_the_lead_is_not_told_about_their_own_failure(self):
        procedure = make_procedure(program=self.program)
        self.mark_failed(procedure, self.lead)
        self.assertEqual(notification_titles(self.lead), [])

    def test_moving_a_step_back_to_in_progress_is_silent(self):
        """Only the end of a step is news; the state it rests in between is not."""
        procedure = make_procedure(program=self.program, status='in_progress')
        self.as_user(self.auditor).patch(
            f'{PROCEDURES_URL}{procedure.id}/', {'status': 'pending'}, format='json',
        )
        self.assertEqual(notification_titles(self.lead), [])

    def test_the_transition_is_still_audit_logged(self):
        procedure = make_procedure(program=self.program)
        self.mark_failed(procedure, self.auditor)
        entry = AuditTrail.objects.filter(
            model_name='AuditProcedure', object_id=str(procedure.id), action='UPDATE',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes, {'status': ['pending', AuditProcedure.FAILED]})


class ProcedureFindingsLinkTest(RoleFixtureMixin, TestCase):
    """The reverse of the linkage the finding's create form enforces.

    A finding must hang off a failed procedure, so every finding in the register
    has a parent step. Nothing ran that relationship backwards: on the execution
    board a failed step looked exactly like a failed step nobody had written up,
    and the only way to find out was to go and look in the findings register.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(lead_auditor=self.auditor)
        self.program = make_program(
            engagement=self.engagement, prepared_by=self.auditor,
        )
        self.procedure = make_procedure(
            program=self.program, step_number='3.1',
            title='Agree disbursements to the ledger',
        )

    def row(self):
        return self.as_user(self.auditor).get(
            f'{PROCEDURES_URL}{self.procedure.id}/'
        ).data

    def test_a_step_with_no_findings_reports_zero(self):
        self.assertEqual(self.row()['findings_count'], 0)

    def test_the_count_follows_the_findings_raised_against_the_step(self):
        for index in range(2):
            make_finding(
                engagement=self.engagement, identified_by=self.auditor,
                procedure=self.procedure, title=f'Finding {index}',
            )
        self.assertEqual(self.row()['findings_count'], 2)

    def test_findings_on_other_steps_are_not_counted(self):
        other = make_procedure(program=self.program, step_number='3.2', title='Other step')
        make_finding(
            engagement=self.engagement, identified_by=self.auditor, procedure=other,
        )
        self.assertEqual(self.row()['findings_count'], 0)
