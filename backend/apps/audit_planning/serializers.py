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
        fields = ['id', 'department_name', 'department_name_am', 'region_name',
                  'region_name_am', 'service_center_name', 'service_center_name_am',
                  'directorate_name', 'directorate_name_am', 'category_display',
                  'due_for_re_audit', 'latest_risk_assessment', 'name', 'code',
                  'category', 'description', 'owner', 'risk_score', 'audit_frequency',
                  'last_audited', 'status', 'technical_metadata', 'created_at',
                  'updated_at', 'department', 'region', 'service_center', 'directorate']

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
        fields = ['id', 'user_details', 'role', 'allocated_days', 'actual_days',
                  'joined_at', 'engagement', 'user']


class ProjectSerializer(OrgScopeNamesMixin, serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'department_name', 'department_name_am', 'region_name',
                  'region_name_am', 'service_center_name', 'service_center_name_am',
                  'code', 'name', 'created_at', 'updated_at', 'department', 'region',
                  'service_center']


class AuditEngagementSerializer(OrgScopeNamesMixin, serializers.ModelSerializer):
    lead_auditor_name = serializers.SerializerMethodField()
    supervisor_name = serializers.SerializerMethodField()
    auditee_name = serializers.SerializerMethodField()
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
        fields = ['id', 'department_name', 'department_name_am', 'region_name',
                  'region_name_am', 'service_center_name', 'service_center_name_am',
                  'lead_auditor_name', 'supervisor_name', 'auditee_name',
                  'directorate_name',
                  'directorate_name_am', 'status_display', 'engagement_type_display',
                  'plan_title', 'plan_year', 'team_members', 'findings_count',
                  'progress_percent', 'title', 'engagement_number', 'engagement_type',
                  'objectives', 'scope', 'status', 'planned_start', 'planned_end',
                  'actual_start', 'actual_end', 'planned_days', 'actual_days',
                  'risk_level', 'technical_metadata', 'created_at', 'updated_at',
                  'plan', 'audit_universe', 'department', 'region', 'service_center',
                  'directorate', 'lead_auditor', 'supervisor', 'auditee']
        # `status` and the two actual dates belong to the `update-status` action,
        # which is the only path that checks the completion precondition (an
        # engagement cannot be completed while findings sit in
        # draft/open/in_progress/disputed), stamps actual_start/actual_end and
        # closes the re-audit loop by writing the universe's last_audited.
        # Left writable, a plain PATCH moved an engagement to `completed` with open
        # findings and no actual_end — the one refusal this route exists to make.
        # Same shape as AuditFindingSerializer.read_only_fields, which closed the
        # identical door on the findings register.
        read_only_fields = ['engagement_number', 'status', 'actual_start',
                            'actual_end']

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

    def get_auditee_name(self, obj):
        # Unlike the two above, a blank auditee is not "unassigned work" — it is
        # the reason this engagement's findings will reach nobody. `None` rather
        # than the string, so the client can tell the difference and prompt.
        if obj.auditee:
            return obj.auditee.full_name
        return None

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
        fields = ['id', 'created_by_name', 'approved_by_name', 'directorate_name',
                  'directorate_name_am', 'plan_scope_display', 'engagements',
                  'engagements_count', 'status_display', 'title', 'year',
                  'description', 'objectives', 'scope', 'methodology', 'status',
                  'plan_scope', 'approved_at', 'start_date', 'end_date',
                  'total_budget_days', 'created_at', 'updated_at', 'directorate',
                  'parent_plan', 'created_by', 'approved_by']
        # `status`, `approved_at` and `approved_by` belong to the `approve` action,
        # which gates on APPROVE_PLANS, stamps the approver and notifies the plan's
        # author; `created_by` is assigned by perform_create. Left writable, a PATCH
        # could approve a plan that no approver had seen — and attribute the
        # approval to a chosen user — which made the action unreachable as the only
        # honest record of sign-off. Same shape as
        # AuditEngagementSerializer.read_only_fields directly above, and
        # AuditFindingSerializer.read_only_fields on the findings register.
        read_only_fields = ['status', 'approved_at', 'approved_by', 'created_by']

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
