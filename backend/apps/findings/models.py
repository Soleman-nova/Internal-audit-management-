from django.db import models
from apps.accounts.models import User
from apps.audit_planning.models import AuditEngagement
from apps.audit_execution.models import AuditProcedure
from apps.common.validators import validate_document_upload


class AuditFinding(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('informational', 'Informational'),
    ]

    # The state a finding sits in between the supervisor publishing it and the
    # auditee answering. It only does that job if the pre-publication states below
    # are actually kept from the auditee — see PRE_PUBLICATION_STATUSES.
    AWAITING_AUDITEE = 'awaiting_auditee_response'

    # The stored value stays `draft` — it is load-bearing in
    # PRE_PUBLICATION_STATUSES and ALLOWED_TRANSITIONS below, in the fixtures and
    # in the E2E specs. Only the human label moves, so `get_status_display()`
    # reports the queue a finding is actually sitting in: from the moment a lead
    # auditor raises it until an approver publishes it, the finding is waiting on
    # a supervisor, and "Draft" described the wrong party's job.
    STATUS_CHOICES = [
        ('draft', 'Pending Supervisor Review'),
        ('open', 'Open'),
        (AWAITING_AUDITEE, 'Awaiting Auditee Response'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('disputed', 'Disputed'),
    ]

    # ── Publication ─────────────────────────────────────────────────────────
    # A finding is the audit team's own draft until a supervisor endorses it.
    # `publish` is what starts the auditee's clock, and these two states are what
    # it publishes *from*.
    #
    # `open` is here for the same reason rather than because anything creates it:
    # no transition targets it any more, so every row still in it predates this
    # rule. Keeping it in the hidden set means those rows fail closed — an
    # unreviewed finding stays out of the auditee's reach until someone publishes
    # it, rather than leaking back into view through a state nothing writes.
    #
    # Every read path filters with `.exclude(status__in=PRE_PUBLICATION_STATUSES)`
    # rather than listing the published values, so a status added later is visible
    # only once someone decides it should be — the failure mode is a missing
    # finding, not a disclosed one.
    PRE_PUBLICATION_STATUSES = ('draft', 'open')

    CATEGORY_CHOICES = [
        ('control_deficiency', 'Control Deficiency'),
        ('compliance', 'Compliance Issue'),
        ('fraud', 'Fraud Risk'),
        ('operational', 'Operational Weakness'),
        ('financial', 'Financial Misstatement'),
        ('it_security', 'IT/Security Issue'),
        ('governance', 'Governance Issue'),
        ('other', 'Other'),
    ]

    engagement = models.ForeignKey(AuditEngagement, on_delete=models.CASCADE, related_name='findings')
    # `blank=False` but `null=True`, deliberately. A finding is raised *from* a
    # failed procedure, so the API requires the parent link on create (see
    # AuditFindingSerializer.validate). The column stays nullable because rows
    # created before this rule existed have no parent, and there is no honest
    # value to backfill them with — inventing a failed procedure for a historical
    # finding would fabricate audit evidence. So: required at the boundary,
    # optional in the table.
    procedure = models.ForeignKey(AuditProcedure, on_delete=models.SET_NULL, null=True, blank=False, related_name='findings')
    finding_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=400)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='control_deficiency')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    condition = models.TextField(help_text="What did we find?", blank=True)
    criteria = models.TextField(help_text="What should exist (policy/standard)?", blank=True)
    cause = models.TextField(help_text="Why did it happen (root cause)?", blank=True)
    effect = models.TextField(help_text="What is the impact/risk?", blank=True)
    recommendation = models.TextField(blank=True)
    management_response = models.TextField(blank=True)
    risk_impact = models.TextField(blank=True)
    root_cause_category = models.CharField(max_length=100, blank=True)
    identified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='identified_findings')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_findings')
    auditee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='auditee_findings')
    target_resolution_date = models.DateField(null=True, blank=True)
    actual_resolution_date = models.DateField(null=True, blank=True)
    is_repeat = models.BooleanField(default=False, help_text="Is this a repeat finding?")
    previous_finding = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.finding_number} - {self.title}"

    class Meta:
        ordering = ['-created_at']


class Evidence(models.Model):
    EVIDENCE_TYPE_CHOICES = [
        ('document', 'Document'),
        ('screenshot', 'Screenshot'),
        ('spreadsheet', 'Spreadsheet'),
        ('photo', 'Photo'),
        ('video', 'Video'),
        ('other', 'Other'),
    ]

    finding = models.ForeignKey(AuditFinding, on_delete=models.CASCADE, related_name='evidence')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    evidence_type = models.CharField(max_length=20, choices=EVIDENCE_TYPE_CHOICES, default='document')
    file = models.FileField(
        upload_to='evidence/%Y/%m/', validators=[validate_document_upload],
    )
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidence: {self.title} for {self.finding.finding_number}"


class FindingComment(models.Model):
    finding = models.ForeignKey(AuditFinding, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    comment = models.TextField()
    is_internal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
