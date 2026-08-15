from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    ADMIN = 'admin'
    AUDIT_MANAGER = 'audit_manager'
    AUDITOR = 'auditor'
    AUDITEE = 'auditee'
    SUPERVISOR = 'supervisor'

    ROLE_CHOICES = [
        (ADMIN, 'Administrator'),
        (AUDIT_MANAGER, 'Audit Manager'),
        (AUDITOR, 'Auditor'),
        (AUDITEE, 'Auditee'),
        (SUPERVISOR, 'Audit Supervisor'),
    ]

    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_name_display()

    class Meta:
        ordering = ['name']


class Department(models.Model):
    """Department / Directorate within EEU.

    Supports the official EEU Internal Audit Executive Office structure:
    the Internal Audit Executive Office (IAEO) is the parent node that
    oversees four core directorates:
      - Financial & Performance Audit (FPA)
      - Technical Audit (TA)
      - Information Technology Audit (ITA)
      - Planning & Performance (PP)
    """

    DIRECTORATE_CHOICES = [
        ('IAEO', 'Internal Audit Executive Office'),
        ('FPA', 'Financial & Performance Audit Directorate'),
        ('TA', 'Technical Audit Directorate'),
        ('ITA', 'Information Technology Audit Directorate'),
        ('PP', 'Planning & Performance Directorate'),
        ('OTHER', 'Other / Non-Directorate'),
    ]

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    head = models.CharField(max_length=200, blank=True)
    directorate_type = models.CharField(
        max_length=20,
        choices=DIRECTORATE_CHOICES,
        default='OTHER',
        help_text='Explicit EEU Internal Audit directorate classification.',
    )
    staff_count = models.PositiveIntegerField(default=0, help_text='Number of staff assigned to this directorate.')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=50,
        choices=Role.ROLE_CHOICES,
        default=Role.AUDITOR
    )
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    employee_id = models.CharField(max_length=50, unique=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'employee_id'
    REQUIRED_FIELDS = ['username', 'email', 'first_name', 'last_name']

    def __str__(self):
        return f"{self.get_full_name()} ({self.employee_id})"

    @property
    def full_name(self):
        return self.get_full_name() or self.email

    class Meta:
        ordering = ['first_name', 'last_name']


class AuditTrail(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('VIEW', 'View'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('EXPORT', 'Export'),
        ('APPROVE', 'Approve'),
        ('REJECT', 'Reject'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=300, blank=True)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} - {self.model_name} - {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']