from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.utils import timezone

from .models import CorrectiveAction, ActionResponse, FollowUp
from .serializers import CorrectiveActionSerializer, ActionResponseSerializer, FollowUpSerializer
from apps.notifications.services import notify
from apps.common.permissions import (
    CanWriteAudit, InvolvedPartyOrCapability, APPROVE_PLANS,
)
from apps.common.audit_utils import log_audit
from apps.common.reference_numbers import save_with_reference_number
from apps.common.request_utils import with_parent


class CorrectiveActionViewSet(viewsets.ModelViewSet):
    queryset = CorrectiveAction.objects.select_related(
        'finding', 'owner', 'assigned_by'
    ).prefetch_related('responses', 'follow_ups').all()
    serializer_class = CorrectiveActionSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'finding', 'owner']
    search_fields = ['title', 'description', 'recommendation', 'action_number']
    ordering_fields = ['due_date', 'created_at', 'priority']
    ordering = ['due_date']

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and user.role == 'auditee':
            if user.department:
                return qs.filter(owner__department=user.department)
            return qs.filter(owner=user)
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            action_obj = save_with_reference_number(
                serializer, 'action_number', 'CAPA',
                assigned_by=self.request.user,
            )
            log_audit(self.request, 'CREATE', action_obj)
            # Notify the owner that a corrective action was assigned to them.
            if action_obj.owner and action_obj.owner != self.request.user:
                due = action_obj.due_date.isoformat() if action_obj.due_date else 'no due date set'
                notify(
                    action_obj.owner,
                    'assigned',
                    f'New corrective action: {action_obj.action_number}',
                    f'You have been assigned corrective action "{action_obj.title}" (due {due}).',
                    f'/capa/{action_obj.id}',
                )

    def perform_update(self, serializer):
        prev_owner_id = serializer.instance.owner_id
        prev_status = serializer.instance.status
        with transaction.atomic():
            action_obj = serializer.save()
            changes = None
            if action_obj.status != prev_status:
                changes = {'status': [prev_status, action_obj.status]}
            log_audit(self.request, 'UPDATE', action_obj, changes=changes)
            # Notify a newly assigned owner.
            if (action_obj.owner_id and action_obj.owner_id != prev_owner_id
                    and action_obj.owner != self.request.user):
                notify(
                    action_obj.owner,
                    'assigned',
                    f'Corrective action assigned: {action_obj.action_number}',
                    f'You have been assigned corrective action "{action_obj.title}".',
                    f'/capa/{action_obj.id}',
                )

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=True, methods=['post'], url_path='add-response',
            permission_classes=[InvolvedPartyOrCapability.for_('owner')])
    def add_response(self, request, pk=None):
        action_obj = self.get_object()
        # `with_parent` rather than `request.data.copy()`: this route accepts an
        # `evidence_file`, and copying a multipart QueryDict deep-copies the
        # upload — which fails outright once the file is big enough to be spooled
        # to disk. See apps/common/request_utils.py.
        data = with_parent(request.data, corrective_action=action_obj.id)
        serializer = ActionResponseSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        prev_status = action_obj.status
        with transaction.atomic():
            serializer.save(responder=request.user)
            # `status_update` is a required ChoiceField on ActionResponse, so it is
            # present and already checked against STATUS_CHOICES by the validation
            # above — read it from validated_data rather than the raw payload.
            action_obj.status = serializer.validated_data['status_update']
            action_obj.save(update_fields=['status', 'updated_at'])
            changes = None
            if action_obj.status != prev_status:
                changes = {'status': [prev_status, action_obj.status]}
            log_audit(request, 'UPDATE', action_obj, changes=changes)
            # Let the assigner know the owner responded / provided progress.
            if action_obj.assigned_by and action_obj.assigned_by != request.user:
                notify(
                    action_obj.assigned_by,
                    'follow_up',
                    f'Response on {action_obj.action_number}',
                    f'{request.user.get_full_name() or request.user.username} responded on '
                    f'corrective action "{action_obj.title}".',
                    f'/capa/{action_obj.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='schedule-followup',
            permission_classes=[InvolvedPartyOrCapability.for_(
                'assigned_by', capability=APPROVE_PLANS)])
    def schedule_followup(self, request, pk=None):
        """Record a verification follow-up against the action.

        Scoped to whoever raised the action, plus APPROVE_PLANS holders
        (supervisor and above) who verify across engagements. The class-level
        WRITE_AUDIT gate let any auditor sign off on a colleague's CAPA.
        """
        action_obj = self.get_object()
        data = with_parent(request.data, corrective_action=action_obj.id)
        serializer = FollowUpSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save(conducted_by=request.user)
            log_audit(request, 'UPDATE', action_obj)
            # Notify the owner that a follow-up was scheduled for their action.
            if action_obj.owner and action_obj.owner != request.user:
                notify(
                    action_obj.owner,
                    'follow_up',
                    f'Follow-up scheduled: {action_obj.action_number}',
                    f'A follow-up has been scheduled for corrective action "{action_obj.title}".',
                    f'/capa/{action_obj.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='overdue')
    def overdue(self, request):
        """Actions past their due date and still open — paginated like every other list.

        This feeds the Overdue tab on the follow-up page, and an audit backlog
        can run to hundreds of rows, so it must not dump the whole queryset.
        Derived from due_date rather than status='overdue' so the tab is correct
        even before the flag_overdue_actions command has run.
        """
        today = timezone.now().date()
        qs = self.filter_queryset(self.get_queryset()).filter(
            due_date__lt=today,
            status__in=['open', 'in_progress']
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        from django.db.models import Count
        today = timezone.now().date()
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'open': qs.filter(status='open').count(),
            'in_progress': qs.filter(status='in_progress').count(),
            'resolved': qs.filter(status='resolved').count(),
            'overdue': qs.filter(due_date__lt=today, status__in=['open', 'in_progress']).count(),
            'by_priority': list(qs.values('priority').annotate(count=Count('id'))),
        })