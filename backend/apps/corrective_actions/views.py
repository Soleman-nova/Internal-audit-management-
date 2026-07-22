from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
import random, string

from .models import CorrectiveAction, ActionResponse, FollowUp
from .serializers import CorrectiveActionSerializer, ActionResponseSerializer, FollowUpSerializer
from apps.accounts.models import AuditTrail


class CorrectiveActionViewSet(viewsets.ModelViewSet):
    queryset = CorrectiveAction.objects.select_related(
        'finding', 'owner', 'assigned_by'
    ).prefetch_related('responses', 'follow_ups').all()
    serializer_class = CorrectiveActionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'finding', 'owner']
    search_fields = ['title', 'description', 'recommendation', 'action_number']
    ordering_fields = ['due_date', 'created_at', 'priority']
    ordering = ['due_date']

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.is_authenticated and user.role == 'auditee':
            if user.department:
                return qs.filter(owner__department=user.department)
            return qs.filter(owner=user)
        return qs

    def perform_create(self, serializer):
        num = ''.join(random.choices(string.digits, k=5))
        action_obj = serializer.save(
            assigned_by=self.request.user,
            action_number=f'CAPA-{num}'
        )
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='CorrectiveAction',
            object_id=str(action_obj.id),
            object_repr=f"{action_obj.action_number} - {action_obj.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        action_obj = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='CorrectiveAction',
            object_id=str(action_obj.id),
            object_repr=f"{action_obj.action_number} - {action_obj.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='CorrectiveAction',
            object_id=str(instance.id),
            object_repr=f"{instance.action_number} - {instance.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()

    @action(detail=True, methods=['post'], url_path='add-response')
    def add_response(self, request, pk=None):
        action_obj = self.get_object()
        data = request.data.copy()
        data['corrective_action'] = action_obj.id
        serializer = ActionResponseSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        response_obj = serializer.save(responder=request.user)
        # Update action status
        action_obj.status = data.get('status_update', action_obj.status)
        action_obj.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='CorrectiveAction',
            object_id=str(action_obj.id),
            object_repr=f"Response added to {action_obj.action_number}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='schedule-followup')
    def schedule_followup(self, request, pk=None):
        action_obj = self.get_object()
        data = request.data.copy()
        data['corrective_action'] = action_obj.id
        serializer = FollowUpSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(conducted_by=request.user)
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='CorrectiveAction',
            object_id=str(action_obj.id),
            object_repr=f"Follow-up scheduled for {action_obj.action_number}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='overdue')
    def overdue(self, request):
        today = timezone.now().date()
        qs = self.get_queryset().filter(
            due_date__lt=today,
            status__in=['open', 'in_progress']
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        from django.db.models import Count
        today = timezone.now().date()
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'open': qs.filter(status='open').count(),
            'in_progress': qs.filter(status='in_progress').count(),
            'resolved': qs.filter(status='resolved').count(),
            'overdue': qs.filter(due_date__lt=today, status__in=['open', 'in_progress']).count(),
            'by_priority': list(qs.values('priority').annotate(count=Count('id'))),
        })