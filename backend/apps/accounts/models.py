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
    """Organizational unit within EEU — chief office, audit directorate, region, or service center.

    Two structures share this model, distinguished by ``unit_type``:

    1. The corporate structure (``EXECUTIVE`` / ``CORPORATE`` / ``REGION`` /
       ``SERVICE_CENTER``): the Chief Executive Officer office at the root, the
       chief offices reporting to it, the 32 EEU regions under Region
       Coordination, and the customer service centers under each region.
    2. The Internal Audit Executive Office structure (``AUDIT``): the IAEO
       node and the four core directorates it oversees:
         - Financial & Performance Audit (FPA)
         - Technical Audit (TA)
         - Information Technology Audit (ITA)
         - Planning & Performance (PP)

    Regions and service centers are modelled as departments rather than
    separate tables so that users, audit universe entries, engagements, and
    risk assessments can point at any level of the organisation through the
    department foreign keys they already have. The forms present the three
    corporate levels as a cascading picker (department → region → service
    center) and store whichever node the user drilled down to.
    """

    DIRECTORATE_CHOICES = [
        ('IAEO', 'Internal Audit Executive Office'),
        ('FPA', 'Financial & Performance Audit Directorate'),
        ('TA', 'Technical Audit Directorate'),
        ('ITA', 'Information Technology Audit Directorate'),
        ('PP', 'Planning & Performance Directorate'),
        ('OTHER', 'Other / Non-Directorate'),
    ]

    EXECUTIVE = 'EXECUTIVE'
    CORPORATE = 'CORPORATE'
    AUDIT = 'AUDIT'
    REGION = 'REGION'
    SERVICE_CENTER = 'SERVICE_CENTER'

    UNIT_TYPE_CHOICES = [
        (EXECUTIVE, 'Executive Office'),
        (CORPORATE, 'Corporate Department / Chief Office'),
        (AUDIT, 'Internal Audit Directorate'),
        (REGION, 'Region'),
        (SERVICE_CENTER, 'Customer Service Center'),
    ]

    name = models.CharField(max_length=200)
    name_am = models.CharField(
        max_length=200,
        blank=True,
        help_text='Amharic name, shown when the interface language is Amharic.',
    )
    code = models.CharField(max_length=20, unique=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    head = models.CharField(max_length=200, blank=True)
    head_title = models.CharField(
        max_length=200,
        blank=True,
        help_text='Title of the officer leading this unit, e.g. "Chief Finance officer".',
    )
    head_title_am = models.CharField(max_length=200, blank=True, help_text='Amharic officer title.')
    unit_type = models.CharField(
        max_length=20,
        choices=UNIT_TYPE_CHOICES,
        default=CORPORATE,
        help_text=(
            'Where this unit sits in the EEU organizational structure. The '
            'corporate side nests three deep: chief office -> region -> '
            'customer service center.'
        ),
    )
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