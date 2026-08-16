"""Seed the EEU corporate organizational structure.

Creates the full hierarchy in one idempotent pass:

    Chief Executive Officer (CEO)
    ├── Internal Audit (Audit)
    ├── Legal Service and Ethics (Legal&Ethics)
    ├── Strategic Planning and Investment (SPlanning)
    ├── Communication (Communication)
    ├── Network Infrastructure Management (NIM)
    ├── Marketing, Sales and Customer Service (Marketing)
    ├── Finance (Finance)
    ├── Human Resource (HR)
    ├── Information Technology (IT)
    ├── Process and Quality Management (P&Qmgt)
    ├── EEU Projects Portfolio Management (PPM)
    ├── Supply Chain Management and PGS (SCM&PGS)
    └── Region Coordination (RGN Coordination)
        └── 32 regions (Adama, Afar, Ambo, ... WAAR)

Every unit carries its Amharic name and Amharic officer title alongside the
English ones, so the interface can render either language.

Run ``manage.py seed_org_structure`` on its own for the corporate structure, or
``manage.py seed_eeu_audit_structure`` afterwards to attach the Internal Audit
Executive Office directorates beneath the Internal Audit chief office.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Department


# ── Chief offices reporting to the CEO ────────────────────────────────────────
# (code, English name, Amharic name, English officer title, Amharic officer title)
# Marketing has no chief-officer title in the source data, so it is left blank.
CHIEF_OFFICES = [
    (
        'Audit',
        'Internal Audit',
        'ውስጣዊ ኦዲት',
        'Chief Internal Audit officer',
        'ዋና ውስጣዊ ኦዲት ኦፊሰር',
    ),
    (
        'Legal&Ethics',
        'Legal Service and Ethics',
        'ህግና ሥነ ምግባር አገልግሎት',
        'Chief Legal Services and Ethics officer',
        'ዋና ህግና ሥነ ምግባር ኦፊሰር',
    ),
    (
        'SPlanning',
        'Strategic Planning and Investment',
        'ስትራቴጂካዊ ዕቅድና ኢንቨስትመንት',
        'Chief Strategic planning and Investment officer',
        'ዋና ስትራቴጂካዊ ዕቅድና ኢንቨስትመንት ኦፊሰር',
    ),
    (
        'Communication',
        'Communication',
        'ኮሙኒኬሽን',
        'Chief Comminication officer',
        'ዋና ኮሙኒኬሽን ኦፊሰር',
    ),
    (
        'NIM',
        'Network Infrastructure Management',
        'ኔትዎርክ መሠረተ ልማት አስተዳደር',
        'Chief Network Infrastructure officer',
        'ዋና ኔትዎርክ መሠረተ ልማት ኦፊሰር',
    ),
    (
        'Marketing',
        'Marketing, Sales and Customer Service',
        'ግብይት፣ ሽያጭና ደንበኛ አገልግሎት',
        'Chief Marketing, Sales and Customer Service officer',
        '',
    ),
    (
        'Finance',
        'Finance',
        'ፋይናንስ',
        'Chief Finance officer',
        'ዋና ፋይናንስ ኦፊሰር',
    ),
    (
        'HR',
        'Human Resource',
        'ሰው ሀይል',
        'Chief Human Resource officer',
        'ዋና ሰው ሀይል ኦፊሰር',
    ),
    (
        'IT',
        'Information Technology',
        'ኢንፎርሜሽን ቴክኖሎጂ',
        'Chief Information Technology officer',
        'ዋና ኢንፎርሜሽን ቴክኖሎጂ ኦፊሰር',
    ),
    (
        'P&Qmgt',
        'Process and Quality Management',
        'ሂደትና ጥራት አስተዳደር',
        'Chief Process and Quality Management officer',
        'ዋና ሂደትና ጥራት አስተዳደር ኦፊሰር',
    ),
    (
        'PPM',
        'EEU Projects Portfolio Management',
        'የኢኢዩ ፕሮጀክቶች ፖርትፎሊዮ አስተዳደር',
        'Chief Projects Portfolio Management officer',
        'ዋና ፕሮጀክቶች ፖርትፎሊዮ ኦፊሰር',
    ),
    (
        'SCM&PGS',
        'Supply Chain Management and PGS',
        'የሰፕላይ ቼይን አስተዳደር ንብረትና ጠቅላላ አገልግሎት',
        'Chief Supply Chain Management and PGS officer',
        'ዋና ሰፕላይ ቼይን አስተዳደር ንብረትና ጠቅላላ አገልግሎት ኦፊሰር',
    ),
    (
        'RGN Coordination',
        'Region Coordination',
        'ክልል ቅንጅት',
        'Chief Regional Coordination officer',
        'ዋና ክልል ቅንጅት ኦፊሰር',
    ),
]

# ── The 32 EEU regions, reporting to Region Coordination ──────────────────────
# (region code, English name, Amharic name)
REGIONS = [
    ('BA', 'Adama', 'አዳማ'),
    ('FA', 'Afar', 'አፋር'),
    ('BG', 'Ambo', 'አምቦ'),
    ('DB', 'ArbaMinch', 'አርባምንጭ'),
    ('CA', 'Bahir Dar', 'ባህር ዳር'),
    ('BH', 'Bale Robe', 'ባሌሮቤ'),
    ('KA', 'Benishangul', 'ቤኒሻንጉል'),
    ('BD', 'Chiro', 'ጭሮ'),
    ('CD', 'DebreBirhan', 'ደ/ብርሃን'),
    ('CE', 'DebreMarkos', 'ደ/ማርቆስ'),
    ('CB', 'Dessie', 'ደሴ'),
    ('IA', 'Dire Dawa', 'ድሬደዋ'),
    ('GA', 'Gambela', 'ጋምቤላ'),
    ('CC', 'Gonder', 'ጎንደር'),
    ('JA', 'Harari', 'ሀረር'),
    ('DC', 'Central Ethiopia', 'ማ/ኢትዮጵያ'),
    ('BE', 'Jimma', 'ጅማ'),
    ('EA', 'Mekele', 'መቀሌ'),
    ('BI', 'Mettu', 'መቱ'),
    ('BF', 'Nekemt', 'ነቀምት'),
    ('BC', 'Shashemene', 'ሻሸመኔ'),
    ('BB', 'SHEGER', 'ሸገር'),
    ('EB', 'Shire', 'ሽሬ'),
    ('LA', 'Sidama', 'ሲዳማ'),
    ('HA', 'Somale', 'ሶማሊ'),
    ('MA', 'South West', 'ደቡብ ምራብ'),
    ('CF', 'Woldiya', 'ወልድያ'),
    ('DE', 'Wolayta', 'ወላይታ ሶዶ'),
    ('AA', 'EAAR', 'ምስራቅአ.አ'),
    ('AD', 'NAAR', 'ሰሜን አ.አ'),
    ('AB', 'SAAR', 'ደቡብአ.አ'),
    ('AC', 'WAAR', 'ምዕራብ አ.አ'),
]

# Region codes collide with no chief-office code today, but a bare two-letter
# code is a poor unique key in a table shared with directorates — prefix it.
REGION_CODE_PREFIX = 'RGN-'


class Command(BaseCommand):
    help = (
        'Seeds the EEU corporate organizational structure: the CEO office, its 13 '
        'chief offices, and the 32 regions under Region Coordination.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Overwrite names, officer titles, and parents on units that already exist.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        update_existing = options['update_existing']
        self.stdout.write('Seeding EEU corporate organizational structure...')

        created_count = 0
        updated_count = 0

        def upsert(code, defaults):
            """get_or_create, honouring --update-existing for already-seeded rows."""
            nonlocal created_count, updated_count
            dept, created = Department.objects.get_or_create(code=code, defaults=defaults)
            if created:
                created_count += 1
                self.stdout.write(f'  + {dept.code}: {dept.name}')
            elif update_existing:
                for field, value in defaults.items():
                    setattr(dept, field, value)
                dept.save()
                updated_count += 1
                self.stdout.write(f'  ~ {dept.code}: {dept.name}')
            return dept

        # ── 1. Chief Executive Officer — root of the corporate hierarchy ──────
        ceo = upsert(
            'CEO',
            {
                'name': 'Chief Executive Officer',
                'name_am': 'ዋና ሥራ አስፈጻሚ ኦፊሰር',
                'head_title': 'Chief Executive Officer',
                'head_title_am': 'ዋና ሥራ አስፈጻሚ ኦፊሰር',
                'unit_type': Department.EXECUTIVE,
                'directorate_type': 'OTHER',
                'parent': None,
                'description': 'Office of the EEU Chief Executive Officer.',
            },
        )

        # ── 2. Chief offices reporting to the CEO ─────────────────────────────
        offices = {}
        for code, name, name_am, title, title_am in CHIEF_OFFICES:
            offices[code] = upsert(
                code,
                {
                    'name': name,
                    'name_am': name_am,
                    'head_title': title,
                    'head_title_am': title_am,
                    'unit_type': Department.CORPORATE,
                    # 'IAEO' is reserved for the Internal Audit Executive Office
                    # node created by seed_eeu_audit_structure, which the org
                    # chart locates by directorate_type — don't claim it here.
                    'directorate_type': 'OTHER',
                    'parent': ceo,
                    'description': f'EEU {name} chief office.',
                },
            )

        # ── 3. Regions reporting to Region Coordination ───────────────────────
        region_coordination = offices['RGN Coordination']
        for region_code, name, name_am in REGIONS:
            upsert(
                f'{REGION_CODE_PREFIX}{region_code}',
                {
                    'name': f'{name} Region',
                    'name_am': f'{name_am} ክልል',
                    'head_title': f'{name} Region Manager',
                    'head_title_am': f'የ{name_am} ክልል ሥራ አስኪያጅ',
                    'unit_type': Department.REGION,
                    'directorate_type': 'OTHER',
                    'parent': region_coordination,
                    'description': f'EEU {name} Region (region code {region_code}).',
                },
            )

        skipped = (1 + len(CHIEF_OFFICES) + len(REGIONS)) - created_count - updated_count
        self.stdout.write('')
        self.stdout.write(f'  created: {created_count}')
        if update_existing:
            self.stdout.write(f'  updated: {updated_count}')
        if skipped:
            self.stdout.write(
                f'  unchanged: {skipped} (re-run with --update-existing to overwrite)'
            )
        self.stdout.write(
            self.style.SUCCESS('EEU corporate organizational structure seeded successfully!')
        )
