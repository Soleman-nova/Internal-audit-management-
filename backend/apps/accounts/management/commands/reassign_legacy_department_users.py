"""Reassign users stranded in the retired demo departments.

``retire_legacy_departments`` deactivated FIN, PROC, and DIST but deliberately
left their users in place, since where each person belongs is a business
decision rather than something derivable from the data. This command applies
the agreed mapping:

    FIN  → FPA      audit staff move to the Financial & Performance Audit
                    Directorate, not the corporate Finance chief office. Placing
                    auditors inside the department they audit would compromise
                    independence.
    PROC → SCM&PGS  Supply Chain Management and PGS is the functional
                    counterpart to Procurement and Logistics.
    DIST → NIM      Network Infrastructure Management covers the power
                    distribution network.

SCM&PGS and NIM are used because the official EEU structure has no Procurement
or Distribution unit; no new units are invented here.

Idempotent — users already in the target department are left alone. Run with
``--dry-run`` first to preview.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Department, User


# Retired source code → target code in the official structure.
REASSIGNMENTS = [
    ('FIN', 'FPA', 'audit staff belong in the audit directorate, not the audited unit'),
    ('PROC', 'SCM&PGS', 'Supply Chain Management and PGS covers procurement and logistics'),
    ('DIST', 'NIM', 'Network Infrastructure Management covers power distribution'),
]


class Command(BaseCommand):
    help = (
        'Reassigns users from the retired demo departments (FIN, PROC, DIST) to their '
        'counterparts in the official EEU structure (FPA, SCM&PGS, NIM).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without writing anything.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved.'))
        self.stdout.write('Reassigning users out of retired departments...')

        moved = 0
        skipped = 0
        problems = []

        for source_code, target_code, rationale in REASSIGNMENTS:
            source = Department.objects.filter(code=source_code).first()
            target = Department.objects.filter(code=target_code).first()

            if source is None:
                problems.append(f'source department {source_code} not found')
                continue
            if target is None:
                problems.append(f'target department {target_code} not found — {source_code} users left in place')
                continue
            if not target.is_active:
                problems.append(f'target {target_code} is retired — {source_code} users left in place')
                continue

            users = list(User.objects.filter(department=source).order_by('employee_id'))
            if not users:
                continue

            self.stdout.write('')
            self.stdout.write(f'  {source_code} → {target_code} ({target.name})')
            self.stdout.write(f'    reason: {rationale}')
            for user in users:
                self.stdout.write(
                    f'    - {user.employee_id} {user.get_full_name()} [{user.role}]'
                )
                if not dry_run:
                    user.department = target
                    user.save(update_fields=['department'])
                moved += 1

        # Anyone left pointing at a retired department that this mapping missed.
        stranded = User.objects.filter(department__is_active=False).exclude(department=None)
        if not dry_run:
            stranded = stranded.select_related('department')
            for user in stranded:
                problems.append(
                    f'{user.employee_id} still in retired {user.department.code}'
                )

        self.stdout.write('')
        self.stdout.write(f'  {"would move" if dry_run else "moved"}: {moved} user(s)')
        if skipped:
            self.stdout.write(f'  unchanged: {skipped}')
        for problem in problems:
            self.stdout.write(self.style.WARNING(f'  ! {problem}'))

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING('DRY RUN — rolled back.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Reassigned {moved} user(s).'))
