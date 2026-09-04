from django.contrib import admin

from .models import ActionResponse, CorrectiveAction, FollowUp


@admin.register(CorrectiveAction)
class CorrectiveActionAdmin(admin.ModelAdmin):
    list_display = ('action_number', 'title', 'finding', 'status', 'priority',
                    'owner', 'due_date', 'completed_date')
    list_filter = ('status', 'priority')
    search_fields = ('action_number', 'title', 'description')
    autocomplete_fields = ('finding', 'owner', 'assigned_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ActionResponse)
class ActionResponseAdmin(admin.ModelAdmin):
    list_display = ('corrective_action', 'responder', 'status_update', 'responded_at')
    list_filter = ('status_update',)
    search_fields = ('corrective_action__action_number', 'response_text')
    autocomplete_fields = ('corrective_action', 'responder')
    readonly_fields = ('responded_at',)


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('corrective_action', 'scheduled_date', 'conducted_by', 'status', 'outcome')
    list_filter = ('status',)
    search_fields = ('corrective_action__action_number', 'notes', 'outcome')
    autocomplete_fields = ('corrective_action', 'conducted_by')
    readonly_fields = ('created_at',)
