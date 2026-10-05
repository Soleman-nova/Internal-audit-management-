from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
import mimetypes

from .models import AuditFinding, Evidence, FindingComment
from .serializers import (
    AuditFindingSerializer, AuditFindingListSerializer, EvidenceSerializer,
    FindingCommentSerializer,
)
from apps.accounts.models import Role, User
from apps.notifications.services import notify
from apps.common.permissions import (
    CanWriteAudit, RequiresCapability, InvolvedPartyOrCapability, CLOSE_FINDINGS,
    APPROVE_PLANS, WRITE_AUDIT, ROLE_CAPABILITIES, has_capability,
)
from apps.common.audit_utils import log_audit
from apps.common.reference_numbers import save_with_reference_number
from apps.common.request_utils import with_parent
from apps.common.scoping import region_for

# Which status a finding may move to, per action. Every action used to assign
# unconditionally, so a closed finding could be closed twice and `resolve` would
# happily run on a disputed one — each time writing an audit-trail entry and
# firing a notification for a transition that never really happened.
ALLOWED_TRANSITIONS = {
    'resolved': {'draft', 'open', 'in_progress', 'disputed'},
    'closed': {'draft', 'open', 'in_progress', 'resolved', 'disputed'},
    'disputed': {'draft', 'open', 'in_progress', 'resolved', AuditFinding.AWAITING_AUDITEE},
    'in_progress': {'resolved', 'closed', 'disputed', AuditFinding.AWAITING_AUDITEE},
    # Publishing is the supervisor's endorsement, so it only moves a finding the
    # team has just raised — not one already out with the auditee or settled.
    AuditFinding.AWAITING_AUDITEE: {'draft', 'open'},
}



