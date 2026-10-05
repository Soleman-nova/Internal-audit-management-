from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
import mimetypes

from .models import AuditProgram, AuditProcedure, WorkingPaper
from .serializers import AuditProgramSerializer, AuditProcedureSerializer, WorkingPaperSerializer
from apps.common.permissions import (
    CanWriteAudit, RequiresCapability, InvolvedPartyOrCapability, APPROVE_PLANS,
)
from apps.common.audit_utils import log_audit
from apps.common.blockers import BLOCKERS_NAMED, describe_blockers
from apps.common.scoping import AuditeeScopeMixin, RegionScopeMixin
from apps.notifications.services import notify, notify_roles


class AuditProgramViewSet(RegionScopeMixin, AuditeeScopeMixin, viewsets.ModelViewSet):
    queryset = AuditProgram.objects.select_related(
        'engagement', 'engagement__lead_auditor', 'prepared_by', 'approved_by'
    ).prefetch_related('procedures').all()
    serializer_class = AuditProgramSerializer
    permission_classes = [CanWriteAudit]

    # The program is the audit team's plan of attack for an engagement, so an
    # auditee sees it only where the engagement is in their department, or where
    # they prepared it. A regional FPA auditor sees only programs whose engagement
    # is tagged with their region.
    region_scope_fields = ('engagement__region_id',)
    auditee_scope_fields = ('engagement__department_id',)
    auditee_scope_personal_fields = ('prepared_by',)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'engagement']
    search_fields = ['title']
    ordering_fields = ['created_at', 'title', 'status']
    # Without a default ordering the queryset comes back in whatever order the
    # database happens to return, so paginating it can repeat or skip rows.
    ordering = ['-created_at']

    def perform_create(self, serializer):
        with transaction.atomic():
            program = serializer.save(prepared_by=self.request.user)
            log_audit(self.request, 'CREATE', program)

    def perform_update(self, serializer):
        prev_status = serializer.instance.status
        with transaction.atomic():
            program = serializer.save()
            changes = None
            if program.status != prev_status:
                changes = {'status': [prev_status, program.status]}
            log_audit(self.request, 'UPDATE', program, changes=changes)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def approve(self, request, pk=None):
        program = self.get_object()
        with transaction.atomic():
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
        with transaction.atomic():
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

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        """Close the program — the only route to `completed`.

        Exists because `status` is read-only (see `AuditProgramSerializer`).
        Before that, moving a program to `completed` was something a plain PATCH
        could do, which meant it was also something nothing checked: a program
        whose steps were still pending could be closed by any auditor, and the
        execution board — which locks every procedure control on `completed` —
        then presented fieldwork that had never happened as finished and
        immutable.

        So this route checks the fieldwork before honouring it. `failed` and
        `not_applicable` count as finished: a step that found the control wanting
        is an outcome, not outstanding work, and one of them is what produces the
        findings this program exists to gather.
        """
        program = self.get_object()
        unfinished = program.procedures.exclude(
            status__in=AuditProcedure.TESTED_STATUSES
        )
        remaining = unfinished.count()
        if remaining:
            named = list(
                unfinished.order_by('order', 'step_number')
                .values_list('step_number', flat=True)[:BLOCKERS_NAMED]
            )
            return Response(
                {'detail': f'Cannot complete this program: {remaining} procedure(s) '
                           f'have no recorded outcome '
                           f'({describe_blockers(named, remaining)}). Mark each one '
                           f'completed, failed or not applicable first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prev_status = program.status
        with transaction.atomic():
            program.status = 'completed'
            program.save()
            log_audit(request, 'UPDATE', program, changes={'status': [prev_status, 'completed']})
            lead = program.engagement.lead_auditor if program.engagement else None
            if lead and lead != request.user:
                notify(
                    lead,
                    'system',
                    f'Fieldwork program completed: {program.title}',
                    f'The audit program "{program.title}" was marked completed by '
                    f'{request.user.get_full_name() or request.user.username}.',
                    f'/execution?program={program.id}',
                )
        return Response(self.get_serializer(program).data)

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen(self, request, pk=None):
        """Return a completed program to `approved` so its steps can be revisited.

        The inverse of `complete`, and deliberately a separate action rather than
        an editable status: `completed` is what locks every procedure control on
        the execution board, so undoing it is a decision somebody makes, not a
        field somebody edits.
        """
        program = self.get_object()
        if program.status != 'completed':
            return Response(
                {'detail': f'Only a completed program can be reopened; this one '
                           f'is "{program.get_status_display()}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prev_status = program.status
        with transaction.atomic():
            program.status = 'approved'
            program.save()
            log_audit(request, 'UPDATE', program, changes={'status': [prev_status, 'approved']})
        return Response(self.get_serializer(program).data)


class AuditProcedureViewSet(RegionScopeMixin, AuditeeScopeMixin, viewsets.ModelViewSet):
    queryset = AuditProcedure.objects.select_related(
        'program', 'program__engagement', 'program__engagement__lead_auditor',
        'assigned_to', 'completed_by'
    ).prefetch_related('findings').all()
    serializer_class = AuditProcedureSerializer
    permission_classes = [CanWriteAudit]

    # Two hops to the department: a procedure belongs to a program, which belongs
    # to an engagement. An auditee also keeps sight of any step assigned to them,
    # so a checklist item they own stays workable even if it is filed elsewhere.
    # A regional FPA auditor sees only procedures from engagements in their region.
    region_scope_fields = ('program__engagement__region_id',)
    auditee_scope_fields = ('program__engagement__department_id',)
    auditee_scope_personal_fields = ('assigned_to',)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # `program__engagement` is the hop the findings form needs: a finding is
    # raised from a *failed* procedure of the engagement it belongs to, and the
    # form has the engagement id, not the program id.
    filterset_fields = [
        'status', 'program', 'program__engagement', 'procedure_type', 'assigned_to',
    ]
    search_fields = ['title', 'description', 'risk_area']
    ordering = ['order', 'step_number']

    def perform_create(self, serializer):
        with transaction.atomic():
            procedure = serializer.save()
            log_audit(self.request, 'CREATE', procedure)

    def perform_update(self, serializer):
        prev_status = serializer.instance.status
        with transaction.atomic():
            procedure = serializer.save()
            changes = None
            if procedure.status != prev_status:
                changes = {'status': [prev_status, procedure.status]}
            log_audit(self.request, 'UPDATE', procedure, changes=changes)
            # A step that failed — or that was ruled inapplicable, which removes it
            # from the fieldwork without answering it — is the trigger event for
            # the whole findings flow, so it is announced on the same terms
            # `complete` announces its own outcome. Without this the engagement
            # lead heard about steps that passed and nothing about the ones that
            # need a finding raised against them, which is the one they have to
            # act on.
            if procedure.status in AuditProcedure.OUTCOME_LABELS:
                self._announce_outcome(
                    procedure, AuditProcedure.OUTCOME_LABELS[procedure.status],
                )

    def _announce_outcome(self, procedure, label):
        """Tell the engagement's lead auditor how one of their steps ended.

        One place for both routes that finish a step — `complete` and a status
        edit — so the two cannot drift apart in who they tell or how. Skipped
        when the lead is the one doing it: they are already looking at it.
        """
        engagement = procedure.program.engagement if procedure.program else None
        lead = engagement.lead_auditor if engagement else None
        if not lead or lead == self.request.user:
            return
        actor = self.request.user.get_full_name() or self.request.user.username
        notify(
            lead,
            'system',
            f'Procedure {label}: {procedure.title}',
            f'Procedure "{procedure.title}" was marked {label} by {actor}.',
            f'/execution?program={procedure.program_id}',
        )

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        procedure = self.get_object()
        prev_status = procedure.status
        with transaction.atomic():
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
            self._announce_outcome(procedure, 'completed')
        # Return the updated record, not just a message, so the client can merge
        # completed_by/completed_at into its row without a second round trip.
        return Response(self.get_serializer(procedure).data)


class WorkingPaperViewSet(RegionScopeMixin, AuditeeScopeMixin, viewsets.ModelViewSet):
    queryset = WorkingPaper.objects.select_related(
        'engagement', 'procedure', 'prepared_by', 'reviewed_by'
    ).all()
    serializer_class = WorkingPaperSerializer
    permission_classes = [CanWriteAudit]

    # Working papers are the audit team's own evidence — the most sensitive thing
    # an auditee could be handed, since it is the documented basis for the
    # findings against them and may cover engagements they are not part of.
    # A regional FPA auditor sees only papers from engagements in their region.
    region_scope_fields = ('engagement__region_id',)
    auditee_scope_fields = ('engagement__department_id',)
    auditee_scope_personal_fields = ('prepared_by',)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['engagement', 'paper_type', 'is_reviewed', 'procedure']
    search_fields = ['title', 'reference', 'description']

    def perform_create(self, serializer):
        with transaction.atomic():
            paper = serializer.save(prepared_by=self.request.user)
            log_audit(self.request, 'CREATE', paper)

    def perform_destroy(self, instance):
        # Capture the storage handle before the row goes, since `instance.file`
        # is the only place the stored name is recorded.
        storage, filename = (
            (instance.file.storage, instance.file.name) if instance.file else (None, None)
        )
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()
        # Deliberately outside the transaction: unlinking a file cannot be rolled
        # back, so it waits until the row is really gone. Reversed, a rollback
        # would leave a working paper pointing at a file that no longer exists —
        # a broken download instead of an undone delete.
        if filename and storage.exists(filename):
            storage.delete(filename)

    @action(detail=True, methods=['post'], url_path='review',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def review(self, request, pk=None):
        paper = self.get_object()
        with transaction.atomic():
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
