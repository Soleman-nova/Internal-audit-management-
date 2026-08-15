from django.db import models
from django.utils import timezone
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
    directorate = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directorate_universe_items',
        help_text='EEU Internal Audit directorate that owns this universe item.',
    )
    description = models.TextField(blank=True)
    owner = models.CharField(max_length=200, blank=True)
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    audit_frequency = models.CharField(max_length=50, blank=True)
    last_audited = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    technical_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Utility-specific technical audit parameters (Asset Type, Voltage Level, Feeder ID, Energy Loss Score, etc.).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_due_for_re_audit(self, as_of=None):
        """Phase 3.3 — whether the entity is overdue for its next audit.

        Driven by ``audit_frequency`` (highest first) relative to
        ``last_audited``. Entities that were never audited are always due.
        """
        if self.last_audited is None:
            return True
        as_of = as_of or timezone.now().date()
        months = {
            'monthly': 1,
            'quarterly': 3,
            'bi-annually': 6,
            'semi-annually': 6,
            'annually': 12,
            'yearly': 12,
            'tri-annually': 36,
            'biennially': 24,
        }.get((self.audit_frequency or '').strip().lower())
        if months is None:
            return False
        return (self.last_audited + timezone.timedelta(days=30 * months)) <= as_of

    @property
    def due_for_re_audit(self):
        return self.is_due_for_re_audit()

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

    PLAN_SCOPE_CHOICES = [
        ('directorate', 'Directorate Plan'),
        ('consolidated', 'EEU Consolidated Master Plan'),
    ]

    title = models.CharField(max_length=300)
    year = models.IntegerField()
    description = models.TextField(blank=True)
    objectives = models.TextField(blank=True)
    scope = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    directorate = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directorate_audit_plans',
        help_text='Directorate that owns this plan segment. Null for the EEU Consolidated Master Plan.',
    )
    plan_scope = models.CharField(
        max_length=20,
        choices=PLAN_SCOPE_CHOICES,
        default='directorate',
        help_text='Whether this is a directorate-level plan or the consolidated master plan.',
    )
    parent_plan = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_plans',
        help_text='For directorate plans, the consolidated master plan they roll up into.',
    )
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
        ('performance', 'Performance Audit'),
        ('technical', 'Technical & Engineering Audit (Substations, Distribution Grids, Loss Reduction, Transmission)'),
        ('it', 'Information Technology Audit (ERP, CIS Billing, Cybersecurity, Infrastructure)'),
        ('special', 'Planning & Special Review Audit'),
    ]

    plan = models.ForeignKey(AuditPlan, on_delete=models.CASCADE, related_name='engagements')
    audit_universe = models.ForeignKey(AuditUniverse, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=300)
    engagement_number = models.CharField(max_length=50, unique=True)
    engagement_type = models.CharField(max_length=50, choices=ENGAGEMENT_TYPE_CHOICES, default='financial')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    directorate = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directorate_engagements',
        help_text='EEU Internal Audit directorate that owns this engagement.',
    )
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
    technical_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Utility-specific technical audit parameters (Asset Type, Voltage Level, Feeder ID, Energy Loss Score, Engineering Compliance Rating, etc.).',
    )
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