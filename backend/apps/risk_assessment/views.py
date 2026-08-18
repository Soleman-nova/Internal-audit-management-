from rest_framework import viewsets, status, generics, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count, Avg
from django.utils import timezone

from .models import RiskParameter, RiskAssessment, SelfAssessment
from .serializers import RiskParameterSerializer, RiskAssessmentSerializer, SelfAssessmentSerializer
from apps.common.permissions import (
    CanManageSettings, CanWriteAudit, RequiresCapability, APPROVE_PLANS, has_capability,
)
from apps.common.audit_utils import log_audit
from apps.notifications.services import notify, notify_roles


class RiskParameterViewSet(viewsets.ModelViewSet):
    queryset = RiskParameter.objects.all()
    serializer_class = RiskParameterSerializer
    permission_classes = [CanManageSettings]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description']

    def perform_create(self, serializer):
        param = serializer.save(created_by=self.request.user)
        log_audit(self.request, 'CREATE', param)

    def perform_update(self, serializer):
        param = serializer.save()
        log_audit(self.request, 'UPDATE', param)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()


class RiskAssessmentViewSet(viewsets.ModelViewSet):
    queryset = RiskAssessment.objects.select_related(
        'department', 'audit_universe', 'assessed_by', 'reviewed_by'
    ).prefetch_related('self_assessment').all()
    serializer_class = RiskAssessmentSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'department', 'audit_universe', 'year', 'assessment_period',
        'risk_rating', 'is_self_assessment',
    ]
    search_fields = ['department__name', 'notes']
    ordering_fields = ['risk_score', 'created_at', 'year']
    ordering = ['-risk_score']

    def perform_create(self, serializer):
        assessment = serializer.save(assessed_by=self.request.user)
        log_audit(self.request, 'CREATE', assessment)

    def perform_update(self, serializer):
        assessment = serializer.save()
        log_audit(self.request, 'UPDATE', assessment)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    @action(detail=False, methods=['get'], url_path='heatmap')
    def heatmap(self, request):
        """Return data structured for the 5x5 risk heat map"""
        year = request.query_params.get('year')
        qs = self.get_queryset()
        if year:
            qs = qs.filter(year=year)
        data = qs.values('likelihood', 'impact', 'department__name', 'risk_rating', 'risk_score')
        return Response(list(data))

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        qs = self.get_queryset()
        summary = {
            'total': qs.count(),
            'by_rating': list(qs.values('risk_rating').annotate(count=Count('id'))),
            'avg_score': qs.aggregate(avg=Avg('risk_score'))['avg'],
            'critical': qs.filter(risk_rating='critical').count(),
            'high': qs.filter(risk_rating='high').count(),
            'medium': qs.filter(risk_rating='medium').count(),
            'low': qs.filter(risk_rating='low').count(),
        }
        return Response(summary)


class SelfAssessmentViewSet(viewsets.ModelViewSet):
    # Newest first, and ordered at all: SelfAssessment has no Meta.ordering, so
    # paginating an unordered queryset could repeat or skip submissions between
    # pages. Same reason EvidenceViewSet carries an explicit ordering.
    queryset = SelfAssessment.objects.select_related(
        'risk_assessment', 'submitted_by', 'reviewed_by'
    ).order_by('-submitted_at')
    serializer_class = SelfAssessmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'submitted_by']

    def get_queryset(self):
        """A submitter sees only their own; reviewers see everything.

        Every role may submit a self-assessment, but a department
        representative has no business reading another department's candid
        self-appraisal. Reviewers (APPROVE_PLANS holders) need the full list to
        work through the queue.
        """
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and not has_capability(user, APPROVE_PLANS):
            return qs.filter(submitted_by=user)
        return qs

    def check_object_permissions(self, request, obj):
        """Only the submitter may edit their own submission, and only while open.

        Without this, any authenticated user could PATCH any submission — which
        also meant PATCHing status='reviewed' and side-stepping the review
        action's APPROVE_PLANS gate entirely. Reviewers go through
        ``review``, which stamps reviewed_by/reviewed_at and notifies.
        """
        super().check_object_permissions(request, obj)
        if request.method in permissions.SAFE_METHODS or self.action == 'review':
            return
        if obj.submitted_by_id != request.user.id:
            raise PermissionDenied('You can only modify your own self-assessment.')
        if obj.status == 'reviewed':
            raise PermissionDenied('A reviewed self-assessment can no longer be edited.')

    def perform_update(self, serializer):
        """Status is a workflow field, not a form field.

        The review flow must go through the gated ``review`` action, so a PATCH
        can never promote a submission to reviewed — silently pin the stored
        value instead of trusting the payload.
        """
        assessment = serializer.save(status=serializer.instance.status)
        log_audit(self.request, 'UPDATE', assessment)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    def perform_create(self, serializer):
        assessment = serializer.save(submitted_by=self.request.user)
        log_audit(self.request, 'CREATE', assessment)
        # Flag the parent so the matrix shows the department has responded.
        # This has to happen server-side: an auditee holds no WRITE_AUDIT, so
        # the client PATCHing RiskAssessment itself would 403 and make a
        # successful submission look like a failure.
        parent = assessment.risk_assessment
        if parent and not parent.is_self_assessment:
            parent.is_self_assessment = True
            parent.save(update_fields=['is_self_assessment'])
        # Notify reviewers that a self-assessment was submitted.
        dept = parent.department if parent else None
        notify_roles(
            ['audit_manager', 'supervisor'],
            'system',
            'Self-assessment submitted',
            f'A self-assessment for {dept.name if dept else "a department"} was submitted by '
            f'{self.request.user.get_full_name() or self.request.user.username}.',
            '/risk',
            exclude=self.request.user,
        )

    @action(detail=True, methods=['post'], url_path='review',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def review(self, request, pk=None):
        assessment = self.get_object()
        assessment.status = 'reviewed'
        assessment.reviewed_by = request.user
        assessment.reviewed_at = timezone.now()
        assessment.reviewer_notes = request.data.get('comments', assessment.reviewer_notes)
        assessment.save()
        log_audit(request, 'UPDATE', assessment)
        # Notify the submitter that their self-assessment was reviewed.
        if assessment.submitted_by and assessment.submitted_by != request.user:
            notify(
                assessment.submitted_by,
                'approved',
                'Self-assessment reviewed',
                'Your submitted self-assessment has been reviewed.',
                '/risk',
            )
        return Response({'detail': 'Self-assessment marked as reviewed.'})
