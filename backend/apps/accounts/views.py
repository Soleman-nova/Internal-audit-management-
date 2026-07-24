from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models
from django.db.models import Count

from .models import User, Department, AuditTrail
from apps.corrective_actions.models import CorrectiveAction
from apps.audit_planning.models import AuditEngagement, AuditPlan
from apps.findings.models import AuditFinding
from .serializers import (
    UserSerializer, UserCreateSerializer, LoginSerializer,
    DepartmentSerializer, AuditTrailSerializer
)


class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        # Log the login
        AuditTrail.objects.create(
            user=user, action='LOGIN', model_name='User',
            object_id=str(user.id), object_repr=str(user),
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user, context={'request': request}).data,
        })


class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            AuditTrail.objects.create(
                user=request.user, action='LOGOUT', model_name='User',
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            return Response({'detail': 'Successfully logged out.'})
        except Exception:
            return Response({'detail': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('department').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'department', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id']
    ordering_fields = ['first_name', 'created_at']
    ordering = ['first_name']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='User',
            object_id=str(user.id),
            object_repr=str(user),
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        old_repr = str(serializer.instance)
        user = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='User',
            object_id=str(user.id),
            object_repr=f"{old_repr} -> {str(user)}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='User',
            object_id=str(instance.id),
            object_repr=str(instance),
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        serializer = UserSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='User',
            object_id=str(user.id),
            object_repr=f"Activated user {user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': 'User activated.'})

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='User',
            object_id=str(user.id),
            object_repr=f"Deactivated user {user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': 'User deactivated.'})

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get('password')
        if not password or len(password) < 8:
            return Response(
                {'detail': 'Password must be at least 8 characters long.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user.set_password(password)
        user.save()
        
        # Log the password reset
        AuditTrail.objects.create(
            user=request.user,
            action='UPDATE',
            model_name='User',
            object_id=str(user.id),
            object_repr=f"Reset password for {user.email}",
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response({'detail': 'Password reset successful.'})


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'code']

    def perform_create(self, serializer):
        dept = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='CREATE',
            model_name='Department',
            object_id=str(dept.id),
            object_repr=str(dept),
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_update(self, serializer):
        old_repr = str(serializer.instance)
        dept = serializer.save()
        AuditTrail.objects.create(
            user=self.request.user,
            action='UPDATE',
            model_name='Department',
            object_id=str(dept.id),
            object_repr=f"{old_repr} -> {str(dept)}",
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )

    def perform_destroy(self, instance):
        AuditTrail.objects.create(
            user=self.request.user,
            action='DELETE',
            model_name='Department',
            object_id=str(instance.id),
            object_repr=str(instance),
            ip_address=self.request.META.get('REMOTE_ADDR'),
        )
        instance.delete()


class AuditTrailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditTrail.objects.select_related('user').all()
    serializer_class = AuditTrailSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['model_name', 'user']
    search_fields = ['object_repr', 'user__email', 'user__first_name', 'user__last_name']
    ordering = ['-timestamp']

    def get_queryset(self):
        queryset = super().get_queryset()
        # Case-insensitive action filter (handled manually since filterset_fields does exact match)
        action_param = self.request.query_params.get('action', None)
        if action_param:
            queryset = queryset.filter(action__icontains=action_param)
        return queryset


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        user = request.user

        if not current_password or not new_password:
            return Response(
                {'detail': 'Both current_password and new_password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(new_password) < 8:
            return Response(
                {'detail': 'New password must be at least 8 characters long.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(current_password):
            return Response(
                {'detail': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        AuditTrail.objects.create(
            user=user,
            action='UPDATE',
            model_name='User',
            object_id=str(user.id),
            object_repr='Password changed',
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        return Response({'detail': 'Password changed successfully.'})


class DashboardStatsView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()

        stats = {
            'total_engagements': AuditEngagement.objects.count(),
            'active_engagements': AuditEngagement.objects.filter(status='in_progress').count(),
            'total_findings': AuditFinding.objects.count(),
            'open_findings': AuditFinding.objects.filter(status='open').count(),
            'critical_findings': AuditFinding.objects.filter(severity='critical', status='open').count(),
            'high_findings': AuditFinding.objects.filter(severity='high', status='open').count(),
            'overdue_actions': CorrectiveAction.objects.filter(due_date__lt=today, status__in=['open', 'in_progress']).count(),
            'open_actions': CorrectiveAction.objects.filter(status__in=['open', 'in_progress']).count(),
            'total_users': User.objects.filter(is_active=True).count(),
            'active_plans': AuditPlan.objects.filter(status='active').count(),
            'findings_by_severity': list(
                AuditFinding.objects.values('severity').annotate(count=Count('id'))
            ),
            'engagements_by_status': list(
                AuditEngagement.objects.values('status').annotate(count=Count('id'))
            ),
        }
        return Response(stats)
