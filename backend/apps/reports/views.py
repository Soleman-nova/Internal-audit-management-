from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.utils import timezone
from django.core.files.base import ContentFile
from io import BytesIO
from django.db import transaction
from django.db.models import Count
import mimetypes

from .models import ReportTemplate, GeneratedReport
from .serializers import ReportTemplateSerializer, GeneratedReportSerializer
from apps.notifications.services import notify
from apps.common.permissions import CanManageSettings, CanWriteAudit
from apps.common.audit_utils import log_audit
from apps.common.scoping import AuditeeScopeMixin, RegionScopeMixin


def _pdf_escape(text):
    """Escape free text for a reportlab `Paragraph`.

    `Paragraph` parses its text as XML markup, so anything the user typed has to be
    escaped before it gets there. Measured on reportlab 4.5.1, the failure is
    silent rather than loud: a title of `R&D <legacy> upgrade` is drawn as
    `R&D; upgrade` — the `<legacy>` is read as an unknown tag, dropped, and a stray
    `;` left in its place. Nothing raises, so the report compiles and the finding
    title is quietly wrong — which is exactly the kind of defect a "does it
    compile" test cannot see.

    The surrounding report markup (`<b>`, `<i>`) is written by this module and is
    deliberately not passed through here.
    """
    from xml.sax.saxutils import escape
    return escape('' if text is None else str(text))


def _pdf_cell(text, style):
    """A table cell that wraps inside its column.

    A plain string in a reportlab `Table` is drawn with `canvas.drawString`, which
    neither wraps nor clips against the column width — so a long title simply
    paints over the next column. Wrapping requires a `Paragraph`, which is also why
    the escaping above is not optional once cells become markup.
    """
    from reportlab.platypus import Paragraph
    return Paragraph(_pdf_escape(text), style)


def _clip(text, limit):
    """Cap a cell's text at `limit` characters.

    Wrapping makes rows grow with their content, so the cap bounds how tall a
    single long title (the field is 300 chars) can make one.
    """
    text = '' if text is None else str(text)
    return text[:limit] + ('...' if len(text) > limit else '')


def _plural(count, noun):
    """`1 finding` / `3 findings`."""
    return f'{count} {noun}' + ('' if count == 1 else 's')


def _withheld_capas_note(count):
    """Why this many corrective actions are absent from a report.

    The *finding* is what is unendorsed, not the action — an action inherits its
    finding's publication state, which is the whole reason it is being withheld,
    so saying the action itself was not endorsed would name the wrong record.
    """
    subject = 'finding has' if count == 1 else 'findings have'
    return (f'{_plural(count, "corrective action")} whose {subject} not yet '
            'been endorsed for publication.')


def _withheld_findings_note(count):
    """The same sentence for findings the report left out."""
    subject = 'has' if count == 1 else 'have'
    return (f'{_plural(count, "finding")} that {subject} not yet been endorsed '
            'for publication.')


def _absence_message(withheld, note, fallback):
    """What a section says when it has no rows to show.

    `fallback` asserts that none of this kind of record exists. That is only
    knowable once the withheld count is in hand, which is the defect this
    replaces: the assertion was printed whether or not the query had dropped
    anything, so a report could deny the existence of an action the reader had
    just seen in the register.
    """
    if not withheld:
        return fallback
    return f'Not included in this report: {note(withheld)}'


def _withheld_above_message(withheld, note):
    """The footnote for a section that has rows *and* withheld siblings."""
    if not withheld:
        return None
    return f'Not shown above: {note(withheld)}'


class ReportTemplateViewSet(viewsets.ModelViewSet):
    # ReportTemplate has no Meta.ordering, so paginating it could repeat or skip
    # templates between pages. Newest first, matching GeneratedReport.
    queryset = ReportTemplate.objects.order_by('-created_at')
    serializer_class = ReportTemplateSerializer
    permission_classes = [CanManageSettings]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['template_type', 'is_default']

    def perform_create(self, serializer):
        with transaction.atomic():
            template = serializer.save(created_by=self.request.user)
            log_audit(self.request, 'CREATE', template)

    def perform_update(self, serializer):
        with transaction.atomic():
            template = serializer.save()
            log_audit(self.request, 'UPDATE', template)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()


