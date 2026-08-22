"""Role-by-role tests for the reporting API.

Covers the MANAGE_SETTINGS gate on templates, the asynchronous generation
contract (201 + ``generating``, then ``ready``/``failed`` from the background
job), the ``fail_stuck_reports`` sweep that closes out compiles a restart
abandoned, a real compile of each of the three formats, the authenticated
``export`` download, and the ``analytics`` month buckets — including the
February and year-boundary cases the old ``30 * i`` day arithmetic got wrong.
"""
import datetime
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_action, make_engagement, make_finding,
    make_risk_assessment,
)
from apps.findings.models import AuditFinding
from apps.notifications.models import Notification
from apps.reports.models import GeneratedReport, ReportTemplate

TEMPLATES_URL = '/api/reports/templates/'
GENERATED_URL = '/api/reports/generated/'


class ReportTemplateTest(RoleFixtureMixin, TestCase):
    """Templates shape every report, so writing them is MANAGE_SETTINGS."""

    def payload(self, **kwargs):
        data = {
            'name': 'Engagement Report',
            'template_type': 'engagement',
            'description': 'Standard fieldwork report layout.',
            'is_default': True,
        }
        data.update(kwargs)
        return data

    def test_every_role_can_read_the_templates(self):
        ReportTemplate.objects.create(name='Board Report', template_type='board')
        self.assert_status_by_role(
            {role: 200 for role in self.users},
            lambda client, role: client.get(TEMPLATES_URL),
        )

    def test_only_manage_settings_roles_can_create(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 403,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            TEMPLATES_URL, self.payload(name=f'Template for {role}'), format='json',
        ))

    def test_only_manage_settings_roles_can_edit(self):
        template = ReportTemplate.objects.create(name='KPI', template_type='kpi')
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 403,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.patch(
            f'{TEMPLATES_URL}{template.id}/', {'description': role}, format='json',
        ))

    def test_create_records_the_author_and_is_audit_logged(self):
        response = self.as_user(self.manager).post(
            TEMPLATES_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            ReportTemplate.objects.get(pk=response.data['id']).created_by, self.manager,
        )
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='ReportTemplate', object_id=str(response.data['id']),
                action='CREATE',
            ).exists()
        )

    def test_the_template_list_is_ordered(self):
        """ReportTemplate has no Meta.ordering, so paginating an unordered
        queryset could repeat or skip templates between pages."""
        for name in ('First', 'Second', 'Third'):
            ReportTemplate.objects.create(name=name, template_type='findings')
        response = self.as_user(self.auditor).get(TEMPLATES_URL)
        stamps = [row['created_at'] for row in response.data['results']]
        self.assertEqual(stamps, sorted(stamps, reverse=True))


