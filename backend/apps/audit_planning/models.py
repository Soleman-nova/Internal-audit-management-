from django.db import models
from apps.accounts.models import User, Department


class AuditUniverse(models.Model):
    """Centralized repository of all auditable entities"""
    CATEGORY_CHOICES = [
        ('department', 'Department'),
        ('process', 'Business Process'),
        ('system', 'IT System'),
        ('project', 'Project'),
        ('subsidiary', 'Subsidiary'),
        ('regulation', 'Regulatory Area'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('under_review', 'Under Review'),
    ]

    name = models.CharField(max_length=300)
    code = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    owner = models.CharField(max_length=200, blank=True)
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    audit_frequency = models.CharField(max_length=50, blank=True)
    last_audited = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['-risk_score', 'name']
        verbose_name = 'Audit Universe Entry'
        verbose_name_plural = 'Audit Universe'


class AuditPlan(models.Model):
    """Annual Audit Plan"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted for Approval'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    title = models.CharField(max_length=300)
    year = models.IntegerField()
    description = models.TextField(blank=True)
    objectives = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_plans')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_plans')
    approved_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    total_budget_days = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Audit Plan {self.year} - {self.title}"

    class Meta:
        ordering = ['-year', '-created_at']


class AuditEngagement(models.Model):
    """Individual audit engagement within a plan"""
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('fieldwork', 'Fieldwork'),
        ('reporting', 'Reporting'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    ENGAGEMENT_TYPE_CHOICES = [
        ('financial', 'Financial Audit'),
        ('operational', 'Operational Audit'),
        ('compliance', 'Compliance Audit'),
        ('it', 'IT Audit'),
        ('performance', 'Performance Audit'),
        ('investigative', 'Investigative Audit'),
        ('followup', 'Follow-up Audit'),
        ('special', 'Special Audit'),
    ]

    plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='engagements')
    audit_universe = models.ForeignKey(AuditUniverse, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=300)
    engagement_number = models.CharField(max_length=50, unique=True)
    engagement_type = models.CharField(max_length=50, choices=ENGAGEMENT_TYPE_CHOICES, default='operational')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    objectives = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    lead_auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='led_engagements')
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_engagements')
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    actual_start = models.DateField(null=True, blank=True)
    actual_end = models.DateField(null=True, blank=True)
    planned_days = models.IntegerField(default=0)
    actual_days = models.IntegerField(default=0)
    risk_level = models.CharField(max_length=20, choices=[('low','Low'),('medium','Medium'),('high','High'),('critical','Critical')], default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.engagement_number} - {self.title}"

    class Meta:
        ordering = ['-created_at']


class AuditTeamMember(models.Model):
    """Team members assigned to an engagement"""
    ROLE_CHOICES = [
        ('lead', 'Lead Auditor'),
        ('member', 'Team Member'),
        ('supervisor', 'Supervisor'),
        ('specialist', 'Subject Matter Expert'),
    ]

    engagement = models.ForeignKey(AuditEngagement, on_delete=models.CASCADE, related_name='team_members')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    allocated_days = models.IntegerField(default=0)
    actual_days = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['engagement', 'user']
