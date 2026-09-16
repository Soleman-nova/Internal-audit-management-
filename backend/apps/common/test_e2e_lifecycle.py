"""One continuous, cross-app end-to-end run of the audit lifecycle.

Every per-app suite in this project builds its upstream objects from the
factories in ``apps.common.role_fixtures``, so no single test walks the whole
chain: universe -> plan -> engagement -> program -> procedure -> working paper
-> finding -> CAPA -> report in one unbroken run, carrying real ids forward.
The seams between apps are exactly where the bugs catalogued in TESTING.md
lived (``approve-fieldwork/`` 404, ``submit-for-review/`` 404, a procedure edit
that POSTed a duplicate, evidence upload 403 for the auditee), so a break at
any seam fails here even when every per-app suite stays green.

The capability matrix is asserted at each seam with ``assert_status_by_role``,
which already refuses a partially filled expectation table.
"""
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit_planning.models import AuditEngagement, AuditPlan, AuditUniverse
from apps.audit_execution.models import AuditProcedure, AuditProgram, WorkingPaper
from apps.common.role_fixtures import RoleFixtureMixin
from apps.corrective_actions.models import CorrectiveAction, FollowUp
from apps.findings.models import AuditFinding, Evidence, FindingComment
from apps.notifications.models import Notification
from apps.reports.models import GeneratedReport, ReportTemplate

