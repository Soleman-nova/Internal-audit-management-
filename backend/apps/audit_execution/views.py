from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone

from .models import AuditProgram, AuditProcedure, WorkingPaper
from .serializers import AuditProgramSerializer, AuditProcedureSerializer, WorkingPaperSerializer


class AuditProgramViewSet(viewsets.ModelViewSet):
    queryset = AuditProgram.objects.select_related(
        'engagement', 'prepared_by', 'approved_by'
    ).prefetch_related('procedures').all()
    serializer_class = AuditProgramSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'engagement']
    search_fields = ['title']

    def perform_create(self, serializer):
        serializer.save(prepared_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        program = self.get_object()
        program.status = 'approved'
        program.approved_by = request.user
        program.approved_at = timezone.now()
        program.save()
        return Response({'detail': 'Audit program approved.'})

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        program = self.get_object()
        program.status = 'submitted'
        program.save()
        return Response({'detail': 'Program submitted for review.'})


class AuditProcedureViewSet(viewsets.ModelViewSet):
    queryset = AuditProcedure.objects.select_related(
        'program', 'assigned_to', 'completed_by'
    ).all()
    serializer_class = AuditProcedureSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'program', 'procedure_type', 'assigned_to']
    search_fields = ['title', 'description', 'risk_area']
    ordering = ['order', 'step_number']

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        procedure = self.get_object()
        procedure.status = 'completed'
        procedure.completed_by = request.user
        procedure.completed_at = timezone.now()
        procedure.conclusion = request.data.get('conclusion', '')
        procedure.save()
        return Response({'detail': 'Procedure marked as completed.'})


class WorkingPaperViewSet(viewsets.ModelViewSet):
    queryset = WorkingPaper.objects.select_related(
        'engagement', 'procedure', 'prepared_by', 'reviewed_by'
    ).all()
    serializer_class = WorkingPaperSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['engagement', 'paper_type', 'is_reviewed', 'procedure']
    search_fields = ['title', 'reference', 'description']

    def perform_create(self, serializer):
        serializer.save(prepared_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='review')
    def review(self, request, pk=None):
        paper = self.get_object()
        paper.is_reviewed = True
        paper.reviewed_by = request.user
        paper.review_notes = request.data.get('review_notes', '')
        paper.save()
        return Response({'detail': 'Working paper reviewed.'})
