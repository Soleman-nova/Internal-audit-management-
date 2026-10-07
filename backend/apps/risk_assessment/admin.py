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
    # Same for the frozen-policy columns: they record what the model computed,
    # and ``is_stale`` tells an administrator whether a recompute is due.
    list_display = ('department', 'audit_universe', 'year', 'assessment_period',
                    'risk_score', 'risk_rating', 'adopted_source', 'is_stale_display',
                    'is_self_assessment', 'assessed_by')
    list_filter = ('year', 'assessment_period', 'risk_rating', 'adopted_source',
                   'is_self_assessment')
    search_fields = ('department__name', 'department__code', 'notes')
    autocomplete_fields = ('department', 'audit_universe', 'assessed_by', 'reviewed_by')
    readonly_fields = ('risk_score', 'risk_rating', 'residual_risk', 'weight_sum',
                       'uplift_applied', 'policy_digest', 'is_stale_display',
                       'created_at', 'updated_at')

    @admin.display(boolean=True, description='Stale')
    def is_stale_display(self, obj):
        """Whether a parameter edit has left this row scored under an old policy."""
        return obj.is_stale if obj.pk else False


@admin.register(SelfAssessment)
class SelfAssessmentAdmin(admin.ModelAdmin):
    list_display = ('risk_assessment', 'submitted_by', 'status', 'submitted_at',
                    'reviewed_by', 'reviewed_at')
    list_filter = ('status',)
    search_fields = ('justification', 'mitigating_controls')
    autocomplete_fields = ('risk_assessment', 'submitted_by', 'reviewed_by')
    readonly_fields = ('submitted_at',)
