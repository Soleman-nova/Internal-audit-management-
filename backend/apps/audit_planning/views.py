from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from .models import AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember, Project
from .serializers import (AuditUniverseSerializer, AuditPlanSerializer,
                          AuditEngagementSerializer, AuditTeamMemberSerializer, ProjectSerializer)
from apps.accounts.models import Department
from apps.common.permissions import (
    CanWriteAudit, RequiresCapability, InvolvedPartyOrCapability, APPROVE_PLANS,
)
from apps.common.audit_utils import log_audit
from apps.common.reference_numbers import save_with_reference_number
from apps.common.request_utils import with_parent
from apps.notifications.services import notify, notify_roles


# Finding statuses that block an engagement from being marked completed.
#
# `update_status` used to validate only that the incoming string was a member of
# STATUS_CHOICES, then stamp `actual_end` and back-fill
# AuditUniverse.last_audited — so an engagement could be signed off as complete,
# and its entity recorded as recently audited, with every one of its findings
# still in draft.
#
# This is the complement of the settled set DashboardStatsView uses
# (SETTLED_FINDING_STATUSES in apps/accounts/views.py) — duplicated rather than
# imported, because a view class in another app is not a home for shared policy.
#
# Narrow this to ('draft', 'disputed') if findings should be allowed to carry
# forward into CAPA follow-up after the engagement closes, which is how many
# internal audit functions work in practice.
BLOCKS_COMPLETION = ('draft', 'open', 'in_progress', 'disputed')
# How many finding numbers to name in the refusal before eliding the rest: enough
# to act on, short enough that an engagement with fifty open findings does not
# return a wall of text.
BLOCKERS_NAMED = 10


# ── Audit Universe bulk import/export ────────────────────────────────────────
#
# A round-trip spreadsheet is flat: each row is one AuditUniverse and the two
# Department links are identified by Department.code (unique) rather than by
# primary key, so a directory exported today can still be re-imported after the
# org tree has been rebuilt. Import is an upsert keyed on the unique `code`: a
# code already in the DB updates that entry (only the columns the sheet actually
# fills — a blank cell leaves the existing value alone, which is what makes an
# export → edit → re-import cycle lossless for technical_metadata etc.), and a
# new code creates an entry. Rows are validated independently so a few bad rows
# never roll back the rest of the batch.

UNIVERSE_EXPORT_HEADERS = [
    'code', 'name', 'category', 'department_code', 'directorate_code',
    'description', 'owner', 'risk_score', 'audit_frequency',
    'last_audited', 'status',
]

# Accepted spreadsheet header spellings, keyed by the canonical column name the
# header maps to. Headers are lower-cased with whitespace collapsed to single
# underscores before matching, so 'Entity Name', 'department', 'Last audit
# date' and 'last_audited' all resolve to the same column.
_UNIVERSE_HEADER_ALIASES = {
    'code': {'code', 'entity_code', 'universe_code', 'unique_code', 'ref_code'},
    'name': {'name', 'entity_name'},
    'category': {'category', 'entity_category', 'type'},
    'department_code': {'department_code', 'department', 'dept', 'dept_code',
                        'org_unit', 'org_unit_code', 'orgunit_code'},
    'directorate_code': {'directorate_code', 'directorate', 'dir_code',
                         'audit_directorate'},
    'description': {'description', 'notes'},
    'owner': {'owner', 'owner_name'},
    'risk_score': {'risk_score', 'risk', 'initial_risk_score', 'risk_level'},
    'audit_frequency': {'audit_frequency', 'frequency', 'audit_freq'},
    'last_audited': {'last_audited', 'last_audit_date', 'last_audited_date',
                     'date_last_audited'},
    'status': {'status'},
}


def _col_key(text):
    """Collapse a header/label into the token shape used for matching."""
    return '_'.join(str(text).strip().lower().split())


def _choice_map(choices):
    """Map punctuation-collapsed labels onto model values.

    Accepts both the stored value ('system') and its human label ('IT System'),
    so a spreadsheet typed by hand imports cleanly.
    """
    mapping = {}
    for value, label in choices:
        mapping[_col_key(value)] = value
        mapping[_col_key(label)] = value
    return mapping


