from rest_framework import serializers
from .models import RiskParameter, RiskAssessment, SelfAssessment
from apps.accounts.serializers import OrgScopeNamesMixin, UserSerializer


class RiskParameterSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = RiskParameter
        fields = ['id', 'category_display', 'name', 'category', 'description',
                  'weight', 'is_active', 'created_at', 'created_by']


class SelfAssessmentSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)

    class Meta:
        model = SelfAssessment
        fields = ['id', 'submitted_by_name', 'submitted_at', 'status',
                  'likelihood_self', 'impact_self', 'control_effectiveness_self',
                  'justification', 'mitigating_controls', 'reviewer_notes',
                  'reviewed_at', 'risk_assessment', 'submitted_by', 'reviewed_by']


class RiskAssessmentSerializer(OrgScopeNamesMixin, serializers.ModelSerializer):
    assessed_by_name = serializers.CharField(source='assessed_by.full_name', read_only=True)
    risk_rating_display = serializers.CharField(source='get_risk_rating_display', read_only=True)
    audit_universe_name = serializers.SerializerMethodField()
    self_assessment = SelfAssessmentSerializer(read_only=True)

    class Meta:
        model = RiskAssessment
        fields = ['id', 'department_name', 'department_name_am', 'region_name',
                  'region_name_am', 'service_center_name', 'service_center_name_am',
                  'assessed_by_name', 'risk_rating_display', 'audit_universe_name',
                  'self_assessment', 'assessment_period', 'year', 'likelihood',
                  'impact', 'risk_score', 'risk_rating', 'inherent_risk',
                  'control_effectiveness', 'residual_risk', 'notes',
                  'is_self_assessment', 'created_at', 'updated_at', 'department',
                  'region', 'service_center', 'audit_universe', 'assessed_by',
                  'reviewed_by']
        read_only_fields = ['risk_score', 'risk_rating', 'residual_risk']

    def get_audit_universe_name(self, obj):
        if obj.audit_universe:
            return obj.audit_universe.name
        return None
