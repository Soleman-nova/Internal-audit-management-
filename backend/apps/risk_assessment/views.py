from rest_framework import viewsets, status, generics, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Count, Avg
from django.utils import timezone

from .models import (
    RiskParameter, RiskAssessment, SelfAssessment, active_policy,
    recompute_assessments,
)
from .serializers import RiskParameterSerializer, RiskAssessmentSerializer, SelfAssessmentSerializer
from apps.common.permissions import (
    CanManageSettings, CanWriteAudit, RequiresCapability, APPROVE_PLANS, MANAGE_SETTINGS,
    has_capability,
)
from apps.common.audit_utils import log_audit
from apps.common.scoping import AuditeeScopeMixin, RegionScopeMixin
from apps.notifications.services import notify, notify_roles


class RiskParameterViewSet(viewsets.ModelViewSet):
    queryset = RiskParameter.objects.all()
    serializer_class = RiskParameterSerializer
    permission_classes = [CanManageSettings]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'description']

    def _apply_policy_change(self, request, param, action_name, previous):
        """Recompute every assessment after a parameter write, and log both facts.

        A parameter edit changes what every stored score *means*, so leaving the
        existing rows untouched is not "no side effect" — it is a register full of
        numbers computed under a policy that no longer exists. Recomputing inline
        is what makes an edit reach the data instead of silently going stale.

        Tradeoff: this is O(assessments) inside the request, rather than a queued
        job. Accepted because the endpoint is MANAGE_SETTINGS-only, the parameter
        set changes a handful of times a year, and the register is small — a
        bounded, rare, privileged write. ``manage.py recompute_risk_scores`` does
        the same thing from the CLI for bulk, scripted, or out-of-band changes.

        The count goes on the audit trail rather than into the response: DELETE
        answers 204 and carries no body, and a recompute that silently rewrote
        every score in the register is exactly the kind of thing the trail exists
        to record.
        """
        policy_now = active_policy()
        updated, total = recompute_assessments()
        log_audit(request, action_name, param, changes={
            'policy_digest': [previous['digest'], policy_now['digest']],
            'assessments_recomputed': [None, updated],
            'assessments_scanned': [None, total],
        })

    def perform_create(self, serializer):
        previous = active_policy()
        with transaction.atomic():
            param = serializer.save(created_by=self.request.user)
            self._apply_policy_change(self.request, param, 'CREATE', previous)

    def perform_update(self, serializer):
        previous = active_policy()
        with transaction.atomic():
            param = serializer.save()
            self._apply_policy_change(self.request, param, 'UPDATE', previous)

    def perform_destroy(self, instance):
        previous = active_policy()
        pk = instance.pk
        with transaction.atomic():
            instance.delete()
            # Model.delete() clears the pk; put it back so the audit entry keeps
            # its object_id instead of recording "None".
            instance.pk = pk
            self._apply_policy_change(self.request, instance, 'DELETE', previous)

    @action(detail=False, methods=['get'], url_path='policy')
    def policy(self, request):
        """The policy currently in force, plus how much of the register is behind it.

        ``stale_assessments`` counts rows frozen under a different digest, **blank
        digests included**. A row that records no policy is the most stale case
        there is, and it has to be counted here or the number disagrees with
        ``RiskAssessment.is_stale``: immediately after the policy columns were
        added, every pre-existing row badges "Older policy" in the listing while
        this endpoint would report zero and offer no way to act on it. Counting
        them means the banner appears with the Recompute that fixes it.
        """
        policy_now = active_policy()
        # A blank digest compares unequal too, which is what we want: a row that
        # records no policy has not been scored under this one.
        stale = RiskAssessment.objects.exclude(policy_digest=policy_now['digest']).count()
        return Response({
            'digest': policy_now['digest'],
            'weight_sum': policy_now['weight_sum'],
            'uplift': policy_now['uplift'],
            'active_count': RiskParameter.objects.filter(is_active=True).count(),
            'stale_assessments': stale,
        })


