"""The one canonical risk-parameter set.

``RISK_PARAMETERS`` is the single source of truth for the risk-scoring policy a
seeded database ends up with. It used to be duplicated: ``seed_data`` defined five
parameters and ``seed_eeu_audit_structure`` defined seven (the same five plus
*Technical Asset Criticality* and *Energy Loss Exposure*). Because the weights act
as an uplift on every score, seeding one way produced +20% and the other +27% —
the identical likelihood×impact pair scored differently depending on which
command happened to have been run. Both commands now import this list, so every
seeding path converges on the same policy and the same digest.

Names, descriptions, weights and categories are preserved verbatim from the
7-parameter version, which is the superset.
"""

RISK_PARAMETERS = [
    {
        'name': 'Financial Impact',
        'description': 'Potential direct or indirect monetary loss to EEU',
        'weight': 0.3,
        'category': 'financial',
    },
    {
        'name': 'Operational Disruption',
        'description': 'Degree of interruption to power supply or utility services',
        'weight': 0.25,
        'category': 'operational',
    },
    {
        'name': 'Compliance Violations',
        'description': 'Exposure to regulatory penalties or audits exceptions',
        'weight': 0.2,
        'category': 'compliance',
    },
    {
        'name': 'Process Complexity',
        'description': 'Internal controls complexity and number of actors',
        'weight': 0.15,
        'category': 'operational',
    },
    {
        'name': 'System Automation',
        'description': 'Lack of automated reconciliation or reliance on manual work',
        'weight': 0.1,
        'category': 'it',
    },
    {
        'name': 'Technical Asset Criticality',
        'description': 'Criticality of substations, feeders, and transmission assets',
        'weight': 0.2,
        'category': 'operational',
    },
    {
        'name': 'Energy Loss Exposure',
        'description': 'Exposure to technical and commercial energy losses',
        'weight': 0.15,
        'category': 'operational',
    },
]


def ensure_risk_parameters(created_by=None):
    """Idempotently create the canonical parameter set. Returns the count created.

    ``get_or_create`` on the name alone, deliberately: re-running a seed command
    must not overwrite a weight an administrator has since tuned on purpose — that
    edit is the thing the recompute machinery exists to respect.
    """
    from .models import RiskParameter

    created = 0
    for entry in RISK_PARAMETERS:
        _, was_created = RiskParameter.objects.get_or_create(
            name=entry['name'],
            defaults={
                'description': entry['description'],
                'weight': entry['weight'],
                'category': entry['category'],
                'created_by': created_by,
            },
        )
        created += int(was_created)
    return created
