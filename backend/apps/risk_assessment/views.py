from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Count, Avg

from .models import RiskParameter, RiskAssessment, SelfAssessment
from .serializers import RiskParameterSerializer, RiskAssessmentSerializer, SelfAssessmentSerializer


class RiskParameterViewSet(viewsets.ModelViewSet):
    queryset = RiskParameter.objects.all()
    serializer_class = RiskParameterSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class RiskAssessmentViewSet(viewsets.ModelViewSet):
    queryset = RiskAssessment.objects.select_related(
        'department', 'assessed_by', 'reviewed_by'
    ).prefetch_related('self_assessment').all()
    serializer_class = RiskAssessmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['department', 'year', 'assessment_period', 'risk_rating', 'is_self_assessment']
    search_fields = ['department__name', 'notes']
    ordering_fields = ['risk_score', 'created_at', 'year']
    ordering = ['-risk_score']

    def perform_create(self, serializer):
        serializer.save(assessed_by=self.request.user)

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
    queryset = SelfAssessment.objects.select_related('risk_assessment', 'submitted_by').all()
    serializer_class = SelfAssessmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'submitted_by']

    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user)
