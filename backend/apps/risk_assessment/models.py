import hashlib

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from apps.accounts.models import User, Department

# The 1–5 scoring scale, declared once and shared by every scoring field
# (RiskAssessment and SelfAssessment alike), so the scale cannot drift between
# the two. `choices` alone is a *serializer*-level guard: it rejects a bad value
# posted to the API but does nothing for a direct ORM write, a fixture, or a
# data migration, any of which could persist a 9 and quietly push the score past
# the 25-point ceiling the heat map is built on. The validators close that gap;
# `full_clean()` and the serializer both pick them up.
SCORE_MIN, SCORE_MAX = 1, 5
SCORE_CHOICES = [(i, i) for i in range(SCORE_MIN, SCORE_MAX + 1)]
SCORE_VALIDATORS = [MinValueValidator(SCORE_MIN), MaxValueValidator(SCORE_MAX)]


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


def active_policy():
    """The risk-scoring policy currently in force.

    Returns ``dict(digest, weight_sum, uplift)`` for the active parameter set.
    The digest is derived from name+weight pairs sorted by name, so it is
    order-independent and changes whenever the set does — which is what makes
    "this assessment was scored under a different policy" a detectable fact
    rather than a silent drift.

    No active parameters is a valid policy, not an error: ``uplift`` is 0 and
    ``risk_score`` is exactly likelihood × impact.
    """
    params = list(RiskParameter.objects.filter(is_active=True).order_by('name'))

    weight_sum = 0.0
    parts = []
    for param in params:
        weight_sum += float(param.weight or 0)
        # `param.weight` comes back from the database as a 2dp Decimal, so the
        # rendered digest is stable across processes and repeated reads.
        parts.append(f'{param.name}:{param.weight}')

    digest = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:12]
    return {
        'digest': digest,
        'weight_sum': round(weight_sum, 2),
        'uplift': round(min(weight_sum * 0.2, RiskAssessment.WEIGHT_MAX_UPLIFT), 3),
    }


