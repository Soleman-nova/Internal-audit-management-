from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q
from django.utils import timezone
import random, string

from .models import AuditFinding, Evidence, FindingComment
from .serializers import AuditFindingSerializer, EvidenceSerializer, FindingCommentSerializer
from apps.notifications.services import notify
from apps.common.permissions import (
    CanWriteAudit, RequiresCapability, InvolvedPartyOrCapability, CLOSE_FINDINGS,
)
from apps.common.audit_utils import log_audit


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

    def get_queryset(self):
        """Auditees see only findings that concern them.

        Same shape as CorrectiveActionViewSet.get_queryset — an auditee is a
        department representative, not an auditor, so a full EEU-wide findings
        register would expose other directorates' issues. Everyone with a
        capability keeps the unfiltered view.
        """
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and user.role == 'auditee':
            scope = Q(auditee=user) | Q(assigned_to=user)
            if user.department_id:
                scope |= Q(engagement__department_id=user.department_id)
            return qs.filter(scope).distinct()
        return qs

    def perform_create(self, serializer):
        num = ''.join(random.choices(string.digits, k=5))
        finding = serializer.save(
            identified_by=self.request.user,
            finding_number=f'FND-{num}'
        )
        log_audit(self.request, 'CREATE', finding)
        # Notify the people responsible for acting on this finding.
        link = f'/findings/{finding.id}'
        recipients = {finding.assigned_to, finding.auditee}
        recipients.discard(None)
        recipients.discard(self.request.user)
        for recipient in recipients:
            notify(
                recipient,
                'finding',
                f'New finding: {finding.finding_number}',
                f'A {finding.get_severity_display() if hasattr(finding, "get_severity_display") else finding.severity} '
                f'finding "{finding.title}" has been assigned to you.',
                link,
            )

    def perform_update(self, serializer):
        prev_assigned_id = serializer.instance.assigned_to_id
        prev_auditee_id = serializer.instance.auditee_id
        prev_status = serializer.instance.status
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
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='add-comment',
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def add_comment(self, request, pk=None):
        finding = self.get_object()
        # The finding comes from the URL, but FindingCommentSerializer still
        # declares it required, so it has to be in `data` and not just in
        # `save()` — otherwise every comment 400s on "finding: required".
        data = request.data.copy()
        data['finding'] = finding.id
        serializer = FindingCommentSerializer(data=data)
        serializer.is_valid(raise_exception=True)
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
        # upload form only carries title/type/file.
        data = request.data.copy()
        data['finding'] = finding.id
        serializer = EvidenceSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
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
        prev_status = finding.status
        finding.status = 'closed'
        finding.actual_resolution_date = timezone.now().date()
        finding.save()
        log_audit(request, 'UPDATE', finding, changes={'status': [prev_status, 'closed']})
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
        prev_status = finding.status
        finding.status = 'resolved'
        finding.actual_resolution_date = timezone.now().date()
        finding.save()
        log_audit(request, 'UPDATE', finding, changes={'status': [prev_status, 'resolved']})
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
        prev_status = finding.status
        finding.status = 'disputed'
        finding.save()
        log_audit(request, 'UPDATE', finding, changes={'status': [prev_status, 'disputed']})
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
        prev_status = finding.status
        finding.status = 'in_progress'
        finding.actual_resolution_date = None
        finding.save()
        log_audit(request, 'UPDATE', finding, changes={'status': [prev_status, 'in_progress']})
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