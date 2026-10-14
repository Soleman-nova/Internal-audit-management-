import datetime
import logging

import jwt
from jwt import PyJWKClientConnectionError
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from django.conf import settings
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import models, transaction
from django.db.models import Count, Q
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import User, Department, AuditTrail, Role
from apps.corrective_actions.models import CorrectiveAction
from apps.audit_planning.models import AuditEngagement, AuditPlan, AuditTeamMember
from apps.audit_execution.models import AuditProgram
from apps.findings.models import AuditFinding, FindingComment
from apps.risk_assessment.models import SelfAssessment
from apps.common.permissions import (
    CanManageUsers, CanManageSettings, CanViewAuditTrail, CanWriteAudit,
    CanViewExecutiveDashboard, APPROVE_PLANS, has_capability,
)
from apps.common.audit_utils import log_audit
from apps.common.date_utils import month_starts, month_end

from .logto import (
    LogtoNotConfigured, identity_candidates, jwt_header,
    resolve_or_provision_user, verify_logto_id_token,
)
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
    # as 'login' (30/min) — tighter than the global anon rate, yet lenient enough
    # that the one-click demo logins and e2e runs do not trip it.
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


class LogtoExchangeView(generics.GenericAPIView):
    """Exchange a verified Logto ID token for this system's SimpleJWT pair.

    Deliberately not a second DRF authentication backend. The Logto token is
    consumed here and never used as an API credential — what comes back is exactly
    what ``LoginView`` returns, so every existing view, permission class, and the
    frontend's whole refresh flow keep working with nothing changed on their side.

    An identity with no matching account is provisioned on the spot, keyed on the
    ``custom_data.EEUID`` claim and always with the lowest-privilege role — see
    ``logto.resolve_or_provision_user``. Promoting anyone to a real role stays a
    Django-side, admin-side action.

    The token arrives from the browser, which by design does not verify it; the
    signature check that used to happen client-side happens here instead, against
    Logto's JWKS.
    """
    permission_classes = [AllowAny]
    # Unauthenticated, and the request body carries a credential — the same shape as
    # LoginView, so it gets the same 30/min scope rather than the looser anon rate.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        # ── Step-wise tracing ──────────────────────────────────────────────────
        # Every branch below is reachable from the browser and several of them look
        # identical from the client — a 401 for a forged token and a 401 for a venv
        # missing `cryptography` are the same response. These lines say which step
        # was reached and what it saw, so the answer is in the console/audit log
        # rather than inferred. Grep for `[logto-exchange]`.
        #
        # INFO, not print: `apps` is configured at INFO with console and rotating-file
        # handlers in settings.LOGGING, so these land in both. The token's *contents*
        # are never logged — it is a credential; only its shape is.
        logger.info('[logto-exchange] step 1/6 received: content_type=%s keys=%s',
                    request.content_type, sorted(request.data.keys()))

        raw_token = request.data.get('id_token')
        if not raw_token:
            logger.warning('[logto-exchange] step 1/6 FAILED: no id_token in body')
            return Response(
                {'detail': 'An id_token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # The header is not secret (it is `alg` and `kid`) and is the fastest way to
        # spot the two classic mismatches: a token signed with an algorithm we do not
        # allow, and a `kid` the JWKS does not contain.
        logger.info('[logto-exchange] step 2/6 id_token present: %d chars, header=%s',
                    len(raw_token), jwt_header(raw_token))

        logger.info('[logto-exchange] step 3/6 config: endpoint=%r app_id=%r issuer=%r',
                    settings.LOGTO_ENDPOINT, settings.LOGTO_APP_ID, settings.LOGTO_ISSUER)

        try:
            claims = verify_logto_id_token(raw_token)
        except LogtoNotConfigured:
            logger.warning('[logto-exchange] step 4/6 FAILED: LOGTO_ENDPOINT/LOGTO_APP_ID unset')
            return Response(
                {'detail': 'Logto sign-in is not configured on this server.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except PyJWKClientConnectionError as exc:
            # Must be caught *before* PyJWTError, which it subclasses. Verifying a
            # real token needs a JWKS fetch from Logto, so an unreachable Logto
            # would otherwise fall into the branch below and tell the user their
            # token is bad — blaming them for our outage, and sending whoever
            # debugs it off to inspect tokens instead of the network.
            logger.error('[logto-exchange] step 4/6 FAILED: JWKS unreachable at %s/jwks (%s)',
                         settings.LOGTO_ISSUER, exc)
            return Response(
                {'detail': 'The sign-in service is unreachable. Try the employee ID '
                           'and password form, or try again shortly.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except jwt.PyJWTError as exc:
            # The exception text is safe to log and useless to a client — telling a
            # caller *why* their forgery was rejected is free help, so they get one
            # flat message and the detail stays in our logs.
            logger.warning('[logto-exchange] step 4/6 FAILED: %s', exc)
            return Response(
                {'detail': 'Logto token could not be verified.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # `iss`/`aud` are echoed because they are the two that jwt.decode above has
        # already proved equal to our config — so a rejection is never about these,
        # and printing them stops the next debugging session re-checking them.
        logger.info('[logto-exchange] step 4/6 VERIFIED: sub=%s iss=%s aud=%s exp=%s',
                    claims.get('sub'), claims.get('iss'), claims.get('aud'), claims.get('exp'))

        logger.info('[logto-exchange] step 5/6 identity candidates=%s',
                    identity_candidates(claims))

        user, provisioned = resolve_or_provision_user(claims)
        if user is None:
            logger.warning('[logto-exchange] step 5/6 FAILED: no active user for sub=%s',
                           claims.get('sub'))
            return Response(
                {
                    'detail': 'Your Logto account is not linked to an active user in '
                              'this system. Contact an administrator.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        logger.info('[logto-exchange] step 5/6 user=%s employee_id=%s role=%s provisioned=%s',
                    user.pk, user.employee_id, user.role, provisioned)

        if provisioned:
            # An account appearing in the audit system is precisely the kind of event
            # the audit trail exists to record — and this one was not created by an
            # administrator, so without this entry the row would have no provenance
            # at all. Attributed to the new account itself so the entry is reachable
            # by filtering the trail on that user. Logged before the LOGIN below.
            log_audit(
                request, 'CREATE', user, user=user,
                object_repr=f'Auto-provisioned from Logto as {user.role}: {user.employee_id}',
            )

        refresh = RefreshToken.for_user(user)
        log_audit(request, 'LOGIN', user, user=user)
        logger.info('[logto-exchange] step 6/6 ISSUED SimpleJWT for user=%s (%s) role=%s',
                    user.pk, user.employee_id, user.role)
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
    queryset = User.objects.select_related('department', 'region', 'service_center').all()
    permission_classes = [CanManageUsers]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'department', 'region', 'service_center', 'is_active']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id']
    ordering_fields = ['first_name', 'created_at']
    # `employee_id` is the tiebreaker, and it matters for correctness rather than
    # tidiness: ordering on `first_name` alone leaves rows tied whenever two
    # accounts share a name, and offset pagination over ties can repeat or drop
    # rows between page flips. The e2e suite proved it — `admin.spec.js` creates an
    # account per run, and once enough shared the seeded 'E2E' first name the new
    # one stopped reliably appearing on page 1. `employee_id` is the USERNAME_FIELD,
    # so it is unique and the order is total. Same reasoning as the planning
    # viewsets' `['-risk_score', 'name']`.
    ordering = ['first_name', 'employee_id']

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

    # --- Deletion guards ---------------------------------------------------
    #
    # A user row is not self-contained. AuditTeamMember and FindingComment both
    # CASCADE off it, so a bare DELETE silently drops the person from every
    # engagement team and destroys their comments on findings — unrecoverable
    # audit history. AuditTrail is SET_NULL, so the trail itself survives but
    # the operator on those rows goes blank. The first two therefore block the
    # delete, and the UI offers deactivation instead.
    #
    # Enforced here rather than only in the interface because the button is not
    # the only way to reach this endpoint.
    def _deletion_blockers(self, user):
        """Reasons `user` must not be hard-deleted, each with a readable message."""
        blockers = []

        if user.pk == self.request.user.pk:
            blockers.append({
                'type': 'self',
                'count': 0,
                'message': 'You cannot delete your own account.',
            })

        # Counts active admins *and* superusers: either can administer the
        # system, so losing the last of them locks everyone out.
        if user.role == Role.ADMIN or user.is_superuser:
            others_exist = User.objects.filter(
                Q(role=Role.ADMIN) | Q(is_superuser=True), is_active=True
            ).exclude(pk=user.pk).exists()
            if not others_exist:
                blockers.append({
                    'type': 'last_admin',
                    'count': 0,
                    'message': 'This is the last active administrator. Promote '
                               'another account before deleting this one.',
                })

        team_count = AuditTeamMember.objects.filter(user=user).count()
        if team_count:
            blockers.append({
                'type': 'engagement_teams',
                'count': team_count,
                'message': f'Member of {team_count} engagement '
                           f'team{"" if team_count == 1 else "s"}.',
            })

        comment_count = FindingComment.objects.filter(author=user).count()
        if comment_count:
            blockers.append({
                'type': 'finding_comments',
                'count': comment_count,
                'message': f'Author of {comment_count} finding '
                           f'comment{"" if comment_count == 1 else "s"}.',
            })

        return blockers

    @action(detail=True, methods=['post'], url_path='deletion-check')
    def deletion_check(self, request, pk=None):
        """Preflight for the delete button.

        Lets the dialog explain what a delete would destroy *before* the admin
        commits, rather than rejecting the request after they have already
        confirmed. POST rather than GET so the viewset's capability check
        applies — safe methods are open to any authenticated user.
        """
        user = self.get_object()
        blockers = self._deletion_blockers(user)
        return Response({'can_delete': not blockers, 'blockers': blockers})

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        blockers = self._deletion_blockers(user)
        if blockers:
            return Response(
                {'detail': blockers[0]['message'], 'blockers': blockers},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

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
    filterset_fields = ['unit_type', 'directorate_type', 'parent', 'is_active', 'region', 'parent__directorate_type']
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


class AuditMetricsMixin:
    """Metric definitions shared by the operational and executive dashboards.

    Both views read their KPI definitions from here rather than restating
    them, so what counts as a live finding or a verified closure is decided
    once and /dashboard and /executive can never disagree about it.
    """

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
    # Everything the register can hold apart from the settled pair — what the
    # "Open Findings" KPI and its donut count. Written out rather than derived by
    # subtracting the settled set, because a status added to the model later
    # should have to be classified here on purpose.
    #
    # This used to be the literal `status='open'`, which was already narrower than
    # the label suggested — it missed `in_progress`, `awaiting_auditee_response`
    # and `disputed` — and once findings are born `draft` it would have matched
    # nothing at all, pinning the tile at zero. `draft` is included deliberately:
    # an unendorsed finding is live work, and it is what a supervisor needs to see
    # waiting on them.
    LIVE_FINDING_STATUSES = (
        'draft', 'open', 'awaiting_auditee_response', 'in_progress', 'disputed',
    )
    # Engagement statuses that mean "work is under way" for the execution chart.
    ACTIVE_ENGAGEMENT_STATUSES = ('in_progress', 'fieldwork', 'reporting')
    # CAPA statuses that still need something from their owner.
    OPEN_ACTION_STATUSES = ('open', 'in_progress', 'partially_resolved', 'not_implemented')

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


class DashboardStatsView(AuditMetricsMixin, generics.GenericAPIView):
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

        # Dashboard scoping is driven entirely by ?directorate= (one of the four
        # EEU audit directorates: FPA, TA, ITA, PP) or the EEU-wide consolidated
        # view when no param is given.  Regional sub-unit narrowing is intentionally
        # NOT applied here: the scope strip only surfaces the four top-level
        # directorates, so narrowing further by region would silently hide data
        # that the user explicitly asked to see.
        total_users_qs = User.objects.filter(is_active=True)

        stats = {
            'directorate': self._directorate_payload(directorate),
            'total_engagements': engagements.count(),
            'active_engagements': engagements.filter(status='in_progress').count(),
            'total_findings': findings.count(),
            'open_findings': findings.filter(status__in=self.LIVE_FINDING_STATUSES).count(),
            'critical_findings': findings.filter(
                severity='critical', status__in=self.LIVE_FINDING_STATUSES,
            ).count(),
            'high_findings': findings.filter(
                severity='high', status__in=self.LIVE_FINDING_STATUSES,
            ).count(),
            'overdue_actions': actions.filter(due_date__lt=today, status__in=['open', 'in_progress']).count(),
            'open_actions': actions.filter(status__in=['open', 'in_progress']).count(),
            'total_users': total_users_qs.count(),
            'active_plans': plans.filter(status='active').count(),
            'compliance_score': self._compliance_score(findings),
            'findings_by_severity': list(
                findings.values('severity').annotate(count=Count('id'))
            ),
            # The dashboard donut is labelled "distribution of open findings", so
            # it needs the open-only split — otherwise it sums to a different
            # total than the Open Findings KPI sitting right above it.
            'open_findings_by_severity': list(
                findings.filter(status__in=self.LIVE_FINDING_STATUSES)
                .values('severity').annotate(count=Count('id'))
            ),
            'engagements_by_status': list(
                engagements.values('status').annotate(count=Count('id'))
            ),
            'monthly_engagements': self._monthly_engagements(engagements, today),
            'compliance_trend': self._compliance_trend(findings, today),
            'my_work': self._my_work(request.user, today),
        }
        return Response(stats)

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
        if user.role == 'auditee':
            # This queue is the auditee's *work*, so an unpublished finding is not
            # on it — the same rule the findings register applies. Restricted to
            # auditees rather than applied to everyone: an auditor assigned to a
            # finding they have not yet put to a supervisor should still see it
            # here, and this is the only place their own drafts surface.
            findings = findings.exclude(
                status__in=AuditFinding.PRE_PUBLICATION_STATUSES,
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


class ExecutiveDashboardView(AuditMetricsMixin, generics.GenericAPIView):
    """Leadership KPI band: plan completion, engagement progress, findings
    aging, CAPA implementation and repeat findings — read-only.

    Gated by ``CanViewExecutiveDashboard`` (``APPROVE_PLANS``): these are
    management numbers, so auditors and auditees are refused outright rather
    than shown an empty screen.

    Scoping mirrors ``DashboardStatsView`` — ``?directorate=<id>`` rescopes
    every number, ``?year=<int>`` picks the plan year, and a regional user
    lands on their own unit by default instead of an EEU-wide view they
    cannot act on.
    """

    permission_classes = [IsAuthenticated, CanViewExecutiveDashboard]

    # A procedure that ran and found the control wanting is a *finished*
    # procedure — see audit_execution/models.py. Progress means "processed",
    # not "passed", or a program that surfaces problems would read as stalled.
    PROCEDURE_DONE_STATUSES = ('completed', 'failed', 'not_applicable')

    def get(self, request):
        today = timezone.now().date()

        year_raw = request.query_params.get('year')
        try:
            year = int(year_raw) if year_raw else today.year
        except (TypeError, ValueError):
            return Response(
                {'detail': 'year must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        directorate = self._resolve_directorate(request)
        if isinstance(directorate, Response):
            return directorate

        # Scope is controlled exclusively by ?directorate= (FPA / TA / ITA / PP)
        # or shows the full EEU-wide consolidated view when the param is absent.
        # Regional sub-unit narrowing is intentionally NOT applied: these
        # dashboards surface the four top-level directorates and silently
        # narrowing by region would hide data the user asked to see.
        engagements = AuditEngagement.objects.all()
        findings = AuditFinding.objects.all()
        actions = CorrectiveAction.objects.all()

        if directorate is not None:
            engagements = engagements.filter(directorate_id=directorate.id)
            findings = findings.filter(engagement__directorate_id=directorate.id)
            actions = actions.filter(finding__engagement__directorate_id=directorate.id)

        return Response({
            'directorate': self._directorate_payload(directorate),
            'year': year,
            'open_findings': findings.filter(
                status__in=self.LIVE_FINDING_STATUSES,
            ).count(),
            # The compliance denominator: every finding in scope, settled or
            # not, so the KPI's sub-line can show what the rate is over.
            'total_findings': findings.count(),
            'plan_completion': self._plan_completion(engagements, year),
            'engagement_progress': self._engagement_progress(engagements),
            'findings_aging': self._findings_aging(findings, today),
            'capa': self._capa_summary(actions, today),
            'repeat_findings': self._repeat_findings_summary(findings),
            'compliance_score': self._compliance_score(findings),
            'compliance_trend': self._compliance_trend(findings, today),
        })

    def _plan_completion(self, engagements, year):
        """Annual plan delivery: the year's engagements, by owning directorate.

        Counted over engagements rather than plan documents — a plan with no
        engagements behind it has delivered nothing, and a cancelled
        engagement is delivery that will never happen, so neither can move
        the rate. Each directorate row carries its own split so the league
        table sorts without a second query.
        """
        year_engagements = engagements.filter(plan__year=year).exclude(status='cancelled')

        totals = year_engagements.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            in_progress=Count('id', filter=Q(status__in=self.ACTIVE_ENGAGEMENT_STATUSES)),
            not_started=Count('id', filter=Q(status='planned')),
        )
        total = totals['total'] or 0
        completed = totals['completed'] or 0

        grouped = list(
            year_engagements.filter(directorate__isnull=False)
            .values('directorate_id')
            .annotate(
                planned=Count('id'),
                completed=Count('id', filter=Q(status='completed')),
                in_progress=Count('id', filter=Q(status__in=self.ACTIVE_ENGAGEMENT_STATUSES)),
                not_started=Count('id', filter=Q(status='planned')),
            )
            .order_by('directorate_id')
        )
        departments = Department.objects.in_bulk(
            [row['directorate_id'] for row in grouped],
        )
        by_directorate = []
        for row in grouped:
            department = departments.get(row['directorate_id'])
            if department is None:
                continue
            planned = row['planned'] or 0
            done = row['completed'] or 0
            by_directorate.append({
                'id': department.id,
                'name': department.name,
                'code': department.directorate_type,
                'planned': planned,
                'completed': done,
                'in_progress': row['in_progress'] or 0,
                'not_started': row['not_started'] or 0,
                'rate': round(100 * done / planned, 1) if planned else 0.0,
            })
        by_directorate.sort(key=lambda entry: entry['name'])

        return {
            'total_planned': total,
            'completed': completed,
            'in_progress': totals['in_progress'] or 0,
            'not_started': totals['not_started'] or 0,
            'rate': round(100 * completed / total, 1) if total else 0.0,
            'by_directorate': by_directorate,
        }

    def _engagement_progress(self, engagements):
        """Percent of procedures finished for each in-flight engagement.

        ``AuditProgram`` is a OneToOneField on the engagement, so most
        engagements have no program at all. Those come back with
        ``has_program: false`` and stay out of the aggregate — folding them
        in as 0% would read as "nothing done" and silently drag the whole
        number down. Items are sorted worst-first: the laggards are what a
        leadership view exists to surface.
        """
        inflight = list(
            engagements.filter(status__in=self.ACTIVE_ENGAGEMENT_STATUSES)
            .annotate(
                procedures_total=Count('program__procedures'),
                procedures_done=Count(
                    'program__procedures',
                    filter=Q(program__procedures__status__in=self.PROCEDURE_DONE_STATUSES),
                ),
            )
        )
        program_ids = set(
            AuditProgram.objects.filter(engagement__in=inflight)
            .values_list('engagement_id', flat=True)
        ) if inflight else set()

        items = []
        overall_total = 0
        overall_done = 0
        for engagement in inflight:
            if engagement.pk not in program_ids:
                continue
            total = engagement.procedures_total or 0
            done = engagement.procedures_done or 0
            overall_total += total
            overall_done += done
            items.append({
                'engagement_number': engagement.engagement_number,
                'title': engagement.title,
                'directorate': (
                    engagement.directorate.name if engagement.directorate_id else None
                ),
                'rate': round(100 * done / total, 1) if total else 0.0,
                'planned_end': engagement.planned_end,
                'has_program': True,
            })
        items.sort(key=lambda item: (item['rate'], item['engagement_number']))

        return {
            'has_program': bool(program_ids),
            'overall': {
                'procedures_total': overall_total,
                'procedures_done': overall_done,
                'rate': (
                    round(100 * overall_done / overall_total, 1)
                    if overall_total else 0.0
                ),
            },
            'items': items,
        }

    def _findings_aging(self, findings, today):
        """Overdue share and age profile of the live findings in scope.

        Age runs from ``created_at`` — a finding that has sat live ninety
        days is a different problem from one raised this morning. One
        aggregate with a filtered Count per bucket, not a query per bucket.
        """
        live = findings.filter(status__in=self.LIVE_FINDING_STATUSES)
        totals = live.aggregate(
            total=Count('id'),
            overdue=Count('id', filter=Q(target_resolution_date__lt=today)),
            bucket_0=Count('id', filter=Q(
                created_at__date__gte=today - datetime.timedelta(days=30),
            )),
            bucket_30=Count('id', filter=Q(
                created_at__date__gte=today - datetime.timedelta(days=60),
                created_at__date__lte=today - datetime.timedelta(days=31),
            )),
            bucket_60=Count('id', filter=Q(
                created_at__date__gte=today - datetime.timedelta(days=90),
                created_at__date__lte=today - datetime.timedelta(days=61),
            )),
            bucket_90=Count('id', filter=Q(
                created_at__date__lte=today - datetime.timedelta(days=91),
            )),
        )
        total = totals['total'] or 0
        overdue = totals['overdue'] or 0
        return {
            'live_findings': total,
            'overdue_findings': overdue,
            'overdue_pct': round(100 * overdue / total, 1) if total else 0.0,
            'buckets': [
                {
                    'days': days,
                    'label': self._aging_label(days),
                    'count': totals[key] or 0,
                }
                for days, key in (
                    (0, 'bucket_0'), (30, 'bucket_30'),
                    (60, 'bucket_60'), (90, 'bucket_90'),
                )
            ],
        }

    @staticmethod
    def _aging_label(days):
        """English label for the bucket starting at ``days``.

        The frontend rewrites these per locale from the ``days`` key; this
        one is the server default so a raw API reader still gets meaning.
        """
        return {
            0: '0-30 days',
            30: '31-60 days',
            60: '61-90 days',
            90: '90+ days',
        }.get(days, f'{days}+ days')

    def _capa_summary(self, actions, today):
        """CAPA implementation rate for the findings in scope.

        ``pending_approval`` is excluded from the total: that is the
        auditee's proposed plan before an approver has signed it, so there
        is no implementation to verify yet. Counting it would let a full
        backlog of unagreed plans read as an implementation failure.
        """
        eligible = actions.exclude(status='pending_approval')
        totals = eligible.aggregate(
            total=Count('id'),
            implemented=Count(
                'id', filter=Q(status__in=CorrectiveAction.TERMINAL_STATUSES),
            ),
        )
        total = totals['total'] or 0
        implemented = totals['implemented'] or 0
        overdue = (
            actions.filter(status__in=self.OPEN_ACTION_STATUSES)
            .filter(
                Q(extended_due_date__lt=today)
                | Q(extended_due_date__isnull=True, due_date__lt=today)
            )
            .count()
        )
        return {
            'total': total,
            'implemented': implemented,
            'rate': round(100 * implemented / total, 1) if total else 0.0,
            'overdue': overdue,
        }

    def _repeat_findings_summary(self, findings):
        """Repeat-finding rate: how much of the register is the same problem again.

        ``is_repeat`` is set when a finding re-occurs against a previous one.
        The rate over all findings in scope is the leadership-level number —
        a rising share here means controls were fixed on paper only.
        """
        totals = findings.aggregate(
            total=Count('id'),
            repeated=Count('id', filter=Q(is_repeat=True)),
        )
        total = totals['total'] or 0
        repeated = totals['repeated'] or 0
        return {
            'total': total,
            'repeated': repeated,
            'rate': round(100 * repeated / total, 1) if total else 0.0,
        }