class GeneratedReportViewSet(RegionScopeMixin, AuditeeScopeMixin, viewsets.ModelViewSet):
    queryset = GeneratedReport.objects.select_related(
        'template', 'engagement', 'generated_by'
    ).all()
    serializer_class = GeneratedReportSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['format', 'status', 'engagement']

    # An auditee sees a report only when it is about their own engagement, or when
    # they generated it. `engagement` is nullable, so an org-wide report matches
    # neither and stays out of reach — which is the intent. A regional FPA
    # auditor sees only reports whose engagement is tagged with their region.
    region_scope_fields = ('engagement__region_id',)
    auditee_scope_fields = ('engagement__department_id',)
    auditee_scope_personal_fields = ('generated_by',)

    def perform_create(self, serializer):
        from apps.reports.jobs import enqueue_report_generation

        with transaction.atomic():
            report = serializer.save(generated_by=self.request.user, status='generating')
            # Phase 3.4 — run the heavy compile off the request thread so the API
            # returns immediately and the frontend can poll status:
            # generating -> ready / failed.
            #
            # on_commit, not a bare call: the worker looks the report up by id in
            # its own connection, so starting the thread inside the transaction is
            # a race it can lose — and if the request then fails, a thread would be
            # compiling a report for a row that was never committed.
            transaction.on_commit(lambda: enqueue_report_generation(report))

    def generate_report_file(self, report, request=None):
        from django.core.files.base import ContentFile
        from apps.findings.models import AuditFinding
        from apps.corrective_actions.models import CorrectiveAction
        from apps.risk_assessment.models import RiskAssessment
        
        findings = []
        corrective_actions = []
        risk_data = []
        engagement = report.engagement
        engagement_info = {}
        # How much the two queries below left out, so the sections can say so. Zero
        # rather than undefined for the no-engagement report, which has both empty
        # and nothing withheld.
        withheld_findings = 0
        withheld_capas = 0
        
        if engagement:
            # Published findings only. A report is a distributable document — it is
            # stored as a file, and an auditee reaches it through
            # GeneratedReportViewSet — so an unendorsed finding compiled into one
            # would leave the audit team's draft in the hands of the party it is
            # about. The corrective actions and risk rows follow their finding for
            # the same reason.
            findings = list(AuditFinding.objects.filter(engagement=engagement).exclude(
                status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            ))
            corrective_actions = list(CorrectiveAction.objects.filter(
                finding__engagement=engagement,
            ).exclude(
                finding__status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            ).select_related('finding'))
            # Counted, not listed: the withheld rows are exactly what must not reach
            # the document, so only their number crosses into it. Without this the
            # sections below could not tell "none exist" from "none I am allowed to
            # print", and printed the first when the second was true — the lead
            # auditor had just seen the action in the register, which applies the
            # same exclusion to auditees only.
            withheld_findings = AuditFinding.objects.filter(
                engagement=engagement,
                status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            ).count()
            withheld_capas = CorrectiveAction.objects.filter(
                finding__engagement=engagement,
                finding__status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            ).count()
            risk_data = list(RiskAssessment.objects.filter(
                department=engagement.department
            ) if engagement.department else [])
            
            engagement_info = {
                'title': engagement.title,
                'number': engagement.engagement_number,
                'type': engagement.get_engagement_type_display(),
                'department': engagement.department.name if engagement.department else 'N/A',
                'status': engagement.get_status_display(),
                'lead_auditor': engagement.lead_auditor.full_name if engagement.lead_auditor else 'N/A',
                'supervisor': engagement.supervisor.full_name if engagement.supervisor else 'N/A',
                'planned_start': engagement.planned_start,
                'planned_end': engagement.planned_end,
                'actual_start': engagement.actual_start,
                'actual_end': engagement.actual_end,
                'risk_level': engagement.risk_level,
            }
            
        buf = BytesIO()
        # The severity/status tally used to be computed inside the `pdf` branch,
        # but the excel and word branches read `total_findings` /
        # `severity_counts` / `critical_count` too — so every non-PDF report died
        # with UnboundLocalError before it wrote a byte, leaving the row stuck on
        # `generating`. Computed once here, for all three formats.
        total_findings = len(findings)
        severity_counts = {}
        status_counts = {}
        for f in findings:
            sev = f.severity.upper() if f.severity else 'UNKNOWN'
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            sts = f.status.upper() if f.status else 'UNKNOWN'
            status_counts[sts] = status_counts.get(sts, 0) + 1

        critical_count = severity_counts.get('CRITICAL', 0)
        high_count = severity_counts.get('HIGH', 0)
        medium_count = severity_counts.get('MEDIUM', 0)
        low_count = severity_counts.get('LOW', 0)

        # Objectives and scope are read by all three formats, so they are resolved
        # once here, for the same reason the tally above is.
        #
        # Two sources, because either may carry them: the engagement is the record
        # the auditee was scheduled against, while the program is the audit team's
        # plan of attack and often where they are actually written. When both are
        # empty the report says so in words — an empty paragraph reads as a broken
        # report rather than as missing input.
        #
        # `getattr(..., None)` rather than `engagement.program`: the reverse side of
        # a OneToOneField raises RelatedObjectDoesNotExist for an engagement with no
        # program, and that exception subclasses AttributeError, so this returns
        # None instead of raising.
        program = getattr(engagement, 'program', None) if engagement else None
        objectives_text = (
            (engagement.objectives if engagement else '')
            or (program.objectives if program else '')
            or 'No specific objectives have been recorded for this engagement.'
        )
        scope_text = (
            (engagement.scope if engagement else '')
            or (program.scope if program else '')
            or 'No scope has been recorded for this engagement.'
        )

        # The real extension, not the format key: `.excel` / `.word` are not file
        # types, so `mimetypes.guess_type` in `export` returned None and the
        # browser was handed octet-stream and a file it could not open.
        extension = {'pdf': 'pdf', 'excel': 'xlsx', 'word': 'docx'}.get(
            report.format, report.format,
        )
        filename = f"{report.title.replace(' ', '_')}.{extension}"

        if report.format == 'pdf':
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import mm
            from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
            
            doc = SimpleDocTemplate(buf, pagesize=A4,
                                    leftMargin=20*mm, rightMargin=20*mm,
                                    topMargin=20*mm, bottomMargin=20*mm)
            styles = getSampleStyleSheet()
            
            # Create custom styles
            styles.add(ParagraphStyle('CoverTitle', parent=styles['Title'],
                                      fontSize=22, spaceAfter=6, alignment=TA_CENTER,
                                      textColor=colors.HexColor('#1E3A5F')))
            styles.add(ParagraphStyle('CoverSubtitle', parent=styles['Normal'],
                                      fontSize=14, alignment=TA_CENTER,
                                      textColor=colors.HexColor('#555555')))
            styles.add(ParagraphStyle('SectionTitle', parent=styles['Heading1'],
                                      fontSize=16, spaceBefore=20, spaceAfter=10,
                                      textColor=colors.HexColor('#1E3A5F'),
                                      borderWidth=2, borderColor=colors.HexColor('#1E3A5F'),
                                      borderPadding=4))
            styles.add(ParagraphStyle('SectionBody', parent=styles['Normal'],
                                      fontSize=10, leading=14, alignment=TA_JUSTIFY,
                                      spaceAfter=8))
            styles.add(ParagraphStyle('TableHeader', parent=styles['Normal'],
                                      fontSize=9, leading=11, fontName='Helvetica-Bold',
                                      textColor=colors.white))
            # Cell styles for the wrapped tables. A Paragraph carries its own style,
            # so the TableStyle FONTSIZE/FONTNAME entries no longer reach these cells
            # — they are set here instead, at the sizes those tables used to declare.
            styles.add(ParagraphStyle('TableCell', parent=styles['Normal'],
                                      fontSize=7, leading=8.5))
            styles.add(ParagraphStyle('TableCellCenter', parent=styles['TableCell'],
                                      alignment=TA_CENTER))

            elements = []
            
            # ========== COVER PAGE ==========
            elements.append(Spacer(1, 60))
            elements.append(Paragraph("ETHIOPIAN ELECTRIC UTILITY", styles['CoverTitle']))
            elements.append(Paragraph("Internal Audit Department", styles['CoverSubtitle']))
            elements.append(Spacer(1, 20))
            elements.append(Paragraph(_pdf_escape(report.title), styles['CoverTitle']))
            elements.append(Spacer(1, 30))
            
            # Engagement info box
            info_data = [
                ['Engagement:', engagement_info.get('title', 'N/A')],
                ['Eng. Number:', engagement_info.get('number', 'N/A')],
                ['Type:', engagement_info.get('type', 'N/A')],
                ['Department:', engagement_info.get('department', 'N/A')],
                ['Lead Auditor:', engagement_info.get('lead_auditor', 'N/A')],
                ['Supervisor:', engagement_info.get('supervisor', 'N/A')],
                ['Risk Level:', engagement_info.get('risk_level', 'N/A')],
            ]
            info_table = Table(info_data, colWidths=[100, 320])
            info_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(info_table)
            elements.append(Spacer(1, 40))
            elements.append(Paragraph(f"Date: {timezone.now().strftime('%d %B %Y')}", styles['CoverSubtitle']))
            elements.append(Paragraph(f"Generated By: {_pdf_escape(report.generated_by.full_name if report.generated_by else 'System')}", styles['CoverSubtitle']))
            elements.append(PageBreak())
            
            # ========== TABLE OF CONTENTS ==========
            elements.append(Paragraph("TABLE OF CONTENTS", styles['SectionTitle']))
            elements.append(Spacer(1, 10))
            toc_items = [
                "1.  Background",
                "2.  Executive Summary",
                "3.  Risk Analysis",
                "4.  Findings Summary Table",
                "5.  Corrective Action Plan (CAPA)",
            ]
            for item in toc_items:
                elements.append(Paragraph(item, styles['SectionBody']))
            elements.append(PageBreak())
            
            # ========== 1. BACKGROUND ==========
            elements.append(Paragraph("1. BACKGROUND", styles['SectionTitle']))
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(
                f"This report presents the findings and recommendations from the audit engagement "
                f"<b>{_pdf_escape(engagement_info.get('title', 'N/A'))}</b> conducted by the EEU Internal Audit Department. "
                f"The audit was performed in accordance with the International Standards for the Professional "
                f"Practice of Internal Auditing (IPPF) and the EEU Internal Audit Charter.",
                styles['SectionBody']
            ))
            elements.append(Spacer(1, 10))
            
            bg_data = [
                ['Engagement Title', engagement_info.get('title', 'N/A')],
                ['Engagement Type', engagement_info.get('type', 'N/A')],
                ['Audited Department', engagement_info.get('department', 'N/A')],
                ['Status', engagement_info.get('status', 'N/A')],
                ['Lead Auditor', engagement_info.get('lead_auditor', 'N/A')],
                ['Supervisor', engagement_info.get('supervisor', 'N/A')],
                ['Planned Start', str(engagement_info.get('planned_start', 'N/A'))],
                ['Planned End', str(engagement_info.get('planned_end', 'N/A'))],
            ]
            bg_table = Table(bg_data, colWidths=[140, 280])
            bg_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F4F8')),
            ]))
            elements.append(bg_table)
            elements.append(Spacer(1, 15))
            
            elements.append(Paragraph("<b>Audit Objectives:</b>", styles['SectionBody']))
            elements.append(Paragraph(_pdf_escape(objectives_text), styles['SectionBody']))
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("<b>Audit Scope:</b>", styles['SectionBody']))
            elements.append(Paragraph(_pdf_escape(scope_text), styles['SectionBody']))
            elements.append(PageBreak())
            
            # ========== 2. EXECUTIVE SUMMARY ==========
            elements.append(Paragraph("2. EXECUTIVE SUMMARY", styles['SectionTitle']))
            elements.append(Spacer(1, 10))

            elements.append(Paragraph(
                f"A total of <b>{total_findings}</b> finding(s) were identified during this audit engagement. "
                f"Of these, <b>{critical_count}</b> are classified as Critical, <b>{high_count}</b> as High, "
                f"<b>{medium_count}</b> as Medium, and <b>{low_count}</b> as Low severity. "
                f"The audit was conducted to evaluate the adequacy and effectiveness of internal controls "
                f"within the audited area.",
                styles['SectionBody']
            ))
            elements.append(Spacer(1, 10))
            
            if total_findings > 0:
                exec_data = [['Severity Level', 'Count']]
                for sev, count in sorted(severity_counts.items(), key=lambda x: ['CRITICAL','HIGH','MEDIUM','LOW'].index(x[0]) if x[0] in ['CRITICAL','HIGH','MEDIUM','LOW'] else 99):
                    exec_data.append([sev, str(count)])
                
                exec_table = Table(exec_data, colWidths=[200, 200])
                exec_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#1E3A5F')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A5F')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ]))
                elements.append(exec_table)
            elements.append(PageBreak())
            
            # ========== 3. RISK ANALYSIS ==========
            elements.append(Paragraph("3. RISK ANALYSIS", styles['SectionTitle']))
            elements.append(Spacer(1, 10))
            
            if risk_data:
                elements.append(Paragraph(
                    f"The following risk assessment data relates to the department <b>{_pdf_escape(engagement_info.get('department', 'N/A'))}</b>. "
                    f"The risk analysis considers inherent risk, control effectiveness, and residual risk levels.",
                    styles['SectionBody']
                ))
                elements.append(Spacer(1, 10))
                
                risk_table_data = [['Period', 'Year', 'Likelihood', 'Impact', 'Risk Score', 'Rating', 'Control Eff.', 'Residual Risk']]
                for r in risk_data[:15]:
                    risk_table_data.append([
                        r.assessment_period,
                        str(r.year),
                        str(r.likelihood),
                        str(r.impact),
                        str(r.risk_score),
                        r.risk_rating.upper() if r.risk_rating else 'N/A',
                        str(r.control_effectiveness),
                        f"{r.residual_risk:.2f}" if r.residual_risk else 'N/A',
                    ])
                
                risk_table = Table(risk_table_data, colWidths=[45, 35, 50, 40, 55, 50, 55, 60])
                risk_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A5F')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
                ]))
                elements.append(risk_table)
            else:
                elements.append(Paragraph(
                    "No risk assessment data is available for this engagement's department. "
                    "A risk analysis should be conducted as part of the audit planning process.",
                    styles['SectionBody']
                ))
            elements.append(PageBreak())
            
            # ========== 4. FINDINGS TABLE ==========
            elements.append(Paragraph("4. FINDINGS SUMMARY TABLE", styles['SectionTitle']))
            elements.append(Spacer(1, 10))
            
            if not findings:
                elements.append(Paragraph(
                    _pdf_escape(_absence_message(
                        withheld_findings, _withheld_findings_note,
                        "No findings were registered for this engagement.",
                    )),
                    styles['SectionBody'],
                ))
            else:
                elements.append(Paragraph(
                    f"The following table provides a comprehensive summary of all <b>{total_findings}</b> finding(s) "
                    f"identified during this audit engagement.",
                    styles['SectionBody']
                ))
                elements.append(Spacer(1, 10))
                
                center = styles['TableCellCenter']
                body = styles['TableCell']
                f_headers = ['#', 'Ref No.', 'Title', 'Severity', 'Category', 'Status', 'Recommendation']
                findings_table_data = [[_pdf_cell(h, styles['TableHeader']) for h in f_headers]]
                for idx, f in enumerate(findings, 1):
                    findings_table_data.append([
                        _pdf_cell(idx, center),
                        _pdf_cell(f.finding_number, body),
                        _pdf_cell(_clip(f.title, 50), body),
                        _pdf_cell(f.severity.upper() if f.severity else 'N/A', center),
                        _pdf_cell(f.category.replace('_', ' ').title() if f.category else 'N/A', center),
                        _pdf_cell(f.status.upper() if f.status else 'N/A', center),
                        _pdf_cell(_clip(f.recommendation, 60) if f.recommendation else 'N/A', body),
                    ])

                # 481pt is what A4 leaves between the document's 20mm margins. The
                # table used to sum to 460 with the slack going nowhere; it now goes
                # to the two columns that wrap, which is where it was needed.
                f_table = Table(findings_table_data, colWidths=[22, 58, 120, 52, 60, 50, 119])
                f_table.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A5F')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8F9FA')]),
                ]))
                elements.append(f_table)
                
                # Detailed findings section
                elements.append(Spacer(1, 20))
                elements.append(Paragraph("<b>Detailed Finding Descriptions:</b>", styles['SectionBody']))
                elements.append(Spacer(1, 10))
                for f in findings:
                    elements.append(Paragraph(
                        f"<b>{_pdf_escape(f.finding_number)}: {_pdf_escape(f.title)}</b> "
                        f"[Severity: {_pdf_escape(f.severity.upper() if f.severity else 'N/A')}] "
                        f"[Status: {_pdf_escape(f.status.upper() if f.status else 'N/A')}]",
                        styles['SectionBody']
                    ))
                    elements.append(Paragraph(f"<b>Condition:</b> {_pdf_escape(f.condition or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Criteria:</b> {_pdf_escape(f.criteria or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Cause:</b> {_pdf_escape(f.cause or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Effect/Impact:</b> {_pdf_escape(f.effect or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Recommendation:</b> {_pdf_escape(f.recommendation or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Management Response:</b> {_pdf_escape(f.management_response or 'N/A')}", styles['SectionBody']))
                    elements.append(Spacer(1, 8))

                # The count of what was left out goes last, so it reads as a note on
                # the table rather than as a heading for it.
                note = _withheld_above_message(withheld_findings, _withheld_findings_note)
                if note:
                    elements.append(Paragraph(
                        f"<i>{_pdf_escape(note)}</i>",
                        styles['SectionBody'],
                    ))
            elements.append(PageBreak())
            
            # ========== 5. CAPA - CORRECTIVE ACTION PLAN ==========
            elements.append(Paragraph("5. CORRECTIVE ACTION PLAN (CAPA)", styles['SectionTitle']))
            elements.append(Spacer(1, 10))
            
            if not corrective_actions:
                elements.append(Paragraph(
                    _pdf_escape(_absence_message(
                        withheld_capas, _withheld_capas_note,
                        "No corrective actions have been assigned for findings in this engagement. "
                        "Corrective actions should be defined for each finding to address identified issues.",
                    )),
                    styles['SectionBody'],
                ))
            else:
                elements.append(Paragraph(
                    f"The following <b>{len(corrective_actions)}</b> corrective action(s) have been defined "
                    f"to address the findings identified during this audit engagement.",
                    styles['SectionBody']
                ))
                elements.append(Spacer(1, 10))
                
                capa_headers = ['#', 'Action No.', 'Title', 'Finding Ref', 'Priority', 'Status', 'Owner', 'Due Date']
                capa_table_data = [[_pdf_cell(h, styles['TableHeader']) for h in capa_headers]]
                for idx, ca in enumerate(corrective_actions, 1):
                    capa_table_data.append([
                        _pdf_cell(idx, center),
                        _pdf_cell(ca.action_number, body),
                        _pdf_cell(_clip(ca.title, 45), body),
                        _pdf_cell(ca.finding.finding_number if ca.finding else 'N/A', center),
                        _pdf_cell(ca.priority.upper() if ca.priority else 'N/A', center),
                        _pdf_cell(ca.status.upper() if ca.status else 'N/A', center),
                        _pdf_cell(ca.owner.full_name if ca.owner else 'Unassigned', center),
                        _pdf_cell(str(ca.due_date), center),
                    ])

                capa_table = Table(capa_table_data, colWidths=[20, 55, 125, 52, 45, 55, 70, 59])
                capa_table.setStyle(TableStyle([
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A5F')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8F9FA')]),
                ]))
                elements.append(capa_table)
                
                # Detailed CAPA descriptions
                elements.append(Spacer(1, 15))
                elements.append(Paragraph("<b>Detailed Corrective Action Descriptions:</b>", styles['SectionBody']))
                elements.append(Spacer(1, 10))
                for ca in corrective_actions:
                    elements.append(Paragraph(
                        f"<b>{_pdf_escape(ca.action_number)}: {_pdf_escape(ca.title)}</b> "
                        f"[Priority: {_pdf_escape((ca.priority or '').upper() or 'N/A')} - "
                        f"Status: {_pdf_escape((ca.status or '').upper() or 'N/A')}]",
                        styles['SectionBody']
                    ))
                    elements.append(Paragraph(f"<b>Finding:</b> {_pdf_escape(ca.finding.finding_number + ' - ' + ca.finding.title if ca.finding else 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Description:</b> {_pdf_escape(ca.description or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Recommendation:</b> {_pdf_escape(ca.recommendation or 'N/A')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Owner:</b> {_pdf_escape(ca.owner.full_name if ca.owner else 'Unassigned')}", styles['SectionBody']))
                    elements.append(Paragraph(f"<b>Due Date:</b> {_pdf_escape(ca.due_date)}", styles['SectionBody']))
                    if ca.management_response:
                        elements.append(Paragraph(f"<b>Management Response:</b> {_pdf_escape(ca.management_response)}", styles['SectionBody']))
                    elements.append(Spacer(1, 8))

                note = _withheld_above_message(withheld_capas, _withheld_capas_note)
                if note:
                    elements.append(Paragraph(
                        f"<i>{_pdf_escape(note)}</i>",
                        styles['SectionBody'],
                    ))

            # Footer disclaimer
            elements.append(Spacer(1, 30))
            elements.append(Paragraph(
                "<i>This report was generated automatically by the EEU Internal Audit Management System. "
                "The information contained herein is confidential and intended solely for internal use "
                "by authorized personnel of Ethiopian Electric Utility.</i>",
                ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=8,
                              textColor=colors.HexColor('#888888'), alignment=TA_CENTER)
            ))
            
            doc.build(elements)
            buf.seek(0)
            report.file.save(filename, ContentFile(buf.read()), save=False)
            report.status = 'ready'
            report.save()
            
            # Log the export
            log_audit(
                request, 'EXPORT', report,
                object_repr=f"Generated PDF report: {report.title}",
                user=report.generated_by,
            )

        elif report.format == 'excel':
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            
            wb = openpyxl.Workbook()
            
            # =========== SHEET 1: COVER & BACKGROUND ===========
            ws_cover = wb.active
            ws_cover.title = "Cover & Background"
            ws_cover.sheet_properties.tabColor = "1E3A5F"
            
            header_fill = PatternFill(fill_type='solid', fgColor='1E3A5F')
            header_font = Font(bold=True, color='FFFFFF', size=11)
            title_font = Font(bold=True, size=16, color='1E3A5F')
            subtitle_font = Font(bold=True, size=12, color='1E3A5F')
            normal_font = Font(size=10)
            bold_font = Font(bold=True, size=10)
            
            thin_border = Border(
                left=Side(style='thin', color='CCCCCC'),
                right=Side(style='thin', color='CCCCCC'),
                top=Side(style='thin', color='CCCCCC'),
                bottom=Side(style='thin', color='CCCCCC'),
            )
            
            ws_cover.merge_cells('A1:H1')
            ws_cover['A1'] = 'ETHIOPIAN ELECTRIC UTILITY - Internal Audit Department'
            ws_cover['A1'].font = title_font
            ws_cover['A1'].alignment = Alignment(horizontal='center')
            
            ws_cover.merge_cells('A2:H2')
            ws_cover['A2'] = report.title
            ws_cover['A2'].font = Font(bold=True, size=14, color='1E3A5F')
            ws_cover['A2'].alignment = Alignment(horizontal='center')
            
            ws_cover['A4'] = f"Generated: {timezone.now().strftime('%d/%m/%Y %H:%M')}"
            ws_cover['A4'].font = normal_font
            ws_cover['A5'] = f"Generated By: {report.generated_by.full_name if report.generated_by else 'System'}"
            
            # Background details
            ws_cover['A7'] = '1. BACKGROUND INFORMATION'
            ws_cover['A7'].font = subtitle_font
            
            bg_fields = [
                ('Engagement Title:', engagement_info.get('title', 'N/A')),
                ('Engagement Number:', engagement_info.get('number', 'N/A')),
                ('Engagement Type:', engagement_info.get('type', 'N/A')),
                ('Department:', engagement_info.get('department', 'N/A')),
                ('Status:', engagement_info.get('status', 'N/A')),
                ('Lead Auditor:', engagement_info.get('lead_auditor', 'N/A')),
                ('Supervisor:', engagement_info.get('supervisor', 'N/A')),
                ('Risk Level:', engagement_info.get('risk_level', 'N/A')),
                ('Planned Start:', str(engagement_info.get('planned_start', 'N/A'))),
                ('Planned End:', str(engagement_info.get('planned_end', 'N/A'))),
            ]
            for i, (label, value) in enumerate(bg_fields):
                row = 8 + i
                ws_cover[f'A{row}'] = label
                ws_cover[f'A{row}'].font = bold_font
                ws_cover[f'B{row}'] = value
                ws_cover[f'B{row}'].font = normal_font
            
            row = 19
            ws_cover[f'A{row}'] = 'Audit Objectives:'
            ws_cover[f'A{row}'].font = bold_font
            ws_cover.merge_cells(f'A{row+1}:H{row+3}')
            ws_cover[f'A{row+1}'] = objectives_text
            ws_cover[f'A{row+1}'].font = normal_font
            ws_cover[f'A{row+1}'].alignment = Alignment(wrap_text=True, vertical='top')

            ws_cover[f'A{row+5}'] = 'Audit Scope:'
            ws_cover[f'A{row+5}'].font = bold_font
            ws_cover.merge_cells(f'A{row+6}:H{row+8}')
            ws_cover[f'A{row+6}'] = scope_text
            ws_cover[f'A{row+6}'].font = normal_font
            ws_cover[f'A{row+6}'].alignment = Alignment(wrap_text=True, vertical='top')
            
            ws_cover.column_dimensions['A'].width = 25
            ws_cover.column_dimensions['B'].width = 50
            
            # =========== SHEET 2: EXECUTIVE SUMMARY ===========
            ws_exec = wb.create_sheet("Executive Summary")
            ws_exec.sheet_properties.tabColor = "4CAF50"
            
            ws_exec.merge_cells('A1:F1')
            ws_exec['A1'] = '2. EXECUTIVE SUMMARY'
            ws_exec['A1'].font = subtitle_font
            
            ws_exec['A3'] = f'Total Findings: {total_findings}'
            ws_exec['A3'].font = bold_font
            
            exec_headers = ['Severity Level', 'Count']
            for col_idx, text in enumerate(exec_headers, 1):
                cell = ws_exec.cell(row=5, column=col_idx, value=text)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal='center')
                cell.border = thin_border
            
            sev_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL']
            row = 6
            for sev in sev_order:
                count = severity_counts.get(sev, 0)
                if count > 0:
                    ws_exec.cell(row=row, column=1, value=sev)
                    ws_exec.cell(row=row, column=2, value=count)
                    ws_exec.cell(row=row, column=1).font = bold_font
                    ws_exec.cell(row=row, column=2).alignment = Alignment(horizontal='center')
                    ws_exec.cell(row=row, column=2).font = normal_font
                    row += 1
            
            ws_exec.column_dimensions['A'].width = 25
            ws_exec.column_dimensions['B'].width = 15
            
            ws_exec[f'A{row+2}'] = 'Summary Description:'
            ws_exec[f'A{row+2}'].font = bold_font
            ws_exec.merge_cells(f'A{row+3}:F{row+5}')
            ws_exec[f'A{row+3}'] = (
                f"A total of {total_findings} finding(s) were identified during this audit engagement. "
                f"Of these, {critical_count} are Critical, {high_count} are High, "
                f"{medium_count} are Medium, and {low_count} are Low severity."
            )
            ws_exec[f'A{row+3}'].font = normal_font
            ws_exec[f'A{row+3}'].alignment = Alignment(wrap_text=True, vertical='top')
            
            # =========== SHEET 3: RISK ANALYSIS ===========
            ws_risk = wb.create_sheet("Risk Analysis")
            ws_risk.sheet_properties.tabColor = "FF9800"
            
            ws_risk.merge_cells('A1:H1')
            ws_risk['A1'] = '3. RISK ANALYSIS'
            ws_risk['A1'].font = subtitle_font
            
            if risk_data:
                risk_headers = ['Period', 'Year', 'Likelihood', 'Impact', 'Risk Score', 'Rating', 'Control Eff.', 'Residual Risk']
                for col_idx, text in enumerate(risk_headers, 1):
                    cell = ws_risk.cell(row=3, column=col_idx, value=text)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center')
                    cell.border = thin_border
                
                for r_idx, r in enumerate(risk_data, 4):
                    vals = [
                        r.assessment_period, r.year, r.likelihood, r.impact,
                        r.risk_score, r.risk_rating.upper() if r.risk_rating else 'N/A',
                        r.control_effectiveness, f"{r.residual_risk:.2f}" if r.residual_risk else 'N/A'
                    ]
                    for c_idx, val in enumerate(vals, 1):
                        cell = ws_risk.cell(row=r_idx, column=c_idx, value=val)
                        cell.font = normal_font
                        cell.alignment = Alignment(horizontal='center')
                        cell.border = thin_border
            else:
                ws_risk['A3'] = 'No risk assessment data available for this engagement.'
                ws_risk['A3'].font = normal_font
                ws_risk.merge_cells('A3:H3')
            
            for col in range(1, 9):
                ws_risk.column_dimensions[get_column_letter(col)].width = 16
            
            # =========== SHEET 4: FINDINGS TABLE ===========
            ws_findings = wb.create_sheet("Findings")
            ws_findings.sheet_properties.tabColor = "F44336"
            
            ws_findings.merge_cells('A1:G1')
            ws_findings['A1'] = '4. FINDINGS SUMMARY TABLE'
            ws_findings['A1'].font = subtitle_font
            
            if findings:
                f_headers = ['#', 'Ref No.', 'Title', 'Severity', 'Category', 'Status', 'Recommendation']
                for col_idx, text in enumerate(f_headers, 1):
                    cell = ws_findings.cell(row=3, column=col_idx, value=text)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center')
                    cell.border = thin_border
                
                for f_idx, f in enumerate(findings, 4):
                    vals = [
                        f_idx - 3,
                        f.finding_number,
                        f.title,
                        f.severity.upper() if f.severity else 'N/A',
                        f.category.replace('_', ' ').title() if f.category else 'N/A',
                        f.status.upper() if f.status else 'N/A',
                        f.recommendation or 'N/A',
                    ]
                    for c_idx, val in enumerate(vals, 1):
                        cell = ws_findings.cell(row=f_idx, column=c_idx, value=val)
                        cell.font = normal_font
                        cell.border = thin_border
                        if c_idx in (3, 7):
                            # Title and Recommendation are the two long columns.
                            # Excel clips text against a non-empty neighbour rather
                            # than overflowing, so without the wrap the title is
                            # simply cut off at the column edge. No explicit row
                            # height: leaving it unset keeps Excel's auto-fit.
                            cell.alignment = Alignment(wrap_text=True, vertical='top')
                        else:
                            cell.alignment = Alignment(horizontal='center')
                
                # Detailed findings section
                detail_row = len(findings) + 6
                ws_findings[f'A{detail_row}'] = 'Detailed Finding Descriptions:'
                ws_findings[f'A{detail_row}'].font = subtitle_font
                
                for f_idx, f in enumerate(findings):
                    dr = detail_row + 1 + (f_idx * 7)
                    ws_findings[f'A{dr}'] = f"{f.finding_number}: {f.title}"
                    ws_findings[f'A{dr}'].font = bold_font
                    # The font belongs to the cell the text was written to. These
                    # six lines wrote to column C and then styled column A, so the
                    # detail text was left unstyled.
                    for offset, text in enumerate([
                        f'Condition: {f.condition or "N/A"}',
                        f'Criteria: {f.criteria or "N/A"}',
                        f'Cause: {f.cause or "N/A"}',
                        f'Effect/Impact: {f.effect or "N/A"}',
                        f'Recommendation: {f.recommendation or "N/A"}',
                        f'Management Response: {f.management_response or "N/A"}',
                    ], start=1):
                        ws_findings[f'C{dr+offset}'] = text
                        ws_findings[f'C{dr+offset}'].font = normal_font

                note = _withheld_above_message(withheld_findings, _withheld_findings_note)
                if note:
                    # Clear of the detail block above it, which is 7 rows per
                    # finding — so this cannot land on top of the last one.
                    note_row = detail_row + 1 + (len(findings) * 7)
                    ws_findings[f'A{note_row}'] = note
                    ws_findings[f'A{note_row}'].font = normal_font
            else:
                ws_findings['A3'] = _absence_message(
                    withheld_findings, _withheld_findings_note,
                    'No findings registered for this engagement.',
                )
                ws_findings['A3'].font = normal_font
            
            ws_findings.column_dimensions['A'].width = 6
            ws_findings.column_dimensions['B'].width = 16
            ws_findings.column_dimensions['C'].width = 55
            ws_findings.column_dimensions['D'].width = 14
            ws_findings.column_dimensions['E'].width = 20
            ws_findings.column_dimensions['F'].width = 14
            ws_findings.column_dimensions['G'].width = 50
            
            # =========== SHEET 5: CAPA ===========
            ws_capa = wb.create_sheet("CAPA")
            ws_capa.sheet_properties.tabColor = "9C27B0"
            
            ws_capa.merge_cells('A1:H1')
            ws_capa['A1'] = '5. CORRECTIVE ACTION PLAN (CAPA)'
            ws_capa['A1'].font = subtitle_font
            
            if corrective_actions:
                capa_headers = ['#', 'Action No.', 'Title', 'Finding Ref', 'Priority', 'Status', 'Owner', 'Due Date']
                for col_idx, text in enumerate(capa_headers, 1):
                    cell = ws_capa.cell(row=3, column=col_idx, value=text)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal='center')
                    cell.border = thin_border
                
                for ca_idx, ca in enumerate(corrective_actions, 4):
                    vals = [
                        ca_idx - 3,
                        ca.action_number,
                        ca.title,
                        ca.finding.finding_number if ca.finding else 'N/A',
                        ca.priority.upper() if ca.priority else 'N/A',
                        ca.status.upper() if ca.status else 'N/A',
                        ca.owner.full_name if ca.owner else 'Unassigned',
                        str(ca.due_date),
                    ]
                    for c_idx, val in enumerate(vals, 1):
                        cell = ws_capa.cell(row=ca_idx, column=c_idx, value=val)
                        cell.font = normal_font
                        cell.border = thin_border
                        if c_idx in (3, 7):
                            # Title and Owner, the two columns that hold prose —
                            # Excel clips rather than overflows, so they need the
                            # wrap. Row height is left unset for auto-fit.
                            cell.alignment = Alignment(wrap_text=True, vertical='top')
                        else:
                            cell.alignment = Alignment(horizontal='center')
                
                # Detailed CAPA section
                detail_row = len(corrective_actions) + 6
                ws_capa[f'A{detail_row}'] = 'Detailed Corrective Action Descriptions:'
                ws_capa[f'A{detail_row}'].font = subtitle_font
                
                for ca_idx, ca in enumerate(corrective_actions):
                    dr = detail_row + 1 + (ca_idx * 6)
                    ws_capa[f'A{dr}'] = f"{ca.action_number}: {ca.title}"
                    ws_capa[f'A{dr}'].font = bold_font
                    ws_capa[f'A{dr+1}'] = f"Finding: {ca.finding.finding_number + ' - ' + ca.finding.title if ca.finding else 'N/A'}"
                    ws_capa[f'A{dr+1}'].font = normal_font
                    ws_capa[f'A{dr+2}'] = f"Description: {ca.description or 'N/A'}"
                    ws_capa[f'A{dr+2}'].font = normal_font
                    ws_capa[f'A{dr+3}'] = f"Recommendation: {ca.recommendation or 'N/A'}"
                    ws_capa[f'A{dr+3}'].font = normal_font
                    ws_capa[f'A{dr+4}'] = f"Owner: {ca.owner.full_name if ca.owner else 'Unassigned'} | Due: {ca.due_date}"
                    ws_capa[f'A{dr+4}'].font = normal_font
                    if ca.management_response:
                        ws_capa[f'A{dr+5}'] = f"Management Response: {ca.management_response}"
                        ws_capa[f'A{dr+5}'].font = normal_font

                note = _withheld_above_message(withheld_capas, _withheld_capas_note)
                if note:
                    note_row = detail_row + 1 + (len(corrective_actions) * 6)
                    ws_capa[f'A{note_row}'] = note
                    ws_capa[f'A{note_row}'].font = normal_font
            else:
                ws_capa['A3'] = _absence_message(
                    withheld_capas, _withheld_capas_note,
                    'No corrective actions have been assigned for findings in this engagement.',
                )
                ws_capa['A3'].font = normal_font
                ws_capa.merge_cells('A3:H3')
            
            ws_capa.column_dimensions['A'].width = 6
            ws_capa.column_dimensions['B'].width = 18
            ws_capa.column_dimensions['C'].width = 45
            ws_capa.column_dimensions['D'].width = 16
            ws_capa.column_dimensions['E'].width = 12
            ws_capa.column_dimensions['F'].width = 16
            ws_capa.column_dimensions['G'].width = 25
            ws_capa.column_dimensions['H'].width = 16
            
            wb.save(buf)
            buf.seek(0)
            report.file.save(filename, ContentFile(buf.read()), save=False)
            report.status = 'ready'
            report.save()
            
            log_audit(
                request, 'EXPORT', report,
                object_repr=f"Generated Excel report: {report.title}",
                user=report.generated_by,
            )
            
        else:  # word or default text
            from docx import Document
            from docx.shared import Inches, Pt, Cm, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.enum.table import WD_TABLE_ALIGNMENT
            
            doc = Document()
            
            # Set default font
            style = doc.styles['Normal']
            font = style.font
            font.name = 'Calibri'
            font.size = Pt(10)
            
            # ========== COVER PAGE ==========
            for _ in range(4):
                doc.add_paragraph('')
            
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run('ETHIOPIAN ELECTRIC UTILITY')
            run.bold = True
            run.font.size = Pt(22)
            run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
            
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run('Internal Audit Department')
            run.font.size = Pt(14)
            run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            
            doc.add_paragraph('')
            
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(report.title)
            run.bold = True
            run.font.size = Pt(18)
            run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
            
            doc.add_paragraph('')
            
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(f"Date: {timezone.now().strftime('%d %B %Y')}")
            run.font.size = Pt(11)
            
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(f"Generated By: {report.generated_by.full_name if report.generated_by else 'System'}")
            run.font.size = Pt(11)
            
            doc.add_page_break()
            
            # ========== TABLE OF CONTENTS ==========
            p = doc.add_paragraph()
            run = p.add_run('Table of Contents')
            run.bold = True
            run.font.size = Pt(16)
            run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
            
            toc_sections = ['1. Background', '2. Executive Summary', '3. Risk Analysis', '4. Findings Summary Table', '5. Corrective Action Plan (CAPA)']
            for item in toc_sections:
                p = doc.add_paragraph(item)
                p.paragraph_format.space_after = Pt(4)
            
            doc.add_page_break()
            
            # Helper function for section headers
            def add_section_header(text):
                p = doc.add_paragraph()
                run = p.add_run(text)
                run.bold = True
                run.font.size = Pt(14)
                run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(6)
            
            def add_bold_text(text):
                p = doc.add_paragraph()
                run = p.add_run(text)
                run.bold = True
                run.font.size = Pt(10)
                return p
            
            def add_normal_text(text):
                p = doc.add_paragraph(text)
                p.paragraph_format.space_after = Pt(4)
                return p

            def set_col_widths(table, widths_cm):
                """Pin a table's columns to `widths_cm`.

                Word's default is to auto-fit, which sizes a 7- or 8-column table to
                its content — i.e. wider than the page. Fixed widths make the cells
                wrap inside their column instead. The totals are 15.0cm, inside the
                15.24cm that python-docx's default Letter template leaves between
                its 1.25in margins (`Document()` is not A4, and does not use 1in).
                """
                table.autofit = False
                for row in table.rows:
                    for cell, width in zip(row.cells, widths_cm):
                        cell.width = Cm(width)
            
            # ========== 1. BACKGROUND ==========
            add_section_header('1. Background')
            
            add_normal_text(
                f"This report presents the findings and recommendations from the audit engagement "
                f"{engagement_info.get('title', 'N/A')} conducted by the EEU Internal Audit Department. "
                f"The audit was performed in accordance with international standards."
            )
            
            # Background table
            table = doc.add_table(rows=8, cols=2)
            table.style = 'Light Grid Accent 1'
            bg_fields = [
                ('Engagement Title', engagement_info.get('title', 'N/A')),
                ('Engagement Type', engagement_info.get('type', 'N/A')),
                ('Department', engagement_info.get('department', 'N/A')),
                ('Lead Auditor', engagement_info.get('lead_auditor', 'N/A')),
                ('Supervisor', engagement_info.get('supervisor', 'N/A')),
                ('Risk Level', engagement_info.get('risk_level', 'N/A')),
                ('Planned Start', str(engagement_info.get('planned_start', 'N/A'))),
                ('Planned End', str(engagement_info.get('planned_end', 'N/A'))),
            ]
            for i, (label, value) in enumerate(bg_fields):
                table.rows[i].cells[0].text = label
                table.rows[i].cells[1].text = value
                for cell in table.rows[i].cells:
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.space_after = Pt(0)
                        for run in paragraph.runs:
                            run.font.size = Pt(10)
            
            doc.add_paragraph('')
            add_bold_text('Audit Objectives:')
            add_normal_text(objectives_text)

            add_bold_text('Audit Scope:')
            add_normal_text(scope_text)
            
            doc.add_page_break()
            
            # ========== 2. EXECUTIVE SUMMARY ==========
            add_section_header('2. Executive Summary')
            
            add_normal_text(
                f"A total of {total_findings} finding(s) were identified during this audit engagement. "
                f"Of these, {critical_count} are Critical, {high_count} are High, "
                f"{medium_count} are Medium, and {low_count} are Low severity."
            )
            
            if total_findings > 0:
                table = doc.add_table(rows=len(severity_counts) + 1, cols=2)
                table.style = 'Light Grid Accent 1'
                table.rows[0].cells[0].text = 'Severity Level'
                table.rows[0].cells[1].text = 'Count'
                row_idx = 1
                for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL']:
                    count = severity_counts.get(sev, 0)
                    if count > 0:
                        table.rows[row_idx].cells[0].text = sev
                        table.rows[row_idx].cells[1].text = str(count)
                        row_idx += 1
            
            doc.add_page_break()
            
            # ========== 3. RISK ANALYSIS ==========
            add_section_header('3. Risk Analysis')
            
            if risk_data:
                add_normal_text(f"Risk assessment data for {engagement_info.get('department', 'N/A')}:")
                table = doc.add_table(rows=min(len(risk_data), 15) + 1, cols=8)
                table.style = 'Light Grid Accent 1'
                headers = ['Period', 'Year', 'Likelihood', 'Impact', 'Risk Score', 'Rating', 'Ctrl Eff.', 'Residual']
                for i, h in enumerate(headers):
                    table.rows[0].cells[i].text = h
                for r_idx, r in enumerate(risk_data[:15]):
                    vals = [
                        r.assessment_period, str(r.year), str(r.likelihood), str(r.impact),
                        str(r.risk_score), r.risk_rating.upper() if r.risk_rating else 'N/A',
                        str(r.control_effectiveness), f"{r.residual_risk:.2f}" if r.residual_risk else 'N/A'
                    ]
                    for c_idx, val in enumerate(vals):
                        table.rows[r_idx + 1].cells[c_idx].text = val
            else:
                add_normal_text('No risk assessment data available for this engagement.')
            
            doc.add_page_break()
            
            # ========== 4. FINDINGS TABLE ==========
            add_section_header('4. Findings Summary Table')
            
            if findings:
                add_normal_text(f"The following table summarizes all {total_findings} finding(s):")
                table = doc.add_table(rows=len(findings) + 1, cols=7)
                table.style = 'Light Grid Accent 1'
                set_col_widths(table, [0.8, 1.7, 4.0, 1.9, 2.0, 1.8, 2.8])
                headers = ['#', 'Ref No.', 'Title', 'Severity', 'Category', 'Status', 'Recommendation']
                for i, h in enumerate(headers):
                    table.rows[0].cells[i].text = h
                for f_idx, f in enumerate(findings):
                    table.rows[f_idx + 1].cells[0].text = str(f_idx + 1)
                    table.rows[f_idx + 1].cells[1].text = f.finding_number
                    table.rows[f_idx + 1].cells[2].text = f.title[:60]
                    table.rows[f_idx + 1].cells[3].text = f.severity.upper() if f.severity else 'N/A'
                    table.rows[f_idx + 1].cells[4].text = f.category.replace('_', ' ').title() if f.category else 'N/A'
                    table.rows[f_idx + 1].cells[5].text = f.status.upper() if f.status else 'N/A'
                    table.rows[f_idx + 1].cells[6].text = f.recommendation[:80] if f.recommendation else 'N/A'
                
                # Detailed findings
                doc.add_paragraph('')
                add_bold_text('Detailed Finding Descriptions:')
                for f in findings:
                    add_bold_text(f"{f.finding_number}: {f.title}")
                    add_normal_text(f"Condition: {f.condition or 'N/A'}")
                    add_normal_text(f"Criteria: {f.criteria or 'N/A'}")
                    add_normal_text(f"Cause: {f.cause or 'N/A'}")
                    add_normal_text(f"Effect/Impact: {f.effect or 'N/A'}")
                    add_normal_text(f"Recommendation: {f.recommendation or 'N/A'}")
                    add_normal_text(f"Management Response: {f.management_response or 'N/A'}")
                    doc.add_paragraph('')

                note = _withheld_above_message(withheld_findings, _withheld_findings_note)
                if note:
                    add_normal_text(note)
            else:
                add_normal_text(_absence_message(
                    withheld_findings, _withheld_findings_note,
                    'No findings were registered for this engagement.',
                ))

            doc.add_page_break()
            
            # ========== 5. CAPA ==========
            add_section_header('5. Corrective Action Plan (CAPA)')
            
            if corrective_actions:
                add_normal_text(f"The following {len(corrective_actions)} corrective action(s) have been defined:")
                table = doc.add_table(rows=len(corrective_actions) + 1, cols=8)
                table.style = 'Light Grid Accent 1'
                set_col_widths(table, [0.65, 1.6, 3.8, 1.7, 1.5, 1.6, 2.25, 1.9])
                headers = ['#', 'Action No.', 'Title', 'Finding Ref', 'Priority', 'Status', 'Owner', 'Due Date']
                for i, h in enumerate(headers):
                    table.rows[0].cells[i].text = h
                for ca_idx, ca in enumerate(corrective_actions):
                    table.rows[ca_idx + 1].cells[0].text = str(ca_idx + 1)
                    table.rows[ca_idx + 1].cells[1].text = ca.action_number
                    table.rows[ca_idx + 1].cells[2].text = ca.title[:50]
                    table.rows[ca_idx + 1].cells[3].text = ca.finding.finding_number if ca.finding else 'N/A'
                    table.rows[ca_idx + 1].cells[4].text = ca.priority.upper() if ca.priority else 'N/A'
                    table.rows[ca_idx + 1].cells[5].text = ca.status.upper() if ca.status else 'N/A'
                    table.rows[ca_idx + 1].cells[6].text = ca.owner.full_name if ca.owner else 'Unassigned'
                    table.rows[ca_idx + 1].cells[7].text = str(ca.due_date)
                
                # Detailed CAPA
                doc.add_paragraph('')
                add_bold_text('Detailed Corrective Action Descriptions:')
                for ca in corrective_actions:
                    add_bold_text(f"{ca.action_number}: {ca.title}")
                    add_normal_text(f"Finding: {ca.finding.finding_number + ' - ' + ca.finding.title if ca.finding else 'N/A'}")
                    add_normal_text(f"Description: {ca.description or 'N/A'}")
                    add_normal_text(f"Recommendation: {ca.recommendation or 'N/A'}")
                    add_normal_text(f"Owner: {ca.owner.full_name if ca.owner else 'Unassigned'} | Due: {ca.due_date}")
                    if ca.management_response:
                        add_normal_text(f"Management Response: {ca.management_response}")
                    doc.add_paragraph('')

                note = _withheld_above_message(withheld_capas, _withheld_capas_note)
                if note:
                    add_normal_text(note)
            else:
                add_normal_text(_absence_message(
                    withheld_capas, _withheld_capas_note,
                    'No corrective actions have been assigned for findings in this engagement.',
                ))
            
            buf = BytesIO()
            doc.save(buf)
            buf.seek(0)
            report.file.save(filename, ContentFile(buf.read()), save=False)
            report.status = 'ready'
            report.save()
            
            log_audit(
                request, 'EXPORT', report,
                object_repr=f"Generated Word report: {report.title}",
                user=report.generated_by,
            )

    @action(detail=True, methods=['get'], url_path='export')
    def export(self, request, pk=None):
        report = self.get_object()
        if report.file:
            # Send the real content type so the browser names and opens the file
            # correctly; octet-stream made every download look like binary junk.
            content_type, _ = mimetypes.guess_type(report.file.name)
            response = HttpResponse(
                report.file.read(), content_type=content_type or 'application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{report.file.name.split("/")[-1]}"'
            return response
        return Response({'detail': 'Report file not generated yet.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='generate-pdf')
    def generate_pdf(self, request):
        """Generate a PDF report using ReportLab"""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        title = request.data.get('title', 'EEU Internal Audit Report')
        elements.append(Paragraph(title, styles['Title']))
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(
            f"Generated: {timezone.now().strftime('%d %B %Y %H:%M')}",
            styles['Normal']
        ))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            "Ethiopian Electric Utility — Internal Audit Department",
            styles['Normal']
        ))

        content = request.data.get('content', '')
        if content:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(content, styles['Normal']))

        doc.build(elements)
        buf.seek(0)
        pdf_bytes = buf.read()

        # One unit: a committed row claiming status='ready' with no file behind it
        # is a Download button that 400s forever, so the insert has to be inside
        # the transaction with the file write rather than committed ahead of it.
        # The bytes themselves may survive a rollback in storage — an unlink
        # cannot be rolled back — but an orphaned file nothing references is
        # harmless, where an orphaned row is a broken button in the UI.
        with transaction.atomic():
            report = GeneratedReport.objects.create(
                title=title, format='pdf', status='ready',
                generated_by=request.user,
                parameters=request.data
            )
            report.file.save(f"{title}.pdf", ContentFile(pdf_bytes), save=True)
            log_audit(
                request, 'EXPORT', report,
                object_repr=f"Generated PDF report: {report.title}",
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{title}.pdf"'
        return response

    @action(detail=False, methods=['post'], url_path='generate-excel')
    def generate_excel(self, request):
        """Generate an Excel report using openpyxl"""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        title = request.data.get('title', 'EEU Audit Report')
        ws.title = 'Audit Report'

        # Header
        ws['A1'] = 'Ethiopian Electric Utility — Internal Audit Department'
        ws['A1'].font = Font(bold=True, size=14)
        ws['A2'] = title
        ws['A2'].font = Font(bold=True, size=12)
        ws['A3'] = f"Generated: {timezone.now().strftime('%d/%m/%Y %H:%M')}"
        ws.column_dimensions['A'].width = 40

        headers = request.data.get('headers', ['Item', 'Details'])
        rows = request.data.get('rows', [])
        start_row = 5
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col, value=h)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill(fill_type='solid', fgColor='1E3A5F')
        for r_idx, row in enumerate(rows, start_row + 1):
            for c_idx, val in enumerate(row, 1):
                ws.cell(row=r_idx, column=c_idx, value=val)

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        xlsx_bytes = buf.read()

        # Record and persist it, exactly as generate_pdf does — insert and file
        # write in one transaction. Streaming the bytes back without saving left
        # no row in the Generated Reports list and nothing for the `export`
        # action to serve, so an Excel export existed only in the browser's
        # download folder.
        with transaction.atomic():
            report = GeneratedReport.objects.create(
                title=title, format='excel', status='ready',
                generated_by=request.user,
                parameters=request.data
            )
            report.file.save(f"{title}.xlsx", ContentFile(xlsx_bytes), save=True)
            log_audit(
                request, 'EXPORT', report,
                object_repr=f"Generated Excel report: {report.title}",
            )

        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{title}.xlsx"'
        return response

    @action(detail=False, methods=['get'], url_path='analytics')
    def analytics(self, request):
        """Return aggregated analytics data for dashboards"""
        from apps.findings.models import AuditFinding
        from apps.corrective_actions.models import CorrectiveAction
        from apps.audit_planning.models import AuditEngagement
        from django.db.models import Count, Q
        from django.utils import timezone
        from apps.common.date_utils import month_starts, month_end

        today = timezone.now().date()
        # Calendar months, not 30-day steps — stepping back by 30 * i skipped
        # February and returned the same 31-day month twice, so the chart lost
        # and duplicated buckets.
        starts = month_starts(today, 6)
        # One aggregate over the whole window instead of a query per month.
        buckets = {
            f'month_{index}': Count('id', filter=Q(
                created_at__date__gte=start, created_at__date__lte=month_end(start),
            ))
            for index, start in enumerate(starts)
        }
        counts = AuditFinding.objects.aggregate(**buckets)
        monthly_findings = [
            {'month': start.strftime('%b %Y'), 'count': counts.get(f'month_{index}', 0) or 0}
            for index, start in enumerate(starts)
        ]

        return Response({
            'findings_by_severity': list(
                AuditFinding.objects.values('severity').annotate(count=Count('id'))
            ),
            'findings_by_category': list(
                AuditFinding.objects.values('category').annotate(count=Count('id'))
            ),
            'actions_by_status': list(
                CorrectiveAction.objects.values('status').annotate(count=Count('id'))
            ),
            'engagements_by_type': list(
                AuditEngagement.objects.values('engagement_type').annotate(count=Count('id'))
            ),
            'monthly_findings': monthly_findings,
        })