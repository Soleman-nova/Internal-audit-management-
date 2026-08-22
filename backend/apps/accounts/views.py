import datetime
import logging

from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models, transaction
from django.db.models import Count, Q
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import User, Department, AuditTrail
from apps.corrective_actions.models import CorrectiveAction
from apps.audit_planning.models import AuditEngagement, AuditPlan
from apps.findings.models import AuditFinding
from apps.risk_assessment.models import SelfAssessment
from apps.common.permissions import (
    CanManageUsers, CanManageSettings, CanViewAuditTrail, CanWriteAudit,
    APPROVE_PLANS, has_capability,
)
from apps.common.audit_utils import log_audit
from apps.common.date_utils import month_starts, month_end
from .serializers import (
    UserSerializer, UserCreateSerializer, LoginSerializer,
    DepartmentSerializer, AuditTrailSerializer, ProfileSerializer
)

logger = logging.getLogger(__name__)


class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    # The only unauthenticated write in the system, against a guessable username
    # space (EEU-#####). The scope is configured in settings.DEFAULT_THROTTLE_RATES
    # as 'login' (5/min) — far tighter than the global anon rate.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        # Log the login
        log_audit(request, 'LOGIN', user, user=user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user, context={'request': request}).data,
        })


class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Blacklist the presented refresh token.

        A malformed, expired or already-blacklisted token is the client's
        problem and earns a 400. Anything else — a database failure writing the
        blacklist row, say — is ours, and used to be reported identically with
        nothing logged, so a broken logout looked exactly like a stale tab.
        """
        raw_token = request.data.get('refresh')
        # Not merely defensive: RefreshToken(None) *mints a new token* rather
        # than raising (that is how for_user builds one), so a request with no
        # refresh field used to blacklist a brand-new token, log a LOGOUT, and
        # report success while the client's real token stayed valid.
        if not raw_token:
            return Response(
                {'detail': 'A refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(raw_token).blacklist()
        except TokenError:
            return Response({'detail': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Logout failed for user %s', request.user.pk)
            return Response(
                {'detail': 'Could not complete logout.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        log_audit(request, 'LOGOUT', request.user)
        return Response({'detail': 'Successfully logged out.'})


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('department').all()
    permission_classes = [CanManageUsers]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'department', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id']
    ordering_fields = ['first_name', 'created_at']
    ordering = ['first_name']

    def get_permissions(self):
        # `me` returns the caller's own profile — any authenticated user may read it.
        if self.action == 'me':
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            log_audit(self.request, 'CREATE', user)

    def perform_update(self, serializer):
        old_repr = str(serializer.instance)
        with transaction.atomic():
            user = serializer.save()
            log_audit(
                self.request, 'UPDATE', user,
                object_repr=f"{old_repr} -> {str(user)}",
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        serializer = UserSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        user = self.get_object()
        with transaction.atomic():
            user.is_active = True
            user.save()
            log_audit(request, 'UPDATE', user, object_repr=f"Activated user {user.email}")
        return Response({'detail': 'User activated.'})

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        user = self.get_object()
        with transaction.atomic():
            user.is_active = False
            user.save()
            log_audit(request, 'UPDATE', user, object_repr=f"Deactivated user {user.email}")
        return Response({'detail': 'User deactivated.'})

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get('password')
        if not password:
            return Response(
                {'detail': 'Password is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)},
                            status=status.HTTP_400_BAD_REQUEST)
        # One unit: an admin-issued password change that is not in the trail is
        # the single entry an investigation would most want to find.
        with transaction.atomic():
            user.set_password(password)
            user.save()
            log_audit(request, 'UPDATE', user, object_repr=f"Reset password for {user.email}")
        return Response({'detail': 'Password reset successful.'})


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [CanWriteAudit]  # reads open to any authenticated user
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['unit_type', 'directorate_type', 'parent', 'is_active']
    search_fields = ['name', 'name_am', 'code']

    # DepartmentSerializer.get_children() filters and orders, so a bare
    # prefetch_related('children') would be re-queried and discarded. The
    # queryset here matches the serializer's exactly and lands on `active_children`,
    # which the serializer reads in preference to querying. Two queries for the
    # page instead of one per row.
    ACTIVE_CHILDREN_PREFETCH = models.Prefetch(
        'children',
        queryset=Department.objects.filter(is_active=True).order_by('name'),
        to_attr='active_children',
    )

    def get_queryset(self):
        """Hide retired departments from the default list.

        Retired units (is_active=False) must stay reachable by ID so they can be
        reactivated and so historical engagements, universe entries, and risk
        assessments still resolve their department. So the active-only filter
        applies to the list action only, and an explicit ?is_active= query
        param always wins — pass ?is_active=false to review retired units.
        """
        queryset = Department.objects.prefetch_related(self.ACTIVE_CHILDREN_PREFETCH)
        if self.action == 'list' and 'is_active' not in self.request.query_params:
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            dept = serializer.save()
            log_audit(self.request, 'CREATE', dept)

    def perform_update(self, serializer):
        old_repr = str(serializer.instance)
        with transaction.atomic():
            dept = serializer.save()
            log_audit(
                self.request, 'UPDATE', dept,
                object_repr=f"{old_repr} -> {str(dept)}",
            )

    def perform_destroy(self, instance):
        with transaction.atomic():
            log_audit(self.request, 'DELETE', instance)
            instance.delete()

    @action(detail=False, methods=['get'], url_path='tree')
    def tree(self, request):
        """Every active unit, flat and unpaginated, for the cascading picker.

        The department → region → service center picker needs the whole tree at
        once: it derives all three levels client-side and, when editing, walks
        parents upward to rehydrate the steps from a stored department id.

        Deliberately not DepartmentSerializer — its get_children() method field
        would fire one query per row across 600+ units, and the picker only
        needs enough to build the parent/child map. One query, ~60 KB.
        """
        units = Department.objects.filter(is_active=True).order_by('name').values(
            'id', 'code', 'name', 'name_am', 'unit_type', 'parent',
        )
        return Response(list(units))


class AuditTrailViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditTrail.objects.select_related('user').all()
    serializer_class = AuditTrailSerializer
    permission_classes = [CanViewAuditTrail]
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

        if not user.check_password(current_password):
            return Response(
                {'detail': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        # The password change and its trail entry are one unit — a changed
        # password with no log entry is exactly what an investigation looks for.
        with transaction.atomic():
            user.set_password(new_password)
            user.save()
            log_audit(request, 'UPDATE', user, object_repr='Password changed', user=user)

        return Response({'detail': 'Password changed successfully.'})


class ProfileView(generics.RetrieveUpdateAPIView):
    """The caller's own profile — GET to read, PATCH to edit name/phone/avatar.

    Deliberately not a route on UserViewSet: that viewset is gated by
    CanManageUsers, so every non-admin would be locked out of editing their own
    name. Here the object is always ``request.user``, so no id is accepted and
    there is nothing to scope — a user cannot reach anyone else's record.
    ProfileSerializer pins role/department/employee_id read-only.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        with transaction.atomic():
            user = serializer.save()
            log_audit(self.request, 'UPDATE', user, object_repr=f"Profile updated: {user.email}")


