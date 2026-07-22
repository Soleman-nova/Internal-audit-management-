from django.db import models
from apps.accounts.models import User


class Notification(models.Model):
    TYPE_CHOICES = [
        ('finding', 'New Finding'),
        ('action_due', 'Action Due'),
        ('action_overdue', 'Action Overdue'),
        ('approval_needed', 'Approval Needed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('assigned', 'Assigned to You'),
        ('follow_up', 'Follow-up Due'),
        ('report_ready', 'Report Ready'),
        ('system', 'System'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=300)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.notification_type}] {self.title} -> {self.user.email}"

    class Meta:
        ordering = ['-created_at']


class SystemSetting(models.Model):
    """Global system configuration"""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key
