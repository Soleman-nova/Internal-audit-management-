"""Seed the detailed EEU head-office (HQ) organizational units.

``seed_org_structure`` seeded the coarse corporate tree — the CEO office and the
13 chief offices plus the 32 regions under Region Coordination — and
``seed_service_centers`` added the customer service centres beneath the regions.
This command adds the *detailed head-office units* (CO Treasury, CO Budget
Control, procurement/warehouse/fleet teams, SCADA/DMS operations, etc.) from the
authoritative corporate org export so an audit universe entry, engagement, or
risk assessment can target a specific head-office unit, not just a whole chief
office.

The export rows come from ``data/org_units.json`` beside this module and form a
self-referencing hierarchy keyed by the source system's ERP unit id, with a
``parent_id`` pointing at another row's ERP id. The parallel ``data/org_units_am.json``
carries the same 154 rows with Amharic names, which are written to ``name_am`` so
the interface can render the head-office units in either language. Each row either

* **merges** onto a Department that ``seed_org_structure`` /
  ``seed_eeu_audit_structure`` already created (the export's CEO Office, chief
  offices, and Internal Audit directorates all overlap the coarse tree), or
* is **skipped** because the audit system already models the unit a better way
  (the export's region-coordination and regional-audit rows), or
* is **created** as a new ``CORPORATE`` department with code ``HO-<erp id>`` and
  wired under the resolved parent (an existing merged node or another created
  node). Orphan rows whose export parent was ``NO_PARNT`` default to the CEO
  root unless ``ORPHAN_PARENT`` re-homes them onto the office that owns them.

Idempotent — re-running creates nothing (pass ``--update-existing`` to overwrite
names and parents on already-created rows). Run ``seed_org_structure`` and
``seed_eeu_audit_structure`` first; the merged rows must already exist.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Department


DEFAULT_DATA_FILE = Path(__file__).resolve().parent / 'data' / 'org_units.json'

# The same units with Amharic names, keyed by the same ERP ids. Optional: when
# absent, units are created with English names only and the interface falls back
# to them in either language.
DEFAULT_AM_FILE = Path(__file__).resolve().parent / 'data' / 'org_units_am.json'

# New head-office departments are keyed on the source ERP id, prefixed the same
# way regions (RGN-) and service centres (CSC-) are, so codes stay unique in the
# shared Department table and read as head-office units at a glance.
CODE_PREFIX = 'HO-'

# Export ERP id -> Department code of the unit it is the same real-world office
# as. These rows are never created; children that reference them are parented to
# the existing unit, so the import enriches the coarse tree instead of
# duplicating it. The Internal Audit directorates (TA/FPA/ITA/PP) merge onto the
# AUDIT directorates created by seed_eeu_audit_structure.
MERGE_MAP = {
    '10000027': 'CEO',            # CEO Office          -> executive root
    '10000026': 'Audit',          # CO Internal Audit   -> Internal Audit chief office
    '10000028': 'TA',             # CO Technical Audit
    '10000029': 'FPA',            # CO Financial and Performance A
    '10000030': 'ITA',            # CO IT Audit
    '10003843': 'PP',             # CO Planning & performance Monitoring
    '10000034': 'Communication',  # CO Communication
    '10000036': 'SPlanning',      # CO Strategic and Investment Executive
    '10000037': 'HR',             # CO Human Resource Management
    '10000038': 'SCM&PGS',        # CO Supply Chain&Property & Gen service
    '10000039': 'Finance',        # CO Finance & Control
    '10000043': 'P&Qmgt',         # CO Process and Quality Management
    '10000046': 'IT',             # CO Information Technology
    '10003304': 'NIM',            # Co Network Infrastructure Management
    '10003313': 'Marketing',      # CO Marketing Sales & Customer Service
    '10003346': 'Legal&Ethics',   # CO Legal Service and Ethics
    # EEU National Operation Coordination Office — the export's umbrella for
    # region coordination and network operations, which the seeded tree already
    # collapses into Region Coordination (the 32 regions hang off it). Its SCADA
    # children are created beneath the same node.
    '10003356': 'RGN Coordination',
}

# Export rows intentionally left out, each with the reason.
SKIP_CODES = {
    # Region-coordination heads for Addis Ababa / Oromia. The seeded tree already
    # models all 32 operating regions under Region Coordination; importing these
    # would add empty coordination stubs beside them. Both are leaf rows.
    '10000048': 'Addis Ababa Region Coordination already covered by the seeded regions',
    '10000049': 'Oromia Region Coordination already covered by the seeded regions',
    # CO Regional Audit Coordination. The audit side of this system is modelled
    # authoritatively as IAEO + the four directorates; a fifth, unwired audit
    # unit would only add noise. Leaf row.
    '10003693': 'audit structure already modelled (IAEO + FPA/TA/ITA/PP)',
}

# Export rows the source left with a NO_PARNT parent, re-homed onto the office
# that actually owns them. Anything else with a null/NO_PARNT parent defaults to
# the CEO root.
ORPHAN_PARENT = {
    '10000107': 'Finance',     # CO General Account
    '10000108': 'Finance',     # CO Budget Control
    '10000109': 'Finance',     # CO Material and Fixed Asset Control
    '10003317': 'Marketing',   # CO Market Research&Business Development
    '10003692': 'SCM&PGS',     # CO Country Supply Chain&PGS Coordination
    # SCADA/DMS Operation — network operations, kept alongside its sibling
    # SCADA/DMS & Communication Operation subtree under Region Coordination.
    '10003819': 'RGN Coordination',
}


class Command(BaseCommand):
    help = (
        'Seeds the detailed EEU head-office organizational units under the '
        'coarse corporate tree. Requires seed_org_structure (and '
        'seed_eeu_audit_structure for the audit overlaps) to have run first.'
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
                'JSON export with the Amharic names for the same units '
                f'(default: {DEFAULT_AM_FILE.name} beside this command).'
            ),
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Overwrite names and parents on head-office units that already exist.',
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
        self.stdout.write(
            f'Seeding head-office units from {data_file.name} ({len(rows)} rows)...'
        )
        amharic_names = self.load_amharic_names(Path(options['amharic_file']))
        if amharic_names:
            self.stdout.write(
                f'  applying {len(amharic_names)} Amharic names from '
                f'{Path(options["amharic_file"]).name}'
            )
        by_code = {str(row.get('orgunit', '')).strip(): row for row in rows}

        # ── Resolve the merged (existing) units the import hangs off ──────────
        # Only anchors the data actually references are required: the rows that
        # merge onto them, the parents those rows point at, and the CEO root that
        # orphan rows default to. This lets a partial export (or a test fixture)
        # import the slice of the tree it covers.
        needed_anchors = {'CEO'}
        for erp in by_code:
            if erp in MERGE_MAP:
                needed_anchors.add(MERGE_MAP[erp])
        for row in rows:
            erp = str(row.get('orgunit', '')).strip()
            if erp in SKIP_CODES:
                continue  # skipped rows are ignored, so neither they nor their parents matter
            parent_id = row.get('parent_id')
            if parent_id is None or str(parent_id).strip().upper() == 'NO_PARNT':
                needed_anchors.add(ORPHAN_PARENT.get(erp, 'CEO'))
            elif str(parent_id).strip() in MERGE_MAP:
                needed_anchors.add(MERGE_MAP[str(parent_id).strip()])

        anchor_depts = {
            db_code: Department.objects.filter(code=db_code).first()
            for db_code in needed_anchors
        }
        missing = [code for code, dept in anchor_depts.items() if dept is None]
        if missing:
            raise CommandError(
                'Existing units not found for merged export rows: '
                + ', '.join(sorted(missing))
                + '. Run "manage.py seed_org_structure" (and '
                '"manage.py seed_eeu_audit_structure") first.'
            )

        # ── Report which export rows merge / are skipped ──────────────────────
        for erp in sorted(erp for erp in MERGE_MAP if erp in by_code):
            row = by_code[erp]
            self.stdout.write(
                f'  = {erp} "{row.get("orgunit_name", "")}" merges into existing '
                f'{MERGE_MAP[erp]}'
            )
        for erp in sorted(SKIP_CODES):
            row = by_code.get(erp)
            if row is None:
                continue
            self.stdout.write(
                self.style.WARNING(
                    f'  - {erp} "{row.get("orgunit_name", "")}": {SKIP_CODES[erp]}'
                )
            )

        created_count = 0
        updated_count = 0
        unchanged_count = 0
        merged_erp = {erp for erp in MERGE_MAP if erp in by_code}
        created_map = {}
        problems = []
        resolving = set()
        seen_sibling_names = {}  # parent code -> set of created unit names

        def parent_for(row):
            """Resolve an export row's parent to an existing/created Department."""
            erp = str(row['orgunit']).strip()
            parent_id = row.get('parent_id')
            if parent_id is None or str(parent_id).strip().upper() == 'NO_PARNT':
                # Orphan: re-home onto ORPHAN_PARENT's office, else the CEO root.
                home = ORPHAN_PARENT.get(erp, 'CEO')
                return anchor_depts[home]
            parent_id = str(parent_id).strip()
            if parent_id in MERGE_MAP:
                return anchor_depts[MERGE_MAP[parent_id]]
            if parent_id in by_code:
                return ensure(parent_id)
            # A parent id that is neither merged nor in the export: surface it,
            # do not silently drop the row.
            problems.append(f'{erp}: parent "{parent_id}" not found — attaching to CEO')
            return anchor_depts['CEO']

        def ensure(erp):
            """Return the Department for an export ERP id, creating it if needed."""
            nonlocal created_count, updated_count, unchanged_count
            erp = str(erp).strip()
            if erp in merged_erp:
                return anchor_depts[MERGE_MAP[erp]]
            if erp in created_map:
                return created_map[erp]
            if erp in SKIP_CODES:
                return None
            if erp in resolving:
                raise CommandError(f'Cycle in export hierarchy at {erp}.')
            row = by_code.get(erp)
            if row is None:
                return None

            resolving.add(erp)
            try:
                parent = parent_for(row)
                if parent is None:
                    return None
                name = str(row.get('orgunit_name', '')).strip()
                if not name:
                    problems.append(f'{erp}: blank orgunit_name — skipped')
                    return None

                code = f'{CODE_PREFIX}{erp}'
                defaults = {
                    'name': name,
                    'name_am': amharic_names.get(erp, ''),
                    'unit_type': Department.CORPORATE,
                    'directorate_type': 'OTHER',
                    'parent': parent,
                    'description': f'EEU head-office unit (export code {erp}).',
                }
                dept, created = Department.objects.get_or_create(
                    code=code, defaults=defaults
                )
                if created:
                    created_count += 1
                    self.stdout.write(
                        f'  + {dept.code}: {dept.name} -> {parent.code}'
                    )
                elif update_existing:
                    for field, value in defaults.items():
                        setattr(dept, field, value)
                    dept.save()
                    updated_count += 1
                    self.stdout.write(
                        f'  ~ {dept.code}: {dept.name} updated'
                    )
                else:
                    unchanged_count += 1

                # Warn on the export's own near-duplicate sibling names (e.g. a
                # parent and child both "Radio Communication") — not an error.
                parent_key = parent.code or ''
                seen = seen_sibling_names.setdefault(parent_key, set())
                if name in seen:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ! duplicate sibling name "{name}" under {parent_key}'
                        )
                    )
                seen.add(name)

                created_map[erp] = dept
                return dept
            finally:
                resolving.discard(erp)

        # Create in file order; parent_for() recurses so a parent is created
        # before the child that references it.
        for row in rows:
            erp = str(row.get('orgunit', '')).strip()
            if erp in by_code and erp not in SKIP_CODES and erp not in merged_erp:
                ensure(erp)

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
                self.style.SUCCESS(
                    f'Seeded {created_count + updated_count} head-office unit(s).'
                )
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
            raise CommandError(f'{data_file} must contain a JSON list of org units.')
        return rows

    def load_amharic_names(self, am_file):
        """ERP id -> Amharic name, from the parallel Amharic export.

        The file is optional: the built-in default may be absent (a bare checkout
        without it) and the import then proceeds with English names only. An
        explicitly passed path that does not exist is a mistake, so it errors.
        """
        if not am_file.exists():
            if str(am_file) != str(DEFAULT_AM_FILE):
                raise CommandError(f'Amharic data file not found: {am_file}')
            self.stdout.write(
                self.style.WARNING(
                    '  Amharic names file not found — importing English names only.'
                )
            )
            return {}
        rows = self.load_rows(am_file)
        return {
            str(row.get('orgunit', '')).strip(): str(row.get('orgunit_name', '')).strip()
            for row in rows
            if str(row.get('orgunit_name', '')).strip()
        }
