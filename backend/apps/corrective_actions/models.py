from django.db import models
from apps.accounts.models import User
from apps.findings.models import AuditFinding


class CorrectiveAction(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('partially_resolved', 'Partially Resolved'),
        ('resolved', 'Resolved'),
        ('overdue', 'Overdue'),
        ('not_implemented', 'Not Implemented'),
        ('closed', 'Closed'),
    ]

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.action_number} - {self.title}"

    class Meta:
        ordering = ['due_date']


class ActionResponse(models.Model):
    """Management responses / progress updates on corrective actions"""
    corrective_action = models.ForeignKey(CorrectiveAction, on_delete=models.CASCADE, related_name='responses')
    responder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    response_text = models.TextField()
    evidence_file = models.FileField(upload_to='capa_evidence/%Y/%m/', null=True, blank=True)
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
