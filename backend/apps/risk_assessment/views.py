from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count, Avg
from django.utils import timezone

from .models import RiskParameter, RiskAssessment, SelfAssessment
from .serializers import RiskParameterSerializer, RiskAssessmentSerializer, SelfAssessmentSerializer
from apps.common.permissions import CanManageSettings, CanWriteAudit, RequiresCapability, APPROVE_PLANS
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
        'department', 'assessed_by', 'reviewed_by'
    ).prefetch_related('self_assessment').all()
    serializer_class = RiskAssessmentSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department', 'year', 'assessment_period', 'risk_rating', 'is_self_assessment']
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
    queryset = SelfAssessment.objects.select_related(
        'risk_assessment', 'submitted_by', 'reviewed_by'
    ).all()
    serializer_class = SelfAssessmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'submitted_by']

    def perform_create(self, serializer):
        assessment = serializer.save(submitted_by=self.request.user)
        log_audit(self.request, 'CREATE', assessment)
        # Notify reviewers that a self-assessment was submitted.
        dept = assessment.risk_assessment.department if assessment.risk_assessment else None
        notify_roles(
            ['audit_manager', 'supervisor'],
            'system',
            'Self-assessment submitted',
            f'A self-assessment for {dept.name if dept else "a department"} was submitted by '
            f'{self.request.user.get_full_name() or self.request.user.username}.',
            '/risk-assessment',
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
                '/risk-assessment',
            )
        return Response({'detail': 'Self-assessment marked as reviewed.'})
