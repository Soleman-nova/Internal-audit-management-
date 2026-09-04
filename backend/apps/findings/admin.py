from django.contrib import admin

from .models import AuditFinding, Evidence, FindingComment


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    autocomplete_fields = ('uploaded_by',)
    readonly_fields = ('uploaded_at',)


@admin.register(AuditFinding)
class AuditFindingAdmin(admin.ModelAdmin):
    list_display = ('finding_number', 'title', 'engagement', 'severity', 'category',
                    'status', 'assigned_to', 'target_resolution_date')
    list_filter = ('severity', 'category', 'status', 'is_repeat')
    search_fields = ('finding_number', 'title', 'description', 'recommendation')
    autocomplete_fields = ('engagement', 'procedure', 'identified_by',
                           'assigned_to', 'auditee', 'previous_finding')
    inlines = [EvidenceInline]
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('title', 'finding', 'evidence_type', 'uploaded_by', 'uploaded_at')
    list_filter = ('evidence_type',)
    search_fields = ('title', 'description', 'finding__finding_number')
    autocomplete_fields = ('finding', 'uploaded_by')
    readonly_fields = ('uploaded_at',)


@admin.register(FindingComment)
class FindingCommentAdmin(admin.ModelAdmin):
    list_display = ('finding', 'author', 'is_internal', 'created_at')
    list_filter = ('is_internal',)
    search_fields = ('comment', 'finding__finding_number')
    autocomplete_fields = ('finding', 'author')
