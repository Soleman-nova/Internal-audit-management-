from rest_framework import serializers
from .models import AuditFinding, Evidence, FindingComment
from apps.accounts.serializers import UserSerializer


class EvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Evidence
        fields = '__all__'

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.full_name
        return None


class FindingCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = FindingComment
        fields = '__all__'
        read_only_fields = ['author', 'created_at']

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.full_name
        return None


class AuditFindingSerializer(serializers.ModelSerializer):
    evidence = EvidenceSerializer(many=True, read_only=True)
    comments = FindingCommentSerializer(many=True, read_only=True)
    identified_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    auditee_name = serializers.SerializerMethodField()
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    engagement_title = serializers.SerializerMethodField()
    corrective_actions_count = serializers.SerializerMethodField()

    class Meta:
        model = AuditFinding
        fields = '__all__'

    def get_identified_by_name(self, obj):
        if obj.identified_by:
            return obj.identified_by.full_name
        return None

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.full_name
        return None

    def get_auditee_name(self, obj):
        if obj.auditee:
            return obj.auditee.full_name
        return None

    def get_engagement_title(self, obj):
        if obj.engagement:
            return obj.engagement.title
        return None

    def get_corrective_actions_count(self, obj):
        return obj.corrective_actions.count()
