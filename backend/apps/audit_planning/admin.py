from django.contrib import admin

from .models import (AuditEngagement, AuditPlan, AuditTeamMember,
                     AuditUniverse, Project)


class AuditTeamMemberInline(admin.TabularInline):
    model = AuditTeamMember
    extra = 0
    autocomplete_fields = ('user',)
    readonly_fields = ('joined_at',)


@admin.register(AuditUniverse)
class AuditUniverseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'department', 'directorate',
                    'risk_score', 'audit_frequency', 'status')
    list_filter = ('category', 'status')
    search_fields = ('code', 'name', 'owner', 'description')
    autocomplete_fields = ('department', 'directorate')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AuditPlan)
class AuditPlanAdmin(admin.ModelAdmin):
    list_display = ('title', 'year', 'plan_scope', 'status', 'directorate',
                    'approved_by', 'approved_at')
    list_filter = ('status', 'plan_scope', 'year')
    search_fields = ('title', 'description', 'objectives')
    autocomplete_fields = ('directorate', 'parent_plan', 'created_by', 'approved_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AuditEngagement)
class AuditEngagementAdmin(admin.ModelAdmin):
    list_display = ('engagement_number', 'title', 'engagement_type', 'status',
                    'plan', 'lead_auditor', 'risk_level')
    list_filter = ('status', 'engagement_type', 'risk_level')
    search_fields = ('engagement_number', 'title', 'objectives')
    autocomplete_fields = ('plan', 'audit_universe', 'department', 'directorate',
                           'lead_auditor', 'supervisor')
    inlines = [AuditTeamMemberInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AuditTeamMember)
class AuditTeamMemberAdmin(admin.ModelAdmin):
    list_display = ('engagement', 'user', 'role', 'allocated_days', 'joined_at')
    list_filter = ('role',)
    search_fields = ('engagement__engagement_number', 'user__employee_id', 'user__email')
    autocomplete_fields = ('engagement', 'user')
    readonly_fields = ('joined_at',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'updated_at')
    search_fields = ('code', 'name')
    autocomplete_fields = ('department',)
    readonly_fields = ('created_at', 'updated_at')
