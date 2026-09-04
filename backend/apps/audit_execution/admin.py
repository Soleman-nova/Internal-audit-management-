from django.contrib import admin

from .models import AuditProcedure, AuditProgram, WorkingPaper


@admin.register(AuditProgram)
class AuditProgramAdmin(admin.ModelAdmin):
    list_display = ('title', 'engagement', 'status', 'version', 'prepared_by', 'approved_at')
    list_filter = ('status',)
    search_fields = ('title', 'objectives', 'scope')
    autocomplete_fields = ('engagement', 'prepared_by', 'reviewed_by', 'approved_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AuditProcedure)
class AuditProcedureAdmin(admin.ModelAdmin):
    list_display = ('step_number', 'title', 'program', 'procedure_type', 'status',
                    'assigned_to', 'is_template', 'order')
    list_filter = ('status', 'procedure_type', 'is_template')
    search_fields = ('step_number', 'title', 'description', 'risk_area')
    autocomplete_fields = ('program', 'assigned_to', 'completed_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WorkingPaper)
class WorkingPaperAdmin(admin.ModelAdmin):
    list_display = ('reference', 'title', 'engagement', 'paper_type',
                    'prepared_by', 'is_reviewed')
    list_filter = ('paper_type', 'is_reviewed')
    search_fields = ('reference', 'title', 'description')
    autocomplete_fields = ('engagement', 'procedure', 'prepared_by', 'reviewed_by')
    readonly_fields = ('created_at', 'updated_at')