class RiskAssessment(models.Model):
    """Risk assessment for an audit universe entry"""
    PERIOD_CHOICES = [
        ('Q1', 'Q1'),
        ('Q2', 'Q2'),
        ('Q3', 'Q3'),
        ('Q4', 'Q4'),
        ('Annual', 'Annual'),
    ]

    # Named like Role.ADMIN: the propagation gate below and the approve action
    # both key off APPROVED, and a bare 'approved' string on both sides of that
    # check is one typo away from a gate that silently stops gating.
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    APPROVED = 'approved'
    REJECTED = 'rejected'

    STATUS_CHOICES = [
        (DRAFT, 'Draft'),
        (SUBMITTED, 'Submitted for Review'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]

    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='risk_assessments')
    # SET_NULL, unlike the CASCADE above: retiring a region or a service center
    # must not take the whole assessment with it.
    region = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        limit_choices_to={'unit_type': Department.REGION},
        help_text='EEU region being assessed, independent of department.',
    )
    service_center = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        limit_choices_to={'unit_type': Department.SERVICE_CENTER},
        help_text='Customer service center being assessed, if any.',
    )
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
    likelihood = models.IntegerField(choices=SCORE_CHOICES, validators=SCORE_VALIDATORS, help_text="1=Rare, 5=Almost Certain")
    impact = models.IntegerField(choices=SCORE_CHOICES, validators=SCORE_VALIDATORS, help_text="1=Negligible, 5=Catastrophic")
    risk_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    risk_rating = models.CharField(max_length=20, choices=[
        ('low','Low'), ('medium','Medium'), ('high','High'), ('critical','Critical')
    ], blank=True)
    control_effectiveness = models.IntegerField(choices=SCORE_CHOICES, validators=SCORE_VALIDATORS, default=3)
    residual_risk = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # ── Frozen policy ────────────────────────────────────────────────────
    # The weighted RiskParameter set is a *policy*, not a global constant: the
    # same L×I pair scores differently under different parameter sets. Rather
    # than let the score silently drift with whatever parameters happen to be
    # active (the old behaviour: a stored 5.08 became 5.2 only when someone
    # re-saved the row), each row records the policy it was scored under, so
    # staleness is visible and recomputing is an explicit, auditable action.
    weight_sum = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    uplift_applied = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    policy_digest = models.CharField(max_length=12, blank=True)
    # Which set of numbers produced the score. A reviewer may adopt the
    # auditee's self-assessed values; the manager's own numbers otherwise.
    adopted_source = models.CharField(max_length=20, default='manager',
                                      choices=[('manager', 'Manager assessment'),
                                               ('self_assessment', 'Auditee self-assessment')])
    adoption_note = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # The assessor's score is a proposal until a reviewer signs it off; only an
    # approved row drives the auditable entity's risk score (see
    # `_propagate_to_universe`). A new row starts as a draft, so an assessor
    # cannot make a number official by pressing save.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    # The reviewer's own note, kept separate from `notes` (the assessor's
    # justification) for the same reason SelfAssessment splits
    # justification/reviewer_notes: overwriting one with the other loses the
    # argument the assessment was made on.
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    assessed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assessments_done')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessments_reviewed')
    is_self_assessment = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Cap on the weighted-parameter uplift. A fully-configured parameter set adds
    # at most +30%; see ``active_policy``. Not a fallback — the parameter set is a
    # policy, and an empty one simply has uplift 0 (score == L×I).
    WEIGHT_MAX_UPLIFT = 0.3

    def _scoring_inputs(self):
        """The (likelihood, impact, control_effectiveness) triple that scores this row.

        ``adopted_source`` decides whose numbers count. A reviewer who accepts an
        auditee's self-assessment flips it to ``self_assessment``, at which point
        the row is scored from the submitted values — the manager's own fields
        stay as they were, so the disagreement is still visible in the record.
        The guard matters because the OneToOne is optional: a row flagged
        ``self_assessment`` with no submission behind it (deleted, or flagged by
        hand) falls back to the manager's numbers rather than blowing up. The
        ``pk`` check covers the subtler version of the same case — a deleted
        submission still sitting in the relation cache, eager to be believed.
        """
        if self.adopted_source == 'self_assessment':
            try:
                submission = self.self_assessment
            except SelfAssessment.DoesNotExist:
                submission = None
            if submission is not None and submission.pk is not None:
                return (
                    submission.likelihood_self,
                    submission.impact_self,
                    submission.control_effectiveness_self,
                )
        return self.likelihood, self.impact, self.control_effectiveness

    def _compute_scores(self):
        """Score the row and freeze the policy that produced the score.

        The total weight of the active parameters is a risk-exposure uplift on the
        base likelihood×impact score, capped at ``WEIGHT_MAX_UPLIFT`` so the 1–25
        scale (and the heat map built on it) keeps its meaning. An empty parameter
        set is a policy with uplift 0: the score is exactly L×I.

        ``weight_sum``/``uplift_applied``/``policy_digest`` are stored alongside so
        the score is reproducible: a row is only meaningful with the policy it was
        scored under, and ``is_stale`` is how a later parameter edit becomes
        visible instead of silently invalidating old numbers.
        """
        likelihood, impact, control_effectiveness = self._scoring_inputs()

        policy = active_policy()
        self.weight_sum = policy['weight_sum']
        self.uplift_applied = policy['uplift']
        self.policy_digest = policy['digest']

        base = float(likelihood * impact)
        if policy['weight_sum'] > 0:
            self.risk_score = round(min(25, base * (1 + policy['uplift'])), 2)
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
            float(self.risk_score) * (1 - (int(control_effectiveness) - 1) * 0.2),
            2,
        )

    @property
    def is_stale(self):
        """True when the row was scored under a different policy than the current one.

        Compared against the live digest on every read rather than stored, so a
        parameter edit is reflected immediately. Deliberately not special-casing a
        blank digest: a row with no frozen policy (pre-dating this column) is the
        most stale case of all, and reporting it as fresh would hide exactly the
        rows a recompute needs to reach.
        """
        return self.policy_digest != active_policy()['digest']

    def _resolve_target_universe(self):
        """The AuditUniverse this assessment's score belongs to, or None.

        An explicit link always wins. Otherwise the department is used *only* when
        it is unambiguous — exactly one active universe row. With zero or several
        the answer is None on purpose: this used to fall back to
        ``order_by('-risk_score').first()``, which picks the target by the very
        field it is about to assign. Two consequences, both observed: a second
        universe row for the department could never receive a score (the loop
        always re-picked the first), and an assessment scoring lower than an
        existing universe silently *lowered* that entity's risk score. Refusing to
        guess is the fix; the serializer rejects the ambiguous case up front.
        """
        from apps.audit_planning.models import AuditUniverse

        if self.audit_universe_id:
            return self.audit_universe
        if not self.department_id:
            return None

        # Two rows is all it takes to know the department is ambiguous; the slice
        # keeps this to one query and avoids counting thousands of rows.
        candidates = list(
            AuditUniverse.objects
            .filter(department_id=self.department_id, status='active')
            .order_by('code')[:2]
        )
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _propagate_to_universe(self):
        """Push the computed score onto the resolved AuditUniverse, if any.

        Only an approved assessment drives the entity's risk score. Approval is
        what makes the number official, so a draft that silently overwrote the
        universe would defeat the point of having a reviewer at all — the
        assessor could move an entity's score onto the risk register on their own
        by pressing save.
        """
        if self.status != self.APPROVED:
            return
        target = self._resolve_target_universe()
        if target is not None:
            target.risk_score = self.risk_score
            target.save(update_fields=['risk_score', 'updated_at'])

    def save(self, *args, **kwargs):
        self._compute_scores()
        super().save(*args, **kwargs)
        self._propagate_to_universe()

    def delete(self, *args, **kwargs):
        """Re-propagate the next latest assessment when this one is removed.

        The replacement is chosen by ``-year, -created_at`` — never by
        ``-risk_score``, the field being written here. Ordering by the assigned
        field would pick the row that already holds the highest score and hand its
        value straight back, so the universe's score would look unchanged while
        the assessment that justified it is gone.

        Which universe to update is resolved by exactly the same rule as
        ``_propagate_to_universe`` (explicit link, else an unambiguous single
        department row) — the two paths disagreeing is how a delete could re-write
        a universe the assessment was never attributed to.
        """
        universe = self._resolve_target_universe()
        dept_id = self.department_id
        super().delete(*args, **kwargs)

        if universe is None:
            return

        # This row is already gone, so no need to exclude it. Only approved rows
        # count: the replacement has to be one that would itself have propagated,
        # or deleting a draft would hand the universe a score nothing approved.
        latest = (
            RiskAssessment.objects
            .filter(audit_universe=universe, status=self.APPROVED)
            .order_by('-year', '-created_at')
            .first()
        )
        if latest is None and dept_id is not None:
            latest = (
                RiskAssessment.objects
                .filter(department_id=dept_id, status=self.APPROVED)
                .order_by('-year', '-created_at')
                .first()
            )
        universe.risk_score = latest.risk_score if latest else 0
        universe.save(update_fields=['risk_score', 'updated_at'])

    def __str__(self):
        return f"Risk: {self.department} - {self.year} {self.assessment_period}"

    class Meta:
        ordering = ['-risk_score']
        constraints = [
            # One assessment per auditable entity per period. The linked variant
            # is a plain composite key; rows with no entity are all distinct to
            # the database (NULLs never collide), so the unlinked case needs its
            # own partial index — see the second constraint.
            models.UniqueConstraint(
                fields=['department', 'year', 'assessment_period', 'audit_universe'],
                name='unique_assessment_per_entity_period',
            ),
            # At most one department-wide (unlinked) assessment per period. This
            # is what makes "the department's risk posture" a single row rather
            # than a set of competing ones.
            models.UniqueConstraint(
                fields=['department', 'year', 'assessment_period'],
                condition=Q(audit_universe__isnull=True),
                name='unique_assessment_per_dept_period',
            ),
        ]


