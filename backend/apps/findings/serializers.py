from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import AuditFinding, Evidence, FindingComment
from apps.accounts.serializers import UserSerializer


class EvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Evidence
        fields = '__all__'
        # `uploaded_by` is stamped from the request by both perform_create and
        # the upload-evidence action — left writable, a PATCH could reattribute
        # someone else's upload. Same shape as
        # FindingCommentSerializer.read_only_fields. `finding` stays writable
        # because both write paths pass it in `data` (see the note in
        # AuditFindingViewSet.upload_evidence), and reassigning it already
        # requires WRITE_AUDIT via the viewset's CanWriteAudit gate.
        read_only_fields = ['uploaded_by', 'uploaded_at']

    def get_file_url(self, obj):
        """The authenticated download endpoint, not the raw MEDIA_URL.

        This used to return `request.build_absolute_uri(obj.file.url)`, which
        served audit evidence to anyone holding the link with no token — and
        404'd in production, where `static()` does not mount MEDIA_URL at all.
        """
        if not obj.file or not obj.pk:
            return None
        request = self.context.get('request')
        return reverse('evidence-download', kwargs={'pk': obj.pk}, request=request)

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
        # Both are the server's to set: perform_create assigns FND-YYYY-NNNN and
        # stamps the caller as the identifier. Left writable, `finding_number`
        # was a *required* field on create — so a client that correctly stopped
        # inventing its own number got a 400 — and `identified_by` could be
        # reassigned to someone else through a plain PATCH. Same shape as
        # AuditEngagementSerializer.engagement_number and
        # CorrectiveActionSerializer.action_number/assigned_by.
        #
        # `status` and `actual_resolution_date` belong to the lifecycle actions
        # (close/resolve/dispute/reopen), which check the transition, gate on
        # CLOSE_FINDINGS, stamp the resolution date, write the audit trail, and
        # notify. A writable `status` let a plain PATCH skip all five.
        read_only_fields = [
            'finding_number', 'identified_by', 'status', 'actual_resolution_date',
        ]

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


class AuditFindingListSerializer(AuditFindingSerializer):
    """The register view: counts where the full serializer nests collections.

    ``AuditFindingSerializer`` embeds every evidence record and every comment on
    every row. The queryset's ``prefetch_related`` kept the query count flat, so
    this never showed up as an N+1 — but the *payload* is unbounded. A findings
    register with long comment threads returned megabytes to render a table that
    displays none of it, and the browser parsed all of it before painting.

    Retrieve still uses the full serializer, so the detail page is unchanged and
    nothing had to move client-side.
    """

    # Declared on the parent, so `fields = '__all__'` is not what pulls them in —
    # `= None` is DRF's documented way to drop an inherited declared field.
    evidence = None
    comments = None

    # Counts, so the table can still show "3 evidence / 2 comments" badges
    # without the rows behind them. Read straight off the queryset annotations
    # added by AuditFindingViewSet.get_queryset: as SerializerMethodFields
    # calling .count() these would be three extra queries per row.
    #
    # Every scalar field is inherited untouched — in particular `description` and
    # `recommendation`, which the follow-up page reads from this list to prefill
    # a new CAPA from the finding chosen in its dropdown.
    evidence_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    corrective_actions_count = serializers.IntegerField(read_only=True)
