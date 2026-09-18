"""Tests for the organisational-unit tree (pagination, the picker endpoint, the
service-center seed), the directorate-scoped dashboard statistics, and the
authentication hardening (login throttling, logout error handling).
"""
import datetime
import importlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import AuditTrail, Department, Role
from apps.accounts.management.commands.seed_service_centers import (
    CSC_CODE_PREFIX, is_amharic, repair_mojibake,
)
from apps.accounts.management.commands.seed_org_structure import REGION_CODE_PREFIX
from apps.accounts.management.commands.seed_hq_org_units import (
    CODE_PREFIX as HO_CODE_PREFIX,
    DEFAULT_DATA_FILE as HQ_DEFAULT_DATA_FILE,
    DEFAULT_AM_FILE as HQ_DEFAULT_AM_FILE,
)
from apps.audit_planning.models import AuditEngagement, AuditPlan, AuditTeamMember
from apps.corrective_actions.models import CorrectiveAction
from apps.findings.models import AuditFinding, FindingComment

User = get_user_model()


class DepartmentTreeEndpointTest(TestCase):
    """The compact tree feeding the cascading department picker."""

    def setUp(self):
        self.client = APIClient()
        self.auditee = User.objects.create_user(
            username='auditee', employee_id='T001', email='auditee@test.com',
            password='pass', role=Role.AUDITEE,
        )
        self.coordination = Department.objects.create(
            name='Region Coordination', code='RGN Coordination',
            unit_type=Department.CORPORATE,
        )
        self.region = Department.objects.create(
            name='Adama Region', name_am='አዳማ ክልል', code=f'{REGION_CODE_PREFIX}BA',
            unit_type=Department.REGION, parent=self.coordination,
        )
        self.center = Department.objects.create(
            name='Adama CSC No.1', code=f'{CSC_CODE_PREFIX}BA01',
            unit_type=Department.SERVICE_CENTER, parent=self.region,
        )
        self.retired = Department.objects.create(
            name='Procurement', code='PROC', is_active=False,
        )

    def test_returns_a_bare_unpaginated_list(self):
        """The picker needs every unit at once, not page one of them."""
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/tree/')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 3)

    def test_excludes_retired_units(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/tree/')
        codes = {unit['code'] for unit in response.data}
        self.assertNotIn('PROC', codes)

    def test_exposes_only_the_fields_the_picker_needs(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/tree/')
        self.assertEqual(
            set(response.data[0].keys()),
            {'id', 'code', 'name', 'name_am', 'unit_type', 'parent'},
        )

    def test_parent_chain_is_walkable(self):
        """Service center -> region -> department, the three cascade steps."""
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/tree/')
        by_id = {unit['id']: unit for unit in response.data}
        center = by_id[self.center.id]
        self.assertEqual(center['parent'], self.region.id)
        self.assertEqual(by_id[center['parent']]['parent'], self.coordination.id)
        self.assertIsNone(by_id[self.coordination.id]['parent'])

    def test_requires_authentication(self):
        response = self.client.get('/api/auth/departments/tree/')
        self.assertEqual(response.status_code, 401)


class DepartmentPaginationTest(TestCase):
    """?page_size= must be honoured — without it the picker saw 20 of 600+ units."""

    def setUp(self):
        self.client = APIClient()
        self.auditee = User.objects.create_user(
            username='auditee', employee_id='T002', email='auditee2@test.com',
            password='pass', role=Role.AUDITEE,
        )
        for index in range(25):
            Department.objects.create(name=f'Unit {index:02d}', code=f'U{index:02d}')

    def test_defaults_to_twenty_per_page(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/')
        self.assertEqual(len(response.data['results']), 20)
        self.assertEqual(response.data['count'], 25)

    def test_page_size_query_param_is_honoured(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/?page_size=100')
        self.assertEqual(len(response.data['results']), 25)

    def test_page_size_is_capped(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/auth/departments/?page_size=999999')
        self.assertEqual(len(response.data['results']), 25)


class MojibakeRepairTest(TestCase):
    """Amharic names in the upstream export arrive UTF-8-decoded-as-Latin-1."""

    def test_repairs_a_latin1_round_trip(self):
        broken = 'ሠመራ'.encode('utf-8').decode('latin-1')
        self.assertEqual(repair_mojibake(broken), 'ሠመራ')

    def test_leaves_correct_amharic_alone(self):
        self.assertEqual(repair_mojibake('አዳማ'), 'አዳማ')

    def test_leaves_ascii_alone(self):
        self.assertEqual(repair_mojibake('FERENSAY CSC'), 'FERENSAY CSC')

    def test_leaves_genuine_latin1_alone(self):
        """'café' survives the encode but not the decode — must not be mangled."""
        self.assertEqual(repair_mojibake('café'), 'café')

    def test_is_amharic(self):
        self.assertTrue(is_amharic('ሀዋሳ ቁ.1'))
        self.assertFalse(is_amharic('Hawassa No.1'))


class SeedServiceCentersTest(TestCase):
    """The seed command that creates the third corporate tier."""

    def setUp(self):
        self.coordination = Department.objects.create(
            name='Region Coordination', code='RGN Coordination',
            unit_type=Department.CORPORATE,
        )
        self.somale = Department.objects.create(
            name='Somale Region', code=f'{REGION_CODE_PREFIX}HA',
            unit_type=Department.REGION, parent=self.coordination,
        )
        self.adama = Department.objects.create(
            name='Adama Region', code=f'{REGION_CODE_PREFIX}BA',
            unit_type=Department.REGION, parent=self.coordination,
        )

    def write_data(self, rows):
        handle = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8',
        )
        json.dump(rows, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def seed(self, rows, **options):
        out = StringIO()
        # Default to an empty Amharic export so these tests exercise the
        # English/mirroring behaviour independent of the shipped Amharic data.
        options.setdefault('amharic_file', self.write_data([]))
        call_command(
            'seed_service_centers',
            data_file=self.write_data(rows),
            stdout=out,
            **options,
        )
        return out.getvalue()

    def test_creates_service_centers_under_their_region(self):
        self.seed([{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'}])
        center = Department.objects.get(code=f'{CSC_CODE_PREFIX}BA01')
        self.assertEqual(center.name, 'Adama No.1')
        self.assertEqual(center.unit_type, Department.SERVICE_CENTER)
        self.assertEqual(center.parent, self.adama)

    def test_parents_by_region_field_not_code_prefix(self):
        """The Gode District rows are coded HB.. but belong to the HA region."""
        self.seed([{'id': 1, 'csc_code': 'HB01', 'csc_name': 'Gode', 'region': 'HA'}])
        self.assertEqual(
            Department.objects.get(code=f'{CSC_CODE_PREFIX}HB01').parent,
            self.somale,
        )

    def test_strips_surrounding_whitespace_from_names(self):
        self.seed([{'id': 1, 'csc_code': 'BA02', 'csc_name': ' FERENSAY CSC', 'region': 'BA'}])
        self.assertEqual(
            Department.objects.get(code=f'{CSC_CODE_PREFIX}BA02').name,
            'FERENSAY CSC',
        )

    def test_repairs_and_mirrors_amharic_names(self):
        broken = 'ሠመራ'.encode('utf-8').decode('latin-1')
        self.seed([{'id': 1, 'csc_code': 'FA01', 'csc_name': broken, 'region': 'HA'}])
        center = Department.objects.get(code=f'{CSC_CODE_PREFIX}FA01')
        self.assertEqual(center.name, 'ሠመራ')
        # No English name exists upstream, so the one name serves both languages.
        self.assertEqual(center.name_am, 'ሠመራ')

    def test_latin_names_get_no_amharic_name(self):
        self.seed([{'id': 1, 'csc_code': 'BA03', 'csc_name': 'Alemtena', 'region': 'BA'}])
        self.assertEqual(Department.objects.get(code=f'{CSC_CODE_PREFIX}BA03').name_am, '')

    def test_is_idempotent(self):
        rows = [{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'}]
        self.seed(rows)
        output = self.seed(rows)
        self.assertEqual(Department.objects.filter(unit_type=Department.SERVICE_CENTER).count(), 1)
        self.assertIn('created: 0', output)
        self.assertIn('unchanged: 1', output)

    def test_update_existing_overwrites_names(self):
        self.seed([{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Old Name', 'region': 'BA'}])
        self.seed(
            [{'id': 1, 'csc_code': 'BA01', 'csc_name': 'New Name', 'region': 'BA'}],
            update_existing=True,
        )
        self.assertEqual(
            Department.objects.get(code=f'{CSC_CODE_PREFIX}BA01').name,
            'New Name',
        )

    def test_dry_run_writes_nothing(self):
        output = self.seed(
            [{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'}],
            dry_run=True,
        )
        self.assertIn('rolled back', output)
        self.assertFalse(Department.objects.filter(unit_type=Department.SERVICE_CENTER).exists())

    def test_reports_unknown_regions_instead_of_crashing(self):
        output = self.seed([
            {'id': 1, 'csc_code': 'ZZ01', 'csc_name': 'Nowhere', 'region': 'ZZ'},
            {'id': 2, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'},
        ])
        self.assertIn('region "ZZ" not found', output)
        # The good row still lands.
        self.assertTrue(Department.objects.filter(code=f'{CSC_CODE_PREFIX}BA01').exists())

    def test_requires_regions_to_exist(self):
        Department.objects.filter(unit_type=Department.REGION).delete()
        with self.assertRaises(CommandError):
            self.seed([{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'}])

    def test_missing_data_file_is_a_clean_error(self):
        with self.assertRaises(CommandError):
            call_command('seed_service_centers', data_file='does-not-exist.json', stdout=StringIO())


    def test_applies_amharic_names_from_the_parallel_export(self):
        self.seed(
            [{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'}],
            amharic_file=self.write_data(
                [{'csc_code': 'BA01', 'csc_name': 'የደንበኞች አገልግሎት ማዕከል 1'}]
            ),
        )
        self.assertEqual(
            Department.objects.get(code=f'{CSC_CODE_PREFIX}BA01').name_am,
            'የደንበኞች አገልግሎት ማዕከል 1',
        )

    def test_amharic_export_wins_over_the_mirrored_source_name(self):
        self.seed(
            [{'id': 1, 'csc_code': 'BA01', 'csc_name': 'ሠመራ', 'region': 'BA'}],
            amharic_file=self.write_data(
                [{'csc_code': 'BA01', 'csc_name': 'የደንበኞች አገልግሎት ማዕከል ሠመራ'}]
            ),
        )
        self.assertEqual(
            Department.objects.get(code=f'{CSC_CODE_PREFIX}BA01').name_am,
            'የደንበኞች አገልግሎት ማዕከል ሠመራ',
        )

    def test_partial_amharic_export_leaves_uncovered_center_blank(self):
        """A center the Amharic export does not name keeps a blank name_am."""
        self.seed(
            [{'id': 1, 'csc_code': 'BA02', 'csc_name': 'Alemtena', 'region': 'BA'}],
            amharic_file=self.write_data(
                [{'csc_code': 'BA01', 'csc_name': 'የደንበኞች አገልግሎት ማዕከል 1'}]
            ),
        )
        self.assertEqual(
            Department.objects.get(code=f'{CSC_CODE_PREFIX}BA02').name_am, ''
        )

    def test_missing_amharic_file_is_a_clean_error(self):
        with self.assertRaises(CommandError):
            self.seed(
                [{'id': 1, 'csc_code': 'BA01', 'csc_name': 'Adama No.1', 'region': 'BA'}],
                amharic_file='does-not-exist.json',
            )


class SeedHqOrgUnitsTest(TestCase):
    """The seed command that adds the detailed head-office tier."""

    def setUp(self):
        # Only the anchors the fixture actually touches are needed: the CEO root
        # (default parent), plus Finance and Marketing which the fixture's merge
        # rows and orphans hang off. Audit anchors stay uncreated on purpose.
        self.ceo = Department.objects.create(
            name='Chief Executive Officer', code='CEO',
            unit_type=Department.EXECUTIVE,
        )
        self.finance = Department.objects.create(
            name='Finance', code='Finance',
            unit_type=Department.CORPORATE, parent=self.ceo,
        )
        self.marketing = Department.objects.create(
            name='Marketing, Sales and Customer Service', code='Marketing',
            unit_type=Department.CORPORATE, parent=self.ceo,
        )

    def rows(self):
        """A small fixture: two merge rows, created children under both an
        anchor and a created node, an orphan, and one skipped row."""
        return [
            # Merges onto Finance / Marketing; never re-created.
            {'orgunit': '10000039', 'orgunit_name': 'CO Finance & Control',
             'location': 'HO', 'parent_id': '10000027'},
            {'orgunit': '10003313', 'orgunit_name': 'CO Marketing Sales & Customer Service',
             'location': 'HO', 'parent_id': '10000027'},
            # Created children.
            {'orgunit': '10000094', 'orgunit_name': 'CO Treasury',
             'location': 'HO', 'parent_id': '10000039'},
            {'orgunit': '10003316', 'orgunit_name': 'CO Marketing',
             'location': 'HO', 'parent_id': '10003313'},
            # Deeper tier whose parent is itself created (CO Marketing above).
            {'orgunit': '10003318', 'orgunit_name': 'CO Pricing and Tariff Management',
             'location': 'HO', 'parent_id': '10003316'},
            # Orphan row re-homed onto Finance by ORPHAN_PARENT.
            {'orgunit': '10000108', 'orgunit_name': 'CO Budget Control',
             'location': 'HO', 'parent_id': 'NO_PARNT'},
            # Skipped row.
            {'orgunit': '10000048', 'orgunit_name': 'Addis Ababa Region Coordination',
             'location': 'HO', 'parent_id': '10003356'},
        ]

    def write_data(self, rows):
        handle = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8',
        )
        json.dump(rows, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def seed(self, rows, **options):
        out = StringIO()
        call_command(
            'seed_hq_org_units',
            data_file=self.write_data(rows),
            stdout=out,
            **options,
        )
        return out.getvalue()

    def test_creates_units_wired_under_the_right_office(self):
        output = self.seed(self.rows())
        # Merge rows are reported but Finance/Marketing are not duplicated.
        self.assertIn('10000039 "CO Finance & Control" merges into existing Finance', output)
        self.assertEqual(Department.objects.filter(code='Finance').count(), 1)
        self.assertFalse(Department.objects.filter(code=f'{HO_CODE_PREFIX}10000039').exists())
        # New units get HO- codes, CORPORATE type, and the resolved parent.
        treasury = Department.objects.get(code=f'{HO_CODE_PREFIX}10000094')
        self.assertEqual(treasury.name, 'CO Treasury')
        self.assertEqual(treasury.unit_type, Department.CORPORATE)
        self.assertEqual(treasury.parent, self.finance)
        # A parent that is itself created (CO Marketing) is created first.
        pricing = Department.objects.get(code=f'{HO_CODE_PREFIX}10003318')
        marketing = Department.objects.get(code=f'{HO_CODE_PREFIX}10003316')
        self.assertEqual(pricing.parent, marketing)
        self.assertEqual(marketing.parent, self.marketing)
        # Skipped rows never land.
        self.assertFalse(Department.objects.filter(code=f'{HO_CODE_PREFIX}10000048').exists())

    def test_rehomes_orphans_onto_their_office(self):
        self.seed(self.rows())
        budget = Department.objects.get(code=f'{HO_CODE_PREFIX}10000108')
        self.assertEqual(budget.name, 'CO Budget Control')
        self.assertEqual(budget.parent, self.finance)

    def test_is_idempotent(self):
        rows = self.rows()
        self.seed(rows)
        output = self.seed(rows)
        self.assertIn('created: 0', output)
        self.assertIn('unchanged: 4', output)  # the four created rows above
        self.assertEqual(
            Department.objects.filter(code__startswith=HO_CODE_PREFIX).count(), 4
        )

    def test_dry_run_writes_nothing(self):
        output = self.seed(self.rows(), dry_run=True)
        self.assertIn('rolled back', output)
        self.assertFalse(Department.objects.filter(code__startswith=HO_CODE_PREFIX).exists())

    def test_update_existing_overwrites_names(self):
        rows = [{'orgunit': '10000094', 'orgunit_name': 'Old Name',
                 'location': 'HO', 'parent_id': '10000039'}]
        self.seed(rows)
        self.seed(
            [{'orgunit': '10000094', 'orgunit_name': 'CO Treasury',
              'location': 'HO', 'parent_id': '10000039'}],
            update_existing=True,
        )
        self.assertEqual(
            Department.objects.get(code=f'{HO_CODE_PREFIX}10000094').name,
            'CO Treasury',
        )

    def test_reports_unresolved_parents_instead_of_crashing(self):
        rows = [{'orgunit': '10000094', 'orgunit_name': 'CO Treasury',
                 'location': 'HO', 'parent_id': '99999999'}]
        output = self.seed(rows)
        self.assertIn('parent "99999999" not found', output)
        # The row still lands, under the CEO default, so nothing is dropped.
        self.assertEqual(
            Department.objects.get(code=f'{HO_CODE_PREFIX}10000094').parent,
            self.ceo,
        )

    def test_requires_an_anchor_it_references(self):
        self.finance.delete()
        # The child's parent ERP id (10000039) is a merge row -> Finance anchor.
        rows = [{'orgunit': '10000094', 'orgunit_name': 'CO Treasury',
                 'location': 'HO', 'parent_id': '10000039'}]
        with self.assertRaises(CommandError) as ctx:
            self.seed(rows)
        self.assertIn('Finance', str(ctx.exception))
        self.assertIn('seed_org_structure', str(ctx.exception))

    def test_missing_data_file_is_a_clean_error(self):
        with self.assertRaises(CommandError):
            call_command('seed_hq_org_units', data_file='does-not-exist.json', stdout=StringIO())

    def test_applies_amharic_names_from_the_parallel_export(self):
        self.seed(
            self.rows(),
            amharic_file=self.write_data(
                [{'orgunit': '10000094', 'orgunit_name': 'የድርጅቱ ግምጃ ቤት'}]
            ),
        )
        self.assertEqual(
            Department.objects.get(code=f'{HO_CODE_PREFIX}10000094').name_am,
            'የድርጅቱ ግምጃ ቤት',
        )

    def test_amharic_name_is_blank_when_the_export_lacks_the_unit(self):
        self.seed(
            self.rows(),
            amharic_file=self.write_data(
                [{'orgunit': '10003316', 'orgunit_name': 'ግብይት'}]
            ),
        )
        # 10000094 is absent from the Amharic export -> falls back to English.
        self.assertEqual(
            Department.objects.get(code=f'{HO_CODE_PREFIX}10000094').name_am, ''
        )

    def test_missing_amharic_file_is_a_clean_error(self):
        with self.assertRaises(CommandError):
            self.seed(self.rows(), amharic_file='does-not-exist.json')


class SeedDataLegacyDepartmentAmharicTest(TestCase):
    """The three legacy demo departments must carry Amharic names.

    Without them the Amharic interface falls back to English for exactly these
    units while every other department renders in Amharic.
    """

    def test_seed_data_gives_legacy_departments_amharic_names(self):
        call_command('seed_data', stdout=StringIO())
        for code, name_am in [
            ('FIN', 'ፋይናንስ እና ሒሳብ'),
            ('PROC', 'ግዢ እና ሎጂስቲክስ'),
            ('DIST', 'የኃይል ስርጭት'),
        ]:
            self.assertEqual(Department.objects.get(code=code).name_am, name_am)


class ShippedHqOrgUnitsDataTest(TestCase):
    """Guard the committed head-office export against silent corruption."""

    def setUp(self):
        self.rows = json.loads(HQ_DEFAULT_DATA_FILE.read_text(encoding='utf-8'))

    def test_has_all_154_units_with_unique_codes(self):
        codes = {row['orgunit'] for row in self.rows}
        self.assertEqual(len(self.rows), 154)
        self.assertEqual(len(codes), 154)
        # The placeholder/sentinel rows never made it into the committed file.
        self.assertFalse(any(str(code).startswith('DEV') for code in codes))
        self.assertNotIn('NO_PARNT', codes)

    def test_every_parent_is_resolvable(self):
        """Every parent_id is null, the NO_PARNT sentinel, or another row —
        otherwise the seed would silently re-home units onto the CEO root."""
        codes = {row['orgunit'] for row in self.rows}
        for row in self.rows:
            parent = row.get('parent_id')
            if parent is None or str(parent).strip().upper() == 'NO_PARNT':
                continue
            self.assertIn(
                str(parent), codes,
                f"{row['orgunit']} points at missing parent {parent}",
            )

    def test_amharic_file_covers_the_same_units_with_no_blanks(self):
        """The Amharic export keys the same units 1:1, so no head-office unit
        ends up without an Amharic name."""
        english = json.loads(HQ_DEFAULT_DATA_FILE.read_text(encoding='utf-8'))
        amharic = json.loads(HQ_DEFAULT_AM_FILE.read_text(encoding='utf-8'))
        self.assertEqual(len(amharic), len(english))
        self.assertEqual(
            {row['orgunit'] for row in amharic},
            {row['orgunit'] for row in english},
        )
        self.assertTrue(all(str(row['orgunit_name']).strip() for row in amharic))



class ShippedServiceCenterDataTest(TestCase):
    """Guard the committed export against silent corruption or truncation."""

    def setUp(self):
        from apps.accounts.management.commands.seed_service_centers import DEFAULT_DATA_FILE
        self.rows = json.loads(DEFAULT_DATA_FILE.read_text(encoding='utf-8'))

    def test_has_all_582_centers_with_unique_codes(self):
        self.assertEqual(len(self.rows), 582)
        self.assertEqual(len({row['csc_code'] for row in self.rows}), 582)

    def test_every_row_names_one_of_the_32_regions(self):
        self.assertEqual(len({row['region'] for row in self.rows}), 32)

    def test_amharic_names_are_not_mojibaked(self):
        """A row whose name changes under repair means the file regressed."""
        broken = [
            row['csc_code'] for row in self.rows
            if repair_mojibake(row['csc_name']) != row['csc_name']
        ]
        self.assertEqual(broken, [])

    def test_no_blank_names(self):
        self.assertEqual([r['csc_code'] for r in self.rows if not r['csc_name'].strip()], [])

    def test_amharic_export_covers_every_center_with_no_blanks(self):
        """The Amharic export names all 582 centers and must never be corrupt:
        every code it names exists in the main export, and none is blank."""
        from apps.accounts.management.commands.seed_service_centers import DEFAULT_AM_FILE
        amharic = json.loads(DEFAULT_AM_FILE.read_text(encoding='utf-8'))
        main_codes = {row['csc_code'] for row in self.rows}
        am_codes = [row['csc_code'] for row in amharic]
        self.assertEqual(len(am_codes), len(self.rows))
        self.assertEqual(len(set(am_codes)), len(am_codes))  # no duplicate keys
        self.assertEqual(set(am_codes), main_codes)  # 1:1 with the main export
        self.assertEqual([r['csc_code'] for r in amharic if not r['csc_name'].strip()], [])
        self.assertEqual(
            [r['csc_code'] for r in amharic if repair_mojibake(r['csc_name']) != r['csc_name']],
            [],
        )


class DashboardStatsDirectorateTest(TestCase):
    """?directorate= must rescope every KPI and chart series.

    Before this existed, picking a directorate on the dashboard changed a label
    and nothing else — the numbers were enterprise-wide (or hardcoded) regardless
    of the selection.
    """

    URL = '/api/auth/dashboard/stats/'

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='dash', employee_id='D001', email='dash@test.com',
            password='pass', role=Role.AUDITEE,
        )
        self.client.force_authenticate(user=self.user)

        self.today = timezone.now().date()
        self.fpa = Department.objects.create(
            name='Financial & Performance Audit', code='FPA',
            unit_type=Department.AUDIT, directorate_type='FPA',
            head='Abebe Kebede', staff_count=12,
        )
        self.ita = Department.objects.create(
            name='Information Technology Audit', code='ITA',
            unit_type=Department.AUDIT, directorate_type='ITA',
        )
        self.empty = Department.objects.create(
            name='Planning & Performance', code='PP',
            unit_type=Department.AUDIT, directorate_type='PP',
        )
        self.plan = AuditPlan.objects.create(
            title='Annual Plan', year=self.today.year, status='active',
            directorate=self.fpa,
        )

        # FPA: 1 in-progress engagement, 4 findings (1 closed, 1 resolved but not
        # yet verified, 1 open critical, 1 open medium) -> verified closure 25.0%.
        fpa_engagement = self._engagement(self.fpa, 'FPA-01', status='in_progress')
        self._finding(fpa_engagement, 'F-1', severity='critical', status='open')
        self._finding(fpa_engagement, 'F-2', severity='medium', status='open')
        self._finding(fpa_engagement, 'F-3', severity='high', status='closed')
        self._finding(fpa_engagement, 'F-4', severity='low', status='resolved')

        # ITA: 1 completed engagement, 1 open finding with an overdue CAPA.
        ita_engagement = self._engagement(self.ita, 'ITA-01', status='completed')
        ita_finding = self._finding(ita_engagement, 'F-5', severity='high', status='open')
        CorrectiveAction.objects.create(
            finding=ita_finding, action_number='CA-1', title='Patch',
            description='d', recommendation='r', status='open',
            due_date=self.today - datetime.timedelta(days=10),
        )

    def _engagement(self, directorate, number, status):
        return AuditEngagement.objects.create(
            plan=self.plan, title=f'Engagement {number}', engagement_number=number,
            status=status, directorate=directorate,
            planned_start=self.today - datetime.timedelta(days=60),
            actual_end=self.today if status == 'completed' else None,
        )

    def _finding(self, engagement, number, severity, status):
        return AuditFinding.objects.create(
            engagement=engagement, finding_number=number, title=number,
            description='d', severity=severity, status=status,
        )

    def test_unscoped_returns_enterprise_totals(self):
        data = self.client.get(self.URL).data
        self.assertIsNone(data['directorate'])
        self.assertEqual(data['total_engagements'], 2)
        self.assertEqual(data['total_findings'], 5)
        self.assertEqual(data['open_findings'], 3)
        self.assertEqual(data['overdue_actions'], 1)

    def test_scoped_counts_only_that_directorate(self):
        data = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        self.assertEqual(data['total_engagements'], 1)
        self.assertEqual(data['active_engagements'], 1)
        self.assertEqual(data['total_findings'], 4)
        self.assertEqual(data['open_findings'], 2)
        self.assertEqual(data['critical_findings'], 1)
        self.assertEqual(data['active_plans'], 1)
        # The overdue CAPA belongs to ITA, so it must not leak into FPA.
        self.assertEqual(data['overdue_actions'], 0)

    def test_capas_are_scoped_through_finding_and_engagement(self):
        data = self.client.get(self.URL, {'directorate': self.ita.id}).data
        self.assertEqual(data['overdue_actions'], 1)
        self.assertEqual(data['open_actions'], 1)

    def test_echoes_the_directorate_it_scoped_to(self):
        data = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        self.assertEqual(data['directorate'], {
            'id': self.fpa.id,
            'name': 'Financial & Performance Audit',
            'code': 'FPA',
            'head': 'Abebe Kebede',
            'staff_count': 12,
        })

    def test_compliance_score_counts_only_verified_closures(self):
        data = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        # 4 FPA findings, but only F-3 is closed. F-4 sits at 'resolved' — a
        # claim of remediation nobody has verified — so it scores nothing.
        self.assertEqual(data['compliance_score'], 25.0)

    def test_resolving_a_finding_does_not_move_the_score_but_closing_does(self):
        resolved = AuditFinding.objects.get(finding_number='F-4')
        self.assertEqual(resolved.status, 'resolved')
        before = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        resolved.status = 'closed'
        resolved.save(update_fields=['status'])
        after = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        self.assertEqual(before['compliance_score'], 25.0)
        self.assertEqual(after['compliance_score'], 50.0)

    def test_compliance_trend_uses_the_same_verified_rule_as_the_kpi(self):
        """The line and the number above it must not disagree."""
        data = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        # Every FPA finding was raised in the current quarter, and the trend is
        # cumulative, so its last point is the KPI.
        self.assertEqual(data['compliance_trend'][-1]['score'], data['compliance_score'])

    def test_directorate_with_no_work_reads_as_zero_and_fully_compliant(self):
        data = self.client.get(self.URL, {'directorate': self.empty.id}).data
        self.assertEqual(data['total_engagements'], 0)
        self.assertEqual(data['open_findings'], 0)
        self.assertEqual(data['overdue_actions'], 0)
        # Nothing outstanding is 100%, not 0% — a zero would read as total failure.
        self.assertEqual(data['compliance_score'], 100.0)
        self.assertEqual(data['open_findings_by_severity'], [])

    def test_open_findings_by_severity_excludes_settled_findings(self):
        data = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        by_severity = {row['severity']: row['count'] for row in data['open_findings_by_severity']}
        self.assertEqual(by_severity, {'critical': 1, 'medium': 1})
        # The full breakdown still carries every finding.
        self.assertEqual(sum(r['count'] for r in data['findings_by_severity']), 4)

    def test_monthly_engagements_walks_six_calendar_months(self):
        data = self.client.get(self.URL).data
        months = data['monthly_engagements']
        self.assertEqual(len(months), 6)
        # Oldest first, ending on the current month.
        self.assertEqual(months[-1]['month'], self.today.strftime('%b %Y'))
        labels = [m['month'] for m in months]
        self.assertEqual(len(set(labels)), 6, 'calendar months must not repeat')
        self.assertEqual(set(months[0]), {'month', 'Completed', 'InProgress'})

    def test_monthly_engagements_counts_completed_in_its_month(self):
        data = self.client.get(self.URL, {'directorate': self.ita.id}).data
        current = data['monthly_engagements'][-1]
        self.assertEqual(current['Completed'], 1)

    def test_monthly_engagements_counts_in_flight_work_as_active(self):
        data = self.client.get(self.URL, {'directorate': self.fpa.id}).data
        # The FPA engagement started 60 days ago and has not finished, so it is
        # active in the current month.
        self.assertEqual(data['monthly_engagements'][-1]['InProgress'], 1)

    def test_compliance_trend_has_five_quarters_oldest_first(self):
        data = self.client.get(self.URL).data
        trend = data['compliance_trend']
        self.assertEqual(len(trend), 5)
        current_quarter = (self.today.month - 1) // 3 + 1
        self.assertEqual(trend[-1]['name'], f'Q{current_quarter} {self.today.year}')
        self.assertEqual(set(trend[0]), {'name', 'score'})

    def test_unknown_directorate_is_a_404_not_a_500(self):
        response = self.client.get(self.URL, {'directorate': 999999})
        self.assertEqual(response.status_code, 404)

    def test_non_numeric_directorate_is_a_400_not_a_500(self):
        response = self.client.get(self.URL, {'directorate': 'FPA'})
        self.assertEqual(response.status_code, 400)

    def test_all_is_treated_as_unscoped(self):
        """The frontend's 'all' sentinel must not 400."""
        response = self.client.get(self.URL, {'directorate': 'all'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['directorate'])
        self.assertEqual(response.data['total_engagements'], 2)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.URL).status_code, 401)


class ProfileViewTest(TestCase):
    """Self-service profile edits.

    The Settings -> Profile tab PATCHed a route that did not exist, so saving
    your own name was a 404 for every role. This is the route that fixed it, and
    the risk it carries is that a self-service endpoint on the user model is one
    careless writable field away from self-promotion.
    """

    URL = '/api/auth/profile/'

    def setUp(self):
        self.client = APIClient()
        self.department = Department.objects.create(name='Finance', code='FIN')
        self.other_department = Department.objects.create(name='Operations', code='OPS')
        self.auditee = User.objects.create_user(
            username='profile-auditee', employee_id='P001', email='auditee@test.com',
            password='pass', first_name='Selam', last_name='Tesfaye',
            role=Role.AUDITEE, department=self.department,
        )
        self.admin = User.objects.create_user(
            username='profile-admin', employee_id='P002', email='admin@test.com',
            password='pass', role=Role.ADMIN, department=self.department,
        )
        self.client.force_authenticate(user=self.auditee)

    def test_get_returns_the_callers_own_profile(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.auditee.id)
        self.assertEqual(response.data['employee_id'], 'P001')
        # The full user payload, so the client can replace its stored user object
        # wholesale — it needs `role` to keep rendering the right navigation.
        self.assertEqual(response.data['role'], Role.AUDITEE)

    def test_a_user_can_edit_their_own_name_and_phone(self):
        response = self.client.patch(self.URL, {
            'first_name': 'Selamawit', 'last_name': 'Tesfaye G.', 'phone': '+251911000111',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.auditee.refresh_from_db()
        self.assertEqual(self.auditee.first_name, 'Selamawit')
        self.assertEqual(self.auditee.phone, '+251911000111')
        self.assertEqual(response.data['full_name'], 'Selamawit Tesfaye G.')

    def test_the_endpoint_takes_no_id_so_no_one_elses_record_is_reachable(self):
        """There is nothing to scope: ``get_object`` returns ``request.user``, so
        the collection-style URL is the whole surface area."""
        self.assertEqual(self.client.patch(
            f'{self.URL}{self.admin.id}/', {'first_name': 'Hijacked'}, format='json',
        ).status_code, 404)
        self.admin.refresh_from_db()
        self.assertNotEqual(self.admin.first_name, 'Hijacked')

    def test_role_cannot_be_changed_through_a_profile_edit(self):
        """The escalation this serializer's read_only_fields exists to stop."""
        response = self.client.patch(
            self.URL, {'role': Role.ADMIN, 'first_name': 'Selam'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.auditee.refresh_from_db()
        self.assertEqual(self.auditee.role, Role.AUDITEE)

    def test_department_employee_id_and_email_are_pinned(self):
        self.client.patch(self.URL, {
            'department': self.other_department.id,
            'employee_id': 'EEU-00001',
            'email': 'someone.else@test.com',
            'is_active': False,
        }, format='json')
        self.auditee.refresh_from_db()
        self.assertEqual(self.auditee.department, self.department)
        self.assertEqual(self.auditee.employee_id, 'P001')
        self.assertEqual(self.auditee.email, 'auditee@test.com')
        self.assertTrue(self.auditee.is_active)

    def test_the_edit_is_audit_logged(self):
        from apps.accounts.models import AuditTrail

        self.client.patch(self.URL, {'phone': '+251911222333'}, format='json')
        entry = AuditTrail.objects.filter(
            model_name='User', object_id=str(self.auditee.id), action='UPDATE',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user, self.auditee)
        self.assertIn('Profile updated', entry.object_repr)

    def test_every_role_can_edit_their_own_profile(self):
        """Deliberately not on UserViewSet: that viewset is gated by
        CanManageUsers, so routing profile edits through it would lock every
        non-admin out of changing their own name."""
        for index, role in enumerate(
            [Role.ADMIN, Role.AUDIT_MANAGER, Role.SUPERVISOR, Role.AUDITOR, Role.AUDITEE],
            start=10,
        ):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f'role-{role}', employee_id=f'P0{index}',
                    email=f'role-{role}@test.com', password='pass', role=role,
                )
                self.client.force_authenticate(user=user)
                response = self.client.patch(
                    self.URL, {'first_name': 'Renamed'}, format='json',
                )
                self.assertEqual(response.status_code, 200, response.data)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(
            self.client.patch(self.URL, {'first_name': 'X'}, format='json').status_code, 401,
        )


class AuditTrailFilterTest(TestCase):
    """The Security Audit Log panel is scoped to account events.

    User Management renders its panel with ``getAuditTrail({ model_name: 'User' })``,
    which is what keeps it a *security* log rather than a second copy of the Audit
    Trail page. Nothing previously asserted that ``?model_name=`` filtered correctly,
    so a future edit that drops the parameter would silently turn the panel back into
    the global feed. This locks the contract.
    """

    URL = '/api/auth/audit-trail/'

    def setUp(self):
        self.client = APIClient()
        self.department = Department.objects.create(name='Finance', code='FIN')
        self.admin = User.objects.create_user(
            username='audit-admin', employee_id='A001', email='admin@test.com',
            password='pass', role=Role.ADMIN, department=self.department,
        )
        self.operator = User.objects.create_user(
            username='audit-operator', employee_id='A002', email='operator@test.com',
            password='pass', role=Role.AUDIT_MANAGER, department=self.department,
        )
        self.client.force_authenticate(user=self.admin)

    def test_model_name_filter_returns_only_user_rows(self):
        AuditTrail.objects.create(
            user=self.admin, action='LOGIN', model_name='User',
            object_id=str(self.admin.id), object_repr='Audit admin signed in',
        )
        AuditTrail.objects.create(
            user=self.admin, action='UPDATE', model_name='User',
            object_id=str(self.operator.id), object_repr='Deactivated user A002',
        )
        AuditTrail.objects.create(
            user=self.admin, action='CREATE', model_name='AuditFinding',
            object_id='1', object_repr='Finding on procurement',
        )
        AuditTrail.objects.create(
            user=self.admin, action='APPROVE', model_name='AuditPlan',
            object_id='1', object_repr='Annual audit plan approved',
        )

        response = self.client.get(self.URL, {'model_name': 'User'})

        self.assertEqual(response.status_code, 200)
        results = response.data['results']
        self.assertEqual(len(results), 2)
        self.assertTrue(all(row['model_name'] == 'User' for row in results))
        self.assertEqual({row['action'] for row in results}, {'LOGIN', 'UPDATE'})

    def test_unauthenticated_requests_are_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.URL, {'model_name': 'User'})
        self.assertEqual(response.status_code, 401)


class LoginThrottleTest(TestCase):
    """Login is rate limited per client.

    It is the only unauthenticated write in the system and the username space is
    the guessable EEU-##### series, so before this there was nothing at all
    slowing down credential stuffing. The rate lives in
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['login'].
    """

    URL = '/api/auth/login/'

    def setUp(self):
        # DRF keeps throttle history in the default cache, which is process-wide
        # and outlives the per-test transaction rollback. Without this the count
        # leaks between tests and the suite fails differently depending on order.
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='throttled', employee_id='EEU-00001',
            email='throttled@test.com', password='correct-horse-battery',
            role=Role.AUDITOR,
        )

    def tearDown(self):
        cache.clear()

    def attempt(self, password='wrong'):
        return self.client.post(
            self.URL, {'employee_id': 'EEU-00001', 'password': password},
            format='json',
        )

    def _rate_limit(self):
        """Attempts allowed per window, read from the configured login rate.

        Kept in sync with settings so these tests survive a rate change instead
        of silently passing because the loop stopped short of the new budget.
        """
        return int(
            settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['login'].split('/')[0]
        )

    def test_the_rate_is_configured(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['login'], '30/min',
        )

    def test_attempts_beyond_the_rate_are_refused(self):
        for index in range(self._rate_limit()):
            with self.subTest(attempt=index + 1):
                self.assertEqual(self.attempt().status_code, 400)
        self.assertEqual(self.attempt().status_code, 429)

    def test_a_successful_login_also_counts_against_the_budget(self):
        """Otherwise an attacker who lands one valid credential gets an
        unmetered channel for enumerating the rest."""
        for _ in range(self._rate_limit()):
            self.attempt()
        self.assertEqual(self.attempt(password='correct-horse-battery').status_code, 429)

    def test_a_valid_login_inside_the_budget_still_works(self):
        """The throttle must not break the ordinary case — one honest typo
        followed by the right password."""
        self.assertEqual(self.attempt().status_code, 400)
        response = self.attempt(password='correct-horse-battery')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_the_login_scope_does_not_throttle_authenticated_traffic(self):
        """The login scope's rate applies to login only; an auditor paging
        through the org tree is on the far looser 'user' rate."""
        self.client.force_authenticate(user=self.user)
        for _ in range(8):
            self.assertEqual(self.client.get('/api/auth/departments/').status_code, 200)


class LogoutViewTest(TestCase):
    """A client error and a server error must not look the same.

    The bare ``except Exception`` reported a stale tab and a database failure
    writing the blacklist row identically — a 400 'Invalid token.' with nothing
    logged anywhere.
    """

    URL = '/api/auth/logout/'

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='logout', employee_id='L001', email='logout@test.com',
            password='pass', role=Role.AUDITOR,
        )
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        cache.clear()

    def test_a_valid_refresh_token_is_blacklisted(self):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        refresh = RefreshToken.for_user(self.user)
        response = self.client.post(self.URL, {'refresh': str(refresh)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            BlacklistedToken.objects.filter(token__jti=refresh['jti']).exists()
        )

    def test_the_logout_is_audit_logged(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.post(self.URL, {'refresh': str(refresh)}, format='json')
        self.assertTrue(
            AuditTrail.objects.filter(action='LOGOUT', user=self.user).exists()
        )

    def test_a_garbage_token_is_the_clients_problem(self):
        response = self.client.post(self.URL, {'refresh': 'not-a-token'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Invalid token.')

    def test_a_missing_token_is_a_400_not_a_silent_success(self):
        """``RefreshToken(None)`` mints a fresh token instead of raising, so this
        used to blacklist a token nobody held, write a LOGOUT trail entry, and
        return 200 while the client's real refresh token stayed valid."""
        response = self.client.post(self.URL, {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('required', response.data['detail'])
        self.assertFalse(AuditTrail.objects.filter(action='LOGOUT').exists())

    def test_a_token_presented_twice_is_a_400(self):
        """The stale-tab case: the second POST is a client error, not an outage."""
        refresh = str(RefreshToken.for_user(self.user))
        self.assertEqual(
            self.client.post(self.URL, {'refresh': refresh}, format='json').status_code, 200,
        )
        self.assertEqual(
            self.client.post(self.URL, {'refresh': refresh}, format='json').status_code, 400,
        )

    def test_an_unexpected_failure_is_a_500_and_is_logged(self):
        """The distinction the bare ``except`` erased. A blacklist write that
        fails is an outage, and reporting it as 'Invalid token.' sent the user
        off to re-authenticate against a backend that was already broken."""
        refresh = str(RefreshToken.for_user(self.user))
        with mock.patch(
            'rest_framework_simplejwt.tokens.RefreshToken.blacklist',
            side_effect=OperationalError('database is locked'),
        ):
            with self.assertLogs('apps.accounts.views', level='ERROR') as logged:
                response = self.client.post(self.URL, {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertIn('Logout failed', '\n'.join(logged.output))

    def test_logout_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.post(self.URL, {'refresh': 'x'}, format='json').status_code, 401,
        )


class DepartmentListQueryCountTest(TestCase):
    """``children`` must not cost a query per department.

    DepartmentSerializer.get_children filters and orders, so a plain
    prefetch_related('children') would be re-queried and thrown away. The
    Prefetch on DepartmentViewSet lands the rows on ``active_children``, which
    the serializer reads in preference to querying. EEU's tree is 600+ units and
    max_page_size is 1000, so the difference is ~600 queries on one request.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.auditee = User.objects.create_user(
            username='counter', employee_id='Q001', email='counter@test.com',
            password='pass', role=Role.AUDITEE,
        )
        self.client.force_authenticate(user=self.auditee)

    def make_tree(self, parents, children_each, offset=0):
        for parent_index in range(parents):
            parent = Department.objects.create(
                name=f'Region {offset + parent_index:03d}',
                code=f'RGN-{offset + parent_index:03d}',
                unit_type=Department.REGION,
            )
            for child_index in range(children_each):
                Department.objects.create(
                    name=f'CSC {offset + parent_index:03d}-{child_index}',
                    code=f'CSC-{offset + parent_index:03d}-{child_index}',
                    unit_type=Department.SERVICE_CENTER, parent=parent,
                )

    def query_count(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get('/api/auth/departments/?page_size=1000')
            self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries), response

    def test_the_query_count_is_flat_as_the_tree_grows(self):
        self.make_tree(parents=3, children_each=3)
        small_count, small_response = self.query_count()

        self.make_tree(parents=15, children_each=3, offset=100)
        large_count, large_response = self.query_count()

        # Six times the rows, the same number of queries.
        self.assertEqual(small_response.data['count'], 12)
        self.assertEqual(large_response.data['count'], 72)
        self.assertEqual(
            large_count, small_count,
            f'query count grew with the tree: {small_count} -> {large_count}',
        )

    def test_children_are_still_serialized(self):
        """The prefetch is only correct if the payload is unchanged — a fix that
        dropped the children would also make the count flat."""
        self.make_tree(parents=1, children_each=2)
        _, response = self.query_count()
        parents = [row for row in response.data['results'] if row['children']]
        self.assertEqual(len(parents), 1)
        self.assertEqual(
            {child['name'] for child in parents[0]['children']},
            {'CSC 000-0', 'CSC 000-1'},
        )

    def test_retired_children_are_excluded(self):
        """The filter the Prefetch queryset has to reproduce exactly."""
        parent = Department.objects.create(name='Region X', code='RGN-X')
        Department.objects.create(name='Live CSC', code='CSC-L', parent=parent)
        Department.objects.create(
            name='Closed CSC', code='CSC-C', parent=parent, is_active=False,
        )
        _, response = self.query_count()
        row = next(r for r in response.data['results'] if r['code'] == 'RGN-X')
        self.assertEqual([child['code'] for child in row['children']], ['CSC-L'])

    def test_children_are_present_on_a_single_object_response(self):
        """retrieve/create/update responses have no prefetch, so the serializer's
        fallback query has to stay — this is the case that proves it."""
        parent = Department.objects.create(name='Region Y', code='RGN-Y')
        Department.objects.create(name='Y CSC', code='CSC-Y', parent=parent)
        response = self.client.get(f'/api/auth/departments/{parent.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([child['code'] for child in response.data['children']], ['CSC-Y'])


class UserDeletionGuardTest(TestCase):
    """Hard-deleting a user row takes engagement-team membership and finding
    comments with it — both relations CASCADE off User — so the endpoint has to
    refuse when either would be destroyed, and when the account is the caller's
    own or the last one able to administer the system."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin', employee_id='T100', email='admin1@test.com',
            password='pass', role=Role.ADMIN,
        )
        self.other_admin = User.objects.create_user(
            username='admin2', employee_id='T101', email='admin2@test.com',
            password='pass', role=Role.ADMIN,
        )
        self.target = User.objects.create_user(
            username='target', employee_id='T102', email='target@test.com',
            password='pass', role=Role.AUDITOR,
        )
        self.client.force_authenticate(user=self.admin)

    def _blocker_types(self, response):
        return {b['type'] for b in response.data['blockers']}

    def _give_engagement_membership(self, user):
        plan = AuditPlan.objects.create(title='2026 Plan', year=2026)
        engagement = AuditEngagement.objects.create(
            plan=plan, title='Cash Audit', engagement_number='ENG-001',
        )
        return AuditTeamMember.objects.create(
            engagement=engagement, user=user, role='member',
        )

    def _give_finding_comment(self, user):
        plan = AuditPlan.objects.create(title='2026 Plan', year=2026)
        engagement = AuditEngagement.objects.create(
            plan=plan, title='Cash Audit', engagement_number='ENG-002',
        )
        finding = AuditFinding.objects.create(
            engagement=engagement, finding_number='F-001', title='Weak control',
            description='Segregation of duties is absent.', severity='high',
        )
        return FindingComment.objects.create(
            finding=finding, author=user, comment='Agreed, will fix.',
        )

    def test_deletes_an_account_with_no_history(self):
        response = self.client.delete(f'/api/auth/users/{self.target.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    def test_deletion_is_recorded_in_the_audit_trail(self):
        self.client.delete(f'/api/auth/users/{self.target.pk}/')
        entry = AuditTrail.objects.filter(
            model_name='User', action='DELETE', object_id=str(self.target.pk),
        ).first()
        self.assertIsNotNone(entry, 'the delete has to leave a trail entry')

    def test_refuses_to_delete_your_own_account(self):
        response = self.client.delete(f'/api/auth/users/{self.admin.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('self', self._blocker_types(response))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_solo_administrator_also_reports_the_last_admin_blocker(self):
        """Deleting the only administrator is both a self-delete and a lockout;
        the invariant is reported outright rather than inferred from `self`."""
        # Take the second admin out of the picture without deleting them.
        User.objects.filter(pk=self.other_admin.pk).update(is_active=False)
        response = self.client.post(
            f'/api/auth/users/{self.admin.pk}/deletion-check/',
        )
        self.assertFalse(response.data['can_delete'])
        self.assertEqual(
            self._blocker_types(response), {'self', 'last_admin'},
        )

    def test_a_second_administrator_is_not_the_last_one(self):
        response = self.client.post(
            f'/api/auth/users/{self.other_admin.pk}/deletion-check/',
        )
        self.assertTrue(response.data['can_delete'])
        self.assertEqual(response.data['blockers'], [])

    def test_refuses_when_the_account_is_on_an_engagement_team(self):
        membership = self._give_engagement_membership(self.target)
        response = self.client.delete(f'/api/auth/users/{self.target.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('engagement_teams', self._blocker_types(response))
        # The whole point of refusing: the team row has to survive.
        self.assertTrue(AuditTeamMember.objects.filter(pk=membership.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_refuses_when_the_account_authored_finding_comments(self):
        comment = self._give_finding_comment(self.target)
        response = self.client.delete(f'/api/auth/users/{self.target.pk}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('finding_comments', self._blocker_types(response))
        self.assertTrue(FindingComment.objects.filter(pk=comment.pk).exists())

    def test_preflight_reports_blockers_with_readable_counts(self):
        self._give_engagement_membership(self.target)
        self._give_finding_comment(self.target)
        response = self.client.post(
            f'/api/auth/users/{self.target.pk}/deletion-check/',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['can_delete'])
        messages = [b['message'] for b in response.data['blockers']]
        self.assertTrue(any('engagement team' in m for m in messages))
        self.assertTrue(any('finding comment' in m for m in messages))
        # Counts drive the message, so they must be present and non-zero.
        self.assertTrue(all(b['count'] > 0 for b in response.data['blockers']))

    def test_preflight_requires_the_manage_users_capability(self):
        """POST rather than GET precisely so this is gated — the viewset opens
        safe methods to any authenticated user."""
        auditor = User.objects.create_user(
            username='auditor', employee_id='T103', email='auditor@test.com',
            password='pass', role=Role.AUDITOR,
        )
        self.client.force_authenticate(user=auditor)
        response = self.client.post(
            f'/api/auth/users/{self.target.pk}/deletion-check/',
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_requires_the_manage_users_capability(self):
        auditor = User.objects.create_user(
            username='auditor2', employee_id='T104', email='auditor2@test.com',
            password='pass', role=Role.AUDITOR,
        )
        self.client.force_authenticate(user=auditor)
        response = self.client.delete(f'/api/auth/users/{self.target.pk}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())


def _backfill_migration():
    """The split-out-geographic-units data migration, imported on demand.

    Not at module scope or in ``setUpTestData``: Django deep-copies every class
    attribute set there, and a module object cannot be deep-copied.
    """
    return importlib.import_module(
        'apps.risk_assessment.migrations.0005_backfill_region_service_center'
    )


class OrgScopeBackfillTest(TestCase):
    """The data migration that split geographic units out of ``department``.

    Records used to store whichever node of the corporate tree the user drilled
    down to, so a service center or a region could sit in ``department``. The
    migration (apps/risk_assessment/migrations/0005) moves those into the
    ``region`` / ``service_center`` columns and re-points ``department`` at the
    chief office they sit under. Its ``_split`` helper is exercised directly —
    running the migration itself would mean replaying the whole graph.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ceo = Department.objects.create(
            name='CEO Office', code='CEO', unit_type=Department.EXECUTIVE,
        )
        cls.coordination = Department.objects.create(
            name='Region Coordination', code='RGN Coordination',
            unit_type=Department.CORPORATE, parent=cls.ceo,
        )
        cls.finance = Department.objects.create(
            name='Finance', code='Finance',
            unit_type=Department.CORPORATE, parent=cls.ceo,
        )
        cls.region = Department.objects.create(
            name='Adama Region', code='RGN-BA',
            unit_type=Department.REGION, parent=cls.coordination,
        )
        cls.center = Department.objects.create(
            name='Adama CSC No.1', code='CSC-BA01',
            unit_type=Department.SERVICE_CENTER, parent=cls.region,
        )

    def setUp(self):
        self.split = _backfill_migration()._split
        self.by_id = {d.pk: d for d in Department.objects.all()}

    def test_a_stored_service_center_splits_into_region_and_center(self):
        region, center, chief = self.split(self.center, self.by_id)
        self.assertEqual(region, self.region)
        self.assertEqual(center, self.center)
        # Region Coordination, not the service center or the region itself.
        self.assertEqual(chief, self.coordination)

    def test_a_stored_region_splits_with_no_service_center(self):
        region, center, chief = self.split(self.region, self.by_id)
        self.assertEqual(region, self.region)
        self.assertIsNone(center)
        self.assertEqual(chief, self.coordination)

    def test_a_chief_office_resolves_to_itself(self):
        """A row already pointing at Finance has nothing to split."""
        region, center, chief = self.split(self.finance, self.by_id)
        self.assertIsNone(region)
        self.assertIsNone(center)
        self.assertEqual(chief, self.finance)

    def test_a_broken_chain_does_not_invent_a_scope(self):
        """``parent`` is SET_NULL, so an orphan must not be re-pointed blindly.

        With nothing above it the walk finds only the unit itself, so it comes
        back as its own chief office. That equality is the signal ``_backfill``
        reads to skip the row — without it the record would be rewritten to
        point at itself, dropping whatever the service center column held.
        """
        orphan = Department.objects.create(
            name='Detached CSC', code='CSC-ORPHAN',
            unit_type=Department.SERVICE_CENTER, parent=None,
        )
        by_id = {d.pk: d for d in Department.objects.all()}
        region, _center, chief = self.split(orphan, by_id)
        self.assertIsNone(region)
        self.assertEqual(chief.pk, orphan.pk)
