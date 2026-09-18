"""Split geographic scopes out of the single ``department`` foreign key.

Before the three-field picker, a record stored whichever org unit the user
drilled down to in ``department`` — so "Adama Region" or "Adama CSC No. 1"
could sit there instead of a chief office. This moves those values into the new
``region`` / ``service_center`` columns and re-points ``department`` at the
unit's chief office (Region Coordination, for every geographic unit), leaving
records that already pointed at an EXECUTIVE/CORPORATE/AUDIT unit untouched.

The transform is applied identically to all five models on purpose. Auditee
read-scoping compares ``department_id`` on both sides (see
audit_planning/views.py, findings/views.py, corrective_actions/views.py), so
rewriting only some of them would silently widen or narrow what an auditee can
read.

One consequence to be aware of: a record previously on "Adama Region" and one
on "Adama CSC No. 1" both become "Region Coordination" and will now match each
other under that scoping.
"""
from django.db import migrations

# The two unit types that are geographic rather than functional. A record
# pointing at one of these is the case this migration exists to fix.
GEOGRAPHIC_TYPES = ('REGION', 'SERVICE_CENTER')

# (app_label, model_name) for every model carrying the new columns.
SCOPED_MODELS = [
    ('accounts', 'User'),
    ('audit_planning', 'AuditUniverse'),
    ('audit_planning', 'AuditEngagement'),
    ('audit_planning', 'Project'),
    ('risk_assessment', 'RiskAssessment'),
]


def _split(unit, by_id):
    """Split a stored org unit into ``(region, service_center, chief_office)``.

    Walks ``parent`` upward from ``unit`` — the tree is three levels deep
    (chief office → region → service center) but the walk does not assume that,
    so a deeper chart keeps working.

    ``Department.parent`` is ``SET_NULL``, so a unit whose chain has been broken
    has nothing above it and comes back as *its own* chief office. Callers read
    that equality as "leave this row alone" rather than inventing a scope for
    it. A unit that genuinely is a region or a service center still reports
    itself in the matching column, which is what a record scoped to a whole
    region should end up holding.
    """
    path, seen, current = [], set(), unit
    while current is not None and current.pk not in seen:
        seen.add(current.pk)
        path.append(current)
        current = by_id.get(current.parent_id) if current.parent_id else None

    region = next((u for u in path if u.unit_type == 'REGION'), None)
    center = next((u for u in path if u.unit_type == 'SERVICE_CENTER'), None)
    # `path` runs leaf → root, so the reversed walk finds the highest non-CEO
    # unit first: the chief office the stored unit actually sits under.
    chief = next((u for u in reversed(path) if u.unit_type != 'EXECUTIVE'), None)
    return region, center, chief


def _backfill(apps, schema_editor):
    Department = apps.get_model('accounts', 'Department')

    # The whole tree is ~600 rows; one query beats a walk per record.
    by_id = {d.pk: d for d in Department.objects.all()}

    for app_label, model_name in SCOPED_MODELS:
        Model = apps.get_model(app_label, model_name)
        updates = []
        for obj in Model.objects.select_related('department').exclude(department=None):
            unit = obj.department
            if unit.unit_type not in GEOGRAPHIC_TYPES:
                continue
            region, center, chief = _split(unit, by_id)
            if chief is None or chief.pk == unit.pk:
                # Broken chain, or the unit is its own chief office — nothing
                # trustworthy to re-point at, so leave the row as it was.
                continue
            obj.region_id = region.pk if region else None
            obj.service_center_id = center.pk if center else None
            obj.department_id = chief.pk
            updates.append(obj)

        if updates:
            Model.objects.bulk_update(
                updates, ['region', 'service_center', 'department'], batch_size=500,
            )


def _unbackfill(apps, schema_editor):
    """Drop the split scope, leaving ``department`` as the backfill left it.

    The original single value is not recoverable — a record that held a service
    center now holds its chief office, and this only clears the two columns it
    was copied into.
    """
    for app_label, model_name in SCOPED_MODELS:
        Model = apps.get_model(app_label, model_name)
        Model.objects.update(region=None, service_center=None)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_user_region_user_service_center'),
        ('audit_planning', '0004_auditengagement_region_and_more'),
        # Anchored here because risk_assessment sorts after the other two apps;
        # the explicit dependencies above are what actually order the graph.
        ('risk_assessment', '0004_riskassessment_region_riskassessment_service_center'),
    ]

    operations = [
        migrations.RunPython(_backfill, _unbackfill),
    ]
