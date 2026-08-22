from django.db import models
from apps.accounts.models import User
from apps.audit_planning.models import AuditEngagement
from apps.common.validators import validate_document_upload


class ReportTemplate(models.Model):
    TEMPLATE_TYPE_CHOICES = [
        ('engagement', 'Engagement Report'),
        ('findings', 'Findings Summary'),
        ('management', 'Management Report'),
        ('board', 'Board Report'),
        ('followup', 'Follow-up Report'),
        ('risk', 'Risk Assessment Report'),
        ('kpi', 'KPI Dashboard Report'),
    ]

    name = models.CharField(max_length=200)
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPE_CHOICES)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    template_file = models.FileField(
        upload_to='report_templates/', null=True, blank=True,
        validators=[validate_document_upload],
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"


class GeneratedReport(models.Model):
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('word', 'Word'),
    ]

    STATUS_CHOICES = [
        ('generating', 'Generating'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    title = models.CharField(max_length=300)
    template = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    engagement = models.ForeignKey(AuditEngagement, on_delete=models.SET_NULL, null=True, blank=True)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='generating')
    parameters = models.JSONField(default=dict)
    file = models.FileField(upload_to='generated_reports/%Y/%m/', null=True, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} ({self.format.upper()})"

    class Meta:
        ordering = ['-generated_at']