class GeneratedReportRequestTest(RoleFixtureMixin, TestCase):
    """Requesting a report returns immediately with ``generating``.

    The compile is queued on a background thread, so every test here patches the
    enqueue helper: a real thread would touch the test database outside the
    transaction the test case rolls back. The queueing itself goes through
    ``transaction.on_commit``, so a test that asserts on it has to open
    ``captureOnCommitCallbacks``.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        patcher = mock.patch('apps.reports.jobs.enqueue_report_generation')
        self.enqueue = patcher.start()
        self.addCleanup(patcher.stop)

    def payload(self, **kwargs):
        data = {
            'title': 'Q3 Finance Engagement Report',
            'format': 'pdf',
            'engagement': self.engagement.id,
        }
        data.update(kwargs)
        return data

    def test_only_write_audit_roles_can_request_a_report(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            GENERATED_URL, self.payload(title=f'Report for {role}'), format='json',
        ))

    def test_the_request_returns_before_the_compile_starts(self):
        """The API used to compile in-band, which blocked the worker for the
        length of a 1000-row PDF and made ``generating`` unobservable."""
        # captureOnCommitCallbacks because the view queues the compile through
        # `transaction.on_commit`, and a TestCase rolls its transaction back
        # rather than committing — so the callback would never run.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.as_user(self.auditor).post(
                GENERATED_URL, self.payload(), format='json',
            )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['status'], 'generating')
        report = GeneratedReport.objects.get(pk=response.data['id'])
        self.assertEqual(report.generated_by, self.auditor)
        self.assertFalse(report.file)
        self.enqueue.assert_called_once()
        self.assertEqual(self.enqueue.call_args.args[0].pk, report.pk)

    def test_nothing_is_queued_for_a_report_that_was_never_committed(self):
        """The enqueue hangs off ``on_commit``, so a rolled-back create must not
        leave a thread compiling a report whose row does not exist. Without that
        the worker races the commit and can fail to find its own report.
        """
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self.as_user(self.auditor).post(
                        GENERATED_URL, self.payload(), format='json',
                    )
                    raise RuntimeError('something later in the request failed')
        self.enqueue.assert_not_called()
        self.assertFalse(GeneratedReport.objects.exists())

    def test_export_before_the_file_exists_is_a_400(self):
        """The frontend polls until ``ready``; a Download click that races the
        job must say so rather than serve an empty file."""
        report_id = self.as_user(self.auditor).post(
            GENERATED_URL, self.payload(), format='json',
        ).data['id']
        response = self.as_user(self.auditor).get(f'{GENERATED_URL}{report_id}/export/')
        self.assertEqual(response.status_code, 400)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-report-test-'))
class ReportGenerationTest(RoleFixtureMixin, TestCase):
    """The compile itself, called synchronously — one test per format."""

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
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            assigned_to=self.supervisor, auditee=self.auditee,
        )
        make_action(finding=finding, owner=self.auditee, assigned_by=self.auditor)
        make_risk_assessment(department=self.department, assessed_by=self.auditor)

    def generate(self, report_format):
        from apps.reports.views import GeneratedReportViewSet

        report = GeneratedReport.objects.create(
            title=f'Engagement Report {report_format}',
            format=report_format,
            engagement=self.engagement,
            generated_by=self.auditor,
        )
        GeneratedReportViewSet().generate_report_file(report)
        report.refresh_from_db()
        return report

    def assert_compiled(self, report, extension):
        self.assertEqual(report.status, 'ready', report.error_message)
        self.assertTrue(report.file, 'no file was attached to the report')
        self.assertTrue(report.file.name.endswith(extension), report.file.name)
        self.assertGreater(report.file.size, 0)
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='GeneratedReport', object_id=str(report.id), action='EXPORT',
            ).exists()
        )

    def test_a_pdf_report_compiles_and_flips_to_ready(self):
        self.assert_compiled(self.generate('pdf'), '.pdf')

    def test_an_excel_report_compiles_and_flips_to_ready(self):
        """Every non-PDF report used to die with UnboundLocalError before writing
        a byte: the severity tally was computed inside the ``pdf`` branch but read
        by the other two, so the row stuck on ``generating`` forever."""
        self.assert_compiled(self.generate('excel'), '.xlsx')

    def test_a_word_report_compiles_and_flips_to_ready(self):
        self.assert_compiled(self.generate('word'), '.docx')

    def test_the_filename_carries_a_real_extension(self):
        """The filename used to be built from the format key — ``.excel`` and
        ``.word`` are not file types, so ``export``'s ``mimetypes.guess_type``
        returned None and the browser was handed octet-stream and a file it could
        not open."""
        for report_format, expected in (
            ('excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('word', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        ):
            with self.subTest(format=report_format):
                report = self.generate(report_format)
                response = self.as_user(self.auditor).get(
                    f'{GENERATED_URL}{report.id}/export/'
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], expected)

    def test_export_serves_the_compiled_file(self):
        report = self.generate('pdf')
        response = self.as_user(self.auditor).get(f'{GENERATED_URL}{report.id}/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="', response['Content-Disposition'])
        # A real PDF, not an error page rendered into the download.
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_a_report_with_no_engagement_still_compiles(self):
        """Findings-summary and board reports are requested EEU-wide, with no
        engagement attached — the generator has to cope with an empty scope."""
        from apps.reports.views import GeneratedReportViewSet

        report = GeneratedReport.objects.create(
            title='EEU-wide Findings Summary', format='pdf', generated_by=self.manager,
        )
        GeneratedReportViewSet().generate_report_file(report)
        report.refresh_from_db()
        self.assertEqual(report.status, 'ready', report.error_message)
        self.assertTrue(report.file)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-report-job-test-'))
class ReportJobTest(RoleFixtureMixin, TestCase):
    """The background worker body, called in-thread so the test can assert on it."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.report = GeneratedReport.objects.create(
            title='Q3 Board Report', format='pdf',
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            generated_by=self.auditor,
        )

    def run_job(self):
        from apps.reports.jobs import _generate_report_task

        _generate_report_task(self.report.id, {})
        self.report.refresh_from_db()

    def test_a_successful_job_notifies_the_requester(self):
        self.run_job()
        self.assertEqual(self.report.status, 'ready', self.report.error_message)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='report_ready',
            ).exists()
        )

    def test_the_ready_notification_deep_links_to_the_row(self):
        self.run_job()
        notification = Notification.objects.get(
            user=self.auditor, notification_type='report_ready',
        )
        self.assertEqual(notification.link, f'/reports?id={self.report.id}')

    def test_a_failing_compile_is_recorded_rather_than_raised(self):
        """A background thread has nowhere to raise to: an unhandled exception
        would leave the row stuck on ``generating`` forever and the user
        polling an empty status."""
        from apps.reports.views import GeneratedReportViewSet

        with mock.patch.object(
            GeneratedReportViewSet, 'generate_report_file',
            side_effect=RuntimeError('LibreOffice is not installed'),
        ):
            self.run_job()

        self.assertEqual(self.report.status, 'failed')
        self.assertIn('LibreOffice is not installed', self.report.error_message)
        notification = Notification.objects.get(
            user=self.auditor, notification_type='system',
        )
        self.assertIn('failed', notification.title.lower())
        self.assertIn('LibreOffice is not installed', notification.message)

    def test_a_missing_report_does_not_crash_the_worker(self):
        from apps.reports.jobs import _generate_report_task

        report_id = self.report.id
        self.report.delete()
        _generate_report_task(report_id, {})  # must not raise
        self.assertFalse(GeneratedReport.objects.filter(pk=report_id).exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-report-adhoc-test-'))
class AdHocExportTest(RoleFixtureMixin, TestCase):
    """``generate-pdf`` / ``generate-excel`` — the one-click table exports."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def test_generate_pdf_streams_and_persists_the_file(self):
        response = self.as_user(self.auditor).post(
            f'{GENERATED_URL}generate-pdf/',
            {'title': 'Findings Extract', 'content': 'Twelve open findings.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

        report = GeneratedReport.objects.get(title='Findings Extract')
        self.assertEqual(report.status, 'ready')
        self.assertEqual(report.generated_by, self.auditor)
        self.assertTrue(report.file)

    def test_generate_excel_persists_a_row_the_export_action_can_serve(self):
        """Streaming the bytes back without saving left no row in the Generated
        Reports list and nothing for ``export`` to serve later, so an Excel
        export existed only in the browser's download folder."""
        response = self.as_user(self.auditor).post(
            f'{GENERATED_URL}generate-excel/',
            {
                'title': 'CAPA Register',
                'headers': ['Action', 'Owner', 'Due'],
                'rows': [['CAPA-00001', 'Finance', '2026-09-30']],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

        report = GeneratedReport.objects.get(title='CAPA Register')
        self.assertEqual(report.format, 'excel')
        self.assertTrue(report.file)

        served = self.as_user(self.auditor).get(f'{GENERATED_URL}{report.id}/export/')
        self.assertEqual(served.status_code, 200)
        # xlsx is a zip container.
        self.assertTrue(served.content.startswith(b'PK'))

    def test_ad_hoc_exports_are_gated_by_write_audit(self):
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 200,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            f'{GENERATED_URL}generate-pdf/', {'title': f'Extract {role}'}, format='json',
        ))


class FailStuckReportsCommandTest(RoleFixtureMixin, TestCase):
    """``fail_stuck_reports`` — the recovery sweep for abandoned compiles.

    Generation runs on a ``daemon=True`` thread, so a restart kills it without
    recording anything and the row keeps ``generating`` forever while the
    frontend polls a status that will never change. The command gives those rows
    a terminal state.
    """

    def stuck_report(self, minutes_ago, status='generating', **kwargs):
        """A report whose request timestamp is pushed into the past.

        ``generated_at`` is ``auto_now_add``, so it cannot be passed to
        ``create()`` — the value has to be written back with an UPDATE.
        """
        report = GeneratedReport.objects.create(
            title=kwargs.pop('title', 'Q3 Board Report'),
            format='pdf', status=status,
            generated_by=kwargs.pop('generated_by', self.auditor),
            **kwargs,
        )
        GeneratedReport.objects.filter(pk=report.pk).update(
            generated_at=timezone.now() - datetime.timedelta(minutes=minutes_ago),
        )
        report.refresh_from_db()
        return report

    def run_command(self, **options):
        out = StringIO()
        call_command('fail_stuck_reports', stdout=out, stderr=StringIO(), **options)
        return out.getvalue()

    def test_a_report_stuck_past_the_timeout_is_failed_and_the_requester_told(self):
        report = self.stuck_report(minutes_ago=45)
        self.run_command()
        report.refresh_from_db()
        self.assertEqual(report.status, 'failed')
        self.assertIn('did not complete', report.error_message)
        notification = Notification.objects.get(
            user=self.auditor, notification_type='system',
        )
        self.assertIn('failed', notification.title.lower())
        self.assertEqual(notification.link, f'/reports?id={report.id}')

    def test_a_report_still_inside_the_timeout_is_left_alone(self):
        """The timeout has to outlast the slowest real compile. Sweeping up a
        live job would replace a spinner with a lie."""
        report = self.stuck_report(minutes_ago=5)
        self.run_command()
        report.refresh_from_db()
        self.assertEqual(report.status, 'generating')
        self.assertFalse(Notification.objects.exists())

    def test_finished_reports_are_never_touched(self):
        ready = self.stuck_report(minutes_ago=500, status='ready', title='Done')
        failed = self.stuck_report(minutes_ago=500, status='failed', title='Broken')
        self.run_command()
        ready.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual(ready.status, 'ready')
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.error_message, '')

    def test_a_second_run_finds_nothing(self):
        """Idempotent, because it is meant to be scheduled: the first run moves
        the rows off ``generating``, so a re-run must not re-notify."""
        self.stuck_report(minutes_ago=45)
        self.run_command()
        self.run_command()
        self.assertEqual(Notification.objects.count(), 1)

    def test_the_timeout_is_configurable(self):
        report = self.stuck_report(minutes_ago=45)
        self.run_command(minutes=90)
        report.refresh_from_db()
        self.assertEqual(report.status, 'generating')
        self.run_command(minutes=15)
        report.refresh_from_db()
        self.assertEqual(report.status, 'failed')

    def test_dry_run_reports_without_writing(self):
        report = self.stuck_report(minutes_ago=45)
        output = self.run_command(dry_run=True)
        self.assertIn(str(report.id), output)
        self.assertIn('Would fail 1', output)
        report.refresh_from_db()
        self.assertEqual(report.status, 'generating')
        self.assertFalse(Notification.objects.exists())

    def test_a_nonsense_timeout_is_refused_rather_than_sweeping_everything(self):
        """``--minutes 0`` would put the cutoff at "now" and fail reports that
        were enqueued this second, whose threads are running perfectly well."""
        report = self.stuck_report(minutes_ago=0)
        with self.assertRaises(CommandError):
            call_command('fail_stuck_reports', minutes=0, stdout=StringIO())
        report.refresh_from_db()
        self.assertEqual(report.status, 'generating')


