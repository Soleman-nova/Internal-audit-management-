"""Role-by-role tests for the reporting API.

Covers the MANAGE_SETTINGS gate on templates, the asynchronous generation
contract (201 + ``generating``, then ``ready``/``failed`` from the background
job), the ``fail_stuck_reports`` sweep that closes out compiles a restart
abandoned, a real compile of each of the three formats, the authenticated
``export`` download, and the ``analytics`` month buckets — including the
February and year-boundary cases the old ``30 * i`` day arithmetic got wrong.

The compile tests also read the generated files back: the objectives/scope
resolution (engagement, else the program, else a written placeholder) is asserted
through the Word and Excel output, the PDF's cover text is recovered by inflating
its FlateDecode streams, and the table formatting the overflow fix introduced
(wrapped Excel cells, pinned Word columns) is asserted on the files themselves.
"""
import datetime
import re
import shutil
import tempfile
import zlib
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
    make_program, make_risk_assessment,
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

    def generate(self, report_format, engagement=None):
        from apps.reports.views import GeneratedReportViewSet

        report = GeneratedReport.objects.create(
            title=f'Engagement Report {report_format}',
            format=report_format,
            engagement=engagement or self.engagement,
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

    # ── Reading the generated files back ────────────────────────────
    # Both defects these cover shipped because the old fixture asserted only that
    # each format *compiled* — a report with a blank objectives section and a
    # title painting over the next column compiles perfectly well.

    def word_text(self, report):
        """Every paragraph in the .docx, as one string."""
        from docx import Document

        return '\n'.join(p.text for p in Document(report.file.path).paragraphs)

    def excel_values(self, report):
        """Every string cell in the .xlsx, across all sheets."""
        from openpyxl import load_workbook

        workbook = load_workbook(report.file.path)
        return [
            cell.value
            for sheet in workbook.worksheets
            for row in sheet.iter_rows()
            for cell in row
            if isinstance(cell.value, str)
        ]

    def content_text(self, report):
        """The readable text of the Word or Excel report."""
        if report.format == 'word':
            return self.word_text(report)
        return '\n'.join(self.excel_values(report))

    def pdf_text(self, report):
        """The page content of a reportlab PDF, decoded.

        reportlab writes each page's content stream as ``[/ASCII85Decode
        /FlateDecode]``, so the drawn text is only visible after taking both
        layers off. No PDF-reading library is installed (pypdf/pdfminer are absent
        from requirements.txt), so this unwraps the streams by hand — enough to
        prove a string was drawn, and no more: it says nothing about *where* on the
        page it landed, so PDF layout is still checked by eye (see TESTING.md).
        """
        import base64

        raw = report.file.read()
        chunks = []
        for match in re.finditer(rb'stream\r?\n(.*?)endstream', raw, re.S):
            data = match.group(1).rstrip(b'\r\n')
            # The base85 terminator sits flush against `endstream`.
            data = data.removesuffix(b'~>')
            try:
                chunks.append(zlib.decompress(base64.a85decode(data)).decode('latin-1'))
            except (zlib.error, ValueError):
                continue  # another filter's stream — fonts and images land here
        return ''.join(chunks)

    def pdf_drawn_text(self, report):
        """Every string a reportlab PDF actually draws, concatenated.

        The content stream is a sequence of operators, so the words have to be
        lifted out of their `(...) Tj` operands — the rest is positioning and
        colour, and it is full of letters (`Tj`, `Tm`, `BT`) that would otherwise
        land in the middle of the text being searched for. Parenthesized literals
        are the only strings in a content stream, and the backslash escapes in them
        are PDF string syntax rather than content.
        """
        literals = re.findall(r'\((?:\\.|[^\\()])*\)', self.pdf_text(report), re.S)
        return ''.join(
            re.sub(r'\\(?=[()\\])', '', literal[1:-1]) for literal in literals
        )

    @staticmethod
    def comparable(text):
        """Letters and digits only.

        reportlab breaks a line into several `Tj` fragments, so the drawn strings
        are compared stripped of everything that is not a letter or a digit.
        """
        return re.sub(r'[^A-Za-z0-9]', '', text)

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

    # ── Audit Objectives / Audit Scope (reported blank in every report) ──

    def test_the_report_prints_the_engagement_objectives(self):
        """The engagement is the record the report documents, so its copy wins."""
        self.engagement.objectives = 'Confirm metering revenue is complete.'
        self.engagement.scope = 'Every metering installation in the region.'
        self.engagement.save(update_fields=['objectives', 'scope'])

        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format))
                self.assertIn('Confirm metering revenue is complete.', text)
                self.assertIn('Every metering installation in the region.', text)

    def test_the_objectives_fall_back_to_the_audit_program(self):
        """Engagements were never the only place these live: an auditor writes them
        on the program, which is the plan of attack for the same engagement."""
        make_program(
            engagement=self.engagement,
            objectives='Program: test the revenue cycle end to end.',
            scope='Program: head office and every branch counter.',
        )

        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format))
                self.assertIn('Program: test the revenue cycle end to end.', text)
                self.assertIn('Program: head office and every branch counter.', text)

    def test_the_engagement_objectives_win_over_the_programs(self):
        self.engagement.objectives = 'Engagement objective'
        self.engagement.save(update_fields=['objectives'])
        make_program(engagement=self.engagement, objectives='Program objective')

        text = self.content_text(self.generate('word'))
        self.assertIn('Engagement objective', text)
        self.assertNotIn('Program objective', text)

    def test_a_report_with_no_objectives_says_so_rather_than_showing_nothing(self):
        """The old default could never fire. `engagement_info.get('objectives',
        default)` returns '' for a key that is present with an empty value, so the
        section rendered an empty paragraph and the report read as broken rather
        than as missing input.
        """
        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format))
                self.assertIn('No specific objectives have been recorded', text)
                self.assertIn('No scope has been recorded', text)

    def test_the_pdf_carries_its_objectives_too(self):
        """All three formats read the same two resolved variables, but only Word and
        Excel can be read back conveniently — so the PDF gets its own check."""
        self.engagement.objectives = 'Verify metering revenue cycle controls'
        self.engagement.save(update_fields=['objectives'])

        report = self.generate('pdf')
        self.assert_compiled(report, '.pdf')
        self.assertIn(
            self.comparable('Verify metering revenue cycle controls'),
            self.comparable(self.pdf_drawn_text(report)),
        )

    # ── Table formatting ────────────────────────────────────────────

    def test_pdf_cells_escape_their_text(self):
        """The direct statement of the rule the two tests below depend on.

        Asserted on the cell rather than on a compiled document because a
        `Paragraph` is the only place the escaping is visible: `_pdf_cell` returns
        a Paragraph holding the escaped source, and reportlab then renders `&lt;`
        as `<`. Passing the text through raw compiles just as happily and quietly
        draws the wrong words.
        """
        from reportlab.lib.styles import getSampleStyleSheet

        from apps.reports.views import _pdf_cell

        cell = _pdf_cell('R&D <legacy> upgrade', getSampleStyleSheet()['Normal'])
        self.assertEqual(cell.text, 'R&amp;D &lt;legacy&gt; upgrade')

    def test_a_finding_title_with_markup_is_not_mangled_in_the_pdf(self):
        """A tag-looking title must reach the page intact.

        Measured on reportlab 4.5.1: handed `R&D <legacy> upgrade` unescaped, the
        Paragraph reads `<legacy>` as an unknown tag and draws `R&D; upgrade` — no
        exception, so the report is ``ready`` and quietly wrong. The title is drawn
        twice (once in the findings table cell, once in the detailed description
        below it), so the intact text appearing only once is what says a cell let
        the markup through.
        """
        make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            title='R&D <legacy> upgrade',
            recommendation='Replace the A&B feed before <Q4>.',
            condition='The A&B feed was patched without a change record.',
        )

        report = self.generate('pdf')
        self.assert_compiled(report, '.pdf')
        drawn = self.comparable(self.pdf_drawn_text(report))
        title = self.comparable('R&D <legacy> upgrade')
        self.assertIn(title, drawn)
        self.assertEqual(
            drawn.count(title), 2,
            'the table cell did not draw the title intact — expected it in both the '
            'findings table and the detailed description',
        )

    def test_a_capa_title_with_markup_is_not_mangled_in_the_pdf(self):
        """The CAPA table interpolates the same kind of free text, and its detail
        block below it prints the action's own description and recommendation."""
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            title='Metering & billing controls',
        )
        action_title = 'Reconcile <metering> & billing'
        make_action(
            finding=finding, owner=self.auditee, assigned_by=self.auditor,
            title=action_title,
            description='Rebuild the A&B reconciliation <monthly>.',
        )

        report = self.generate('pdf')
        self.assert_compiled(report, '.pdf')
        drawn = self.comparable(self.pdf_drawn_text(report))
        title = self.comparable(action_title)
        self.assertIn(title, drawn)
        self.assertEqual(
            drawn.count(title), 2,
            'the CAPA table cell did not draw the title intact — expected it in both '
            'the CAPA table and the detailed description',
        )

    def test_the_excel_tables_wrap_their_long_columns(self):
        """Excel clips text against a non-empty neighbour rather than overflowing,
        so an unwrapped title is cut off at the column edge."""
        from openpyxl import load_workbook

        long_title = ('Metering revenue reconciliation is performed monthly without '
                      'independent review or supporting evidence')
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor, title=long_title,
        )
        make_action(
            finding=finding, owner=self.auditee, assigned_by=self.auditor,
            title=long_title,
        )

        report = self.generate('excel')
        workbook = load_workbook(report.file.path)

        for sheet_name in ('Findings', 'CAPA'):
            with self.subTest(sheet=sheet_name):
                wrapped = [
                    cell for row in workbook[sheet_name].iter_rows()
                    for cell in row if cell.value == long_title
                ]
                self.assertTrue(wrapped, f'{sheet_name} does not carry the title')
                for cell in wrapped:
                    self.assertTrue(
                        cell.alignment.wrap_text,
                        f'{sheet_name}!{cell.coordinate} is not wrapped',
                    )
                    self.assertEqual(cell.alignment.vertical, 'top')

    def test_the_excel_detail_blocks_style_the_cells_they_write(self):
        """These six lines wrote the detail text to column C and then set the font on
        column A, so the text was left unstyled."""
        from openpyxl import load_workbook

        make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            condition='No independent review was performed.',
        )

        report = self.generate('excel')
        sheet = load_workbook(report.file.path)['Findings']
        detail = [
            cell for row in sheet.iter_rows() for cell in row
            if isinstance(cell.value, str) and cell.value.startswith('Condition: ')
        ]
        self.assertTrue(detail, 'the detail block was not written')
        for cell in detail:
            with self.subTest(cell=cell.coordinate):
                self.assertEqual(cell.column_letter, 'C')
                # The default openpyxl font carries no explicit size; the report's
                # normal_font is 10pt.
                self.assertEqual(cell.font.size, 10)

    def test_the_word_tables_pin_their_column_widths(self):
        """Word auto-fits by default, which sizes a 7- or 8-column table to its
        content — i.e. wider than the page. The findings and CAPA tables are pinned
        to the width the page actually has.
        """
        from docx import Document

        report = self.generate('word')
        document = Document(report.file.path)
        # Identified by their header row, not by column count: the risk table also
        # has 8 columns and is deliberately left to auto-fit (short values only).
        wide = [
            table for table in document.tables
            if 'Title' in [cell.text for cell in table.rows[0].cells]
        ]
        self.assertEqual(len(wide), 2, 'expected the findings and CAPA tables')

        section = document.sections[0]
        usable = section.page_width - section.left_margin - section.right_margin
        for table in wide:
            with self.subTest(columns=len(table.columns)):
                self.assertFalse(table.autofit)
                for row in table.rows:
                    self.assertTrue(
                        all(cell.width for cell in row.cells),
                        'a column has no explicit width',
                    )
                    self.assertLessEqual(sum(cell.width for cell in row.cells), usable)

    # ── Material the report left out ────────────────────────────────
    # A corrective action is only as distributable as the finding it answers, so
    # one whose finding is still Pending Supervisor Review is kept out of the
    # report. What the report also used to do was *deny* it: the section printed
    # "No corrective actions have been assigned", which the lead auditor knew to
    # be false, because the register applies that same exclusion to auditees only
    # and had just shown them the action.

    def unendorsed_case(self):
        """An engagement whose only finding is unendorsed, with an action against
        it. A second engagement rather than another finding on the fixture's, so
        the withheld row is the only row and the count is unambiguous."""
        engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        finding = make_finding(
            engagement=engagement, identified_by=self.auditor, auditee=self.auditee,
            status='draft',
        )
        action = make_action(
            finding=finding, owner=self.auditee, assigned_by=self.auditor,
            action_number='CAPA-90001', title='Reinstate the unendorsed control',
        )
        return engagement, action

    def test_an_unendorsed_actions_finding_is_named_as_the_reason(self):
        """Both the disclosure and the reason, in the two formats whose text is
        exact. The reason matters: the action's own status is what a reader would
        guess at, and it is the finding that is unendorsed."""
        engagement, action = self.unendorsed_case()

        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format, engagement=engagement))
                self.assertNotIn(
                    action.action_number, text,
                    'an unendorsed finding\'s remedy reached a downloadable report',
                )
                self.assertIn('Not included in this report', text)
                self.assertIn(
                    '1 corrective action whose finding has not yet been endorsed',
                    text,
                )
                self.assertNotIn(
                    'No corrective actions have been assigned', text,
                    'the report denied an action that exists',
                )

    def test_the_pdf_carries_the_disclosure_too(self):
        """All three formats read the same two statements, but only Word and Excel
        can be read back conveniently — so the PDF gets its own check."""
        engagement, action = self.unendorsed_case()

        report = self.generate('pdf', engagement=engagement)
        self.assert_compiled(report, '.pdf')
        drawn = self.comparable(self.pdf_drawn_text(report))
        self.assertIn(self.comparable('Not included in this report'), drawn)
        self.assertNotIn(
            self.comparable(action.action_number), drawn,
            'an unendorsed finding\'s remedy reached a downloadable report',
        )

    def test_an_endorsed_action_is_listed_with_nothing_said_about_withholding(self):
        """The regression guard. The fixture's engagement holds one endorsed
        finding and one action against it, which is the ordinary report."""
        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format))
                self.assertIn('Corrective Action', text)
                self.assertNotIn('Not shown above', text)
                self.assertNotIn('Not included in this report', text)

    def test_a_half_endorsed_engagement_lists_one_and_counts_the_other(self):
        """Both halves at once: the section has rows to draw *and* a sibling it
        cannot, which is the case the fallback message was never reached for."""
        make_action(
            finding=make_finding(
                engagement=self.engagement, identified_by=self.auditor,
                auditee=self.auditee, status='draft',
            ),
            owner=self.auditee, assigned_by=self.auditor,
            action_number='CAPA-90002', title='Withheld control',
        )

        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format))
                self.assertIn('Corrective Action', text)
                self.assertIn('Not shown above', text)
                self.assertIn(
                    '1 corrective action whose finding has not yet been endorsed',
                    text,
                )

    def test_a_finding_awaiting_endorsement_is_disclosed_as_well(self):
        """The same defect one section up. A finding that is not endorsed is left
        out of the findings table, and "No findings were registered" said there
        were none."""
        engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        make_finding(
            engagement=engagement, identified_by=self.auditor, auditee=self.auditee,
            status='draft',
        )

        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format, engagement=engagement))
                self.assertIn(
                    '1 finding that has not yet been endorsed for publication', text,
                )
                self.assertNotIn('No findings were registered', text)

    def test_an_engagement_with_nothing_at_all_keeps_the_plain_messages(self):
        """The guard against the disclosure firing on every report: with no rows
        and nothing withheld, the original sentences are still the true ones."""
        engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        # The two formats have always worded the findings fallback differently —
        # Excel's sheet drops the auxiliary verb — and this change does not
        # silently unify prose they disagree on.
        empty_findings = {
            'word': 'No findings were registered for this engagement.',
            'excel': 'No findings registered for this engagement.',
        }

        for report_format in ('word', 'excel'):
            with self.subTest(format=report_format):
                text = self.content_text(self.generate(report_format, engagement=engagement))
                self.assertIn(empty_findings[report_format], text)
                self.assertIn(
                    'No corrective actions have been assigned for findings in this engagement.',
                    text,
                )
                self.assertNotIn('Not included in this report', text)
                self.assertNotIn('Not shown above', text)


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
