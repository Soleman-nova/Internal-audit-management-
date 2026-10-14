from rest_framework import serializers
from .models import ReportTemplate, GeneratedReport


class ReportTemplateSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_template_type_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReportTemplate
        fields = ['id', 'type_display', 'created_by_name', 'name', 'template_type',
                  'description', 'is_default', 'template_file', 'created_at',
                  'created_by']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.full_name
        return None


class GeneratedReportSerializer(serializers.ModelSerializer):
    generated_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    engagement_title = serializers.SerializerMethodField()
    engagement_number = serializers.SerializerMethodField()
    template_name = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    directorate_name = serializers.SerializerMethodField()
    lead_auditor_name = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedReport
        fields = [
            'id', 'generated_by_name', 'file_url', 'engagement_title',
            'engagement_number', 'template_name', 'department_name',
            'directorate_name', 'lead_auditor_name', 'title', 'format',
            'status', 'parameters', 'file', 'generated_at', 'error_message',
            'template', 'engagement', 'generated_by',
        ]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None

    def get_engagement_title(self, obj):
        if obj.engagement:
            return obj.engagement.title
        return None

    def get_engagement_number(self, obj):
        if obj.engagement:
            return obj.engagement.engagement_number
        return None

    def get_template_name(self, obj):
        if obj.template:
            return obj.template.name
        return None

    def get_department_name(self, obj):
        if obj.engagement and obj.engagement.department:
            return obj.engagement.department.name
        return None

    def get_directorate_name(self, obj):
        if obj.engagement and obj.engagement.directorate:
            return obj.engagement.directorate.name
        return None

    def get_lead_auditor_name(self, obj):
        if obj.engagement and obj.engagement.lead_auditor:
            return obj.engagement.lead_auditor.full_name
        return None

    def get_generated_by_name(self, obj):
        if obj.generated_by:
            return obj.generated_by.full_name
        return 'System'

