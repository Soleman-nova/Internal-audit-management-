from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import AuditTrail, Department, Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'unit_type', 'directorate_type', 'parent', 'is_active')
    list_filter = ('unit_type', 'directorate_type', 'is_active')
    search_fields = ('name', 'name_am', 'code', 'head')
    autocomplete_fields = ('parent',)
    ordering = ('name',)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the EEU custom User (logs in via employee_id).

    ``username`` is retained from AbstractUser and required by the app's own
    creation flow, so it stays in the forms; ``employee_id`` is surfaced as the
    primary login identifier.
    """
    ordering = ('employee_id',)
    list_display = ('employee_id', 'full_name', 'email', 'role', 'department',
                    'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('employee_id', 'username', 'email', 'first_name', 'last_name', 'phone')
    autocomplete_fields = ('department',)
    readonly_fields = ('last_login_ip', 'created_at', 'updated_at')
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('EEU Details', {
            'fields': ('employee_id', 'role', 'department', 'phone',
                       'last_login_ip', 'created_at', 'updated_at'),
        }),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('EEU Details', {
            'classes': ('wide',),
            'fields': ('employee_id', 'email', 'first_name', 'last_name',
                       'role', 'department', 'phone'),
        }),
    )


@admin.register(AuditTrail)
class AuditTrailAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'model_name', 'object_repr', 'ip_address', 'timestamp')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('user__employee_id', 'user__email', 'model_name',
                     'object_id', 'object_repr', 'ip_address')
    readonly_fields = ('user', 'action', 'model_name', 'object_id', 'object_repr',
                       'changes', 'ip_address', 'user_agent', 'timestamp')
