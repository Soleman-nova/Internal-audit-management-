"""Retire the legacy demo departments that predate the official EEU structure.

``seed_data`` created five ad-hoc departments (FIN, IT, HR, PROC, DIST) before the
official structure existed. ``seed_org_structure`` adopted IT and HR into the
CEO-rooted hierarchy because their codes matched real chief offices; FIN, PROC,
and DIST have no counterpart and were left as stray top-level nodes.

This command retires them by clearing ``is_active`` — it deliberately does NOT
delete them. Deleting would CASCADE away the RiskAssessment rows that reference
them and SET_NULL the department on their AuditUniverse entries and
AuditEngagements, destroying audit history. Retiring keeps every record intact
and resolvable while dropping the units out of the pickers used to create new
work. Pass ``--reactivate`` to reverse.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Department


# Demo-seed codes with no counterpart in the official EEU structure.
LEGACY_CODES = ['FIN', 'PROC', 'DIST']


class Command(BaseCommand):
    help = (
        'Retires the legacy demo departments (FIN, PROC, DIST) by deactivating them, '
        'preserving all attached audit records.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reactivate',
            action='store_true',
            help='Reverse the retirement — mark the legacy departments active again.',
        )
        parser.add_argument(
            '--codes',
            nargs='+',
            default=LEGACY_CODES,
            metavar='CODE',
            help=f'Department codes to act on (default: {" ".join(LEGACY_CODES)}).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reactivate = options['reactivate']
        codes = options['codes']
        target_active = reactivate
        verb = 'Reactivating' if reactivate else 'Retiring'

        self.stdout.write(f'{verb} legacy departments: {", ".join(codes)}')

        changed = 0
        already = 0
        missing = []

        for code in codes:
            dept = Department.objects.filter(code=code).first()
            if dept is None:
                missing.append(code)
                continue

            # Report the history that stays attached, so retiring is never silent.
            # Walked dynamically so the report can't drift as relations are added;
            # 'children' is a Department->Department link, reported separately.
            counts = {}
            for rel in Department._meta.related_objects:
                accessor = rel.get_accessor_name()
                if accessor == 'children':
                    continue
                n = getattr(dept, accessor).count()
                if n:
                    counts[f'{rel.related_model.__name__}.{rel.field.name}'] = n
            attached = ', '.join(f'{n} x {label}' for label, n in sorted(counts.items()))
            child_count = dept.children.count()

            if dept.is_active == target_active:
                already += 1
                state = 'active' if target_active else 'retired'
                self.stdout.write(f'  = {code}: already {state}')
                continue

            dept.is_active = target_active
            dept.save(update_fields=['is_active'])
            changed += 1
            marker = '+' if reactivate else '-'
            self.stdout.write(f'  {marker} {code}: {dept.name}')
            if attached:
                self.stdout.write(f'      retained: {attached}')
            if child_count:
                self.stdout.write(
                    self.style.WARNING(
                        f'      note: {child_count} child unit(s) still report to this one'
                    )
                )

        self.stdout.write('')
        self.stdout.write(f'  changed: {changed}')
        if already:
            self.stdout.write(f'  unchanged: {already}')
        if missing:
            self.stdout.write(f'  not found: {", ".join(missing)}')

        if not reactivate and changed:
            self.stdout.write(
                '  Retired units keep all history and stay reachable by ID; they no '
                'longer appear in the default department list. Re-running seed_data '
                'will recreate them as active.'
            )

        self.stdout.write(self.style.SUCCESS(f'{verb.rstrip("ing")}ed {changed} department(s).'))