class DashboardStatsView(generics.GenericAPIView):
    """Dashboard KPI cards and chart series, optionally scoped to one directorate.

    Pass ``?directorate=<department id>`` to rescope every number to the audit
    directorate that owns the work. Everything hangs off
    ``AuditEngagement.directorate``:

        engagements  ->  directorate_id
        findings     ->  engagement__directorate_id
        CAPAs        ->  finding__engagement__directorate_id
        plans        ->  directorate_id

    Without the param the response is EEU-wide, which is what the consolidated
    master view on the dashboard shows.
    """
    permission_classes = [IsAuthenticated]

    # Findings that count towards the compliance score. ``closed`` only, on
    # purpose: ``resolved`` records a claim that remediation happened and is set
    # by the audit team itself, while ``closed`` is the state a finding reaches
    # once that claim has been verified. Counting both let the score be
    # self-awarded — a directorate could read 100% compliant with nothing
    # actually verified.
    VERIFIED_FINDING_STATUSES = ('closed',)
    # Findings that need nothing further from the person they sit with. Wider
    # than the scoring set deliberately: once remediation is claimed the ball is
    # with the reviewer, so a resolved finding leaves its owner's My Work queue
    # even though it does not score yet.
    SETTLED_FINDING_STATUSES = ('resolved', 'closed')
    # Engagement statuses that mean "work is under way" for the execution chart.
    ACTIVE_ENGAGEMENT_STATUSES = ('in_progress', 'fieldwork', 'reporting')
    # CAPA statuses that still need something from their owner.
    OPEN_ACTION_STATUSES = ('open', 'in_progress', 'partially_resolved', 'not_implemented')
    # Rows returned per "My Work" list — enough to act on, short enough that the
    # dashboard payload does not grow with the size of someone's backlog.
    MY_WORK_LIMIT = 5

    def get(self, request):
        today = timezone.now().date()

        directorate = self._resolve_directorate(request)
        if isinstance(directorate, Response):
            return directorate

        engagements = AuditEngagement.objects.all()
        findings = AuditFinding.objects.all()
        actions = CorrectiveAction.objects.all()
        plans = AuditPlan.objects.all()

        if directorate is not None:
            engagements = engagements.filter(directorate_id=directorate.id)
            findings = findings.filter(engagement__directorate_id=directorate.id)
            actions = actions.filter(finding__engagement__directorate_id=directorate.id)
            plans = plans.filter(directorate_id=directorate.id)

        stats = {
            'directorate': self._directorate_payload(directorate),
            'total_engagements': engagements.count(),
            'active_engagements': engagements.filter(status='in_progress').count(),
            'total_findings': findings.count(),
            'open_findings': findings.filter(status='open').count(),
            'critical_findings': findings.filter(severity='critical', status='open').count(),
            'high_findings': findings.filter(severity='high', status='open').count(),
            'overdue_actions': actions.filter(due_date__lt=today, status__in=['open', 'in_progress']).count(),
            'open_actions': actions.filter(status__in=['open', 'in_progress']).count(),
            'total_users': User.objects.filter(is_active=True).count(),
            'active_plans': plans.filter(status='active').count(),
            'compliance_score': self._compliance_score(findings),
            'findings_by_severity': list(
                findings.values('severity').annotate(count=Count('id'))
            ),
            # The dashboard donut is labelled "distribution of open findings", so
            # it needs the open-only split — otherwise it sums to a different
            # total than the Open Findings KPI sitting right above it.
            'open_findings_by_severity': list(
                findings.filter(status='open').values('severity').annotate(count=Count('id'))
            ),
            'engagements_by_status': list(
                engagements.values('status').annotate(count=Count('id'))
            ),
            'monthly_engagements': self._monthly_engagements(engagements, today),
            'compliance_trend': self._compliance_trend(findings, today),
            'my_work': self._my_work(request.user, today),
        }
        return Response(stats)

    def _resolve_directorate(self, request):
        """Return the Department to scope to, None for EEU-wide, or an error Response."""
        raw = request.query_params.get('directorate')
        if raw in (None, '', 'all'):
            return None
        try:
            department_id = int(raw)
        except (TypeError, ValueError):
            return Response(
                {'detail': 'directorate must be a department id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        department = Department.objects.filter(pk=department_id).first()
        if department is None:
            return Response(
                {'detail': f'Department {department_id} not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return department

    @staticmethod
    def _directorate_payload(directorate):
        if directorate is None:
            return None
        return {
            'id': directorate.id,
            'name': directorate.name,
            'code': directorate.directorate_type,
            'head': directorate.head,
            'staff_count': directorate.staff_count,
        }

    @classmethod
    def _compliance_score(cls, findings):
        """Verified closure rate: closed findings as a percentage of all findings.

        Only ``closed`` counts — see VERIFIED_FINDING_STATUSES. A finding sitting
        at ``resolved`` is awaiting verification and scores nothing, so the number
        can only move when someone with CLOSE_FINDINGS signs the finding off.

        A scope with no findings scores 100.0, not 0.0 — nothing is outstanding,
        so reading it as fully non-compliant would be backwards.
        """
        totals = findings.aggregate(
            total=Count('id'),
            settled=Count('id', filter=Q(status__in=cls.VERIFIED_FINDING_STATUSES)),
        )
        if not totals['total']:
            return 100.0
        return round(100 * totals['settled'] / totals['total'], 1)

    @classmethod
    def _my_work(cls, user, today):
        """The signed-in user's own actionable queue.

        Deliberately *not* rescoped by ``?directorate=`` — this is "my work", and
        an auditee whose findings sit outside the selected directorate would
        otherwise get an empty list with no explanation. Auditees in particular
        used to land on an EEU-wide dashboard with nothing on it they could act
        on; this is the one section that is theirs.

        Reviewers (APPROVE_PLANS) see the self-assessment queue waiting on them;
        everyone else sees their own submissions.
        """
        findings = (
            AuditFinding.objects
            .filter(Q(assigned_to=user) | Q(auditee=user))
            .exclude(status__in=cls.SETTLED_FINDING_STATUSES)
            # Soonest deadline first, undated last — and no ordering on
            # ``severity``, which is a choice string that sorts alphabetically
            # (medium before critical) rather than by how bad the finding is.
            .order_by(models.F('target_resolution_date').asc(nulls_last=True), '-created_at')
        )
        actions = (
            CorrectiveAction.objects
            .filter(owner=user, status__in=cls.OPEN_ACTION_STATUSES)
            .order_by('due_date')
        )

        reviewing = has_capability(user, APPROVE_PLANS)
        assessments = SelfAssessment.objects.select_related(
            'risk_assessment', 'risk_assessment__department',
        ).filter(status='submitted')
        if not reviewing:
            assessments = assessments.filter(submitted_by=user)
        assessments = assessments.order_by('-submitted_at')

        return {
            'findings_count': findings.count(),
            'actions_count': actions.count(),
            # An overdue count of its own: the list is capped, so a long backlog
            # would otherwise hide the overdue rows below the cut-off.
            'overdue_actions_count': actions.filter(
                Q(extended_due_date__lt=today)
                | Q(extended_due_date__isnull=True, due_date__lt=today)
            ).count(),
            'assessments_count': assessments.count(),
            'assessments_are_for_review': reviewing,
            'findings': [
                {
                    'id': f.id,
                    'finding_number': f.finding_number,
                    'title': f.title,
                    'severity': f.severity,
                    'status': f.status,
                    'target_resolution_date': f.target_resolution_date,
                }
                for f in findings[:cls.MY_WORK_LIMIT]
            ],
            'actions': [
                {
                    'id': a.id,
                    'action_number': a.action_number,
                    'title': a.title,
                    'status': a.status,
                    'priority': a.priority,
                    'due_date': a.extended_due_date or a.due_date,
                    'is_overdue': (a.extended_due_date or a.due_date) < today,
                }
                for a in actions[:cls.MY_WORK_LIMIT]
            ],
            'assessments': [
                {
                    'id': s.id,
                    'status': s.status,
                    'department': getattr(s.risk_assessment.department, 'name', None),
                    'year': s.risk_assessment.year,
                    'period': s.risk_assessment.assessment_period,
                    'submitted_at': s.submitted_at,
                }
                for s in assessments[:cls.MY_WORK_LIMIT]
            ],
        }

    @classmethod
    def _monthly_engagements(cls, engagements, today, months=6):
        """Completed vs. in-flight engagements per month, oldest first.

        One aggregate over the whole window rather than a query per month.
        """
        starts = month_starts(today, months)
        buckets = {}
        for index, start in enumerate(starts):
            end = month_end(start)
            buckets[f'completed_{index}'] = Count('id', filter=Q(
                status='completed', actual_end__gte=start, actual_end__lte=end,
            ))
            # Active during the month: started on or before it ended, and had
            # not finished before it began.
            buckets[f'active_{index}'] = Count('id', filter=Q(
                Q(actual_end__isnull=True) | Q(actual_end__gte=start),
                status__in=cls.ACTIVE_ENGAGEMENT_STATUSES,
                planned_start__lte=end,
            ))

        counts = engagements.aggregate(**buckets) if buckets else {}
        return [
            {
                'month': start.strftime('%b %Y'),
                'Completed': counts.get(f'completed_{index}', 0) or 0,
                'InProgress': counts.get(f'active_{index}', 0) or 0,
            }
            for index, start in enumerate(starts)
        ]

    @classmethod
    def _compliance_trend(cls, findings, today, quarters=5):
        """Verified closure rate at the end of each of the last ``quarters`` quarters.

        Same metric as the KPI card, so the same ``closed``-only rule applies —
        the line and the number above it must not disagree.

        Cumulative — every finding raised up to that quarter's end counts — so
        the line tracks the standing backlog instead of spiking on quarters that
        happened to be quiet.
        """
        quarter = (today.month - 1) // 3 + 1
        year = today.year
        points = []
        for _ in range(quarters):
            points.append((year, quarter))
            quarter -= 1
            if quarter == 0:
                year, quarter = year - 1, 4
        points.reverse()

        buckets = {}
        for index, (point_year, point_quarter) in enumerate(points):
            end_month = point_quarter * 3
            next_start = (
                datetime.date(point_year + 1, 1, 1) if end_month == 12
                else datetime.date(point_year, end_month + 1, 1)
            )
            cutoff = next_start - datetime.timedelta(days=1)
            raised = Q(created_at__date__lte=cutoff)
            buckets[f'total_{index}'] = Count('id', filter=raised)
            buckets[f'settled_{index}'] = Count('id', filter=raised & Q(
                status__in=cls.VERIFIED_FINDING_STATUSES,
            ))

        counts = findings.aggregate(**buckets) if buckets else {}
        trend = []
        for index, (point_year, point_quarter) in enumerate(points):
            total = counts.get(f'total_{index}', 0) or 0
            settled = counts.get(f'settled_{index}', 0) or 0
            trend.append({
                'name': f'Q{point_quarter} {point_year}',
                'score': 100.0 if not total else round(100 * settled / total, 1),
            })
        return trend
