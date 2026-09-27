from rest_framework import serializers
from .models import CorrectiveAction, ActionResponse, FollowUp
from apps.accounts.serializers import UserSerializer


class ActionResponseSerializer(serializers.ModelSerializer):
    responder_name = serializers.SerializerMethodField()

    class Meta:
        model = ActionResponse
        fields = ['id', 'responder_name', 'response_text', 'evidence_file',
                  'status_update', 'responded_at', 'corrective_action', 'responder']

    def get_responder_name(self, obj):
        if obj.responder:
            return obj.responder.full_name
        return None


class FollowUpSerializer(serializers.ModelSerializer):
    conducted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = FollowUp
        fields = ['id', 'conducted_by_name', 'scheduled_date', 'status', 'notes',
                  'outcome', 'email_sent', 'email_sent_at', 'created_at',
                  'corrective_action', 'conducted_by']

    def get_conducted_by_name(self, obj):
        if obj.conducted_by:
            return obj.conducted_by.full_name
        return None


class CorrectiveActionSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    finding_title = serializers.SerializerMethodField()
    finding_severity = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    responses = ActionResponseSerializer(many=True, read_only=True)
    follow_ups = FollowUpSerializer(many=True, read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = CorrectiveAction
        fields = ['id', 'owner_name', 'finding_title', 'finding_severity',
                  'status_display', 'priority_display', 'responses', 'follow_ups',
                  'is_overdue', 'action_number', 'title', 'description',
                  'recommendation', 'status', 'priority', 'due_date',
                  'extended_due_date', 'completed_date', 'due_reminder_sent',
                  'management_response', 'follow_up_notes', 'created_at', 'updated_at',
                  'finding', 'owner', 'assigned_by']
        read_only_fields = ['action_number', 'assigned_by']

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.full_name
        return None

    def get_finding_title(self, obj):
        if obj.finding:
            return obj.finding.title
        return None

    def get_finding_severity(self, obj):
        if obj.finding:
            return obj.finding.severity
        return None

    def get_is_overdue(self, obj):
        from django.utils import timezone
        if obj.status in ['open', 'in_progress']:
            return obj.due_date < timezone.now().date()
        return False
