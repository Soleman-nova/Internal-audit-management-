from django.db import models
from django.utils import timezone
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
    # Phase 3.1 — link the assessment to the auditable entity it is about, so the
    # computed risk score can be propagated into AuditUniverse.risk_score.
    audit_universe = models.ForeignKey(
        'audit_planning.AuditUniverse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='risk_assessments',
    )
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

    # Legacy fallback kept for records that were never weighted (score = L × I).
    WEIGHT_MAX_UPLIFT = 0.3  # fully-configured parameter set adds at most +30%

    def _compute_scores(self):
        """Compute inherent/residual scores using active RiskParameter weights.

        Phase 3.2 — the weighted RiskParameter configuration is now real:
        the total weight of active parameters acts as a risk-exposure uplift on
        the base likelihood×impact score (capped at the 1–25 scale so the
        existing heat map / rating semantics keep working). An empty parameter
        set falls back to the legacy likelihood × impact formula.
        """
        base = float(self.likelihood * self.impact)

        weight_sum = 0.0
        for param in RiskParameter.objects.filter(is_active=True):
            weight_sum += float(param.weight or 0)

        if weight_sum > 0:
            uplift = min(weight_sum * 0.2, self.WEIGHT_MAX_UPLIFT)
            self.risk_score = round(min(25, base * (1 + uplift)), 2)
        else:
            self.risk_score = round(base, 2)

        if self.risk_score <= 4:
            self.risk_rating = 'low'
        elif self.risk_score <= 9:
            self.risk_rating = 'medium'
        elif self.risk_score <= 16:
            self.risk_rating = 'high'
        else:
            self.risk_rating = 'critical'

        # Control effectiveness (1..5) reduces the inherent risk: CE=1 keeps 100%,
        # CE=5 reduces to 20% of the inherent score.
        self.residual_risk = round(
            float(self.risk_score) * (1 - (int(self.control_effectiveness) - 1) * 0.2),
            2,
        )

    def _propagate_to_universe(self):
        """Phase 3.1 — push the computed score onto the linked AuditUniverse.

        Falls back to resolving the universe by department when an explicit
        link was not provided, so existing clients that only send `department`
        still drive universe risk scores.
        """
        from apps.audit_planning.models import AuditUniverse

        target = self.audit_universe
        if target is None and self.department_id:
            target = (
                AuditUniverse.objects
                .filter(department_id=self.department_id, status='active')
                .order_by('-risk_score')
                .first()
            )
        if target is not None:
            target.risk_score = self.risk_score
            target.save(update_fields=['risk_score', 'updated_at'])

    def save(self, *args, **kwargs):
        self._compute_scores()
        super().save(*args, **kwargs)
        self._propagate_to_universe()

    def delete(self, *args, **kwargs):
        """Re-propagate the next latest assessment when this one is removed."""
        from apps.audit_planning.models import AuditUniverse

        universe = self.audit_universe
        dept_id = self.department_id
        super().delete(*args, **kwargs)

        if universe is not None:
            latest = (
                RiskAssessment.objects
                .filter(audit_universe=universe)
                .exclude(pk=self.pk)
                .order_by('-year', '-created_at')
                .first()
            )
            if latest is None and dept_id is not None:
                latest = (
                    RiskAssessment.objects
                    .filter(department_id=dept_id)
                    .exclude(pk=self.pk)
                    .order_by('-year', '-created_at')
                    .first()
                )
            universe.risk_score = latest.risk_score if latest else 0
            universe.save(update_fields=['risk_score', 'updated_at'])

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
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='self_assessments_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)