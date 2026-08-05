from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from .models import AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember
from .serializers import (AuditUniverseSerializer, AuditPlanSerializer,
                          AuditEngagementSerializer, AuditTeamMemberSerializer)
from apps.common.permissions import CanWriteAudit, RequiresCapability, APPROVE_PLANS
from apps.common.audit_utils import log_audit
from apps.notifications.services import notify, notify_roles


class AuditUniverseViewSet(viewsets.ModelViewSet):
    queryset = AuditUniverse.objects.select_related('department').all()
    serializer_class = AuditUniverseSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'status', 'department']
    search_fields = ['name', 'code', 'owner']
    ordering_fields = ['risk_score', 'name', 'last_audited']
    ordering = ['-risk_score']

    def perform_create(self, serializer):
        obj = serializer.save()
        log_audit(self.request, 'CREATE', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        log_audit(self.request, 'UPDATE', obj)

    def perform_destroy(self, instance):
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


class AuditPlanViewSet(viewsets.ModelViewSet):
    queryset = AuditPlan.objects.select_related('created_by', 'approved_by').prefetch_related('engagements').all()
    serializer_class = AuditPlanSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'year']
    search_fields = ['title', 'description']
    ordering = ['-year']

    def perform_create(self, serializer):
        plan = serializer.save(created_by=self.request.user)
        log_audit(self.request, 'CREATE', plan)

    def perform_update(self, serializer):
        plan = serializer.save()
        log_audit(self.request, 'UPDATE', plan)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def approve(self, request, pk=None):
        plan = self.get_object()
        prev_status = plan.status
        plan.status = 'approved'
        plan.approved_by = request.user
        from django.utils import timezone
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
                f'/audit-planning?plan={plan.id}',
            )
        return Response({'detail': 'Plan approved successfully.'})

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        plan = self.get_object()
        prev_status = plan.status
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
            f'/audit-planning?plan={plan.id}',
            exclude=request.user,
        )
        return Response({'detail': 'Plan submitted for approval.'})


class AuditEngagementViewSet(viewsets.ModelViewSet):
    queryset = AuditEngagement.objects.select_related(
        'plan', 'department', 'lead_auditor', 'supervisor', 'audit_universe'
    ).prefetch_related('team_members', 'findings').all()
    serializer_class = AuditEngagementSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'engagement_type', 'plan', 'department', 'risk_level']
    search_fields = ['title', 'engagement_number', 'objectives']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        import random, string
        num = ''.join(random.choices(string.digits, k=5))
        engagement = serializer.save(engagement_number=f'ENG-{num}')
        log_audit(self.request, 'CREATE', engagement)
        # Notify the lead auditor and supervisor of their assignment.
        link = f'/engagements?id={engagement.id}'
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
        engagement = serializer.save()
        log_audit(self.request, 'UPDATE', engagement)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='add-member')
    def add_member(self, request, pk=None):
        engagement = self.get_object()
        data = request.data.copy()
        data['engagement'] = engagement.id
        serializer = AuditTeamMemberSerializer(data=data)
        serializer.is_valid(raise_exception=True)
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
                f'/engagements?id={engagement.id}',
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        engagement = self.get_object()
        new_status = request.data.get('status')
        if new_status not in dict(AuditEngagement.STATUS_CHOICES):
            return Response({'detail': 'Invalid status.'}, status=400)
        old_status = engagement.status
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
        link = f'/engagements?id={engagement.id}'
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