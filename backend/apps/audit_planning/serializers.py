from rest_framework import serializers
from .models import (AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember, Project)
from apps.accounts.serializers import OrgScopeNamesMixin, UserSerializer


class AuditUniverseSerializer(OrgScopeNamesMixin, serializers.ModelSerializer):
    directorate_name = serializers.SerializerMethodField()
    directorate_name_am = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    due_for_re_audit = serializers.BooleanField(read_only=True)
    latest_risk_assessment = serializers.SerializerMethodField()

    class Meta:
        model = AuditUniverse
        fields = '__all__'

    def get_directorate_name(self, obj):
        if obj.directorate:
            return obj.directorate.name
        return None

    def get_directorate_name_am(self, obj):
        if obj.directorate:
            return obj.directorate.name_am
        return None

    def get_latest_risk_assessment(self, obj):
        """Expose the most recent linked risk assessment score/rating (Phase 3.1)."""
        latest = obj.risk_assessments.order_by('-year', '-created_at').first()
        if latest is None:
            return None
        return {
            'id': latest.id,
            'year': latest.year,
            'assessment_period': latest.assessment_period,
            'risk_score': str(latest.risk_score),
            'risk_rating': latest.risk_rating,
        }


class AuditTeamMemberSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = AuditTeamMember
        fields = '__all__'


class ProjectSerializer(OrgScopeNamesMixin, serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'


class AuditEngagementSerializer(OrgScopeNamesMixin, serializers.ModelSerializer):
    lead_auditor_name = serializers.SerializerMethodField()
    supervisor_name = serializers.SerializerMethodField()
    directorate_name = serializers.SerializerMethodField()
    directorate_name_am = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    engagement_type_display = serializers.CharField(source='get_engagement_type_display', read_only=True)
    # The plan an engagement belongs to is fixed by that engagement, so the
    # engagement pickers on Execution/Findings/Reports show it read-back rather
    # than asking for it. Sent as a flat pair so those pages don't have to fetch
    # the whole plan catalogue just to name one.
    plan_title = serializers.SerializerMethodField()
    plan_year = serializers.SerializerMethodField()
    team_members = AuditTeamMemberSerializer(many=True, read_only=True)
    findings_count = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = AuditEngagement
        fields = '__all__'
        read_only_fields = ['engagement_number']

    @staticmethod
    def _plan_of(obj):
        # `plan` is a non-null FK but a stale id can still blow up the detail
        # route, so read it defensively like the nullable relations above.
        try:
            return obj.plan
        except AuditPlan.DoesNotExist:
            return None

    def get_plan_title(self, obj):
        plan = self._plan_of(obj)
        return plan.title if plan else None

    def get_plan_year(self, obj):
        plan = self._plan_of(obj)
        return plan.year if plan else None

    def get_lead_auditor_name(self, obj):
        if obj.lead_auditor:
            return obj.lead_auditor.full_name
        return 'Unassigned'

    def get_supervisor_name(self, obj):
        if obj.supervisor:
            return obj.supervisor.full_name
        return 'Unassigned'

    def get_directorate_name(self, obj):
        if obj.directorate:
            return obj.directorate.name
        return None

    def get_directorate_name_am(self, obj):
        if obj.directorate:
            return obj.directorate.name_am
        return None

    def get_findings_count(self, obj):
        return obj.findings.count()

    def get_progress_percent(self, obj):
        if hasattr(obj, 'program'):
            total = obj.program.procedures.count()
            if total == 0:
                return 0
            done = obj.program.procedures.filter(status='completed').count()
            return round((done / total) * 100)
        return 0


class AuditPlanSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    directorate_name = serializers.SerializerMethodField()
    directorate_name_am = serializers.SerializerMethodField()
    plan_scope_display = serializers.CharField(source='get_plan_scope_display', read_only=True)
    engagements = AuditEngagementSerializer(many=True, read_only=True)
    engagements_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = AuditPlan
        fields = '__all__'

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.full_name
        return 'System'

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.full_name
        return None

    def get_directorate_name(self, obj):
        if obj.directorate:
            return obj.directorate.name
        return None

    def get_directorate_name_am(self, obj):
        if obj.directorate:
            return obj.directorate.name_am
        return None

    def get_engagements_count(self, obj):
        return obj.engagements.count()