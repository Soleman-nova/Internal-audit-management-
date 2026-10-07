from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CorrectiveAction, ActionResponse, FollowUp
from .serializers import CorrectiveActionSerializer, ActionResponseSerializer, FollowUpSerializer
from apps.findings.models import AuditFinding
from apps.notifications.services import notify
from apps.common.permissions import (
    CanProposeCorrectiveAction, CanWriteAudit, InvolvedPartyOrCapability,
    APPROVE_PLANS, WRITE_AUDIT, has_capability,
)
from apps.common.audit_utils import log_audit
from apps.common.reference_numbers import save_with_reference_number
from apps.common.request_utils import with_parent
from apps.common.scoping import region_for


class CorrectiveActionViewSet(viewsets.ModelViewSet):
    queryset = CorrectiveAction.objects.select_related(
        'finding', 'owner', 'assigned_by'
    ).prefetch_related('responses', 'follow_ups').all()
    serializer_class = CorrectiveActionSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # Dict form so django-filter also honours ?status__in=open,in_progress —
    # the FollowUp page filters its tabs server-side with that multi-value
    # lookup. The rest stay exact matches as before.
    filterset_fields = {
        'status': ['exact', 'in'],
        'priority': ['exact'],
        'finding': ['exact'],
        'owner': ['exact'],
    }
    search_fields = ['title', 'description', 'recommendation', 'action_number']
    ordering_fields = ['due_date', 'created_at', 'priority']
    # 'id' is a deterministic tiebreaker: offset pagination over a shared
    # due_date could otherwise repeat/drop rows between page flips.
    ordering = ['due_date', 'id']

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        # Region scoping: a regional FPA auditor sees only CAPAs from their
        # region's engagements (via the finding chain). Runs before auditee
        # scoping — different roles, never overlap.
        region_id = region_for(user)
        if region_id is not None:
            return qs.filter(
                finding__engagement__region_id=region_id,
            ).distinct()
        if user.is_authenticated and user.role == 'auditee':
            scope = (
                Q(owner__department=user.department) if user.department
                else Q(owner=user)
            )
            # A corrective action is only as visible as the finding it answers, so
            # one raised against an unpublished finding stays out of reach even
            # when it is owned by the auditee's own department. Without this the
            # gate on the findings register would be decorative: the action's
            # title and description restate the finding's content, and the owner
            # filter above never looked at the finding at all.
            return qs.filter(scope).exclude(
                finding__status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            )
        return qs

    def get_permissions(self):
        """Creation is the one write here an auditee may perform.

        Spec Step 11 is the auditee acknowledging the finding and formulating
        the remediation plan themselves. Every other write on this endpoint —
        editing an action, reassigning it, deleting it — stays behind
        WRITE_AUDIT, so the proposal is the whole of what they gain.
        """
        if self.action == 'create':
            return [CanProposeCorrectiveAction()]
        return super().get_permissions()

    @staticmethod
    def _approver_for(finding):
        """The audit-side user who signs this plan off.

        The lead auditor on the engagement, falling back to whoever raised the
        finding. ``assigned_by`` is what ``approve`` and ``schedule-followup``
        gate on, so aiming it at the auditee who wrote the proposal would hand
        them the sign-off on their own remedy — the one thing the approval gate
        exists to prevent. Returns None when the finding names no auditor at
        all; APPROVE_PLANS holders pass the gate regardless, so a supervisor
        can still approve it.
        """
        if finding is None:
            return None
        lead = getattr(finding.engagement, 'lead_auditor', None)
        return lead or finding.identified_by

    def perform_create(self, serializer):
        user = self.request.user
        # An auditee holds no capabilities, so reaching here as one means this
        # is their own proposal: they author it, they own it, and it lands with
        # the auditor for sign-off rather than live. `owner` and `status` are
        # forced rather than defaulted — both are writable model fields, and a
        # client-sent status would otherwise be a way to open a closed action,
        # or to close the finding behind it, in a single POST.
        proposed_by_auditee = not has_capability(user, WRITE_AUDIT)
        if proposed_by_auditee:
            approver = self._approver_for(serializer.validated_data.get('finding'))
            extra = {
                'owner': user,
                'assigned_by': approver,
                'status': 'pending_approval',
            }
        else:
            approver = None
            extra = {'assigned_by': user}

        with transaction.atomic():
            action_obj = save_with_reference_number(
                serializer, 'action_number', 'CAPA', **extra,
            )
            log_audit(self.request, 'CREATE', action_obj)
            if proposed_by_auditee:
                self._announce_proposal(action_obj, approver)
                return
            # Notify the owner that a corrective action was assigned to them.
            if action_obj.owner and action_obj.owner != user:
                due = action_obj.due_date.isoformat() if action_obj.due_date else 'no due date set'
                notify(
                    action_obj.owner,
                    'assigned',
                    f'New corrective action: {action_obj.action_number}',
                    f'You have been assigned corrective action "{action_obj.title}" (due {due}).',
                    f'/capa/{action_obj.id}',
                )

    def _announce_proposal(self, action_obj, approver):
        """Tell the auditor a remediation plan is waiting on them.

        Spec Step 11's second half. Without it a proposal lands in the queue of
        somebody who was never told, and `pending_approval` has no exit until
        they happen to look.
        """
        if approver is None or approver == self.request.user:
            return
        notify(
            approver,
            'assigned',
            f'Remediation plan awaiting approval: {action_obj.action_number}',
            f'{self.request.user.full_name} has proposed a remediation plan for '
            f'finding {action_obj.finding.finding_number}. Review and approve it '
            'to start implementation.',
            f'/capa/{action_obj.id}',
        )

    def perform_update(self, serializer):
        prev_owner_id = serializer.instance.owner_id
        prev_status = serializer.instance.status
        # Signing the action off is the lead auditor's, as it is on `approve` and
        # `schedule-followup`. Those two are object-scoped, but a status PATCH is
        # not, so without this the class-level WRITE_AUDIT gate left a side door:
        # any auditor at all could close a colleague's CAPA — and with it, through
        # the cascade, the finding behind it — while the two purpose-built
        # sign-off routes refused them.
        new_status = serializer.validated_data.get('status', prev_status)
        if new_status != prev_status:
            self._guard_status_edit(serializer.instance, prev_status, new_status)
        with transaction.atomic():
            action_obj = serializer.save()
            changes = None
            if action_obj.status != prev_status:
                changes = {'status': [prev_status, action_obj.status]}
            log_audit(self.request, 'UPDATE', action_obj, changes=changes)
            # Carry a terminal status up to the finding it remediates.
            self._sync_parent(action_obj, request=self.request)
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

    def _guard_status_edit(self, action_obj, prev_status, new_status):
        """Which status transitions an ordinary PATCH is not allowed to make.

        Four of this model's statuses exist only because of the route that writes
        them, and that route does more than write a status: `approve` checks who
        may sign a plan off and stamps who did and when, `verify-and-close`
        records the follow-up visit that justifies calling a remedy a failure,
        and `flag_overdue_actions` derives its flag from the due date. A PATCH
        can do none of that, so it is refused for each of them — in both
        directions where a status has two owners, since an auditee's proposal is
        to be answered through `approve`, not overwritten by an edit.

        Leaving a terminal status is refused for the same reason from the other
        side: there is no reopen ceremony to record why a settled action is being
        reconsidered, and `_sync_parent` would carry the reopening back to the
        finding as well.

        400 rather than 403: nothing here is about *who* is asking — a sign-off
        would be perfectly available to some callers — but about the request
        asking an edit to do a transition's job. The one rule that really is about
        the caller, `_may_sign_off` on the terminal pair, stays a 403 below.
        """
        if new_status in CorrectiveAction.RESERVED_PATCH_STATUSES:
            raise ValidationError({
                'status': f'"{new_status}" is set by the action that owns it, not by '
                          f'an edit. Use the purpose-built route for this transition.',
            })
        if prev_status in CorrectiveAction.RESERVED_PATCH_STATUSES:
            raise ValidationError({
                'status': f'An action in "{prev_status}" only moves through the '
                          f'route that owns that stage — an edit cannot skip it.',
            })
        if prev_status in CorrectiveAction.TERMINAL_STATUSES:
            raise ValidationError({
                'status': f'"{action_obj.action_number}" is already settled '
                          f'({prev_status}) and there is no reopen route: raise a new '
                          f'action rather than rewinding a closed one.',
            })
        if (new_status in CorrectiveAction.TERMINAL_STATUSES
                and not self._may_sign_off(action_obj)):
            raise PermissionDenied(
                'Only the auditor this action is assigned to, or an approver, '
                'can settle it. Use the verify-and-close route to record the '
                'verification alongside the closure.'
            )

    def _may_sign_off(self, action_obj):
        """The audience `approve` and `schedule-followup` already gate on.

        Expressed here rather than as a permission class because this one guards a
        single field value inside an otherwise ordinary edit, not the request —
        reassigning an owner or moving a due date stays open to the audit team.
        """
        return (
            has_capability(self.request.user, APPROVE_PLANS)
            or action_obj.assigned_by_id == self.request.user.id
        )

    def _sync_parent(self, action_obj, request=None):
        """Propagate a terminal CAPA status to its finding, and say so.

        Returns the finding status that was set, or None. The audit entry is
        written against the *finding*, so the register's history shows why it
        moved rather than showing a status that changed with no cause.
        """
        finding = action_obj.finding
        previous = finding.status
        moved = action_obj.sync_parent_finding()
        if moved and request is not None:
            log_audit(
                request, 'UPDATE', finding,
                object_repr=f'{action_obj.action_number} closed {finding.finding_number}',
                changes={'status': [previous, moved]},
            )
        return moved

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[InvolvedPartyOrCapability.for_(
                'assigned_by', capability=APPROVE_PLANS)])
    def approve(self, request, pk=None):
        """Accept the remediation plan and start implementation.

        The auditor's sign-off on the *plan*, before any work is done: until it
        is given the action sits in `pending_approval`. Gated the same way as
        schedule-followup — whoever raised the action, plus APPROVE_PLANS holders
        — so the owner cannot approve their own remedy.
        """
        action_obj = self.get_object()
        # The belt to the permission braces: `assigned_by` now always names an
        # audit-side user, but the invariant is "the owner never signs off their
        # own remedy" and that is worth stating where the sign-off happens
        # rather than only where the field is written.
        if action_obj.owner_id == request.user.id:
            return Response(
                {'detail': 'You cannot approve your own remediation plan.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if action_obj.status != 'pending_approval':
            return Response(
                {'detail': f'This action is "{action_obj.get_status_display()}" '
                           'and is not awaiting approval.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            action_obj.status = 'open'
            action_obj.approved_by = request.user
            action_obj.approved_at = timezone.now()
            action_obj.save(update_fields=[
                'status', 'approved_by', 'approved_at', 'updated_at',
            ])
            log_audit(request, 'APPROVE', action_obj,
                      changes={'status': ['pending_approval', 'open']})
            if action_obj.owner and action_obj.owner != request.user:
                notify(
                    action_obj.owner,
                    'approved',
                    f'Corrective action approved: {action_obj.action_number}',
                    f'Your remediation plan for "{action_obj.title}" was approved. '
                    'Implementation can begin.',
                    f'/capa/{action_obj.id}',
                )
        return Response({'detail': 'Corrective action approved.'})

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
        # `status_update` is a required ChoiceField on ActionResponse, so it is
        # present and already checked against STATUS_CHOICES by the validation
        # above — read it from validated_data rather than the raw payload.
        new_status = serializer.validated_data['status_update']
        # Nothing to report progress on until the plan has been agreed. Without
        # this an owner could post `in_progress` against their own unapproved
        # proposal and walk it out of `pending_approval` — the one state `approve`
        # accepts — so the sign-off step became unreachable and the plan approved
        # itself. The status gate below cannot catch that: the value is a
        # legitimately owner-reportable one, and it is the *stage* that is wrong.
        if action_obj.status == 'pending_approval':
            return Response(
                {'detail': 'This remediation plan is awaiting the auditor\'s '
                           'approval, so there is no implementation to report on yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # The owner reports progress; the audit side records what it amounts to.
        # This route is the one an owner can reach, so it is the one that has to
        # hold the line: `closed` here would settle the action *and*, through the
        # cascade below, the finding behind it — an auditee awarding themselves
        # the verification the flow reserves for the auditor.
        if (not has_capability(request.user, WRITE_AUDIT)
                and new_status not in CorrectiveAction.OWNER_REPORTABLE_STATUSES):
            return Response(
                {'detail': f'"{new_status}" is not a status the owner of an action '
                           'can report. Submit the evidence and the audit team will '
                           'verify it.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        prev_status = action_obj.status
        with transaction.atomic():
            serializer.save(responder=request.user)
            action_obj.status = new_status
            action_obj.save(update_fields=['status', 'updated_at'])
            changes = None
            if action_obj.status != prev_status:
                changes = {'status': [prev_status, action_obj.status]}
            log_audit(request, 'UPDATE', action_obj, changes=changes)
            # Filing evidence that resolves or closes the action also settles the
            # finding it remediates.
            self._sync_parent(action_obj, request=request)
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

    @action(detail=True, methods=['post'], url_path='verify-and-close',
            permission_classes=[InvolvedPartyOrCapability.for_(
                'assigned_by', capability=APPROVE_PLANS)])
    def verify_and_close(self, request, pk=None):
        """The auditor's verification of the remedy, and the closure that follows.

        One act, not two, because they were two and neither half worked alone:
        `schedule-followup` records a visit and leaves the action exactly where it
        was, so a CAPA could be formally verified as effective and sit in
        `in_progress` indefinitely; and the only thing that actually closed one was
        a bare status write, which recorded no verification at all. The follow-up
        is what proves the verification happened, so writing it and closing the
        action are the same transaction — there is no window in which one exists
        without the other.

        Gated like `approve` and `schedule-followup`: the auditor this action is
        assigned to, plus APPROVE_PLANS holders who verify across engagements. The
        owner cannot sign off their own remedy.
        """
        action_obj = self.get_object()
        # The belt to the permission braces, as on `approve`: `assigned_by` always
        # names an audit-side user, but "the owner never signs off their own
        # remedy" is worth stating where the sign-off happens rather than only
        # where the field is written.
        if action_obj.owner_id == request.user.id:
            return Response(
                {'detail': 'You cannot verify your own remediation.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if action_obj.status not in CorrectiveAction.CLOSEABLE_FROM:
            return Response(
                {'detail': f'This action is "{action_obj.get_status_display()}" '
                           'and cannot be verified and closed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = with_parent(request.data, corrective_action=action_obj.id)
        today = timezone.now().date()
        serializer = FollowUpSerializer(data={
            'corrective_action': action_obj.id,
            'scheduled_date': data.get('scheduled_date') or today.isoformat(),
            'notes': data.get('notes') or '',
            # A closing verification is by definition a conducted one, so the visit
            # is recorded as completed rather than scheduled.
            'status': 'completed',
            'outcome': data.get('outcome') or 'Implementation verified as effective',
        })
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save(conducted_by=request.user)
            previous = action_obj.status
            action_obj.status = 'closed'
            if action_obj.completed_date is None:
                action_obj.completed_date = today
            action_obj.save(update_fields=['status', 'completed_date', 'updated_at'])
            log_audit(request, 'APPROVE', action_obj,
                      changes={'status': [previous, 'closed']})
            # Closing the action settles the finding it remediates.
            self._sync_parent(action_obj, request=request)
            if action_obj.owner and action_obj.owner != request.user:
                notify(
                    action_obj.owner,
                    'approved',
                    f'Corrective action verified and closed: {action_obj.action_number}',
                    f'Your remediation for "{action_obj.title}" was verified as '
                    'effective and the action is now closed.',
                    f'/capa/{action_obj.id}',
                )
        return Response(self.get_serializer(action_obj).data)

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