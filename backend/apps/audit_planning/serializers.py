from rest_framework import serializers
from .models import (AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember)
from apps.accounts.serializers import UserSerializer


class AuditUniverseSerializer(serializers.ModelSerializer):
    department_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = AuditUniverse
        fields = '__all__'

    def get_department_name(self, obj):
        if obj.department:
            return obj.department.name
        return None


class AuditTeamMemberSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)

    class Meta:
        model = AuditTeamMember
        fields = '__all__'


class AuditEngagementSerializer(serializers.ModelSerializer):
    lead_auditor_name = serializers.SerializerMethodField()
    supervisor_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    team_members = AuditTeamMemberSerializer(many=True, read_only=True)
    findings_count = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = AuditEngagement
        fields = '__all__'
        read_only_fields = ['engagement_number']

    def get_lead_auditor_name(self, obj):
        if obj.lead_auditor:
            return obj.lead_auditor.full_name
        return 'Unassigned'

    def get_supervisor_name(self, obj):
        if obj.supervisor:
            return obj.supervisor.full_name
        return 'Unassigned'

    def get_department_name(self, obj):
        if obj.department:
            return obj.department.name
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

    def get_engagements_count(self, obj):
        return obj.engagements.count()