class AnalyticsTest(RoleFixtureMixin, TestCase):
    """``analytics`` — the six-month chart the reports page renders.

    The month buckets used to be built by stepping back ``30 * i`` days, which
    skips February entirely and returns a 31-day month twice, so the chart
    silently lost and duplicated buckets. These tests pin the calendar
    arithmetic across both cases.
    """

    URL = f'{GENERATED_URL}analytics/'

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )

    def finding_on(self, when, **kwargs):
        """A finding stamped at a fixed instant.

        ``created_at`` is ``auto_now_add``, so it cannot be passed to
        ``create()`` — the value has to be written back with an UPDATE.
        """
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor, **kwargs
        )
        AuditFinding.objects.filter(pk=finding.pk).update(
            created_at=timezone.make_aware(datetime.datetime(*when, 12, 0)),
        )
        return finding

    def analytics_at(self, year, month, day, user=None):
        """Call the endpoint as though today were the given date."""
        frozen = timezone.make_aware(datetime.datetime(year, month, day, 9, 0))
        with mock.patch('django.utils.timezone.now', return_value=frozen):
            response = self.as_user(user or self.auditor).get(self.URL)
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_it_returns_exactly_six_calendar_months(self):
        data = self.analytics_at(2026, 4, 15)
        self.assertEqual(
            [row['month'] for row in data['monthly_findings']],
            ['Nov 2025', 'Dec 2025', 'Jan 2026', 'Feb 2026', 'Mar 2026', 'Apr 2026'],
        )

    def test_february_is_not_skipped(self):
        """The month a 30-day step always jumped over."""
        self.finding_on((2026, 2, 14))
        self.finding_on((2026, 2, 27))
        data = self.analytics_at(2026, 4, 15)
        buckets = {row['month']: row['count'] for row in data['monthly_findings']}
        self.assertEqual(buckets['Feb 2026'], 2)
        self.assertEqual(buckets['Mar 2026'], 0)

    def test_it_crosses_the_year_boundary(self):
        data = self.analytics_at(2026, 1, 20)
        self.assertEqual(
            [row['month'] for row in data['monthly_findings']],
            ['Aug 2025', 'Sep 2025', 'Oct 2025', 'Nov 2025', 'Dec 2025', 'Jan 2026'],
        )

    def test_a_finding_lands_in_its_own_month_only(self):
        """The boundary a 30-day window blurs: the last day of one month and the
        first of the next must not share a bucket."""
        self.finding_on((2025, 12, 31))
        self.finding_on((2026, 1, 1))
        buckets = {
            row['month']: row['count']
            for row in self.analytics_at(2026, 1, 20)['monthly_findings']
        }
        self.assertEqual(buckets['Dec 2025'], 1)
        self.assertEqual(buckets['Jan 2026'], 1)

    def test_a_month_with_no_findings_is_still_a_bucket(self):
        """Zero-count months have to be present, or the chart's x-axis collapses
        and two non-adjacent months are drawn side by side."""
        data = self.analytics_at(2026, 4, 15)
        self.assertEqual(len(data['monthly_findings']), 6)
        self.assertTrue(all(row['count'] == 0 for row in data['monthly_findings']))

    def test_it_groups_findings_and_actions_for_the_charts(self):
        self.finding_on((2026, 4, 2), severity='critical')
        self.finding_on((2026, 4, 3), severity='critical')
        self.finding_on((2026, 4, 4), severity='low')
        data = self.analytics_at(2026, 4, 15)
        by_severity = {
            row['severity']: row['count'] for row in data['findings_by_severity']
        }
        self.assertEqual(by_severity['critical'], 2)
        self.assertEqual(by_severity['low'], 1)
        by_type = {
            row['engagement_type']: row['count'] for row in data['engagements_by_type']
        }
        self.assertEqual(by_type['financial'], 1)

    def test_every_role_can_read_the_analytics(self):
        """Aggregate counts only — no record-level data, so this is the one
        reporting endpoint an auditee can reach."""
        for user in self.users.values():
            with self.subTest(role=user.role):
                self.analytics_at(2026, 4, 15, user=user)
