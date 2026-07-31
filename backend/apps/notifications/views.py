from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Notification, SystemSetting
from .serializers import NotificationSerializer, SystemSettingSerializer
from apps.common.permissions import CanManageSettings
from apps.common.audit_utils import log_audit


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save()
        return Response({'detail': 'Marked as read.'})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({'detail': 'All notifications marked as read.'})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread': count})


class SystemSettingViewSet(viewsets.ModelViewSet):
    queryset = SystemSetting.objects.all()
    serializer_class = SystemSettingSerializer
    permission_classes = [CanManageSettings]

    def perform_update(self, serializer):
        setting = serializer.save(updated_by=self.request.user)
        # Settings changes are sensitive — always record them.
        log_audit(self.request, 'UPDATE', setting)
