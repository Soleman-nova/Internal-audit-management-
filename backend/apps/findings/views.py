from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
import random, string

from .models import AuditFinding, Evidence, FindingComment
from .serializers import AuditFindingSerializer, EvidenceSerializer, FindingCommentSerializer
from apps.accounts.models import AuditTrail


class AuditFindingViewSet(viewsets.ModelViewSet):
    queryset = AuditFinding.objects.select_related(
        'engagement', 'procedure', 'identified_by', 'assigned_to', 'auditee'
    ).prefetch_related('evidence', 'comments', 'corrective_actions').all()
    serializer_class = AuditFindingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['severity', 'status', 'category', 'engagement', 'is_repeat']
    search_fields = ['title', 'description', 'finding_number', 'recommendation']
    ordering_fields = ['created_at', 'severity', 'status', 'target_resolution_date']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        num = ''.join(random.choices(string.digits, k=5))
        finding = serializer.save(
            identified_by=self.request.user,
            finding_number=f'FND-{num}'
        )
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='AuditFinding',
            object_id=str(finding.id),
            object_repr=f"{finding.finding_number} - {finding.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        old_repr = str(serializer.instance)
        finding = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='AuditFinding',
            object_id=str(finding.id),
            object_repr=f"{finding.finding_number} - {finding.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='AuditFinding',
            object_id=str(instance.id),
            object_repr=f"{instance.finding_number} - {instance.title}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()

    @action(detail=True, methods=['post'], url_path='add-comment')
    def add_comment(self, request, pk=None):
        finding = self.get_object()
        serializer = FindingCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(finding=finding, author=request.user)
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='AuditFinding',
            object_id=str(finding.id),
            object_repr=f"Comment added to {finding.finding_number}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='upload-evidence')
    def upload_evidence(self, request, pk=None):
        finding = self.get_object()
        serializer = EvidenceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save(finding=finding, uploaded_by=request.user)
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='AuditFinding',
            object_id=str(finding.id),
            object_repr=f"Evidence uploaded for {finding.finding_number}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        finding = self.get_object()
        finding.status = 'closed'
        finding.actual_resolution_date = timezone.now().date()
        finding.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='AuditFinding',
            object_id=str(finding.id),
            object_repr=f"Closed {finding.finding_number} - {finding.title}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': 'Finding closed.'})


class EvidenceViewSet(viewsets.ModelViewSet):
    queryset = Evidence.objects.select_related('finding', 'uploaded_by').all()
    serializer_class = EvidenceSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['finding', 'evidence_type']

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)