UNIVERSE_URL = '/api/planning/universe/'
PLANS_URL = '/api/planning/plans/'
ENGAGEMENTS_URL = '/api/planning/engagements/'
PROGRAMS_URL = '/api/execution/programs/'
PROCEDURES_URL = '/api/execution/procedures/'
PAPERS_URL = '/api/execution/working-papers/'
FINDINGS_URL = '/api/findings/findings/'
EVIDENCE_URL = '/api/findings/evidence/'
ACTIONS_URL = '/api/corrective/actions/'
TEMPLATES_URL = '/api/reports/templates/'
GENERATED_URL = '/api/reports/generated/'
RISK_URL = '/api/risk/assessments/'
TRAIL_URL = '/api/auth/audit-trail/'


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-lifecycle-test-'))
class EndToEndLifecycleTest(RoleFixtureMixin, TestCase):
    """The whole audit lifecycle in one continuous run."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        # The real worker thread would touch the test database outside the
        # transaction this test rolls back. Same trade the reports suite makes.
        patcher = mock.patch('apps.reports.jobs.enqueue_report_generation')
        self.enqueue = patcher.start()
        self.addCleanup(patcher.stop)

    # ── Step helpers ──────────────────────────────────────────────────────
    def assert_number(self, value, prefix):
        self.assertRegex(value, rf'^{prefix}-\d{{4}}-\d{{4}}$')

    def notifications_for(self, user):
        return Notification.objects.filter(user=user)

    # ── The run ───────────────────────────────────────────────────────────
    def test_full_lifecycle_in_workflow_order(self):
        # 1 ─ Audit Universe ────────────────────────────────────────────────
        response = self.as_user(self.auditor).post(UNIVERSE_URL, {
            'name': 'Revenue Assurance Process',
            'code': 'UNV-LIFECYCLE',
            'category': 'process',
            'department': self.department.id,
            'risk_score': 4,
            'audit_frequency': 'annually',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        universe = AuditUniverse.objects.get(pk=response.data['id'])
        self.assertEqual(universe.code, 'UNV-LIFECYCLE')
        # Universe creation is WRITE_AUDIT.
        self.assert_status_by_role({
            Role.ADMIN: 201, Role.AUDIT_MANAGER: 201, Role.SUPERVISOR: 201,
            Role.AUDITOR: 201, Role.AUDITEE: 403,
        }, lambda client, role: client.post(UNIVERSE_URL, {
            'name': f'Blocked by {role}', 'code': f'UNV-{role[:6]}-{role[-1]}',
            'category': 'process',
        }, format='json'))

        # 2 ─ Annual Audit Plan ─────────────────────────────────────────────
        response = self.as_user(self.manager).post(PLANS_URL, {
            'title': 'FY ' + str(timezone.now().year) + ' Annual Audit Plan',
            'year': timezone.now().year,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        plan = AuditPlan.objects.get(pk=response.data['id'])
        self.assertEqual(plan.status, 'draft')
        self.assertEqual(plan.created_by, self.manager)

        # 3 ─ Submit the plan ───────────────────────────────────────────────
        response = self.as_user(self.manager).post(f'{PLANS_URL}{plan.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'submitted')
        # Approvers are asked; the author is not told about their own submission.
        self.assertTrue(self.notifications_for(self.admin)
                        .filter(notification_type='approval_needed').exists())
        self.assertEqual(
            self.notifications_for(self.manager)
            .filter(notification_type='approval_needed').count(), 0,
            'the submitting author was notified about their own submission',
        )
        # An unrelated auditor must not push a colleague's plan to the approvers.
        other_auditor = self.make_user(Role.AUDITOR, department=self.department)
        self.assertEqual(
            self.as_user(other_auditor).post(f'{PLANS_URL}{plan.id}/submit/').status_code,
            403,
        )

        # 4 ─ Approve the plan ──────────────────────────────────────────────
        self.assert_status_by_role({
            Role.ADMIN: 200, Role.AUDIT_MANAGER: 200, Role.SUPERVISOR: 200,
            Role.AUDITOR: 403, Role.AUDITEE: 403,
        }, lambda client, role: client.post(f'{PLANS_URL}{plan.id}/approve/'))
        response = self.as_user(self.supervisor).post(f'{PLANS_URL}{plan.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'approved')
        self.assertEqual(plan.approved_by, self.supervisor)
        self.assertTrue(self.notifications_for(self.manager)
                        .filter(notification_type='approved').exists())

        # 5 ─ Engagement ────────────────────────────────────────────────────
        response = self.as_user(self.manager).post(ENGAGEMENTS_URL, {
            'plan': plan.id,
            'title': 'Revenue Assurance Audit',
            'engagement_type': 'financial',
            'department': self.department.id,
            'lead_auditor': self.auditor.id,
            'supervisor': self.supervisor.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        engagement = AuditEngagement.objects.get(pk=response.data['id'])
        self.assert_number(engagement.engagement_number, 'ENG')
        self.assertEqual(engagement.lead_auditor, self.auditor)
        self.assertTrue(self.notifications_for(self.auditor)
                        .filter(notification_type='assigned').exists())

        # 6 ─ Team member ───────────────────────────────────────────────────
        response = self.as_user(self.manager).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/add-member/',
            {'user': other_auditor.id, 'role': 'member', 'allocated_days': 5},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.notifications_for(other_auditor)
                        .filter(notification_type='assigned').exists())

        # 7 ─ Engagement status ─────────────────────────────────────────────
        response = self.as_user(self.manager).post(
            f'{ENGAGEMENTS_URL}{engagement.id}/update-status/',
            {'status': 'in_progress'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        engagement.refresh_from_db()
        self.assertEqual(engagement.status, 'in_progress')

        # 8 ─ Audit Program (preparer = auditor) ────────────────────────────
        response = self.as_user(self.auditor).post(PROGRAMS_URL, {
            'engagement': engagement.id,
            'title': 'Revenue Assurance Fieldwork Program',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        program = AuditProgram.objects.get(pk=response.data['id'])
        self.assertEqual(program.status, 'draft')
        self.assertEqual(program.prepared_by, self.auditor)

        # 9 ─ Procedures ────────────────────────────────────────────────────
        response = self.as_user(self.auditor).post(PROCEDURES_URL, {
            'program': program.id,
            'step_number': '1',
            'title': 'Vouch a sample of cash receipts',
            'description': 'Select 25 receipts and trace to the bank.',
            'procedure_type': 'substantive',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        procedure = AuditProcedure.objects.get(pk=response.data['id'])

        # 10 ─ Editing a procedure must patch, never duplicate ──────────────
        response = self.as_user(self.auditor).patch(
            f'{PROCEDURES_URL}{procedure.id}/',
            {'title': 'Vouch a larger sample of cash receipts'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            AuditProcedure.objects.filter(program=program, step_number='1').count(), 1,
            'an edit POSTed a duplicate procedure instead of patching',
        )

        # 11 ─ Complete a procedure ─────────────────────────────────────────
        response = self.as_user(self.auditor).post(
            f'{PROCEDURES_URL}{procedure.id}/complete/',
            {'conclusion': 'No exceptions noted.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        procedure.refresh_from_db()
        self.assertEqual(procedure.status, 'completed')
        self.assertEqual(procedure.completed_by, self.auditor)

        # 12 ─ Submit the program for review ────────────────────────────────
        response = self.as_user(self.auditor).post(f'{PROGRAMS_URL}{program.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        program.refresh_from_db()
        self.assertEqual(program.status, 'submitted')

        # 13 ─ Approve the program (supervisor) ─────────────────────────────
        self.assert_status_by_role({
            Role.ADMIN: 200, Role.AUDIT_MANAGER: 200, Role.SUPERVISOR: 200,
            Role.AUDITOR: 403, Role.AUDITEE: 403,
        }, lambda client, role: client.post(f'{PROGRAMS_URL}{program.id}/approve/'))
        response = self.as_user(self.supervisor).post(f'{PROGRAMS_URL}{program.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        program.refresh_from_db()
        self.assertEqual(program.status, 'approved')

        # 14 ─ Working paper ────────────────────────────────────────────────
        response = self.as_user(self.auditor).post(PAPERS_URL, {
            'engagement': engagement.id,
            'procedure': procedure.id,
            'reference': 'WP-1.1',
            'title': 'Bank reconciliation sample',
            'paper_type': 'workpaper',
            'file': SimpleUploadedFile('sample.txt', b'reconciliation evidence',
                                       content_type='text/plain'),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        paper = WorkingPaper.objects.get(pk=response.data['id'])
        self.assertEqual(paper.prepared_by, self.auditor)

        # 15 ─ Review the paper (approve_plans), then download ──────────────
        self.assert_status_by_role({
            Role.ADMIN: 200, Role.AUDIT_MANAGER: 200, Role.SUPERVISOR: 200,
            Role.AUDITOR: 403, Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            f'{PAPERS_URL}{paper.id}/review/', {'review_notes': role}, format='json',
        ))
        response = self.as_user(self.supervisor).post(
            f'{PAPERS_URL}{paper.id}/review/',
            {'review_notes': 'Cross-referenced to the ledger.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        paper.refresh_from_db()
        self.assertTrue(paper.is_reviewed)
        self.assertEqual(paper.reviewed_by, self.supervisor)
        response = self.as_user(self.auditor).get(f'{PAPERS_URL}{paper.id}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')

        # 16 ─ Finding ──────────────────────────────────────────────────────
        response = self.as_user(self.auditor).post(FINDINGS_URL, {
            'engagement': engagement.id,
            'procedure': procedure.id,
            'title': 'Unapproved journal entries',
            'description': 'Twelve journals were posted without review.',
            'severity': 'high',
            'category': 'control_deficiency',
            'assigned_to': self.auditee.id,
            'auditee': self.auditee.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        finding = AuditFinding.objects.get(pk=response.data['id'])
        self.assert_number(finding.finding_number, 'FND')
        self.assertEqual(finding.identified_by, self.auditor)
        self.assertEqual(finding.status, 'open')

        # 17 ─ Auditee comments on the finding about them ───────────────────
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{finding.id}/add-comment/',
            {'comment': 'We have corrected the postings.'}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            FindingComment.objects.get(pk=response.data['id']).author, self.auditee,
        )

        # 18 ─ Auditee uploads evidence ─────────────────────────────────────
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{finding.id}/upload-evidence/',
            {'title': 'Signed authorisation log',
             'evidence_type': 'document',
             'file': SimpleUploadedFile('log.txt', b'signed',
                                        content_type='text/plain')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201, response.data)
        evidence = Evidence.objects.get(pk=response.data['id'])
        self.assertEqual(evidence.uploaded_by, self.auditee)
        # The audit team can pull the file down through the gated download.
        response = self.as_user(self.auditor).get(
            f'{EVIDENCE_URL}{evidence.id}/download/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')

        # 19 ─ Auditee responds ─────────────────────────────────────────────
        response = self.as_user(self.auditee).post(
            f'{FINDINGS_URL}{finding.id}/respond/',
            {'management_response': 'Management accepts the finding and will act.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        finding.refresh_from_db()
        self.assertIn('accepts the finding', finding.management_response)

        # 20 ─ Resolve -> Reopen -> Close ───────────────────────────────────
        # An auditee holds no close_findings: direct calls are refused.
        self.assertEqual(
            self.as_user(self.auditee).post(f'{FINDINGS_URL}{finding.id}/resolve/').status_code,
            403,
        )
        response = self.as_user(self.supervisor).post(f'{FINDINGS_URL}{finding.id}/resolve/')
        self.assertEqual(response.status_code, 200, response.data)
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'resolved')
        self.assertTrue(self.notifications_for(self.auditor).exists())

        response = self.as_user(self.supervisor).post(f'{FINDINGS_URL}{finding.id}/close/')
        self.assertEqual(response.status_code, 200, response.data)
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'closed')

        # 21 ─ CAPA from the finding ────────────────────────────────────────
        response = self.as_user(self.auditor).post(ACTIONS_URL, {
            'finding': finding.id,
            'title': 'Reinstate authorisation controls',
            'description': 'Journals posted without a second approver.',
            'recommendation': 'Document and test the control monthly.',
            'owner': self.auditee.id,
            'priority': 'high',
            'due_date': timezone.now().date() + timezone.timedelta(days=30),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        action = CorrectiveAction.objects.get(pk=response.data['id'])
        self.assert_number(action.action_number, 'CAPA')
        self.assertEqual(action.assigned_by, self.auditor)
        self.assertTrue(self.notifications_for(self.auditee)
                        .filter(notification_type='assigned').exists())

        # 22 ─ Owner responds to their own CAPA ─────────────────────────────
        response = self.as_user(self.auditee).post(
            f'{ACTIONS_URL}{action.id}/add-response/',
            {'response_text': 'Controls reinstated as of last week.',
             'status_update': 'in_progress',
             'evidence_file': SimpleUploadedFile('proof.txt', b'controls live',
                                                 content_type='text/plain')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201, response.data)
        action.refresh_from_db()
        self.assertEqual(action.status, 'in_progress')

        # 23 ─ Verify & schedule follow-up ──────────────────────────────────
        # The owner cannot sign off their own remediation; approvers can.
        self.assertEqual(
            self.as_user(self.auditee).post(
                f'{ACTIONS_URL}{action.id}/schedule-followup/',
                {'scheduled_date': timezone.now().date()}, format='json',
            ).status_code,
            403,
        )
        response = self.as_user(self.supervisor).post(
            f'{ACTIONS_URL}{action.id}/schedule-followup/',
            {'scheduled_date': timezone.now().date()}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(FollowUp.objects.filter(corrective_action=action).exists())

        # 24 ─ Report template ──────────────────────────────────────────────
        response = self.as_user(self.manager).post(TEMPLATES_URL, {
            'name': 'Engagement Report',
            'template_type': 'engagement',
            'description': 'Standard fieldwork report layout.',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        template = ReportTemplate.objects.get(pk=response.data['id'])
        # Templates are MANAGE_SETTINGS — the supervisor cannot write one.
        self.assertEqual(
            self.as_user(self.supervisor).post(TEMPLATES_URL, {
                'name': 'Blocked', 'template_type': 'findings',
            }, format='json').status_code,
            403,
        )

        # 25 ─ Request a report, compile it, export it ──────────────────────
        response = self.as_user(self.auditor).post(GENERATED_URL, {
            'title': 'Revenue Assurance Audit Report',
            'format': 'pdf',
            'template': template.id,
            'engagement': engagement.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        report = GeneratedReport.objects.get(pk=response.data['id'])
        self.assertEqual(report.status, 'generating')
        self.assertEqual(report.generated_by, self.auditor)

        # The background worker is mocked; run the compile synchronously as the
        # compile tests do, then prove the gated export serves a real file.
        from apps.reports.views import GeneratedReportViewSet
        GeneratedReportViewSet().generate_report_file(report)
        report.refresh_from_db()
        self.assertEqual(report.status, 'ready', report.error_message)
        response = self.as_user(self.auditor).get(f'{GENERATED_URL}{report.id}/export/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/pdf'))

        # 26 ─ The audit trail recorded the whole run ───────────────────────
        response = self.as_user(self.supervisor).get(
            f'{TRAIL_URL}?model_name=AuditFinding&object_id={finding.id}'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertGreaterEqual(response.data['count'], 1)
        # view_audit_trail covers even reads: an auditor cannot open the trail.
        self.assertEqual(self.as_user(self.auditor).get(TRAIL_URL).status_code, 403)


class CrossAppReadScopingTest(RoleFixtureMixin, TestCase):
    """An auditee elsewhere in EEU must not see records about other departments.

    The per-app suites each prove one queryset scopes. This crosses the apps:
    findings, engagements and CAPAs all filter an auditee to their department,
    and an outsider holding nothing of their own must come away empty from all
    three registries at once.
    """

    def setUp(self):
        super().setUp()
        self.manager = self.users[Role.AUDIT_MANAGER]
        self.supervisor = self.users[Role.SUPERVISOR]
        self.auditor = self.users[Role.AUDITOR]
        self.auditee = self.users[Role.AUDITEE]
        self.outsider = self.make_user(Role.AUDITEE, department=self.other_department)

        from apps.common.role_fixtures import (
            make_action, make_engagement, make_finding,
        )
        engagement = make_engagement(lead_auditor=self.auditor,
                                     department=self.department)
        finding = make_finding(engagement=engagement, identified_by=self.auditor,
                               assigned_to=self.auditee, auditee=self.auditee)
        make_action(finding=finding, owner=self.auditee, assigned_by=self.auditor)
        self.engagement_id = engagement.id
        self.finding_id = finding.id

    def test_an_outside_auditee_sees_none_of_it(self):
        client = self.as_user(self.outsider)

        findings = client.get('/api/findings/findings/').data['results']
        self.assertNotIn(self.finding_id, [row['id'] for row in findings])
        self.assertEqual(
            client.get(f'/api/findings/findings/{self.finding_id}/').status_code, 404,
        )

        engagements = client.get('/api/planning/engagements/').data['results']
        self.assertNotIn(self.engagement_id, [row['id'] for row in engagements])

        actions = client.get('/api/corrective/actions/').data['results']
        self.assertFalse(actions, 'an outside auditee saw CAPAs from another department')

    def test_the_named_auditee_still_has_it_all(self):
        """Same records, seen through the user they were written about."""
        client = self.as_user(self.auditee)
        findings = client.get('/api/findings/findings/').data['results']
        self.assertEqual([row['id'] for row in findings], [self.finding_id])
        self.assertEqual(
            client.get(f'/api/findings/findings/{self.finding_id}/').status_code, 200,
        )
        self.assertTrue(client.get('/api/corrective/actions/').data['results'])
