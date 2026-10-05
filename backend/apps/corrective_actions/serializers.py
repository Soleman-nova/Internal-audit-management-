from rest_framework import serializers
from .models import CorrectiveAction, ActionResponse, FollowUp
from apps.accounts.serializers import UserSerializer
from apps.findings.models import AuditFinding


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
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True)
    finding_title = serializers.SerializerMethodField()
    finding_severity = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    responses = ActionResponseSerializer(many=True, read_only=True)
    follow_ups = FollowUpSerializer(many=True, read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = CorrectiveAction
        fields = ['id', 'owner_name', 'approved_by_name', 'finding_title',
                  'finding_severity', 'status_display', 'priority_display',
                  'responses', 'follow_ups', 'is_overdue', 'action_number', 'title',
                  'description', 'recommendation', 'status', 'priority', 'due_date',
                  'extended_due_date', 'completed_date', 'due_reminder_sent',
                  'management_response', 'follow_up_notes', 'approved_at',
                  'created_at', 'updated_at', 'finding', 'owner', 'assigned_by',
                  'approved_by']
        # `approved_by`/`approved_at` are the approve action's to write: they check
        # the transition, gate on APPROVE_PLANS and write the audit trail. Left
        # writable, an owner could stamp their own plan as approved.
        read_only_fields = ['action_number', 'assigned_by', 'approved_by', 'approved_at']

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

    def validate_finding(self, value):
        """Refuse to link an action to a finding no supervisor has endorsed.

        Everything downstream already assumed this rule held, which is why it had
        to be enforced here. ``CorrectiveActionViewSet.get_queryset`` hides an
        action from the auditee while its finding is pre-publication, and the
        compiled report drops it for the same reason — so an action raised against
        an unendorsed finding was a record the system would create and then refuse
        to show anybody, while the report told its reader no corrective action had
        ever been defined. The auditee's route was already closed
        (``CanProposeCorrectiveAction`` repeats the publication filter); only the
        audit team's was open, because ``has_permission`` returns True for a
        WRITE_AUDIT holder before it ever looks at the finding.

        Only a *new* link is refused. An action raised while the hole was open
        stays editable — re-pointing one at a draft finding is the mistake worth
        stopping, and a title fix whose PATCH happens to carry ``finding`` is not.
        """
        if self.instance is not None and self.instance.finding_id == value.pk:
            return value
        if value.status in AuditFinding.PRE_PUBLICATION_STATUSES:
            raise serializers.ValidationError(
                f'{value.finding_number} is "{value.get_status_display()}" — a '
                'corrective action can be raised once a supervisor has endorsed '
                'it for publication.'
            )
        return value
