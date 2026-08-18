from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.http import HttpResponse
from django.utils import timezone
import mimetypes

from .models import AuditProgram, AuditProcedure, WorkingPaper
from .serializers import AuditProgramSerializer, AuditProcedureSerializer, WorkingPaperSerializer
from apps.common.permissions import (
    CanWriteAudit, RequiresCapability, InvolvedPartyOrCapability, APPROVE_PLANS,
)
from apps.common.audit_utils import log_audit
from apps.notifications.services import notify, notify_roles


class AuditProgramViewSet(viewsets.ModelViewSet):
    queryset = AuditProgram.objects.select_related(
        'engagement', 'engagement__lead_auditor', 'prepared_by', 'approved_by'
    ).prefetch_related('procedures').all()
    serializer_class = AuditProgramSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'engagement']
    search_fields = ['title']
    ordering_fields = ['created_at', 'title', 'status']
    # Without a default ordering the queryset comes back in whatever order the
    # database happens to return, so paginating it can repeat or skip rows.
    ordering = ['-created_at']

    def perform_create(self, serializer):
        program = serializer.save(prepared_by=self.request.user)
        log_audit(self.request, 'CREATE', program)

    def perform_update(self, serializer):
        prev_status = serializer.instance.status
        program = serializer.save()
        changes = None
        if program.status != prev_status:
            changes = {'status': [prev_status, program.status]}
        log_audit(self.request, 'UPDATE', program, changes=changes)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def approve(self, request, pk=None):
        program = self.get_object()
        program.status = 'approved'
        program.approved_by = request.user
        program.reviewed_by = request.user
        program.approved_at = timezone.now()
        program.save()
        log_audit(request, 'APPROVE', program)
        # Let the auditor who prepared/leads it know it was approved.
        lead = program.engagement.lead_auditor if program.engagement else None
        recipient = lead or program.prepared_by
        if recipient and recipient != request.user:
            notify(
                recipient,
                'approved',
                f'Audit program approved: {program.title}',
                f'The audit program "{program.title}" has been approved.',
                f'/execution?program={program.id}',
            )
        return Response({'detail': 'Audit program approved.'})

    @action(detail=True, methods=['post'], url_path='submit',
            permission_classes=[InvolvedPartyOrCapability.for_(
                'prepared_by', 'engagement.lead_auditor', capability=APPROVE_PLANS)])
    def submit(self, request, pk=None):
        """Send the program up for approval.

        Restricted to the people who own the work — whoever prepared it or leads
        the engagement — plus APPROVE_PLANS holders, who may push any program
        through. At the class-level WRITE_AUDIT gate, any auditor in the
        organisation could submit a colleague's program for review.
        """
        program = self.get_object()
        prev_status = program.status
        program.status = 'submitted'
        program.save()
        log_audit(request, 'UPDATE', program, changes={'status': [prev_status, 'submitted']})
        notify_roles(
            ['audit_manager', 'supervisor'],
            'approval_needed',
            f'Audit program awaiting approval: {program.title}',
            f'The audit program "{program.title}" was submitted for review by '
            f'{request.user.get_full_name() or request.user.username}.',
            f'/execution?program={program.id}',
            exclude=request.user,
        )
        return Response({'detail': 'Program submitted for review.'})


class AuditProcedureViewSet(viewsets.ModelViewSet):
    queryset = AuditProcedure.objects.select_related(
        'program', 'program__engagement', 'program__engagement__lead_auditor',
        'assigned_to', 'completed_by'
    ).all()
    serializer_class = AuditProcedureSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'program', 'procedure_type', 'assigned_to']
    search_fields = ['title', 'description', 'risk_area']
    ordering = ['order', 'step_number']

    def perform_create(self, serializer):
        procedure = serializer.save()
        log_audit(self.request, 'CREATE', procedure)

    def perform_update(self, serializer):
        prev_status = serializer.instance.status
        procedure = serializer.save()
        changes = None
        if procedure.status != prev_status:
            changes = {'status': [prev_status, procedure.status]}
        log_audit(self.request, 'UPDATE', procedure, changes=changes)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        procedure = self.get_object()
        prev_status = procedure.status
        procedure.status = 'completed'
        procedure.completed_by = request.user
        procedure.completed_at = timezone.now()
        # Only overwrite the conclusion when one is supplied — completing from the
        # status dropdown sends no body, and blanking a written conclusion there
        # would quietly destroy fieldwork evidence.
        if 'conclusion' in request.data:
            procedure.conclusion = request.data.get('conclusion') or ''
        procedure.save()
        log_audit(request, 'UPDATE', procedure, changes={'status': [prev_status, 'completed']})
        # Notify the engagement lead that a procedure was completed.
        engagement = procedure.program.engagement if procedure.program else None
        lead = engagement.lead_auditor if engagement else None
        if lead and lead != request.user:
            notify(
                lead,
                'system',
                f'Procedure completed: {procedure.title}',
                f'Procedure "{procedure.title}" was marked completed by '
                f'{request.user.get_full_name() or request.user.username}.',
                f'/execution?program={procedure.program_id}',
            )
        # Return the updated record, not just a message, so the client can merge
        # completed_by/completed_at into its row without a second round trip.
        return Response(self.get_serializer(procedure).data)


class WorkingPaperViewSet(viewsets.ModelViewSet):
    queryset = WorkingPaper.objects.select_related(
        'engagement', 'procedure', 'prepared_by', 'reviewed_by'
    ).all()
    serializer_class = WorkingPaperSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['engagement', 'paper_type', 'is_reviewed', 'procedure']
    search_fields = ['title', 'reference', 'description']

    def perform_create(self, serializer):
        paper = serializer.save(prepared_by=self.request.user)
        log_audit(self.request, 'CREATE', paper)

    def perform_destroy(self, instance):
        log_audit(self.request, 'DELETE', instance)
        # Remove the physical file from storage when the paper is deleted.
        if instance.file:
            storage, filename = instance.file.storage, instance.file.name
            instance.delete()
            if filename and storage.exists(filename):
                storage.delete(filename)
        else:
            instance.delete()

    @action(detail=True, methods=['post'], url_path='review',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def review(self, request, pk=None):
        paper = self.get_object()
        paper.is_reviewed = True
        paper.reviewed_by = request.user
        paper.review_notes = request.data.get('review_notes', '')
        paper.save()
        log_audit(request, 'UPDATE', paper)
        # Notify the preparer that their working paper was reviewed.
        if paper.prepared_by and paper.prepared_by != request.user:
            notify(
                paper.prepared_by,
                'approved',
                f'Working paper reviewed: {paper.title}',
                f'Your working paper "{paper.title}" has been reviewed.',
                f'/execution?engagement={paper.engagement_id}',
            )
        return Response({'detail': 'Working paper reviewed.'})

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        paper = self.get_object()
        if paper.file:
            # Determine content type from file extension
            content_type, _ = mimetypes.guess_type(paper.file.name)
            if not content_type:
                content_type = 'application/octet-stream'

            response = HttpResponse(paper.file.read(), content_type=content_type)
            filename = paper.file.name.split('/')[-1]
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        return Response({'detail': 'No file attached to this working paper.'}, status=status.HTTP_400_BAD_REQUEST)
