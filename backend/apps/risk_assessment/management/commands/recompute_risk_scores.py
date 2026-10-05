"""Re-score every risk assessment against the parameter policy in force.

Run this after a parameter change that did not go through the API — a fixture, a
``RiskParameter`` edited in the Django admin, or a direct database update. Those
paths cannot trigger the inline recompute the ``/api/risk/parameters/`` endpoints
do, so the stored scores keep reflecting the old policy until something rewrites
them. The API equivalent is ``POST /api/risk/assessments/recompute/``.

This never changes the parameters themselves; it only re-reads them and re-scores
the rows. So it is safe to run at any time and idempotent — a second run reports
``updated 0`` because nothing has changed in between.

    manage.py recompute_risk_scores              # apply
    manage.py recompute_risk_scores --dry-run    # report what would change
"""
from django.core.management.base import BaseCommand

from apps.risk_assessment.models import active_policy, recompute_assessments


class Command(BaseCommand):
    help = 'Recompute all risk assessment scores against the active risk parameters.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        updated, scanned = recompute_assessments(dry_run=dry_run)

        if dry_run:
            policy = active_policy()
            self.stdout.write(self.style.WARNING(
                f'Dry run — nothing written. Policy {policy["digest"]} '
                f'(weight_sum {policy["weight_sum"]}, uplift {policy["uplift"]}).'
            ))
        self.stdout.write(f'scanned {scanned}, updated {updated}')
