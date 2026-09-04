from django.contrib import admin

from .models import RiskAssessment, RiskParameter, SelfAssessment


@admin.register(RiskParameter)
class RiskParameterAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'weight', 'is_active', 'created_by')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'description')
    autocomplete_fields = ('created_by',)


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    # Scores are recomputed by the model on save (weighted parameters, control
    # effectiveness), so they are surfaced read-only rather than hand-editable.
    list_display = ('department', 'audit_universe', 'year', 'assessment_period',
                    'risk_score', 'risk_rating', 'is_self_assessment', 'assessed_by')
    list_filter = ('year', 'assessment_period', 'risk_rating', 'is_self_assessment')
    search_fields = ('department__name', 'department__code', 'notes')
    autocomplete_fields = ('department', 'audit_universe', 'assessed_by', 'reviewed_by')
    readonly_fields = ('risk_score', 'risk_rating', 'inherent_risk', 'residual_risk',
                       'created_at', 'updated_at')


@admin.register(SelfAssessment)
class SelfAssessmentAdmin(admin.ModelAdmin):
    list_display = ('risk_assessment', 'submitted_by', 'status', 'submitted_at',
                    'reviewed_by', 'reviewed_at')
    list_filter = ('status',)
    search_fields = ('justification', 'mitigating_controls')
    autocomplete_fields = ('risk_assessment', 'submitted_by', 'reviewed_by')
    readonly_fields = ('submitted_at',)