class RiskAssessmentViewSet(RegionScopeMixin, AuditeeScopeMixin, viewsets.ModelViewSet):
    queryset = RiskAssessment.objects.select_related(
        'department', 'region', 'service_center', 'audit_universe', 'assessed_by', 'reviewed_by'
    ).prefetch_related('self_assessment').all()
    serializer_class = RiskAssessmentSerializer
    permission_classes = [CanWriteAudit]

    # An auditee sees their own department's risk posture, plus anything they
    # assessed personally. Without this the 5x5 heat map was an EEU-wide risk
    # register, readable by the party being assessed. A regional FPA auditor
    # sees only assessments tagged with their region.
    #
    # `/heatmap/` and `/summary/` below both read through `get_queryset`, so they
    # narrow with the list rather than sidestepping it — which is the trap with
    # derived actions, and the reason this is a queryset-level fix.
    region_scope_fields = ('region_id',)
    auditee_scope_fields = ('department_id',)
    auditee_scope_personal_fields = ('assessed_by',)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        'department', 'region', 'service_center', 'audit_universe', 'year',
        'assessment_period', 'risk_rating', 'is_self_assessment',
    ]
    search_fields = ['department__name', 'notes']
    ordering_fields = ['risk_score', 'created_at', 'year']
    ordering = ['-risk_score']

    def perform_create(self, serializer):
        with transaction.atomic():
            assessment = serializer.save(assessed_by=self.request.user)
            log_audit(self.request, 'CREATE', assessment)

    def perform_update(self, serializer):
        """A manager who restates the numbers takes ownership of the score.

        ``adopted_source`` records whose figures produced the score. Once the
        manager edits likelihood/impact/control effectiveness they have asserted
        their own numbers, so a previously adopted self-assessment must stop
        driving the score — otherwise the row would keep scoring from the
        auditee's figures while displaying the manager's, and the stored score
        would silently disagree with the inputs on screen.

        Only an actual value change counts: re-sending the same numbers (a PATCH
        that touches only ``notes``, or a client echoing the whole object) is not
        a restatement and leaves an adoption in place.

        A restatement also sends an approved row back to draft. The approval
        covers the numbers that were on the row when it was given, so letting a
        reviewer's sign-off survive a changed score would mean the entity's
        propagated risk score carried an approval nobody gave.
        """
        changed_inputs = any(
            field in serializer.validated_data
            and serializer.validated_data[field] != getattr(serializer.instance, field)
            for field in ('likelihood', 'impact', 'control_effectiveness')
        )
        with transaction.atomic():
            assessment = serializer.save(**({
                'adopted_source': 'manager',
                'status': RiskAssessment.DRAFT,
                'reviewed_by': None,
                'reviewed_at': None,
            } if changed_inputs else {})
            )
            log_audit(self.request, 'UPDATE', assessment)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=False, methods=['post'], url_path='recompute',
            permission_classes=[RequiresCapability.for_(MANAGE_SETTINGS)])
    def recompute(self, request):
        """Re-score the whole register against the policy now in force.

        The explicit "take the new policy into effect" button. Parameter edits
        already recompute inline, so this exists for the cases that bypass the API
        — a fixture, the Django admin, a direct database edit — and to clear the
        ``stale_assessments`` count the policy endpoint reports.

        Gated on MANAGE_SETTINGS rather than the viewset's WRITE_AUDIT: it is a
        register-wide rewrite, so it sits with the parameter editor it responds
        to, not with ordinary assessment writing.
        """
        updated, total = recompute_assessments()
        return Response({'updated': updated, 'total': total})

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        """Send a draft to the reviewers. The assessor's own move.

        Restricted to the assessor plus APPROVE_PLANS holders: at the class-level
        WRITE_AUDIT gate any auditor could push a colleague's assessment to the
        approvers under their own name.
        """
        assessment = self.get_object()
        if not (request.user.id == assessment.assessed_by_id
                or has_capability(request.user, APPROVE_PLANS)):
            raise PermissionDenied('Only the assessor can submit this assessment.')

        if assessment.status not in (RiskAssessment.DRAFT, RiskAssessment.REJECTED):
            return Response(
                {'detail': f'This assessment is "{assessment.get_status_display()}" '
                           'and is already with a reviewer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prev_status = assessment.status
        with transaction.atomic():
            assessment.status = RiskAssessment.SUBMITTED
            assessment.save(update_fields=['status', 'updated_at'])
            log_audit(request, 'UPDATE', assessment,
                      changes={'status': [prev_status, RiskAssessment.SUBMITTED]})
            notify_roles(
                ['audit_manager', 'supervisor'],
                'approval_needed',
                f'Risk assessment awaiting approval: {assessment.year}',
                f'{assessment.department} — {assessment.assessment_period} has been '
                f'submitted for approval by '
                f'{request.user.get_full_name() or request.user.username}.',
                f'/risk?assessment={assessment.id}',
                exclude=request.user,
            )
        return Response({'detail': 'Risk assessment submitted for approval.'})

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def approve(self, request, pk=None):
        """Sign the score off, which is what puts it on the auditable entity.

        Saving re-runs ``_propagate_to_universe``, and that only propagates an
        approved row — so the approve action is the moment the entity's risk
        score actually moves.
        """
        assessment = self.get_object()
        if assessment.status == RiskAssessment.APPROVED:
            return Response(
                {'detail': 'This assessment is already approved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prev_status = assessment.status
        with transaction.atomic():
            assessment.status = RiskAssessment.APPROVED
            assessment.reviewed_by = request.user
            assessment.reviewed_at = timezone.now()
            if request.data.get('review_notes'):
                assessment.review_notes = request.data['review_notes']
            # A full save, not update_fields: the propagation hook lives in save().
            assessment.save()
            log_audit(request, 'APPROVE', assessment,
                      changes={'status': [prev_status, RiskAssessment.APPROVED]})
            if assessment.assessed_by and assessment.assessed_by != request.user:
                notify(
                    assessment.assessed_by,
                    'approved',
                    f'Risk assessment approved: {assessment.year}',
                    f'Your {assessment.assessment_period} assessment of '
                    f'{assessment.department} has been approved.',
                    f'/risk?assessment={assessment.id}',
                )
        return Response({'detail': 'Risk assessment approved.'})

    @action(detail=True, methods=['post'], url_path='reject',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def reject(self, request, pk=None):
        """Send the score back to the assessor, with a reason.

        A rejected row stops propagating, so an entity that was scored by an
        earlier approved assessment keeps that score rather than silently
        inheriting this one.
        """
        assessment = self.get_object()
        prev_status = assessment.status
        with transaction.atomic():
            assessment.status = RiskAssessment.REJECTED
            assessment.reviewed_by = request.user
            assessment.reviewed_at = timezone.now()
            assessment.review_notes = request.data.get('review_notes', '')
            assessment.save()
            log_audit(request, 'UPDATE', assessment,
                      changes={'status': [prev_status, RiskAssessment.REJECTED]})
            if assessment.assessed_by and assessment.assessed_by != request.user:
                notify(
                    assessment.assessed_by,
                    'system',
                    f'Risk assessment returned: {assessment.year}',
                    f'Your {assessment.assessment_period} assessment of '
                    f'{assessment.department} was returned for revision.'
                    + (f' {assessment.review_notes}' if assessment.review_notes else ''),
                    f'/risk?assessment={assessment.id}',
                )
        return Response({'detail': 'Risk assessment returned for revision.'})

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
        with transaction.atomic():
            assessment = serializer.save(status=serializer.instance.status)
            log_audit(self.request, 'UPDATE', assessment)

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()
    def perform_create(self, serializer):
        with transaction.atomic():
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
        """Mark a submission reviewed, optionally adopting the auditee's numbers.

        ``adopt_self_values`` is the one route to ``adopted_source='self_assessment'``:
        a reviewer who accepts the submission's figures hands the score over to
        them, and saving the parent recomputes and propagates it. Left false or
        absent the parent keeps scoring from the manager's own numbers, and its
        ``adopted_source`` is not touched — declining to adopt is not a reset.

        ``comments`` is unchanged (it lands in ``reviewer_notes``); ``note`` is the
        separate, optional justification recorded for the adoption itself.
        """
        assessment = self.get_object()
        # Accept both a JSON boolean and the string forms a form-encoded body can
        # send, where 'false' would otherwise be truthy.
        raw_adopt = request.data.get('adopt_self_values', False)
        adopt_self_values = (
            raw_adopt.strip().lower() in ('1', 'true', 'yes', 'on')
            if isinstance(raw_adopt, str) else bool(raw_adopt)
        )

        with transaction.atomic():
            assessment.status = 'reviewed'
            assessment.reviewed_by = request.user
            assessment.reviewed_at = timezone.now()
            assessment.reviewer_notes = request.data.get('comments', assessment.reviewer_notes)
            assessment.save()
            log_audit(request, 'UPDATE', assessment)

            parent = assessment.risk_assessment
            if adopt_self_values and parent is not None:
                previous_source = parent.adopted_source
                parent.adopted_source = 'self_assessment'
                parent.adoption_note = request.data.get('note', '') or ''
                # Full save: recomputes from the adopted values and propagates the
                # new score onto the auditable entity.
                parent.save()
                log_audit(request, 'UPDATE', parent, changes={
                    'adopted_source': [previous_source, 'self_assessment'],
                })

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
