from django.db import models
from apps.accounts.models import User
from apps.audit_planning.models import AuditEngagement
from apps.audit_execution.models import AuditProcedure


class AuditFinding(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('informational', 'Informational'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('disputed', 'Disputed'),
    ]

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
    procedure = models.ForeignKey(AuditProcedure, on_delete=models.SET_NULL, null=True, blank=True, related_name='findings')
    finding_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=400)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='control_deficiency')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
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
    file = models.FileField(upload_to='evidence/%Y/%m/')
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
