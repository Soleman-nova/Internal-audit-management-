from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
import mimetypes

from .models import AuditFinding, Evidence, FindingComment
from .serializers import (
    AuditFindingSerializer, AuditFindingListSerializer, EvidenceSerializer,
    FindingCommentSerializer,
)
from apps.notifications.services import notify
from apps.common.permissions import (
    CanWriteAudit, RequiresCapability, InvolvedPartyOrCapability, CLOSE_FINDINGS,
)
from apps.common.audit_utils import log_audit
from apps.common.reference_numbers import save_with_reference_number
from apps.common.request_utils import with_parent

# Which status a finding may move to, per action. Every action used to assign
# unconditionally, so a closed finding could be closed twice and `resolve` would
# happily run on a disputed one — each time writing an audit-trail entry and
# firing a notification for a transition that never really happened.
ALLOWED_TRANSITIONS = {
    'resolved': {'draft', 'open', 'in_progress', 'disputed'},
    'closed': {'draft', 'open', 'in_progress', 'resolved', 'disputed'},
    'disputed': {'draft', 'open', 'in_progress', 'resolved'},
    'in_progress': {'resolved', 'closed', 'disputed'},
}



class AuditFindingViewSet(viewsets.ModelViewSet):
    queryset = AuditFinding.objects.select_related(
        'engagement', 'procedure', 'identified_by', 'assigned_to', 'auditee'
    ).prefetch_related('evidence', 'comments', 'corrective_actions').all()
    serializer_class = AuditFindingSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['severity', 'status', 'category', 'engagement', 'is_repeat']
    search_fields = ['title', 'description', 'finding_number', 'recommendation']
    ordering_fields = ['created_at', 'severity', 'status', 'target_resolution_date']
    ordering = ['-created_at']

    def get_serializer_class(self):
        """The register gets counts; everything else gets the full record.

        Only `list` — `retrieve` still returns nested evidence and comments, so
        the detail page needs no second round of requests.
        """
        if self.action == 'list':
            return AuditFindingListSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """Auditees see only findings that concern them.

        Same shape as CorrectiveActionViewSet.get_queryset — an auditee is a
        department representative, not an auditor, so a full EEU-wide findings
        register would expose other directorates' issues. Everyone with a
        capability keeps the unfiltered view.
        """
        user = self.request.user
        qs = super().get_queryset()
        if self.action == 'list':
            # The list serializer reports counts rather than nesting the rows, so
            # the class-level prefetch would fetch every evidence record and
            # every comment on the page only to throw them away. Annotate
            # instead — one query for the page, no per-row .count().
            #
            # distinct=True because three joins against the same rows multiply
            # each other; without it every count would be inflated by the size
            # of the other two.
            qs = qs.prefetch_related(None).annotate(
                evidence_count=Count('evidence', distinct=True),
                comments_count=Count('comments', distinct=True),
                corrective_actions_count=Count('corrective_actions', distinct=True),
            )
        if user.is_authenticated and user.role == 'auditee':
            scope = Q(auditee=user) | Q(assigned_to=user)
            if user.department_id:
                scope |= Q(engagement__department_id=user.department_id)
            return qs.filter(scope).distinct()
        return qs

    def perform_create(self, serializer):
        # One transaction for the row, its audit-trail entry, and its
        # notifications. Notifications are DB rows, so they roll back with the
        # finding on failure rather than pointing at a record that never
        # committed — no post-commit hook needed.
        with transaction.atomic():
            finding = save_with_reference_number(
                serializer, 'finding_number', 'FND',
                identified_by=self.request.user,
            )
            log_audit(self.request, 'CREATE', finding)
            # Notify the people responsible for acting on this finding.
            link = f'/findings/{finding.id}'
            recipients = {finding.assigned_to, finding.auditee}
            recipients.discard(None)
            recipients.discard(self.request.user)
            severity = (
                finding.get_severity_display()
                if hasattr(finding, 'get_severity_display') else finding.severity
            )
            for recipient in recipients:
                notify(
                    recipient,
                    'finding',
                    f'New finding: {finding.finding_number}',
                    f'A {severity} finding "{finding.title}" has been assigned to you.',
                    link,
                )

    def perform_update(self, serializer):
        prev_assigned_id = serializer.instance.assigned_to_id
        prev_auditee_id = serializer.instance.auditee_id
        prev_status = serializer.instance.status
        with transaction.atomic():
            finding = serializer.save()
            changes = None
            if finding.status != prev_status:
                changes = {'status': [prev_status, finding.status]}
            log_audit(self.request, 'UPDATE', finding, changes=changes)
            # Notify anyone newly assigned during this update.
            link = f'/findings/{finding.id}'
            newly = []
            if finding.assigned_to_id and finding.assigned_to_id != prev_assigned_id:
                newly.append(finding.assigned_to)
            if finding.auditee_id and finding.auditee_id != prev_auditee_id:
                newly.append(finding.auditee)
            for recipient in newly:
                if recipient and recipient != self.request.user:
                    notify(
                        recipient,
                        'assigned',
                        f'Finding assigned: {finding.finding_number}',
                        f'You have been assigned to finding "{finding.title}".',
                        link,
                    )

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    def _transition(self, request, finding, new_status, resolution_date=...):
        """Apply a status change, or return a 400 Response if it is not legal.

        ``resolution_date`` is ``...`` when the action should leave
        ``actual_resolution_date`` alone; pass a date or None to set it.
        """
        allowed = ALLOWED_TRANSITIONS.get(new_status, set())
        if finding.status not in allowed:
            return None, Response(
                {'detail': f'Cannot move a {finding.get_status_display()} finding to '
                           f'{dict(AuditFinding.STATUS_CHOICES)[new_status]}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prev_status = finding.status
        finding.status = new_status
        if resolution_date is not ...:
            finding.actual_resolution_date = resolution_date
        finding.save()
        log_audit(request, 'UPDATE', finding, changes={'status': [prev_status, new_status]})
        return prev_status, None

    @action(detail=True, methods=['post'], url_path='add-comment',
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def add_comment(self, request, pk=None):
        finding = self.get_object()
        # The finding comes from the URL, but FindingCommentSerializer still
        # declares it required, so it has to be in `data` and not just in
        # `save()` — otherwise every comment 400s on "finding: required".
        data = with_parent(request.data, finding=finding.id)
        serializer = FindingCommentSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            comment = serializer.save(author=request.user)
            log_audit(request, 'UPDATE', finding,
                      object_repr=f'Comment added to {finding.finding_number}')
            # Pull the rest of the thread in: whoever raised it, owns it, or is
            # answering for it should know a reply landed.
            recipients = {finding.identified_by, finding.assigned_to, finding.auditee}
            recipients.discard(None)
            recipients.discard(request.user)
            for recipient in recipients:
                notify(
                    recipient,
                    'comment',
                    f'New comment on {finding.finding_number}',
                    f'{request.user.get_full_name() or request.user.email} commented: '
                    f'{comment.comment[:120]}',
                    f'/findings/{finding.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='upload-evidence',
            parser_classes=[MultiPartParser, FormParser, JSONParser],
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def upload_evidence(self, request, pk=None):
        finding = self.get_object()
        # Same as add_comment: `finding` is a required serializer field, and the
        # upload form only carries title/type/file. `with_parent` rather than
        # `request.data.copy()` because copying a multipart QueryDict deep-copies
        # the upload, and a file large enough to be spooled to disk cannot be
        # pickled — see apps/common/request_utils.py.
        data = with_parent(request.data, finding=finding.id)
        serializer = EvidenceSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            evidence = serializer.save(uploaded_by=request.user)
            log_audit(request, 'UPDATE', finding,
                      object_repr=f'Evidence "{evidence.title}" added to {finding.finding_number}')
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'finding',
                    f'Evidence added to {finding.finding_number}',
                    f'{request.user.get_full_name() or request.user.email} attached '
                    f'"{evidence.title}".',
                    f'/findings/{finding.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close',
            permission_classes=[RequiresCapability.for_(CLOSE_FINDINGS)])
    def close(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, 'closed',
                                        resolution_date=timezone.now().date())
            if error:
                return error
            # Let the auditor who raised it know it was closed.
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'system',
                    f'Finding closed: {finding.finding_number}',
                    f'Finding "{finding.title}" has been closed.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding closed.'})

    @action(detail=True, methods=['post'], url_path='resolve',
            permission_classes=[RequiresCapability.for_(CLOSE_FINDINGS)])
    def resolve(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, 'resolved',
                                        resolution_date=timezone.now().date())
            if error:
                return error
            # Let the auditor who raised it know it was resolved.
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'system',
                    f'Finding resolved: {finding.finding_number}',
                    f'Finding "{finding.title}" has been marked as resolved.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding marked as resolved.'})

    @action(detail=True, methods=['post'], url_path='dispute',
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def dispute(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            # Clear the resolution date, as `reopen` already did. Disputing a
            # resolved finding used to leave the old date behind, so an
            # unresolved record still carried a resolution date — and that date
            # feeds the report analytics.
            _, error = self._transition(request, finding, 'disputed', resolution_date=None)
            if error:
                return error
            # Notify the auditor who identified it that the finding is disputed.
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'system',
                    f'Finding disputed: {finding.finding_number}',
                    f'Finding "{finding.title}" has been disputed by '
                    f'{request.user.get_full_name() or request.user.username}.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding marked as disputed.'})

    @action(detail=True, methods=['post'], url_path='reopen',
            permission_classes=[RequiresCapability.for_(CLOSE_FINDINGS)])
    def reopen(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, 'in_progress', resolution_date=None)
            if error:
                return error
            # Notify the assignee that the finding was reopened.
            if finding.assigned_to and finding.assigned_to != request.user:
                notify(
                    finding.assigned_to,
                    'system',
                    f'Finding reopened: {finding.finding_number}',
                    f'Finding "{finding.title}" has been reopened and needs attention.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding reopened.'})


