from django.contrib import admin

from .models import GeneratedReport, ReportTemplate


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'is_default', 'created_by', 'created_at')
    list_filter = ('template_type', 'is_default')
    search_fields = ('name', 'description')
    autocomplete_fields = ('created_by',)


@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'template', 'engagement', 'format', 'status',
                    'generated_by', 'generated_at')
    list_filter = ('status', 'format')
    search_fields = ('title',)
    autocomplete_fields = ('template', 'engagement', 'generated_by')
    readonly_fields = ('generated_at',)
