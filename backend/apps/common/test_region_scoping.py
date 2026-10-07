"""Read-scoping and visibility tests for regional FPA auditors and the
Regional Coordination Audit Manager.

Regional FPA audit units (``FPA-RGN-*``) carry a foreign key to the corporate
``REGION`` department they audit. Users belonging to such units are confined
by ``RegionScopeMixin`` / ``region_for`` to records tagged with that region.
Meanwhile, HQ staff (``FPA-STAFF``) and the Regional Coordination Audit
Manager (``FPA-RAC``) have no region constraint on their department and
retain full organization-wide visibility.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role
from apps.common.role_fixtures import (
    make_action,
    make_engagement,
    make_finding,
    make_universe,
    next_seq,
)
from apps.common.scoping import region_for

User = get_user_model()


def ids_on(response):
    """Row ids from a DRF response, paginated or not."""
    data = response.data
    rows = data['results'] if isinstance(data, dict) else data
    return {row['id'] for row in rows}


class RegionScopingTest(TestCase):
    """Test read-scoping across registers for regional FPA auditors vs HQ/Coordination."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        seq = next_seq()

        # Corporate Region Departments
        cls.coordination_dept = Department.objects.create(
            name=f'Corporate Region Coordination {seq}',
            code=f'RGN-COORD-{seq}',
            unit_type=Department.CORPORATE,
        )
        cls.region_adama = Department.objects.create(
            name=f'Adama Region {seq}',
            code=f'RGN-ADAMA-{seq}',
            unit_type=Department.REGION,
            parent=cls.coordination_dept,
        )
        cls.region_hawassa = Department.objects.create(
            name=f'Hawassa Region {seq}',
            code=f'RGN-HAWASSA-{seq}',
            unit_type=Department.REGION,
            parent=cls.coordination_dept,
        )

        # Audit Directorate and Subdivided Units
        cls.iaeo = Department.objects.create(
            name=f'IAEO {seq}',
            code=f'IAEO-{seq}',
            unit_type=Department.AUDIT,
            directorate_type='IAEO',
        )
        cls.fpa_directorate = Department.objects.create(
            name=f'Financial & Performance Audit Directorate {seq}',
            code=f'FPA-{seq}',
            unit_type=Department.AUDIT,
            directorate_type='FPA',
            parent=cls.iaeo,
        )
        cls.fpa_staff_dept = Department.objects.create(
            name=f'FPA Staff {seq}',
            code=f'FPA-STAFF-{seq}',
            unit_type=Department.AUDIT,
            directorate_type='FPA',
            parent=cls.fpa_directorate,
            region=None,
        )
        cls.fpa_rac_dept = Department.objects.create(
            name=f'Regional Audit Coordination {seq}',
            code=f'FPA-RAC-{seq}',
            unit_type=Department.AUDIT,
            directorate_type='FPA',
            parent=cls.fpa_directorate,
            region=None,
        )
        cls.fpa_adama_dept = Department.objects.create(
            name=f'Adama FPA Audit {seq}',
            code=f'FPA-RGN-ADAMA-{seq}',
            unit_type=Department.AUDIT,
            directorate_type='FPA',
            parent=cls.fpa_rac_dept,
            region=cls.region_adama,
        )
        cls.fpa_hawassa_dept = Department.objects.create(
            name=f'Hawassa FPA Audit {seq}',
            code=f'FPA-RGN-HAWASSA-{seq}',
            unit_type=Department.AUDIT,
            directorate_type='FPA',
            parent=cls.fpa_rac_dept,
            region=cls.region_hawassa,
        )

        # Users
        cls.auditor_adama = User.objects.create_user(
            username=f'auditor-adama-{seq}',
            employee_id=f'RAD-{seq}',
            email=f'auditor-adama-{seq}@eeu.et',
            password='pass',
            role=Role.AUDITOR,
            department=cls.fpa_adama_dept,
        )
        cls.auditor_hawassa = User.objects.create_user(
            username=f'auditor-hawassa-{seq}',
            employee_id=f'RHW-{seq}',
            email=f'auditor-hawassa-{seq}@eeu.et',
            password='pass',
            role=Role.AUDITOR,
            department=cls.fpa_hawassa_dept,
        )
        cls.manager_rac = User.objects.create_user(
            username=f'manager-rac-{seq}',
            employee_id=f'RAC-{seq}',
            email=f'manager-rac-{seq}@eeu.et',
            password='pass',
            role=Role.AUDIT_MANAGER,
            department=cls.fpa_rac_dept,
        )
        cls.auditor_hq = User.objects.create_user(
            username=f'auditor-hq-{seq}',
            employee_id=f'HQ-{seq}',
            email=f'auditor-hq-{seq}@eeu.et',
            password='pass',
            role=Role.AUDITOR,
            department=cls.fpa_staff_dept,
        )

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def test_region_for_helper(self):
        """region_for resolves to the department's region_id or None."""
        self.assertIsNone(region_for(None))
        self.assertIsNone(region_for(self.auditor_hq))
        self.assertIsNone(region_for(self.manager_rac))
        self.assertEqual(region_for(self.auditor_adama), self.region_adama.id)
        self.assertEqual(region_for(self.auditor_hawassa), self.region_hawassa.id)

    def test_universe_scoping(self):
        """Regional auditor sees only their region's universe items; RAC manager sees all."""
        u_adama = make_universe(region=self.region_adama)
        u_hawassa = make_universe(region=self.region_hawassa)

        # Adama auditor
        resp = self.as_user(self.auditor_adama).get('/api/planning/universe/')
        seen = ids_on(resp)
        self.assertIn(u_adama.id, seen)
        self.assertNotIn(u_hawassa.id, seen)

        # Detail route 404 for other region
        detail_ok = self.as_user(self.auditor_adama).get(f'/api/planning/universe/{u_adama.id}/')
        self.assertEqual(detail_ok.status_code, 200)
        detail_hidden = self.as_user(self.auditor_adama).get(f'/api/planning/universe/{u_hawassa.id}/')
        self.assertEqual(detail_hidden.status_code, 404)

        # Regional Coordination Manager sees both
        resp_mgr = self.as_user(self.manager_rac).get('/api/planning/universe/')
        seen_mgr = ids_on(resp_mgr)
        self.assertIn(u_adama.id, seen_mgr)
        self.assertIn(u_hawassa.id, seen_mgr)

    def test_engagements_scoping(self):
        """Regional auditor sees only their region's engagements; RAC manager sees all."""
        eng_adama = make_engagement(region=self.region_adama)
        eng_hawassa = make_engagement(region=self.region_hawassa)

        # Adama auditor
        resp = self.as_user(self.auditor_adama).get('/api/planning/engagements/')
        seen = ids_on(resp)
        self.assertIn(eng_adama.id, seen)
        self.assertNotIn(eng_hawassa.id, seen)

        # Detail route
        self.assertEqual(
            self.as_user(self.auditor_adama).get(f'/api/planning/engagements/{eng_adama.id}/').status_code,
            200,
        )
        self.assertEqual(
            self.as_user(self.auditor_adama).get(f'/api/planning/engagements/{eng_hawassa.id}/').status_code,
            404,
        )

        # RAC Manager sees both
        seen_mgr = ids_on(self.as_user(self.manager_rac).get('/api/planning/engagements/'))
        self.assertIn(eng_adama.id, seen_mgr)
        self.assertIn(eng_hawassa.id, seen_mgr)

    def test_findings_scoping(self):
        """Regional auditor sees only findings from engagements in their region."""
        eng_adama = make_engagement(region=self.region_adama)
        eng_hawassa = make_engagement(region=self.region_hawassa)

        fnd_adama = make_finding(engagement=eng_adama)
        fnd_hawassa = make_finding(engagement=eng_hawassa)

        # Adama auditor
        seen = ids_on(self.as_user(self.auditor_adama).get('/api/findings/findings/'))
        self.assertIn(fnd_adama.id, seen)
        self.assertNotIn(fnd_hawassa.id, seen)

        self.assertEqual(
            self.as_user(self.auditor_adama).get(f'/api/findings/findings/{fnd_adama.id}/').status_code,
            200,
        )
        self.assertEqual(
            self.as_user(self.auditor_adama).get(f'/api/findings/findings/{fnd_hawassa.id}/').status_code,
            404,
        )

        # RAC Manager sees both
        seen_mgr = ids_on(self.as_user(self.manager_rac).get('/api/findings/findings/'))
        self.assertIn(fnd_adama.id, seen_mgr)
        self.assertIn(fnd_hawassa.id, seen_mgr)

    def test_corrective_actions_scoping(self):
        """Regional auditor sees only CAPAs tied to findings in their region."""
        eng_adama = make_engagement(region=self.region_adama)
        eng_hawassa = make_engagement(region=self.region_hawassa)

        fnd_adama = make_finding(engagement=eng_adama)
        fnd_hawassa = make_finding(engagement=eng_hawassa)

        capa_adama = make_action(finding=fnd_adama)
        capa_hawassa = make_action(finding=fnd_hawassa)

        # Adama auditor
        seen = ids_on(self.as_user(self.auditor_adama).get('/api/corrective/actions/'))
        self.assertIn(capa_adama.id, seen)
        self.assertNotIn(capa_hawassa.id, seen)

        self.assertEqual(
            self.as_user(self.auditor_adama).get(f'/api/corrective/actions/{capa_adama.id}/').status_code,
            200,
        )
        self.assertEqual(
            self.as_user(self.auditor_adama).get(f'/api/corrective/actions/{capa_hawassa.id}/').status_code,
            404,
        )

        # RAC Manager sees both
        seen_mgr = ids_on(self.as_user(self.manager_rac).get('/api/corrective/actions/'))
        self.assertIn(capa_adama.id, seen_mgr)
        self.assertIn(capa_hawassa.id, seen_mgr)

    def test_dashboard_stats_region_scoping(self):
        """Dashboard stats counts are narrowed to the region for regional auditors."""
        eng_adama = make_engagement(region=self.region_adama)
        eng_hawassa = make_engagement(region=self.region_hawassa)

        make_finding(engagement=eng_adama)
        make_finding(engagement=eng_hawassa)

        resp_adama = self.as_user(self.auditor_adama).get('/api/auth/dashboard/stats/')
        self.assertEqual(resp_adama.status_code, 200)
        # Regional counts should only reflect Adama
        self.assertEqual(resp_adama.data['total_engagements'], 1)
        self.assertEqual(resp_adama.data['total_findings'], 1)

        # Regional Coordination Manager sees both
        resp_rac = self.as_user(self.manager_rac).get('/api/auth/dashboard/stats/')
        self.assertEqual(resp_rac.status_code, 200)
        self.assertGreaterEqual(resp_rac.data['total_engagements'], 2)
        self.assertGreaterEqual(resp_rac.data['total_findings'], 2)

    def test_fpa_subdivision_seed_structure(self):
        """seed_eeu_audit_structure creates FPA-STAFF, FPA-RAC, and 32 regional units."""
        from django.core.management import call_command
        from apps.accounts.management.commands.seed_org_structure import REGIONS

        call_command('seed_org_structure')
        call_command('seed_eeu_audit_structure')

        fpa = Department.objects.get(code='FPA')
        staff = Department.objects.get(code='FPA-STAFF')
        self.assertEqual(staff.parent, fpa)
        self.assertEqual(staff.unit_type, Department.AUDIT)
        self.assertEqual(staff.directorate_type, 'FPA')
        self.assertIsNone(staff.region)

        rac = Department.objects.get(code='FPA-RAC')
        self.assertEqual(rac.parent, fpa)
        self.assertEqual(rac.unit_type, Department.AUDIT)
        self.assertEqual(rac.directorate_type, 'FPA')
        self.assertIsNone(rac.region)

        # Check regional units created by the seed
        seeded_codes = [f'FPA-RGN-{suffix}' for suffix, _name, _am in REGIONS]
        regional_units = Department.objects.filter(code__in=seeded_codes)
        self.assertEqual(regional_units.count(), len(REGIONS))
        for reg_unit in regional_units:
            self.assertEqual(reg_unit.parent, rac)
            self.assertEqual(reg_unit.unit_type, Department.AUDIT)
            self.assertEqual(reg_unit.directorate_type, 'FPA')
            self.assertIsNotNone(reg_unit.region)
            self.assertEqual(reg_unit.region.unit_type, Department.REGION)
