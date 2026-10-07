from django.db import models
from django.utils import timezone
from apps.accounts.models import User
from apps.findings.models import AuditFinding
from apps.common.validators import validate_document_upload


class CorrectiveAction(models.Model):
    STATUS_CHOICES = [
        # The auditee's proposed plan before the auditor has signed it off. It is
        # distinct from `open` because the plan is not yet agreed: implementation
        # has not started, and the auditor has not accepted that the remedy
        # addresses the finding.
        ('pending_approval', 'Pending Auditor Approval'),
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('partially_resolved', 'Partially Resolved'),
        # The owner has filed evidence; the auditor has not verified it yet.
        # Without this state "the auditee says it is done" and "the auditor
        # confirmed it" were the same row status, so a register built from them
        # could not tell an unverified claim from a verified fix.
        ('evidence_submitted', 'Evidence Submitted / Pending Verification'),
        ('resolved', 'Resolved'),
        ('overdue', 'Overdue'),
        ('not_implemented', 'Not Implemented'),
        ('closed', 'Closed'),
    ]

    # Terminal CAPA statuses, and the parent-finding status each one implies.
    # `resolved` and `closed` are the two the spec treats as "the remedy landed";
    # everything else (partially_resolved, not_implemented, overdue) leaves the
    # finding where it is, because the finding is not in fact remediated.
    FINDING_STATUS_FOR = {
        'resolved': 'resolved',
        'closed': 'closed',
    }

    # A finding in one of these is live, so a terminal corrective action may move
    # it. `draft` is excluded (not yet published, nothing to resolve), and so are
    # `disputed` — an auditee's formal disagreement must not be quietly settled by
    # a status write — and the terminal pair themselves.
    FINDING_MOVABLE_FROM = {'open', 'in_progress', 'awaiting_auditee_response'}

    # The statuses that settle the action and, through `sync_parent_finding`, its
    # finding. Kept beside FINDING_STATUS_FOR rather than derived from it: the two
    # answer different questions (what may be written / what it implies) and a
    # status could plausibly be terminal without settling a finding.
    TERMINAL_STATUSES = ('resolved', 'closed')

    # ── Who may write which status ──────────────────────────────────────────
    # The two sides report different things: the owner reports how the work is
    # going, the audit side records what the work amounts to. Before this split an
    # owner could POST `status_update: 'closed'` through add-response and settle
    # both their action and the finding behind it in one request — the auditor's
    # verification was not a gate at all but an optional extra, and the party
    # being audited awarded it to themselves.
    #
    # `evidence_submitted` is here because it is the handoff: "the work is done,
    # here is the proof", which is precisely the owner's claim to make and
    # precisely not the auditor's conclusion. The states left out (`open`,
    # `overdue`, `not_implemented`, and the terminal pair) are either the system's
    # to derive or an assessment of the outcome rather than a progress report.
    OWNER_REPORTABLE_STATUSES = (
        'in_progress', 'partially_resolved', 'evidence_submitted',
    )

    # What `verify_and_close` may act on: everything except `closed` itself (there
    # is nothing left to do) and `pending_approval` (the plan was never agreed, so
    # there is no implementation to verify).
    CLOSEABLE_FROM = (
        'open', 'in_progress', 'partially_resolved', 'evidence_submitted',
        'overdue', 'not_implemented', 'resolved',
    )

    # Statuses a plain PATCH of `status` may not write, because the route that
    # owns each one does more than write the status:
    #
    #   pending_approval  perform_create sets it for an auditee's own proposal,
    #                     and only `approve` takes it back off
    #   overdue           flag_overdue_actions derives it from the due date
    #   not_implemented   verify-and-close records it next to the follow-up visit
    #                     that justifies calling the remedy a failure
    #
    # `approve` is why `pending_approval` is the load-bearing entry here. Leaving
    # that state is what the action is for: it checks who may sign the plan off
    # (the auditor it was routed to, or an APPROVE_PLANS holder — never its own
    # author) and stamps approved_by and approved_at. A PATCH does neither, so
    # before this existed any auditor could open a plan awaiting their own
    # approval and no record of who agreed to it.
    #
    # It is reserved in *both* directions — see the view's guard, which refuses a
    # PATCH that leaves `pending_approval` as well as one that enters it. An
    # auditee's proposal has to be answered, not overwritten.
    #
    # The terminal pair is deliberately *not* here: `resolved`/`closed` are legal
    # in a PATCH for the party `_may_sign_off` names, and the view checks that
    # separately.
    RESERVED_PATCH_STATUSES = ('pending_approval', 'overdue', 'not_implemented')

    PRIORITY_CHOICES = [
        ('immediate', 'Immediate'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    finding = models.ForeignKey(AuditFinding, on_delete=models.CASCADE, related_name='corrective_actions')
    action_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=400)
    description = models.TextField()
    recommendation = models.TextField()
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='owned_actions')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_actions')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    due_date = models.DateField()
    extended_due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    due_reminder_sent = models.BooleanField(default=False, help_text="True if 3-day due-soon reminder was sent")
    management_response = models.TextField(blank=True)
    follow_up_notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_actions',
        help_text='Auditor who accepted the remediation plan.',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.action_number} - {self.title}"

    def sync_parent_finding(self):
        """Move the parent finding on when this action reaches a terminal status.

        A finding is resolved by its remediation, not by a separate click: the
        auditor who closes the corrective action has, by that act, verified the
        fix. Without this the two lifecycles drift — the register shows a finding
        still open whose corrective action was closed months ago, because nothing
        ever carried the closure upward.

        Only ever moves the finding *forward* into a terminal state, and only from
        a live one. Returns the finding status it set, or None when it did not act.
        """
        target = self.FINDING_STATUS_FOR.get(self.status)
        if target is None or self.finding_id is None:
            return None

        finding = self.finding
        if finding.status not in self.FINDING_MOVABLE_FROM:
            return None

        finding.status = target
        if target == 'closed' and finding.actual_resolution_date is None:
            finding.actual_resolution_date = timezone.now().date()
        finding.save()
        return target

    class Meta:
        ordering = ['due_date']


class ActionResponse(models.Model):
    """Management responses / progress updates on corrective actions"""
    corrective_action = models.ForeignKey(CorrectiveAction, on_delete=models.CASCADE, related_name='responses')
    responder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    response_text = models.TextField()
    evidence_file = models.FileField(
        upload_to='capa_evidence/%Y/%m/', null=True, blank=True,
        validators=[validate_document_upload],
    )
    status_update = models.CharField(max_length=30, choices=CorrectiveAction.STATUS_CHOICES)
    responded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-responded_at']


class FollowUp(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    corrective_action = models.ForeignKey(CorrectiveAction, on_delete=models.CASCADE, related_name='follow_ups')
    scheduled_date = models.DateField()
    conducted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='follow_ups_conducted')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)
    outcome = models.CharField(max_length=200, blank=True)
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_date']