class EvidenceViewSet(viewsets.ModelViewSet):
    # Newest first, and ordered at all: Evidence has no Meta.ordering, so
    # paginating an unordered queryset could repeat or skip attachments between
    # pages. Same reason AuditProgramViewSet carries an explicit ordering.
    queryset = Evidence.objects.select_related('finding', 'uploaded_by').order_by('-uploaded_at')
    serializer_class = EvidenceSerializer
    permission_classes = [CanWriteAudit]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['finding', 'evidence_type']

    def get_queryset(self):
        """Evidence inherits its finding's visibility — auditees see only theirs."""
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and user.role == 'auditee':
            scope = Q(finding__auditee=user) | Q(finding__assigned_to=user)
            if user.department_id:
                scope |= Q(finding__engagement__department_id=user.department_id)
            return qs.filter(scope).distinct()
        return qs

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """Stream the attachment through the API instead of exposing /media/.

        `EvidenceSerializer.file_url` used to hand out an absolute MEDIA_URL,
        which meant audit evidence was readable by anyone holding the link with
        no token at all — and bypassed the auditee scoping in `get_queryset`
        entirely. It also stopped working under DEBUG=False, because the
        `static()` helper mounting MEDIA_URL returns [] in production.

        Authorization is `get_object()` running against the scoped queryset, so
        an auditee can only reach evidence on findings that concern them. Same
        shape as WorkingPaperViewSet.download.
        """
        evidence = self.get_object()
        if not evidence.file:
            return Response({'detail': 'No file attached to this evidence.'},
                            status=status.HTTP_400_BAD_REQUEST)
        content_type, _ = mimetypes.guess_type(evidence.file.name)
        response = HttpResponse(evidence.file.read(),
                                content_type=content_type or 'application/octet-stream')
        filename = evidence.file.name.split('/')[-1]
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response