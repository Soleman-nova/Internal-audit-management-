from rest_framework import serializers
from .models import AuditProgram, AuditProcedure, WorkingPaper
from apps.accounts.serializers import UserSerializer


class AuditProcedureSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.full_name', read_only=True)
    completed_by_name = serializers.CharField(source='completed_by.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    type_display = serializers.CharField(source='get_procedure_type_display', read_only=True)
    # How many findings this step has already produced. The reverse of the link
    # the finding's own create form enforces: without it a failed step on the
    # execution board looks identical to a failed step nobody has written up, and
    # the auditor's only way to find out is to go and look in another register.
    findings_count = serializers.SerializerMethodField()

    class Meta:
        model = AuditProcedure
        fields = ['id', 'assigned_to_name', 'completed_by_name', 'status_display',
                  'type_display', 'findings_count',
                  'step_number', 'title', 'description',
                  'procedure_type', 'risk_area', 'assertion', 'expected_evidence',
                  'status', 'completed_at', 'conclusion', 'is_template', 'order',
                  'created_at', 'updated_at', 'program', 'assigned_to', 'completed_by']

    def get_findings_count(self, obj):
        # `len(obj.findings.all())`, not `.count()`: the view prefetches
        # `findings` for the whole page, so this reads rows already in memory —
        # a `.count()` here would fire one query per procedure in the response,
        # which on a long program is one query per row to return a single digit.
        return len(obj.findings.all())


class AuditProgramSerializer(serializers.ModelSerializer):
    procedures = AuditProcedureSerializer(many=True, read_only=True)
    prepared_by_name = serializers.CharField(source='prepared_by.full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    completion_percent = serializers.SerializerMethodField()

    class Meta:
        model = AuditProgram
        fields = ['id', 'procedures', 'prepared_by_name', 'approved_by_name',
                  'status_display', 'completion_percent', 'title', 'objectives',
                  'scope', 'status', 'version', 'approved_at', 'created_at',
                  'updated_at', 'engagement', 'prepared_by', 'reviewed_by',
                  'approved_by']
        # The lifecycle fields are the server's to move. `submit` and `approve`
        # are capability-gated actions that check who may send the program up and
        # who may sign it off, and `approve` is what stamps approved_by /
        # reviewed_by / approved_at — without them an approval has no author, and
        # without the gate it never happened as far as the capability matrix is
        # concerned. Left writable, a PATCH let any WRITE_AUDIT holder approve
        # their own program and attribute it to anyone they liked, which also made
        # `approve`'s gate and notification unreachable. Same shape as
        # AuditFindingSerializer.read_only_fields, which closed the identical door
        # on the findings register.
        #
        # `prepared_by` joins them because perform_create already assigns the
        # caller; accepting a client value could only ever contradict the audit
        # trail's own author. `version` is left writable for now — no route
        # stamps it yet, so a re-issue has to be able to set it by hand.
        read_only_fields = ['status', 'approved_at', 'approved_by', 'reviewed_by',
                            'prepared_by']

    def get_completion_percent(self, obj):
        total = obj.procedures.count()
        if total == 0:
            return 0
        # `failed` and `not_applicable` are terminal fieldwork outcomes — the test
        # ran and the control did not hold, or the step did not apply — so they
        # are finished work like `completed`. Counting only `completed` meant a
        # program whose steps legitimately failed could never reach 100%, and the
        # progress bar said the audit was unfinished when the fieldwork was, in
        # fact, done.
        done = obj.procedures.filter(status__in=AuditProcedure.TESTED_STATUSES).count()
        return round((done / total) * 100)


class WorkingPaperSerializer(serializers.ModelSerializer):
    prepared_by_name = serializers.CharField(source='prepared_by.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = WorkingPaper
        fields = ['id', 'prepared_by_name', 'reviewed_by_name', 'file_url',
                  'reference', 'title', 'description', 'paper_type', 'file',
                  'is_reviewed', 'review_notes', 'created_at', 'updated_at',
                  'engagement', 'procedure', 'prepared_by', 'reviewed_by']

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
        return None
