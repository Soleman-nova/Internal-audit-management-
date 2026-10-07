"""Freeze the scoring policy on each assessment, and stop duplicate rows.

The weighted ``RiskParameter`` set is a *policy*: with parameters installed the
5×5 matrix uplifts every score, and 9 of the 25 cells land in a different rating
band than they do without them. So a stored score is meaningless without the
parameter set that produced it. This adds the three columns that record it
(``weight_sum``, ``uplift_applied``, ``policy_digest``) plus the two that record
whose numbers were scored (``adopted_source``, ``adoption_note``), and drops
``inherent_risk`` — a field that was never computed and never read, and which
made the API advertise an inherent/residual distinction the system does not have
(``risk_score`` is the inherent score, ``residual_risk`` the post-control one).

The two unique constraints make "the department's assessment for this period"
a single row:

* ``unique_assessment_per_entity_period`` — one assessment per auditable entity
  per period. Rows with no ``audit_universe`` are all distinct to the database
  (NULLs never collide in a unique index), which is exactly why the second
  constraint exists.
* ``unique_assessment_per_dept_period`` — the partial index that covers the
  unlinked case, where the assessment is about the department as a whole.

These constraints will FAIL on a database that already holds duplicates. The dev
database had 0 duplicate rows at the time this was written, so it applies
cleanly there; on any database that does not, resolve the duplicates first —
group by (department, year, assessment_period, audit_universe), keep the row you
want, and delete or re-point the rest — then re-run ``migrate``.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_user_region_user_service_center'),
        ('audit_planning', '0004_auditengagement_region_and_more'),
        ('risk_assessment', '0005_backfill_region_service_center'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='riskassessment',
            name='inherent_risk',
        ),
        migrations.AddField(
            model_name='riskassessment',
            name='adopted_source',
            field=models.CharField(choices=[('manager', 'Manager assessment'), ('self_assessment', 'Auditee self-assessment')], default='manager', max_length=20),
        ),
        migrations.AddField(
            model_name='riskassessment',
            name='adoption_note',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='riskassessment',
            name='policy_digest',
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AddField(
            model_name='riskassessment',
            name='uplift_applied',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=4),
        ),
        migrations.AddField(
            model_name='riskassessment',
            name='weight_sum',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=6),
        ),
        migrations.AddConstraint(
            model_name='riskassessment',
            constraint=models.UniqueConstraint(fields=('department', 'year', 'assessment_period', 'audit_universe'), name='unique_assessment_per_entity_period'),
        ),
        migrations.AddConstraint(
            model_name='riskassessment',
            constraint=models.UniqueConstraint(condition=models.Q(('audit_universe__isnull', True)), fields=('department', 'year', 'assessment_period'), name='unique_assessment_per_dept_period'),
        ),
    ]
