from rest_framework import serializers
from .models import Notification, SystemSetting


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source='get_notification_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'type_display', 'notification_type', 'title', 'message',
                  'link', 'is_read', 'read_at', 'created_at', 'user']
        read_only_fields = ['user', 'created_at', 'read_at']


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = ['id', 'key', 'value', 'description', 'updated_at', 'updated_by']
