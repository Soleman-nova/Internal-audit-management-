"""Tests for the organisational-unit tree: pagination, the picker endpoint, and
the service-center seed.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role
from apps.accounts.management.commands.seed_service_centers import (
    CSC_CODE_PREFIX, is_amharic, repair_mojibake,
)
from apps.accounts.management.commands.seed_org_structure import REGION_CODE_PREFIX

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