def _score_snapshot(assessment):
    """The stored values a recompute can change, normalised for comparison.

    Floats and Decimals do not compare equal across a re-read in every corner
    case, and this snapshot is what decides whether a row counts as "updated" —
    so both sides are rendered to a fixed-precision string.
    """
    return (
        round(float(assessment.risk_score or 0), 2),
        assessment.risk_rating,
        round(float(assessment.residual_risk or 0), 2),
        round(float(assessment.weight_sum or 0), 2),
        round(float(assessment.uplift_applied or 0), 3),
        assessment.policy_digest,
    )


def recompute_assessments(queryset=None, dry_run=False):
    """Re-score assessments against the policy in force. Returns ``(updated, total)``.

    Idempotent by construction: "updated" counts rows whose stored values actually
    changed, not rows that were written, so a second run over an unchanged policy
    reports 0. With ``dry_run`` the new values are computed in memory and never
    saved, which is what the ``recompute_risk_scores`` command reports rather than
    writes.
    """
    queryset = RiskAssessment.objects.all() if queryset is None else queryset

    updated = 0
    total = 0
    for assessment in queryset:
        total += 1
        before = _score_snapshot(assessment)
        if dry_run:
            # Mutates this in-memory instance only; nothing is written back.
            assessment._compute_scores()
        else:
            # A full save: recompute, persist, and — for approved rows only —
            # propagate to the universe. An unapproved row is re-scored but its
            # entity keeps whatever an approved assessment last said.
            assessment.save()
        if _score_snapshot(assessment) != before:
            updated += 1

    return updated, total


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
    likelihood_self = models.IntegerField(choices=SCORE_CHOICES, validators=SCORE_VALIDATORS)
    impact_self = models.IntegerField(choices=SCORE_CHOICES, validators=SCORE_VALIDATORS)
    control_effectiveness_self = models.IntegerField(choices=SCORE_CHOICES, validators=SCORE_VALIDATORS)
    justification = models.TextField()
    mitigating_controls = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='self_assessments_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)