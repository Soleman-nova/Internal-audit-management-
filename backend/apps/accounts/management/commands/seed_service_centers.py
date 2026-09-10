"""Seed the EEU customer service centers beneath their regions.

``seed_org_structure`` created the 32 regions under Region Coordination. This
command adds the third and deepest corporate tier — the 582 customer service
centers — so the forms can drill department → region → service center and store
the result in the ``department`` foreign keys that already exist.

The source data lives in ``data/service_centers.json`` beside this module rather
than in Python literals: 582 rows are too many to inline, and reading the names
from a UTF-8 file is what keeps the Amharic ones intact. Amharic names for the
centers come from the parallel ``data/service_centers_am.json`` (``--amharic-file``
to override), which names all 582 centers; the lookup stays subset-tolerant, so a
partial export leaves the centers it does not cover to the mirrored-from-source
behaviour.

Idempotent — re-running creates nothing. Pass ``--update-existing`` to overwrite
names and parents on rows that are already there, and ``--dry-run`` to preview.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Department
from .seed_org_structure import REGION_CODE_PREFIX


DEFAULT_DATA_FILE = Path(__file__).resolve().parent / 'data' / 'service_centers.json'

# Amharic names for the same centers, keyed by the same csc_code. Optional: the
# committed export covers all 582 centers, but an absent entry still leaves
# name_am as it was (mirrored from the source name when that is Amharic), so a
# partial override passed via --amharic-file is fine.
DEFAULT_AM_FILE = Path(__file__).resolve().parent / 'data' / 'service_centers_am.json'

# Service-center codes are two-letter region + serial ('BA07'). Prefixed for the
# same reason regions are: a bare code is a poor unique key in a table shared
# with chief offices and audit directorates.
CSC_CODE_PREFIX = 'CSC-'

# Ethiopic (Amharic) code block — used to tell an Amharic name from a Latin one.
ETHIOPIC_RANGE = range(0x1200, 0x1380)


def is_amharic(text):
    """True if the text contains any Ethiopic character."""
    return any(ord(char) in ETHIOPIC_RANGE for char in text)


def repair_mojibake(text):
    """Recover Amharic text that came through a Latin-1 round trip.

    The upstream export that produced this data emits some rows as UTF-8 bytes
    decoded as Latin-1 — 'ሠመራ' arrives as 'á\\x88\\xa0á\\x88\\x98á\\x88«'.
    Re-encoding to Latin-1 and decoding as UTF-8 reverses it.

    The committed data file has already been repaired, so this only matters for
    a fresh export passed via --data-file. The result is accepted only when it
    actually yields Ethiopic characters, so correct text and genuine Latin-1
    names ('café') are returned untouched.
    """
    try:
        repaired = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if is_amharic(repaired) else text


class Command(BaseCommand):
    help = (
        'Seeds the EEU customer service centers as departments parented to their '
        'region. Requires seed_org_structure to have run first.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--data-file',
            default=str(DEFAULT_DATA_FILE),
            metavar='PATH',
            help=f'JSON export to read (default: {DEFAULT_DATA_FILE.name} beside this command).',
        )
        parser.add_argument(
            '--amharic-file',
            default=str(DEFAULT_AM_FILE),
            metavar='PATH',
            help=(
                'JSON export with Amharic names for the same centers, keyed by '
                f'csc_code (default: {DEFAULT_AM_FILE.name} beside this command).'
            ),
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Overwrite names and parents on service centers that already exist.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without writing anything.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        data_file = Path(options['data_file'])
        update_existing = options['update_existing']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved.'))

        rows = self.load_rows(data_file)
        amharic_names = self.load_amharic_names(Path(options['amharic_file']))
        if amharic_names:
            self.stdout.write(
                f'  applying {len(amharic_names)} Amharic names from '
                f'{Path(options["amharic_file"]).name}'
            )
        regions = self.load_regions()
        if not regions:
            raise CommandError(
                'No regions found. Run "manage.py seed_org_structure" first — service '
                'centers are parented to their region.'
            )

        self.stdout.write(f'Seeding {len(rows)} customer service centers from {data_file.name}...')

        created_count = 0
        updated_count = 0
        unchanged_count = 0
        problems = []

        for row in rows:
            csc_code = str(row.get('csc_code', '')).strip()
            if not csc_code:
                problems.append(f'row id={row.get("id")} has no csc_code — skipped')
                continue

            # Key the parent off the `region` field, never the code prefix: the
            # Gode District rows (HB01-HB13) belong to the Somale region (HA).
            region_code = str(row.get('region', '')).strip()
            region = regions.get(region_code)
            if region is None:
                problems.append(
                    f'{csc_code}: region "{region_code}" not found '
                    f'({REGION_CODE_PREFIX}{region_code}) — skipped'
                )
                continue

            name = repair_mojibake(str(row.get('csc_name', ''))).strip()
            if not name:
                problems.append(f'{csc_code}: blank name — skipped')
                continue

            defaults = {
                'name': name,
                # Prefer the parallel Amharic export; otherwise some centers are
                # recorded only in Amharic, so the one name serves both languages.
                'name_am': amharic_names.get(csc_code) or (name if is_amharic(name) else ''),
                'unit_type': Department.SERVICE_CENTER,
                'directorate_type': 'OTHER',
                'parent': region,
                'description': (
                    f'EEU customer service center {csc_code} in {region.name}.'
                ),
            }

            code = f'{CSC_CODE_PREFIX}{csc_code}'
            dept, created = Department.objects.get_or_create(code=code, defaults=defaults)
            if created:
                created_count += 1
            elif update_existing:
                for field, value in defaults.items():
                    setattr(dept, field, value)
                dept.save()
                updated_count += 1
            else:
                unchanged_count += 1

        self.stdout.write('')
        self.stdout.write(f'  {"would create" if dry_run else "created"}: {created_count}')
        if update_existing:
            self.stdout.write(f'  {"would update" if dry_run else "updated"}: {updated_count}')
        if unchanged_count:
            self.stdout.write(
                f'  unchanged: {unchanged_count} (re-run with --update-existing to overwrite)'
            )
        for problem in problems:
            self.stdout.write(self.style.WARNING(f'  ! {problem}'))

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING('DRY RUN — rolled back.'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Seeded {created_count + updated_count} service center(s).')
            )

    def load_rows(self, data_file):
        """Read and validate the JSON export."""
        if not data_file.exists():
            raise CommandError(f'Data file not found: {data_file}')
        try:
            with data_file.open(encoding='utf-8') as handle:
                rows = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f'Could not read {data_file}: {exc}')
        if not isinstance(rows, list):
            raise CommandError(f'{data_file} must contain a JSON list of service centers.')
        return rows

    def load_amharic_names(self, am_file):
        """csc_code -> Amharic name, from the parallel Amharic export.

        Optional: a checkout without the default file proceeds with the source
        names only, while an explicitly passed path that does not exist errors.
        The lookup is subset-tolerant, so codes a partial file does not cover are
        simply absent.
        """
        if not am_file.exists():
            if str(am_file) != str(DEFAULT_AM_FILE):
                raise CommandError(f'Amharic data file not found: {am_file}')
            return {}
        return {
            str(row.get('csc_code', '')).strip(): repair_mojibake(
                str(row.get('csc_name', ''))
            ).strip()
            for row in self.load_rows(am_file)
            if str(row.get('csc_name', '')).strip()
        }

    def load_regions(self):
        """Region code ('HA') → Department, for parenting each service center."""
        return {
            dept.code[len(REGION_CODE_PREFIX):]: dept
            for dept in Department.objects.filter(
                unit_type=Department.REGION,
                code__startswith=REGION_CODE_PREFIX,
            )
        }
