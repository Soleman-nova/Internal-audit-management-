from rest_framework import serializers
from .models import AuditProgram, AuditProcedure, WorkingPaper
from apps.accounts.serializers import UserSerializer


class AuditProcedureSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.full_name', read_only=True)
    completed_by_name = serializers.CharField(source='completed_by.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    type_display = serializers.CharField(source='get_procedure_type_display', read_only=True)

    class Meta:
        model = AuditProcedure
        fields = '__all__'


class AuditProgramSerializer(serializers.ModelSerializer):
    procedures = AuditProcedureSerializer(many=True, read_only=True)
    prepared_by_name = serializers.CharField(source='prepared_by.full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    completion_percent = serializers.SerializerMethodField()

    class Meta:
        model = AuditProgram
        fields = '__all__'

    def get_completion_percent(self, obj):
        total = obj.procedures.count()
        if total == 0:
            return 0
        done = obj.procedures.filter(status='completed').count()
        return round((done / total) * 100)


class WorkingPaperSerializer(serializers.ModelSerializer):
    prepared_by_name = serializers.CharField(source='prepared_by.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = WorkingPaper
        fields = '__all__'

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None