_CATEGORY_MAP = _choice_map(AuditUniverse.CATEGORY_CHOICES)
_STATUS_MAP = _choice_map(AuditUniverse.STATUS_CHOICES)


def _canonical_column(header):
    for column, aliases in _UNIVERSE_HEADER_ALIASES.items():
        if _col_key(header) in aliases or _col_key(header) == column:
            return column
    return None


def _read_universe_upload(upload):
    """Read an uploaded .xlsx/.csv into canonical rows.

    Returns (data, blank_rows). ``data`` is a list of (row_number, fields)
    where fields maps canonical column names onto raw cell values ('' for blank
    cells) and row_number is the spreadsheet's 1-based row including the header,
    so errors can point the user at the exact row in Excel. Returns (None, None)
    when no header row is found.
    """
    name = (upload.name or '').lower()
    if name.endswith('.csv'):
        import csv
        import io
        text = upload.read().decode('utf-8-sig', errors='replace')
        upload.seek(0)
        rows = list(csv.reader(io.StringIO(text)))
    else:  # .xlsx
        import openpyxl
        workbook = openpyxl.load_workbook(upload, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        finally:
            workbook.close()

    def blank_row(row):
        return all(cell is None or not str(cell).strip() for cell in row)

    header_index = next(
        (i for i, row in enumerate(rows) if not blank_row(row)), None,
    )
    if header_index is None:
        return None, None

    columns = {}
    for index, cell in enumerate(rows[header_index]):
        if cell is None:
            continue
        column = _canonical_column(cell)
        if column:
            columns[index] = column

    data = []
    blank_rows = 0
    for offset, raw in enumerate(rows[header_index + 1:], start=1):
        if blank_row(raw):
            blank_rows += 1
            continue
        fields = {
            column: (raw[index] if index < len(raw) and raw[index] is not None else '')
            for index, column in columns.items()
        }
        data.append((header_index + 1 + offset, fields))
    return data, blank_rows


def _resolve_department(text, dept_by_code, dept_by_name):
    token = text.strip().lower()
    return dept_by_code.get(token) or dept_by_name.get(token)


def _parse_import_date(cell):
    from datetime import date, datetime
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    text = str(cell).strip()
    for parser in (date.fromisoformat, datetime.fromisoformat):
        try:
            parsed = parser(text)
        except ValueError:
            continue
        return parsed.date() if isinstance(parsed, datetime) else parsed
    return None


def _coerce_universe_row(fields, dept_by_code, dept_by_name, creating):
    """Validate one imported row and map it onto model-ready values.

    Returns (values, errors). ``values`` only carries columns the sheet filled,
    so during an update a blank cell leaves that attribute untouched; Department
    references arrive as resolved instances.
    """
    from decimal import Decimal, InvalidOperation

    errors = []
    values = {}

    def filled(cell):
        return cell is not None and str(cell).strip()

    code = str(fields.get('code') or '').strip()
    if not code:
        errors.append('code is required.')
    elif len(code) > 50:
        errors.append('code must be at most 50 characters.')
    else:
        values['code'] = code

    name = str(fields.get('name') or '').strip()
    if not name:
        if creating:
            errors.append('name is required for new entries.')
    elif len(name) > 300:
        errors.append('name must be at most 300 characters.')
    else:
        values['name'] = name

    category = fields.get('category')
    if filled(category):
        matched = _CATEGORY_MAP.get(_col_key(category))
        if matched:
            values['category'] = matched
        else:
            errors.append(f"invalid category '{category}'.")
    elif creating:
        errors.append('category is required for new entries.')

    status = fields.get('status')
    if filled(status):
        matched = _STATUS_MAP.get(_col_key(status))
        if matched:
            values['status'] = matched
        else:
            errors.append(f"invalid status '{status}'.")

    for attribute, key, limit in (
        ('description', 'description', None),
        ('owner', 'owner', 200),
        ('audit_frequency', 'audit_frequency', 50),
    ):
        cell = fields.get(key)
        if not filled(cell):
            continue
        text = str(cell).strip()
        if limit is not None and len(text) > limit:
            errors.append(f'{key} must be at most {limit} characters.')
        else:
            values[attribute] = text

    risk_score = fields.get('risk_score')
    if filled(risk_score):
        try:
            score = Decimal(str(risk_score).strip())
        except InvalidOperation:
            errors.append(f"risk_score must be a number, got '{risk_score}'.")
        else:
            if score < 0 or score > Decimal('999.99'):
                errors.append('risk_score must be between 0 and 999.99.')
            else:
                values['risk_score'] = score

    last_audited = fields.get('last_audited')
    if filled(last_audited):
        when = _parse_import_date(last_audited)
        if when is None:
            errors.append(f"last_audited must be a date (YYYY-MM-DD), got '{last_audited}'.")
        else:
            values['last_audited'] = when

    for attribute, key in (('department', 'department_code'),
                           ('directorate', 'directorate_code')):
        cell = fields.get(key)
        if not filled(cell):
            continue
        department = _resolve_department(str(cell).strip(), dept_by_code, dept_by_name)
        if department is None:
            errors.append(
                f"unknown {key} '{cell}': match it to a Department by its code or name."
            )
        else:
            values[attribute] = department

    return values, errors


class AuditUniverseViewSet(viewsets.ModelViewSet):
    queryset = AuditUniverse.objects.select_related('department', 'directorate').all()
    serializer_class = AuditUniverseSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'status', 'department', 'directorate']
    search_fields = ['name', 'code', 'owner']
    ordering_fields = ['risk_score', 'name', 'last_audited']
    # 'name' breaks the many ties at a shared risk score so offset pagination
    # over the universe cannot repeat or drop rows between page flips.
    ordering = ['-risk_score', 'name']

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            log_audit(self.request, 'CREATE', obj)

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            log_audit(self.request, 'UPDATE', obj)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=False, methods=['get'], url_path='due-for-re-audit')
    def due_for_re_audit(self, request):
        """Phase 3.3 — entities whose next audit window has lapsed.

        Filters by the entity's configured ``audit_frequency`` relative to
        ``last_audited``. Accepts ``?as_of=YYYY-MM-DD`` for "what if" queries
        and optional ``?category=`` to narrow results.
        """
        queryset = self.get_queryset().filter(status='active')
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        as_of = request.query_params.get('as_of')
        as_of_date = None
        if as_of:
            try:
                as_of_date = timezone.datetime.strptime(as_of, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'detail': 'Invalid as_of date, expected YYYY-MM-DD.'},
                    status=400,
                )
        results = [u for u in queryset if u.is_due_for_re_audit(as_of=as_of_date)]
        page = self.paginate_queryset(results)
        serializer = self.get_serializer(page or results, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """Stream the audit universe as an Excel (.xlsx) or CSV file.

        Honors the viewset's filterset/search/ordering, so ``?filetype=csv`` on
        a filtered list exports exactly what the caller filtered to; with no
        query params it is the whole universe. The column layout is the import
        template, so an exported file can be edited and uploaded back.

        The selector is deliberately *not* named ``format``: DRF treats a
        ``?format=`` query parameter as its URL-format override and 404s a
        request whose value matches no renderer (``xlsx``/``csv`` never would).
        """
        export_format = (request.query_params.get('filetype') or 'xlsx').lower()
        if export_format not in ('xlsx', 'csv'):
            return Response(
                {'detail': "Unsupported format; expected 'xlsx' or 'csv'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = []
        for item in self.filter_queryset(self.get_queryset()):
            rows.append([
                item.code,
                item.name,
                item.category,
                item.department.code if item.department else '',
                item.directorate.code if item.directorate else '',
                item.description,
                item.owner,
                item.risk_score,
                item.audit_frequency,
                item.last_audited.isoformat() if item.last_audited else '',
                item.status,
            ])

        filename = f"audit_universe_{timezone.now().strftime('%Y%m%d')}"
        if export_format == 'csv':
            import csv
            import io
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(UNIVERSE_EXPORT_HEADERS)
            writer.writerows(rows)
            # BOM so Excel opens a CSV holding Amharic department names correctly.
            payload = b'\xef\xbb\xbf' + buffer.getvalue().encode('utf-8')
            content_type = 'text/csv'
            filename += '.csv'
        else:
            import io
            import openpyxl
            from openpyxl.styles import Font, PatternFill
            from openpyxl.utils import get_column_letter
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = 'Audit Universe'
            header_font = Font(bold=True, color='FFFFFF')
            header_fill = PatternFill(fill_type='solid', fgColor='1E3A5F')
            for column_index, header in enumerate(UNIVERSE_EXPORT_HEADERS, 1):
                cell = sheet.cell(row=1, column=column_index, value=header)
                cell.font = header_font
                cell.fill = header_fill
            for row_index, row in enumerate(rows, start=2):
                for column_index, value in enumerate(row, 1):
                    sheet.cell(row=row_index, column=column_index, value=value)
            for column_index in range(1, len(UNIVERSE_EXPORT_HEADERS) + 1):
                sheet.column_dimensions[get_column_letter(column_index)].width = 40
            buffer = io.BytesIO()
            workbook.save(buffer)
            payload = buffer.getvalue()
            content_type = (
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            filename += '.xlsx'

        response = HttpResponse(payload, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        log_audit(
            request, 'EXPORT', None, model_name='AuditUniverse',
            object_repr=f'Exported {len(rows)} audit universe record(s) as {export_format.upper()}.',
        )
        return response

    @action(detail=False, methods=['post'], url_path='import',
            parser_classes=[MultiPartParser, FormParser, JSONParser])
    def import_universe(self, request):
        """Bulk-create or -update universe entries from an uploaded file.

        ``file`` is a multipart field holding an .xlsx or .csv whose columns are
        the export layout above. Rows are upserted by the unique ``code`` and
        validated independently: valid rows are committed and invalid ones are
        returned with their spreadsheet row number, never rolling back the rest
        of the batch.
        """
        upload = request.FILES.get('file')
        if upload is None:
            return Response(
                {'detail': 'No file uploaded (expected a multipart field named "file").'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        filename = (upload.name or '').lower()
        if not filename.endswith(('.xlsx', '.csv')):
            return Response(
                {'detail': 'Unsupported file type. Upload an .xlsx or .csv file.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data, blank_rows = _read_universe_upload(upload)
        except Exception as exc:
            return Response(
                {'detail': f'Could not read the file: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if data is None:
            return Response(
                {'detail': 'The file is empty — expected a header row followed by data rows.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Every non-empty row carries the same columns, so the first one tells us
        # whether the file has the identity columns at all.
        if data:
            missing = [c for c in ('code', 'name') if c not in data[0][1]]
            if missing:
                return Response(
                    {'detail': 'Missing required column(s): '
                               f'{", ".join(missing)}. Expected at least code and name.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        departments = list(Department.objects.all())
        dept_by_code = {d.code.strip().lower(): d for d in departments if d.code}
        dept_by_name = {d.name.strip().lower(): d for d in departments}

        file_codes = {
            str(fields.get('code') or '').strip() for _, fields in data
        }
        existing = {
            universe.code: universe
            for universe in AuditUniverse.objects.filter(code__in=file_codes)
        }

        created = updated = 0
        errors = []
        for row_number, fields in data:
            code = str(fields.get('code') or '').strip()
            target = existing.get(code)
            values, row_errors = _coerce_universe_row(
                fields, dept_by_code, dept_by_name, creating=target is None,
            )
            if row_errors:
                errors.extend(
                    {'row': row_number, 'message': message}
                    for message in row_errors
                )
                continue

            try:
                with transaction.atomic():
                    if target is None:
                        AuditUniverse.objects.create(**values)
                        created += 1
                    else:
                        changed = False
                        for attribute, value in values.items():
                            if attribute == 'code':
                                continue  # identity key, never rewritten
                            if getattr(target, attribute) != value:
                                setattr(target, attribute, value)
                                changed = True
                        if changed:
                            target.save()
                            updated += 1
            except Exception as exc:
                errors.append(
                    {'row': row_number, 'message': f'could not be imported: {exc}'}
                )

        log_audit(
            request, 'IMPORT', None, model_name='AuditUniverse',
            object_repr=(
                f'Imported {upload.name}: {created} created, {updated} updated, '
                f'{len(errors)} error(s).'
            )[:300],
        )
        return Response({
            'total_rows': len(data),
            'blank_rows': blank_rows,
            'created': created,
            'updated': updated,
            'errors': errors,
        })


class ProjectViewSet(viewsets.ModelViewSet):
    """PPM project registry feeding the Audit Universe project dropdown."""
    queryset = Project.objects.select_related('department').all()
    serializer_class = ProjectSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department']
    search_fields = ['name', 'code']
    ordering = ['name']

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            log_audit(self.request, 'CREATE', obj)

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            log_audit(self.request, 'UPDATE', obj)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()


class AuditPlanViewSet(viewsets.ModelViewSet):
    queryset = AuditPlan.objects.select_related('created_by', 'approved_by', 'directorate', 'parent_plan').prefetch_related('engagements').all()
    serializer_class = AuditPlanSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'year', 'directorate', 'plan_scope']
    search_fields = ['title', 'description']
    # 'created_at' is a deterministic tiebreaker: many plans share a year, and
    # offset pagination over ties can repeat/drop rows between page flips.
    ordering = ['-year', '-created_at']

    def perform_create(self, serializer):
        with transaction.atomic():
            plan = serializer.save(created_by=self.request.user)
            log_audit(self.request, 'CREATE', plan)

    def perform_update(self, serializer):
        with transaction.atomic():
            plan = serializer.save()
            log_audit(self.request, 'UPDATE', plan)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def approve(self, request, pk=None):
        plan = self.get_object()
        prev_status = plan.status
        with transaction.atomic():
            plan.status = 'approved'
            plan.approved_by = request.user
            plan.approved_at = timezone.now()
            plan.save()
            log_audit(request, 'APPROVE', plan, changes={'status': [prev_status, 'approved']})
            # Notify the plan's author that it was approved.
            if plan.created_by and plan.created_by != request.user:
                notify(
                    plan.created_by,
                    'approved',
                    f'Audit plan approved: {plan.year}',
                    f'Your audit plan "{plan.title}" has been approved.',
                    f'/planning?plan={plan.id}',
                )
        return Response({'detail': 'Plan approved successfully.'})

    @action(detail=True, methods=['post'], url_path='submit',
            permission_classes=[InvolvedPartyOrCapability.for_(
                'created_by', capability=APPROVE_PLANS)])
    def submit(self, request, pk=None):
        """Send the plan up for approval.

        Restricted to the author plus APPROVE_PLANS holders. At the class-level
        WRITE_AUDIT gate any auditor could submit a plan they had no part in
        drafting, which then went to the approvers under their name.
        """
        plan = self.get_object()
        prev_status = plan.status
        with transaction.atomic():
            plan.status = 'submitted'
            plan.save()
            log_audit(request, 'UPDATE', plan, changes={'status': [prev_status, 'submitted']})
            # Notify the approvers that a plan is awaiting their approval.
            notify_roles(
                ['admin', 'audit_manager'],
                'approval_needed',
                f'Audit plan awaiting approval: {plan.year}',
                f'Audit plan "{plan.title}" has been submitted for approval by '
                f'{request.user.get_full_name() or request.user.username}.',
                f'/planning?plan={plan.id}',
                exclude=request.user,
            )
        return Response({'detail': 'Plan submitted for approval.'})


class AuditEngagementViewSet(viewsets.ModelViewSet):
    queryset = AuditEngagement.objects.select_related(
        'plan', 'department', 'directorate', 'lead_auditor', 'supervisor', 'audit_universe'
    ).prefetch_related('team_members', 'findings').all()
    serializer_class = AuditEngagementSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'engagement_type', 'plan', 'department', 'directorate', 'risk_level']
    search_fields = ['title', 'engagement_number', 'objectives']
    ordering = ['-created_at', '-id']

    def get_queryset(self):
        """Auditees see only engagements covering their own department.

        Same shape as AuditFindingViewSet.get_queryset. An auditee is a
        department representative, so the EEU-wide engagement calendar — who is
        being audited, when, and by whom — is not theirs to read. A user with no
        department sees only the engagements they are personally named on rather
        than everything, which is the safer reading of a missing department.
        """
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and user.role == 'auditee':
            scope = Q(lead_auditor=user) | Q(supervisor=user) | Q(team_members__user=user)
            if user.department_id:
                scope |= Q(department_id=user.department_id)
            return qs.filter(scope).distinct()
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            engagement = save_with_reference_number(
                serializer, 'engagement_number', 'ENG',
            )
            log_audit(self.request, 'CREATE', engagement)
            # Notify the lead auditor and supervisor of their assignment.
            link = f'/planning?engagement={engagement.id}'
            recipients = {engagement.lead_auditor, engagement.supervisor}
            recipients.discard(None)
            recipients.discard(self.request.user)
            for recipient in recipients:
                notify(
                    recipient,
                    'assigned',
                    f'New engagement: {engagement.engagement_number}',
                    f'You have been assigned to audit engagement "{engagement.title}".',
                    link,
                )

    def perform_update(self, serializer):
        with transaction.atomic():
            engagement = serializer.save()
            log_audit(self.request, 'UPDATE', engagement)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=True, methods=['post'], url_path='add-member')
    def add_member(self, request, pk=None):
        engagement = self.get_object()
        data = with_parent(request.data, engagement=engagement.id)
        serializer = AuditTeamMemberSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            member = serializer.save()
            log_audit(request, 'UPDATE', engagement)
            # Notify the newly added team member.
            if member.user and member.user != request.user:
                notify(
                    member.user,
                    'assigned',
                    f'Added to engagement: {engagement.engagement_number}',
                    f'You have been added to audit engagement "{engagement.title}" '
                    f'as {member.get_role_display()}.',
                    f'/planning?engagement={engagement.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        engagement = self.get_object()
        new_status = request.data.get('status')
        if new_status not in dict(AuditEngagement.STATUS_CHOICES):
            return Response({'detail': 'Invalid status.'},
                            status=status.HTTP_400_BAD_REQUEST)
        # Completion is a sign-off, so it has a precondition. Checked *before*
        # the transaction opens, so a refusal writes nothing at all — no status
        # change, no actual_end, no last_audited back-fill, no audit-trail entry
        # and no notifications.
        #
        # Only `completed` is guarded: `cancelled` may legitimately be applied to
        # an engagement that still has open findings, and `reporting` is exactly
        # when findings are being worked.
        if new_status == 'completed':
            unresolved = engagement.findings.filter(status__in=BLOCKS_COMPLETION)
            total = unresolved.count()
            if total:
                named = list(
                    unresolved.order_by('finding_number')
                    .values_list('finding_number', flat=True)[:BLOCKERS_NAMED]
                )
                listed = ', '.join(named) + (', …' if total > len(named) else '')
                return Response(
                    {'detail': f'Cannot complete this engagement: {total} finding(s) are '
                               f'not yet resolved or closed ({listed}). Resolve or close '
                               f'them first.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        old_status = engagement.status
        with transaction.atomic():
            engagement.status = new_status
            if new_status == 'in_progress' and not engagement.actual_start:
                engagement.actual_start = timezone.now().date()
            elif new_status == 'completed' and not engagement.actual_end:
                engagement.actual_end = timezone.now().date()
            engagement.save()
            # Phase 3.3 — close the re-audit loop: record the audit date on the
            # universe entry the engagement covered.
            if new_status == 'completed':
                universe = engagement.audit_universe
                if universe is None and engagement.department_id:
                    universe = (
                        AuditUniverse.objects
                        .filter(department_id=engagement.department_id, status='active')
                        .order_by('-risk_score')
                        .first()
                    )
                if universe is not None:
                    universe.last_audited = engagement.actual_end or timezone.now().date()
                    universe.save(update_fields=['last_audited', 'updated_at'])
            log_audit(request, 'UPDATE', engagement, changes={'status': [old_status, new_status]})
            # Notify the relevant parties of the status transition.
            link = f'/planning?engagement={engagement.id}'
            if new_status == 'in_progress' and engagement.lead_auditor and engagement.lead_auditor != request.user:
                notify(
                    engagement.lead_auditor,
                    'assigned',
                    f'Engagement started: {engagement.engagement_number}',
                    f'Audit engagement "{engagement.title}" has been moved to In Progress.',
                    link,
                )
            elif new_status in ('reporting', 'completed'):
                notify_roles(
                    ['supervisor', 'audit_manager'],
                    'system',
                    f'Engagement {engagement.get_status_display().lower()}: {engagement.engagement_number}',
                    f'Audit engagement "{engagement.title}" is now {engagement.get_status_display()}.',
                    link,
                    exclude=request.user,
                )
        return Response({'detail': f'Status updated to {new_status}.'})