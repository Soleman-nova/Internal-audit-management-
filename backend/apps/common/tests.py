"""
Tests for the RBAC capability matrix and permission classes.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.accounts.models import Department, Role
from apps.common.permissions import (
    has_capability, MANAGE_USERS, MANAGE_SETTINGS, APPROVE_PLANS,
    WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL
)

User = get_user_model()


class CapabilityMatrixTest(TestCase):
    """Test the capability-matrix helper function."""

    def setUp(self):
        self.dept = Department.objects.create(name='Test Dept', code='TST')
        self.admin = User.objects.create_user(
            username='admin', employee_id='E001', email='admin@test.com',
            password='pass', role=Role.ADMIN, department=self.dept
        )
        self.manager = User.objects.create_user(
            username='manager', employee_id='E002', email='manager@test.com',
            password='pass', role=Role.AUDIT_MANAGER, department=self.dept
        )
        self.supervisor = User.objects.create_user(
            username='supervisor', employee_id='E003', email='supervisor@test.com',
            password='pass', role=Role.SUPERVISOR, department=self.dept
        )
        self.auditor = User.objects.create_user(
            username='auditor', employee_id='E004', email='auditor@test.com',
            password='pass', role=Role.AUDITOR, department=self.dept
        )
        self.auditee = User.objects.create_user(
            username='auditee', employee_id='E005', email='auditee@test.com',
            password='pass', role=Role.AUDITEE, department=self.dept
        )

    def test_admin_has_all_capabilities(self):
        self.assertTrue(has_capability(self.admin, MANAGE_USERS))
        self.assertTrue(has_capability(self.admin, MANAGE_SETTINGS))
        self.assertTrue(has_capability(self.admin, APPROVE_PLANS))
        self.assertTrue(has_capability(self.admin, WRITE_AUDIT))
        self.assertTrue(has_capability(self.admin, CLOSE_FINDINGS))
        self.assertTrue(has_capability(self.admin, VIEW_AUDIT_TRAIL))

    def test_audit_manager_capabilities(self):
        self.assertFalse(has_capability(self.manager, MANAGE_USERS))
        self.assertTrue(has_capability(self.manager, MANAGE_SETTINGS))
        self.assertTrue(has_capability(self.manager, APPROVE_PLANS))
        self.assertTrue(has_capability(self.manager, WRITE_AUDIT))
        self.assertTrue(has_capability(self.manager, CLOSE_FINDINGS))
        self.assertTrue(has_capability(self.manager, VIEW_AUDIT_TRAIL))

    def test_supervisor_capabilities(self):
        self.assertFalse(has_capability(self.supervisor, MANAGE_USERS))
        self.assertFalse(has_capability(self.supervisor, MANAGE_SETTINGS))
        self.assertTrue(has_capability(self.supervisor, APPROVE_PLANS))
        self.assertTrue(has_capability(self.supervisor, WRITE_AUDIT))
        self.assertTrue(has_capability(self.supervisor, CLOSE_FINDINGS))
        self.assertTrue(has_capability(self.supervisor, VIEW_AUDIT_TRAIL))

    def test_auditor_capabilities(self):
        self.assertFalse(has_capability(self.auditor, MANAGE_USERS))
        self.assertFalse(has_capability(self.auditor, MANAGE_SETTINGS))
        self.assertFalse(has_capability(self.auditor, APPROVE_PLANS))
        self.assertTrue(has_capability(self.auditor, WRITE_AUDIT))
        self.assertTrue(has_capability(self.auditor, CLOSE_FINDINGS))
        self.assertFalse(has_capability(self.auditor, VIEW_AUDIT_TRAIL))

    def test_auditee_has_no_capabilities(self):
        self.assertFalse(has_capability(self.auditee, MANAGE_USERS))
        self.assertFalse(has_capability(self.auditee, MANAGE_SETTINGS))
        self.assertFalse(has_capability(self.auditee, APPROVE_PLANS))
        self.assertFalse(has_capability(self.auditee, WRITE_AUDIT))
        self.assertFalse(has_capability(self.auditee, CLOSE_FINDINGS))
        self.assertFalse(has_capability(self.auditee, VIEW_AUDIT_TRAIL))


class RBACAPITest(TestCase):
    """Integration tests for API-level RBAC enforcement."""

    def setUp(self):
        self.dept = Department.objects.create(name='Finance', code='FIN')
        self.admin = User.objects.create_user(
            username='admin', employee_id='A001', email='admin@test.com',
            password='admin123', role=Role.ADMIN, department=self.dept
        )
        self.auditor = User.objects.create_user(
            username='auditor', employee_id='A002', email='auditor@test.com',
            password='user123', role=Role.AUDITOR, department=self.dept
        )
        self.auditee = User.objects.create_user(
            username='auditee', employee_id='A003', email='auditee@test.com',
            password='user123', role=Role.AUDITEE, department=self.dept
        )
        self.client = APIClient()

    def test_admin_can_create_user(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/auth/users/', {
            'username': 'newuser',
            'employee_id': 'A999',
            'email': 'new@test.com',
            'password': 'testpass123',
            'role': Role.AUDITOR,
            'department': self.dept.id,
        })
        self.assertEqual(response.status_code, 201)

    def test_auditor_cannot_create_user(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.post('/api/auth/users/', {
            'username': 'blocked',
            'employee_id': 'B001',
            'email': 'blocked@test.com',
            'password': 'testpass123',
            'role': Role.AUDITOR,
            'department': self.dept.id,
        })
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_create_audit_record(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.post('/api/planning/universe/', {
            'name': 'Test Process',
            'code': 'TST-001',
            'category': 'process',
            'risk_score': 3.5,
            'audit_frequency': 'Annually',
            'owner': 'Process Owner',
            'department': self.dept.id,
            'status': 'active',
        })
        self.assertEqual(response.status_code, 201)

    def test_auditee_cannot_create_audit_record(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.post('/api/planning/universe/', {
            'name': 'Blocked Process',
            'code': 'BLK-001',
            'category': 'process',
            'risk_score': 2.0,
            'audit_frequency': 'Annually',
            'owner': 'Owner',
            'department': self.dept.id,
            'status': 'active',
        })
        self.assertEqual(response.status_code, 403)

    def test_auditee_can_read_audit_records(self):
        self.client.force_authenticate(user=self.auditee)
        response = self.client.get('/api/planning/universe/')
        self.assertEqual(response.status_code, 200)

    def test_auditor_cannot_view_audit_trail(self):
        self.client.force_authenticate(user=self.auditor)
        response = self.client.get('/api/auth/audit-trail/')
        self.assertEqual(response.status_code, 403)