class AuditFindingViewSet(viewsets.ModelViewSet):
    queryset = AuditFinding.objects.select_related(
        'engagement', 'procedure', 'identified_by', 'assigned_to', 'auditee'
    ).prefetch_related('evidence', 'comments', 'corrective_actions').all()
    serializer_class = AuditFindingSerializer
    permission_classes = [CanWriteAudit]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['severity', 'status', 'category', 'engagement', 'is_repeat']
    search_fields = ['title', 'description', 'finding_number', 'recommendation']
    ordering_fields = ['created_at', 'severity', 'status', 'target_resolution_date']
    ordering = ['-created_at']

    def get_serializer_class(self):
        """The register gets counts; everything else gets the full record.

        Only `list` — `retrieve` still returns nested evidence and comments, so
        the detail page needs no second round of requests.
        """
        if self.action == 'list':
            return AuditFindingListSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """Auditees see only findings that concern them, and only once published.
        Regional FPA auditors see only findings from their region's engagements.

        Same shape as CorrectiveActionViewSet.get_queryset — an auditee is a
        department representative, not an auditor, so a full EEU-wide findings
        register would expose other directorates' issues. Everyone with a
        capability keeps the unfiltered view.

        The publication filter is the second half of that: a finding is the audit
        team's own draft until a supervisor endorses it, so until then the auditee
        has no business seeing it at all. This is also what makes `respond`,
        `dispute`, `add_comment` and `upload_evidence` refuse an unpublished
        finding — all four resolve it through ``self.get_object()``, which runs
        against this queryset, so they 404 rather than needing a status check each.

        A regional auditor is not an auditee, so the two scopes never interact.
        """
        user = self.request.user
        qs = super().get_queryset()
        if self.action == 'list':
            # The list serializer reports counts rather than nesting the rows, so
            # the class-level prefetch would fetch every evidence record and
            # every comment on the page only to throw them away. Annotate
            # instead — one query for the page, no per-row .count().
            #
            # distinct=True because three joins against the same rows multiply
            # each other; without it every count would be inflated by the size
            # of the other two.
            qs = qs.prefetch_related(None).annotate(
                evidence_count=Count('evidence', distinct=True),
                comments_count=Count('comments', distinct=True),
                corrective_actions_count=Count('corrective_actions', distinct=True),
            )
        # Region scoping (runs before auditee scoping — different roles).
        region_id = region_for(user)
        if region_id is not None:
            return qs.filter(engagement__region_id=region_id).distinct()
        if user.is_authenticated and user.role == 'auditee':
            scope = Q(auditee=user) | Q(assigned_to=user)
            if user.department_id:
                scope |= Q(engagement__department_id=user.department_id)
            return qs.filter(scope).exclude(
                status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            ).distinct()
        return qs

    def perform_create(self, serializer):
        # One transaction for the row, its audit-trail entry, and its
        # notifications. Notifications are DB rows, so they roll back with the
        # finding on failure rather than pointing at a record that never
        # committed — no post-commit hook needed.
        with transaction.atomic():
            # Forced rather than left to the model default: a finding is always
            # born a draft, whoever raises it, and the supervisor's publish is the
            # only way out. `status` is read-only on the serializer, so this closes
            # the loop — there is no input, here or upstream, that opens one live.
            finding = save_with_reference_number(
                serializer, 'finding_number', 'FND',
                identified_by=self.request.user, status='draft',
            )
            log_audit(self.request, 'CREATE', finding)
            # Notify the audit team, and only the audit team. This used to go to
            # `assigned_to` and `auditee` as well, which told the auditee a finding
            # existed before anyone had reviewed it — and on the common shape where
            # the assigned contact *is* the auditee, it told them directly.
            # Publishing is what brings them in; `publish` notifies them there.
            link = f'/findings/{finding.id}'
            recipients = {finding.assigned_to, finding.auditee}
            recipients.discard(None)
            recipients.discard(self.request.user)
            recipients = {u for u in recipients if has_capability(u, WRITE_AUDIT)}
            severity = (
                finding.get_severity_display()
                if hasattr(finding, 'get_severity_display') else finding.severity
            )
            for recipient in recipients:
                notify(
                    recipient,
                    'finding',
                    f'New finding: {finding.finding_number}',
                    f'A {severity} finding "{finding.title}" has been assigned to you.',
                    link,
                )
            # And whoever has to endorse it. This is the half that was missing:
            # a finding is born `draft` and only `publish` moves it, so without a
            # notification the reviewer was never told there was anything to
            # review — the register just quietly accumulated findings nobody had
            # been asked to look at, and the auditee's clock never started.
            for recipient in self._reviewers_for(finding, self.request.user):
                notify(
                    recipient,
                    'approval_needed',
                    f'Finding awaiting your review: {finding.finding_number}',
                    f'A {severity} finding "{finding.title}" needs supervisor '
                    'endorsement before it goes to the auditee.',
                    link,
                )

    @staticmethod
    def _reviewers_for(finding, exclude):
        """Who is asked to endorse a newly raised finding.

        The engagement's own supervisor, since that is the person accountable
        for the audit it came from. Falling back to every active APPROVE_PLANS
        holder when the engagement names none: the finding is still publishable
        by them (`publish` is gated on the capability, not the assignment), so
        notifying nobody would leave a reviewable finding with no reviewer told —
        the same dead end one level down.

        The fallback narrows by role in the database rather than sifting every
        user through `has_capability`: the roles that hold APPROVE_PLANS are
        derived from the capability matrix, so this cannot drift from the gate it
        is announcing. Superusers are included explicitly because they hold every
        capability without appearing in the matrix.
        """
        reviewer = finding.engagement.supervisor
        if reviewer is not None:
            return [reviewer] if reviewer != exclude else []
        approver_roles = [
            role for role, caps in ROLE_CAPABILITIES.items() if APPROVE_PLANS in caps
        ]
        return list(
            User.objects
            .filter(Q(role__in=approver_roles) | Q(is_superuser=True), is_active=True)
            .distinct()
            .exclude(pk=getattr(exclude, 'pk', None))
        )

    def perform_update(self, serializer):
        prev_assigned_id = serializer.instance.assigned_to_id
        prev_auditee_id = serializer.instance.auditee_id
        prev_status = serializer.instance.status
        with transaction.atomic():
            finding = serializer.save()
            changes = None
            if finding.status != prev_status:
                changes = {'status': [prev_status, finding.status]}
            log_audit(self.request, 'UPDATE', finding, changes=changes)
            # Notify anyone newly assigned during this update.
            link = f'/findings/{finding.id}'
            newly = []
            if finding.assigned_to_id and finding.assigned_to_id != prev_assigned_id:
                newly.append(finding.assigned_to)
            if finding.auditee_id and finding.auditee_id != prev_auditee_id:
                newly.append(finding.auditee)
            for recipient in newly:
                if recipient and recipient != self.request.user:
                    notify(
                        recipient,
                        'assigned',
                        f'Finding assigned: {finding.finding_number}',
                        f'You have been assigned to finding "{finding.title}".',
                        link,
                    )

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    def _transition(self, request, finding, new_status, resolution_date=...):
        """Apply a status change, or return a 400 Response if it is not legal.

        ``resolution_date`` is ``...`` when the action should leave
        ``actual_resolution_date`` alone; pass a date or None to set it.
        """
        allowed = ALLOWED_TRANSITIONS.get(new_status, set())
        if finding.status not in allowed:
            return None, Response(
                {'detail': f'Cannot move a {finding.get_status_display()} finding to '
                           f'{dict(AuditFinding.STATUS_CHOICES)[new_status]}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prev_status = finding.status
        finding.status = new_status
        if resolution_date is not ...:
            finding.actual_resolution_date = resolution_date
        finding.save()
        log_audit(request, 'UPDATE', finding, changes={'status': [prev_status, new_status]})
        return prev_status, None

    @action(detail=True, methods=['post'], url_path='add-comment',
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def add_comment(self, request, pk=None):
        finding = self.get_object()
        # The finding comes from the URL, but FindingCommentSerializer still
        # declares it required, so it has to be in `data` and not just in
        # `save()` — otherwise every comment 400s on "finding: required".
        data = with_parent(request.data, finding=finding.id)
        serializer = FindingCommentSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            comment = serializer.save(author=request.user)
            log_audit(request, 'UPDATE', finding,
                      object_repr=f'Comment added to {finding.finding_number}')
            # Pull the rest of the thread in: whoever raised it, owns it, or is
            # answering for it should know a reply landed.
            recipients = {finding.identified_by, finding.assigned_to, finding.auditee}
            recipients.discard(None)
            recipients.discard(request.user)
            for recipient in recipients:
                notify(
                    recipient,
                    'comment',
                    f'New comment on {finding.finding_number}',
                    f'{request.user.get_full_name() or request.user.email} commented: '
                    f'{comment.comment[:120]}',
                    f'/findings/{finding.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='upload-evidence',
            parser_classes=[MultiPartParser, FormParser, JSONParser],
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def upload_evidence(self, request, pk=None):
        finding = self.get_object()
        # Same as add_comment: `finding` is a required serializer field, and the
        # upload form only carries title/type/file. `with_parent` rather than
        # `request.data.copy()` because copying a multipart QueryDict deep-copies
        # the upload, and a file large enough to be spooled to disk cannot be
        # pickled — see apps/common/request_utils.py.
        data = with_parent(request.data, finding=finding.id)
        serializer = EvidenceSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            evidence = serializer.save(uploaded_by=request.user)
            log_audit(request, 'UPDATE', finding,
                      object_repr=f'Evidence "{evidence.title}" added to {finding.finding_number}')
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'finding',
                    f'Evidence added to {finding.finding_number}',
                    f'{request.user.get_full_name() or request.user.email} attached '
                    f'"{evidence.title}".',
                    f'/findings/{finding.id}',
                )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='publish',
            permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    def publish(self, request, pk=None):
        """Supervisor sign-off: endorse the finding and put it to the auditee.

        A finding is the audit team's own draft until a reviewer agrees it stands
        up. Publishing is what starts the auditee's response clock, and it is
        gated on APPROVE_PLANS rather than CLOSE_FINDINGS so the auditor who
        raised the finding cannot also be the one who endorses it.
        """
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, AuditFinding.AWAITING_AUDITEE)
            if error:
                return error
            recipients = self._publication_recipients(finding)
            recipients.discard(request.user)
            for recipient in recipients:
                notify(
                    recipient,
                    'finding',
                    f'Finding requires your response: {finding.finding_number}',
                    f'Finding "{finding.title}" has been published for your response.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding published to the auditee.'})

    @staticmethod
    def _publication_recipients(finding):
        """Everyone the published finding now concerns.

        `finding.auditee` is the person it is addressed to, and on anything raised
        through the register that is populated — it is inherited from the
        engagement (see AuditFindingSerializer.validate). The engagement's own
        auditee is added for rows stamped before that inheritance existed, and the
        department's auditees are the last resort.

        That last branch is not decoration. A finding with no auditee anywhere is
        still *readable* by the auditee's department — the register's scope falls
        back to `engagement.department` — so publishing it and telling only the
        two fields that happen to be NULL meant the finding went live in front of
        an audience that was never informed. Publishing must not be able to mean
        "published into the void".
        """
        recipients = {finding.auditee, finding.assigned_to}
        if finding.engagement_id:
            recipients.add(finding.engagement.auditee)
        if not any(u is not None for u in (finding.auditee, finding.engagement.auditee)) \
                and finding.engagement_id and finding.engagement.department_id:
            recipients.update(
                User.objects.filter(
                    role=Role.AUDITEE, is_active=True,
                    department_id=finding.engagement.department_id,
                )
            )
        recipients.discard(None)
        return recipients

    @action(detail=True, methods=['post'], url_path='close',
            permission_classes=[RequiresCapability.for_(CLOSE_FINDINGS)])
    def close(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, 'closed',
                                        resolution_date=timezone.now().date())
            if error:
                return error
            # Let the auditor who raised it know it was closed.
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'system',
                    f'Finding closed: {finding.finding_number}',
                    f'Finding "{finding.title}" has been closed.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding closed.'})

    @action(detail=True, methods=['post'], url_path='resolve',
            permission_classes=[RequiresCapability.for_(CLOSE_FINDINGS)])
    def resolve(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, 'resolved',
                                        resolution_date=timezone.now().date())
            if error:
                return error
            # Let the auditor who raised it know it was resolved.
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'system',
                    f'Finding resolved: {finding.finding_number}',
                    f'Finding "{finding.title}" has been marked as resolved.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding marked as resolved.'})

    @action(detail=True, methods=['post'], url_path='respond',
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def respond(self, request, pk=None):
        """The auditee's own formal position on the finding.

        `management_response` feeds the audit report, and the class-level
        CanWriteAudit gate meant only the audit team could write it — an auditee
        holds no capabilities, so they could not even PATCH the finding that is
        about them. The auditor therefore typed the auditee's response on their
        behalf, which inverts the workflow. This is the fourth involved-party
        action, alongside add_comment / upload_evidence / dispute.

        Re-posting replaces the text, so an auditee can revise their response
        while the finding is open; the previous wording is kept in the audit
        trail rather than in a second field.

        Deliberately does *not* touch `status`: responding is not a lifecycle
        event — `dispute` is the action for disagreement — and ALLOWED_TRANSITIONS
        has no path into `in_progress` from `open` in any case.
        """
        finding = self.get_object()
        text = (request.data.get('management_response') or '').strip()
        if not text:
            return Response({'management_response': ['This field may not be blank.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if finding.status == 'closed':
            return Response(
                {'detail': 'This finding is closed and no longer accepts a management response.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        previous = finding.management_response
        was_awaiting = finding.status == AuditFinding.AWAITING_AUDITEE
        with transaction.atomic():
            finding.management_response = text
            if was_awaiting:
                # The ball was with the auditee, so their response is the event
                # that ends that state. Any other status keeps its own — revising
                # an open finding's text is not a lifecycle move, and `dispute`
                # is the action for disagreement.
                finding.status = 'in_progress'
                finding.save(update_fields=[
                    'management_response', 'status', 'updated_at',
                ])
                log_audit(request, 'UPDATE', finding, changes={
                    'status': [AuditFinding.AWAITING_AUDITEE, 'in_progress'],
                })
            else:
                finding.save(update_fields=['management_response', 'updated_at'])
            # Truncated to 300 in `changes` for the same reason log_audit
            # truncates object_repr: a long response should not bloat every
            # audit-trail row that records one.
            log_audit(request, 'UPDATE', finding,
                      object_repr=f'Management response recorded on {finding.finding_number}',
                      changes={'management_response': [previous[:300], text[:300]]})
            # Whoever raised it and whoever owns it need to read the response;
            # the responder does not need telling. 'finding' rather than a new
            # type: upload_evidence already uses it for the same
            # "the auditee did something on your finding" case, and it is a
            # declared TYPE_CHOICES member, so no migration.
            recipients = {finding.identified_by, finding.assigned_to}
            recipients.discard(None)
            recipients.discard(request.user)
            for recipient in recipients:
                notify(
                    recipient,
                    'finding',
                    f'Management response on {finding.finding_number}',
                    f'{request.user.get_full_name() or request.user.email} responded: '
                    f'{text[:120]}',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Management response recorded.',
                         'management_response': finding.management_response})

    @action(detail=True, methods=['post'], url_path='dispute',
            permission_classes=[InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    def dispute(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            # Clear the resolution date, as `reopen` already did. Disputing a
            # resolved finding used to leave the old date behind, so an
            # unresolved record still carried a resolution date — and that date
            # feeds the report analytics.
            _, error = self._transition(request, finding, 'disputed', resolution_date=None)
            if error:
                return error
            # Notify the auditor who identified it that the finding is disputed.
            if finding.identified_by and finding.identified_by != request.user:
                notify(
                    finding.identified_by,
                    'system',
                    f'Finding disputed: {finding.finding_number}',
                    f'Finding "{finding.title}" has been disputed by '
                    f'{request.user.get_full_name() or request.user.username}.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding marked as disputed.'})

    @action(detail=True, methods=['post'], url_path='reopen',
            permission_classes=[RequiresCapability.for_(CLOSE_FINDINGS)])
    def reopen(self, request, pk=None):
        finding = self.get_object()
        with transaction.atomic():
            _, error = self._transition(request, finding, 'in_progress', resolution_date=None)
            if error:
                return error
            # Notify the assignee that the finding was reopened.
            if finding.assigned_to and finding.assigned_to != request.user:
                notify(
                    finding.assigned_to,
                    'system',
                    f'Finding reopened: {finding.finding_number}',
                    f'Finding "{finding.title}" has been reopened and needs attention.',
                    f'/findings/{finding.id}',
                )
        return Response({'detail': 'Finding reopened.'})


class EvidenceViewSet(viewsets.ModelViewSet):
    # Newest first, and ordered at all: Evidence has no Meta.ordering, so
    # paginating an unordered queryset could repeat or skip attachments between
    # pages. Same reason AuditProgramViewSet carries an explicit ordering.
    queryset = Evidence.objects.select_related('finding', 'uploaded_by').order_by('-uploaded_at')
    serializer_class = EvidenceSerializer
    permission_classes = [CanWriteAudit]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['finding', 'evidence_type']

    def get_queryset(self):
        """Evidence inherits its finding's visibility — auditees see only theirs.
        Regional FPA auditors see only evidence from their region's engagements.

        Including publication: evidence on an unpublished finding would otherwise
        hand back the file and its title, which is the finding's content by
        another route.
        """
        user = self.request.user
        qs = super().get_queryset()
        # Region scoping (runs before auditee scoping — different roles).
        region_id = region_for(user)
        if region_id is not None:
            return qs.filter(finding__engagement__region_id=region_id).distinct()
        if user.is_authenticated and user.role == 'auditee':
            scope = Q(finding__auditee=user) | Q(finding__assigned_to=user)
            if user.department_id:
                scope |= Q(finding__engagement__department_id=user.department_id)
            return qs.filter(scope).exclude(
                finding__status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
            ).distinct()
        return qs

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """Stream the attachment through the API instead of exposing /media/.

        `EvidenceSerializer.file_url` used to hand out an absolute MEDIA_URL,
        which meant audit evidence was readable by anyone holding the link with
        no token at all — and bypassed the auditee scoping in `get_queryset`
        entirely. It also stopped working under DEBUG=False, because the
        `static()` helper mounting MEDIA_URL returns [] in production.

        Authorization is `get_object()` running against the scoped queryset, so
        an auditee can only reach evidence on findings that concern them. Same
        shape as WorkingPaperViewSet.download.
        """
        evidence = self.get_object()
        if not evidence.file:
            return Response({'detail': 'No file attached to this evidence.'},
                            status=status.HTTP_400_BAD_REQUEST)
        content_type, _ = mimetypes.guess_type(evidence.file.name)
        response = HttpResponse(evidence.file.read(),
                                content_type=content_type or 'application/octet-stream')
        filename = evidence.file.name.split('/')[-1]
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response