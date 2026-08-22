from django.db import models
from apps.accounts.models import User
from apps.audit_planning.models import AuditEngagement
from apps.common.validators import validate_document_upload


class AuditProgram(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Review'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]

    engagement = models.OneToOneField(AuditEngagement, on_delete=models.CASCADE, related_name='program')
    title = models.CharField(max_length=300)
    objectives = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    version = models.IntegerField(default=1)
    prepared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='prepared_programs')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_programs')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_programs')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Program: {self.title} (v{self.version})"

    class Meta:
        ordering = ['-created_at']


class AuditProcedure(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('not_applicable', 'Not Applicable'),
    ]

    PROCEDURE_TYPE_CHOICES = [
        ('test_of_controls', 'Test of Controls'),
        ('substantive', 'Substantive Testing'),
        ('analytical', 'Analytical Procedures'),
        ('inquiry', 'Inquiry'),
        ('observation', 'Observation'),
        ('inspection', 'Inspection & Re-performance'),
    ]

    program = models.ForeignKey(AuditProgram, on_delete=models.CASCADE, related_name='procedures')
    step_number = models.CharField(max_length=20)
    title = models.CharField(max_length=300)
    description = models.TextField()
    procedure_type = models.CharField(max_length=30, choices=PROCEDURE_TYPE_CHOICES, default='substantive')
    risk_area = models.CharField(max_length=200, blank=True)
    assertion = models.CharField(max_length=200, blank=True)
    expected_evidence = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_procedures')
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_procedures')
    completed_at = models.DateTimeField(null=True, blank=True)
    conclusion = models.TextField(blank=True)
    is_template = models.BooleanField(default=False)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.step_number}. {self.title}"

    class Meta:
        ordering = ['order', 'step_number']


class WorkingPaper(models.Model):
    PAPER_TYPE_CHOICES = [
        ('planning', 'Planning Document'),
        ('program', 'Audit Program'),
        ('evidence', 'Evidence'),
        ('workpaper', 'Work Paper'),
        ('correspondence', 'Correspondence'),
        ('report', 'Report'),
        ('other', 'Other'),
    ]

    engagement = models.ForeignKey(AuditEngagement, on_delete=models.CASCADE, related_name='working_papers')
    procedure = models.ForeignKey(AuditProcedure, on_delete=models.SET_NULL, null=True, blank=True, related_name='working_papers')
    reference = models.CharField(max_length=50)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    paper_type = models.CharField(max_length=30, choices=PAPER_TYPE_CHOICES, default='workpaper')
    file = models.FileField(
        upload_to='working_papers/%Y/%m/', null=True, blank=True,
        validators=[validate_document_upload],
    )
    prepared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='prepared_papers')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_papers')
    is_reviewed = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.reference} - {self.title}"

    class Meta:
        ordering = ['reference']
