from django.db import models
from apps.accounts.models import User, Department


class RiskParameter(models.Model):
    """User-defined parameters for risk assessment"""
    CATEGORY_CHOICES = [
        ('financial', 'Financial Impact'),
        ('operational', 'Operational Impact'),
        ('compliance', 'Compliance/Legal'),
        ('reputational', 'Reputational'),
        ('strategic', 'Strategic'),
        ('it', 'IT/Technology'),
    ]

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1.0, help_text="Weight factor for scoring")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    class Meta:
        ordering = ['category', 'name']


class RiskAssessment(models.Model):
    """Risk assessment for an audit universe entry"""
    PERIOD_CHOICES = [
        ('Q1', 'Q1'),
        ('Q2', 'Q2'),
        ('Q3', 'Q3'),
        ('Q4', 'Q4'),
        ('Annual', 'Annual'),
    ]

    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='risk_assessments')
    assessment_period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='Annual')
    year = models.IntegerField()
    likelihood = models.IntegerField(choices=[(i, i) for i in range(1, 6)], help_text="1=Rare, 5=Almost Certain")
    impact = models.IntegerField(choices=[(i, i) for i in range(1, 6)], help_text="1=Negligible, 5=Catastrophic")
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    risk_rating = models.CharField(max_length=20, choices=[
        ('low','Low'), ('medium','Medium'), ('high','High'), ('critical','Critical')
    ], blank=True)
    inherent_risk = models.IntegerField(default=0)
    control_effectiveness = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=3)
    residual_risk = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    assessed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assessments_done')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments_reviewed')
    is_self_assessment = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.risk_score = self.likelihood * self.impact
        if self.risk_score <= 4:
            self.risk_rating = 'low'
        elif self.risk_score <= 9:
            self.risk_rating = 'medium'
        elif self.risk_score <= 16:
            self.risk_rating = 'high'
        else:
            self.risk_rating = 'critical'
        self.residual_risk = self.risk_score * (1 - (self.control_effectiveness - 1) * 0.2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Risk: {self.department} - {self.year} {self.assessment_period}"

    class Meta:
        ordering = ['-risk_score']


class SelfAssessment(models.Model):
    """Auditee self-assessment submission"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('reviewed', 'Reviewed'),
    ]

    risk_assessment = models.OneToOneField(RiskAssessment, on_delete=models.CASCADE, related_name='self_assessment')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    likelihood_self = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    impact_self = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    control_effectiveness_self = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    justification = models.TextField()
    mitigating_controls = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
