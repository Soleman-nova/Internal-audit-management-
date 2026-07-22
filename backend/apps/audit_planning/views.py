from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import AuditUniverse, AuditPlan, AuditEngagement, AuditTeamMember
from .serializers import (AuditUniverseSerializer, AuditPlanSerializer,
                          AuditEngagementSerializer, AuditTeamMemberSerializer)
from apps.accounts.models import AuditTrail


class AuditUniverseViewSet(viewsets.ModelViewSet):
    queryset = AuditUniverse.objects.select_related('department').all()
    serializer_class = AuditUniverseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'status', 'department']
    search_fields = ['name', 'code', 'owner']
    ordering_fields = ['risk_score', 'name', 'last_audited']
    ordering = ['-risk_score']

    def perform_create(self, serializer):
        obj = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='AuditUniverse',
            object_id=str(obj.id),
            object_repr=f"{obj.code} - {obj.name}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        obj = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='AuditUniverse',
            object_id=str(obj.id),
            object_repr=f"{obj.code} - {obj.name}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='AuditUniverse',
            object_id=str(instance.id),
            object_repr=f"{instance.code} - {instance.name}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()


class AuditPlanViewSet(viewsets.ModelViewSet):
    queryset = AuditPlan.objects.select_related('created_by', 'approved_by').prefetch_related('engagements').all()
    serializer_class = AuditPlanSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'year']
    search_fields = ['title', 'description']
    ordering = ['-year']

    def perform_create(self, serializer):
        plan = serializer.save(created_by=self.request.user)
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='AuditPlan',
            object_id=str(plan.id),
            object_repr=f"Audit Plan {plan.year} - {plan.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        plan = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='AuditPlan',
            object_id=str(plan.id),
            object_repr=f"Audit Plan {plan.year} - {plan.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='AuditPlan',
            object_id=str(instance.id),
            object_repr=f"Audit Plan {instance.year} - {instance.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        plan = self.get_object()
        plan.status = 'approved'
        plan.approved_by = request.user
        from django.utils import timezone
        plan.approved_at = timezone.now()
        plan.save()
        AuditTrail.objects.create(
            user=request.user,
            action='APPROVE',
            model_name='AuditPlan',
            object_id=str(plan.id),
            object_repr=f"Approved Audit Plan {plan.year} - {plan.title}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': 'Plan approved successfully.'})

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        plan = self.get_object()
        plan.status = 'submitted'
        plan.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='AuditPlan',
            object_id=str(plan.id),
            object_repr=f"Submitted Audit Plan {plan.year} - {plan.title}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': 'Plan submitted for approval.'})


class AuditEngagementViewSet(viewsets.ModelViewSet):
    queryset = AuditEngagement.objects.select_related(
        'plan', 'department', 'lead_auditor', 'supervisor', 'audit_universe'
    ).prefetch_related('team_members', 'findings').all()
    serializer_class = AuditEngagementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'engagement_type', 'plan', 'department', 'risk_level']
    search_fields = ['title', 'engagement_number', 'objectives']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        import random, string
        num = ''.join(random.choices(string.digits, k=5))
        engagement = serializer.save(engagement_number=f'ENG-{num}')
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='AuditEngagement',
            object_id=str(engagement.id),
            object_repr=f"{engagement.engagement_number} - {engagement.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        engagement = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='AuditEngagement',
            object_id=str(engagement.id),
            object_repr=f"{engagement.engagement_number} - {engagement.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='AuditEngagement',
            object_id=str(instance.id),
            object_repr=f"{instance.engagement_number} - {instance.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()

    @action(detail=True, methods=['post'], url_path='add-member')
    def add_member(self, request, pk=None):
        engagement = self.get_object()
        data = request.data.copy()
        data['engagement'] = engagement.id
        serializer = AuditTeamMemberSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='AuditEngagement',
            object_id=str(engagement.id),
            object_repr=f"Member added to {engagement.engagement_number}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        engagement = self.get_object()
        new_status = request.data.get('status')
        if new_status not in dict(AuditEngagement.STATUS_CHOICES):
            return Response({'detail': 'Invalid status.'}, status=400)
        old_status = engagement.status
        engagement.status = new_status
        from django.utils import timezone
        if new_status == 'in_progress' and not engagement.actual_start:
            engagement.actual_start = timezone.now().date()
        elif new_status == 'completed' and not engagement.actual_end:
            engagement.actual_end = timezone.now().date()
        engagement.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='AuditEngagement',
            object_id=str(engagement.id),
            object_repr=f"Status changed: {old_status} -> {new_status} for {engagement.engagement_number}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': f'Status updated to {new_status}.'})