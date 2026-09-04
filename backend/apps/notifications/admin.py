from django.contrib import admin

from .models import Notification, SystemSetting


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'message', 'user__email', 'user__employee_id')
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at',)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'updated_by', 'updated_at')
    search_fields = ('key', 'description', 'value')
    autocomplete_fields = ('updated_by',)
    readonly_fields = ('updated_at',)
