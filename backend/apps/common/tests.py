"""
Tests for the RBAC capability matrix and permission classes.
"""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.accounts.models import Department, Role
from apps.common.permissions import (
    has_capability, MANAGE_USERS, MANAGE_SETTINGS, APPROVE_PLANS,
    WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL
)
from apps.common.validators import (
    MAX_DOCUMENT_SIZE, MAX_IMAGE_SIZE, UploadValidator,
    validate_document_upload, validate_image_upload,
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


class UploadValidatorTest(SimpleTestCase):
    """The extension allowlist and size cap in apps/common/validators.py.

    Every file field in the system was a bare FileField: no allowlist, no cap.
    Auditees can reach ``upload-evidence`` by design, so that was an
    authenticated arbitrary-file store. Unit-level here, with a stub standing in
    for the uploaded file — the two attributes the validator reads are ``name``
    and ``size``, and stubbing them keeps the size cases from allocating 10 MB.
    """

    class Stub:
        def __init__(self, name, size=0):
            self.name = name
            self.size = size

    def assert_rejected(self, validator, stub, code):
        with self.assertRaises(ValidationError) as caught:
            validator(stub)
        self.assertEqual(caught.exception.code, code)

    # ── Extensions ───────────────────────────────────────────────────────
    def test_an_executable_is_rejected(self):
        self.assert_rejected(
            validate_document_upload, self.Stub('payroll.exe', 1024),
            'invalid_extension',
        )

    def test_the_formats_an_audit_actually_attaches_are_accepted(self):
        for name in ('ledger.pdf', 'sample.xlsx', 'memo.docx', 'export.csv',
                     'scan.jpg', 'bundle.zip', 'notes.txt'):
            with self.subTest(name=name):
                validate_document_upload(self.Stub(name, 1024))

    def test_the_extension_check_is_case_insensitive(self):
        """Windows clients routinely send SCAN.PDF."""
        validate_document_upload(self.Stub('SCAN.PDF', 1024))

    def test_a_file_with_no_extension_is_rejected(self):
        self.assert_rejected(
            validate_document_upload, self.Stub('Makefile', 10),
            'invalid_extension',
        )

    def test_only_the_final_extension_counts(self):
        """``report.pdf.exe`` is an executable, whatever the middle segment says."""
        self.assert_rejected(
            validate_document_upload, self.Stub('report.pdf.exe', 10),
            'invalid_extension',
        )

    def test_the_rejection_message_names_the_allowed_types(self):
        """The auditee who picked the wrong file needs to know what to pick."""
        with self.assertRaises(ValidationError) as caught:
            validate_document_upload(self.Stub('macro.xlsm', 10))
        message = str(caught.exception)
        self.assertIn('xlsm', message)
        self.assertIn('xlsx', message)

    # ── Size ─────────────────────────────────────────────────────────────
    def test_a_document_over_the_cap_is_rejected(self):
        self.assert_rejected(
            validate_document_upload, self.Stub('dump.pdf', MAX_DOCUMENT_SIZE + 1),
            'file_too_large',
        )

    def test_a_document_exactly_at_the_cap_is_accepted(self):
        """The boundary is inclusive — 10.0 MB exactly must not be refused."""
        validate_document_upload(self.Stub('dump.pdf', MAX_DOCUMENT_SIZE))

    def test_the_size_message_reports_megabytes_not_bytes(self):
        with self.assertRaises(ValidationError) as caught:
            validate_document_upload(self.Stub('dump.pdf', 50 * 1024 * 1024))
        self.assertIn('50.0 MB', str(caught.exception))
        self.assertIn('10.0 MB', str(caught.exception))

    def test_a_missing_size_is_not_treated_as_zero_or_as_a_failure(self):
        """A FileField re-validated from storage may expose no size; the
        extension check still has to run and must not raise on the size branch."""
        validate_document_upload(self.Stub('ledger.pdf', None))

    # ── The avatar variant ───────────────────────────────────────────────
    def test_the_avatar_validator_is_narrower_than_the_document_one(self):
        """A real TIFF is a valid image as far as ImageField is concerned, so the
        allowlist is the only thing keeping a 40 MB scan out of the nav bar."""
        validate_document_upload(self.Stub('scan.tiff', 1024))
        self.assert_rejected(
            validate_image_upload, self.Stub('scan.tiff', 1024), 'invalid_extension',
        )
        self.assert_rejected(
            validate_image_upload, self.Stub('cv.pdf', 1024), 'invalid_extension',
        )
        validate_image_upload(self.Stub('portrait.png', 1024))

    def test_the_avatar_cap_is_tighter_than_the_document_cap(self):
        self.assertLess(MAX_IMAGE_SIZE, MAX_DOCUMENT_SIZE)
        self.assert_rejected(
            validate_image_upload, self.Stub('portrait.png', MAX_IMAGE_SIZE + 1),
            'file_too_large',
        )

    # ── Migration safety ─────────────────────────────────────────────────
    def test_two_validators_with_the_same_settings_compare_equal(self):
        """Without __eq__, Django reads the field as changed on every run and
        ``makemigrations`` emits an identical migration each time."""
        self.assertEqual(validate_document_upload, UploadValidator())
        self.assertEqual(
            hash(validate_document_upload), hash(UploadValidator()),
        )
        self.assertNotEqual(validate_document_upload, validate_image_upload)

    def test_the_validator_deconstructs_to_an_importable_path(self):
        path, args, kwargs = validate_image_upload.deconstruct()
        self.assertEqual(path, 'apps.common.validators.UploadValidator')
        # Reconstructing from the deconstructed form must round-trip, which is
        # exactly what the migration file does at load time.
        rebuilt = UploadValidator(*args, **kwargs)
        self.assertEqual(rebuilt, validate_image_upload)
