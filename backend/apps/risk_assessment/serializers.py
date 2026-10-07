from rest_framework import serializers
from .models import (
    RiskParameter, RiskAssessment, SelfAssessment, active_policy,
)
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
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)
    risk_rating_display = serializers.CharField(source='get_risk_rating_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    audit_universe_name = serializers.SerializerMethodField()
    self_assessment = SelfAssessmentSerializer(read_only=True)
    # Computed the same way the model does, so the client can badge a row as
    # needing a recompute without fetching the parameter set itself.
    is_stale = serializers.SerializerMethodField()

    class Meta:
        model = RiskAssessment
        fields = ['id', 'department_name', 'department_name_am', 'region_name',
                  'region_name_am', 'service_center_name', 'service_center_name_am',
                  'assessed_by_name', 'reviewed_by_name', 'risk_rating_display',
                  'status_display', 'audit_universe_name',
                  'self_assessment', 'assessment_period', 'year', 'likelihood',
                  'impact', 'risk_score', 'risk_rating', 'status',
                  'control_effectiveness', 'residual_risk', 'notes',
                  'adopted_source', 'adoption_note', 'weight_sum', 'uplift_applied',
                  'policy_digest', 'is_stale', 'reviewed_at', 'review_notes',
                  'is_self_assessment', 'created_at', 'updated_at', 'department',
                  'region', 'service_center', 'audit_universe', 'assessed_by',
                  'reviewed_by']
        # adopted_source/adoption_note are set by the review action, never by a
        # client: a writable adopted_source would let a caller claim the auditee's
        # softer numbers produced a score the manager's numbers did not.
        #
        # `status` and `reviewed_at` are the same shape: the approve/reject actions
        # own them (they check the transition, gate on APPROVE_PLANS, stamp the
        # reviewer and write the audit trail). A writable `status` would let the
        # assessor approve their own score with a plain PATCH.
        read_only_fields = ['risk_score', 'risk_rating', 'residual_risk',
                            'weight_sum', 'uplift_applied', 'policy_digest',
                            'adopted_source', 'adoption_note',
                            'status', 'reviewed_at']

    def get_audit_universe_name(self, obj):
        if obj.audit_universe:
            return obj.audit_universe.name
        return None

    def get_is_stale(self, obj):
        # Memoised on the serializer, not the model or the module: the digest is
        # the same for every row in one response, so this is one query per request
        # rather than one per assessment. It must not outlive the request — a
        # cached digest is exactly how a parameter edit would go unnoticed.
        if not hasattr(self, '_current_digest'):
            self._current_digest = active_policy()['digest']
        return obj.policy_digest != self._current_digest

    def validate(self, attrs):
        """Refuse to guess which auditable entity a scoreless assessment belongs to.

        The model falls back to the department when no entity was named, but only
        when that department has exactly one active ``AuditUniverse`` row. With
        more than one there is no defensible choice, and the old silent guess
        (``order_by('-risk_score').first()``) picked by the field it was about to
        overwrite — so the caller is told to name the entity instead.
        """
        from apps.audit_planning.models import AuditUniverse

        universe = attrs.get('audit_universe')
        if universe is None and self.instance is not None:
            universe = self.instance.audit_universe
        department = attrs.get('department', getattr(self.instance, 'department', None))

        if universe is None and department is not None:
            count = AuditUniverse.objects.filter(
                department=department, status='active',
            ).count()
            if count > 1:
                raise serializers.ValidationError({
                    'audit_universe': (
                        f'{department} has {count} auditable entities. Pick the one this '
                        'assessment is about; the score is propagated onto it.'
                    ),
                })
        return attrs

