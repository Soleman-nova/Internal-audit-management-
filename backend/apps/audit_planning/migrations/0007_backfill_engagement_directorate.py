"""Backfill ``AuditEngagement.directorate`` from each engagement's plan.

``directorate`` is derived in ``AuditEngagement.save()`` — the plan is the single
source of truth for which audit directorate owns an engagement — but the field
predates that rule and nothing had ever written it. Every dashboard number
scoped with ``?directorate=<id>`` filters through this column, so on a database
seeded before the rule existed the four directorate scopes all resolved to zero
engagements while the unscoped view looked healthy.

Rows whose plan carries no directorate are left alone rather than guessed at:
the derivation has nothing to inherit from, and inventing a value here would put
a different answer in the column than ``save()`` would produce on the next edit.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    AuditPlan = apps.get_model('audit_planning', 'AuditPlan')
    AuditEngagement = apps.get_model('audit_planning', 'AuditEngagement')

    # One UPDATE per plan rather than one per engagement, and not a single
    # joined UPDATE: Django refuses an F() that traverses a relation in an
    # assignment ("Joined field references are not permitted in this query").
    # Walking the plans sidesteps that and keeps the statement count tied to
    # the number of directorate-owned plans, which is small.
    #
    # `update()` also bypasses AuditEngagement.save(), which is what we want:
    # the derivation would compute exactly this value, and routing the backfill
    # through it would re-open a transaction per row for no gain.
    plans = AuditPlan.objects.filter(
        directorate__isnull=False,
    ).values_list('id', 'directorate_id')
    for plan_id, directorate_id in plans:
        AuditEngagement.objects.filter(plan_id=plan_id).update(
            directorate_id=directorate_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('audit_planning', '0006_auditengagement_auditee'),
    ]

    operations = [
        # No reverse. The column was uniformly NULL on every database this could
        # reach, so "restore what was there" and "clear it" are the same thing —
        # but a noop is honest about it, where clearing would also wipe any
        # directorate written after this migration ran.
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
