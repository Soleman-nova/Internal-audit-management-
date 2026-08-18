"""Centralized role-based access control for the EEU Internal Audit system.

A single capability matrix (`ROLE_CAPABILITIES`) maps each role to the set of
capabilities it holds. Small, reusable DRF permission classes consult that matrix
so authorization policy lives in one place instead of being scattered across
viewsets. This is the server-side source of truth; the frontend mirrors the same
matrix for UI gating but never replaces this enforcement.

Roles (from apps.accounts.models.Role):
    admin, audit_manager, supervisor, auditor, auditee
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


# ── Capabilities ────────────────────────────────────────────────────────────
# Coarse-grained capabilities keyed to real actions in the audit workflow.
MANAGE_USERS = 'manage_users'           # create/update/delete users, reset passwords
MANAGE_SETTINGS = 'manage_settings'     # system settings, report templates, risk parameters
APPROVE_PLANS = 'approve_plans'         # approve/submit audit plans, approve programs
WRITE_AUDIT = 'write_audit'             # create/edit audit records (universe, plans, engagements,
                                        # programs, procedures, working papers, findings, CAPAs, risk)
CLOSE_FINDINGS = 'close_findings'       # close/resolve findings
VIEW_AUDIT_TRAIL = 'view_audit_trail'   # read the system-wide audit trail


# ── Role → capability matrix ────────────────────────────────────────────────
ROLE_CAPABILITIES = {
    'admin': {
        MANAGE_USERS, MANAGE_SETTINGS, APPROVE_PLANS,
        WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL,
    },
    'audit_manager': {
        MANAGE_SETTINGS, APPROVE_PLANS,
        WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL,
    },
    'supervisor': {
        APPROVE_PLANS, WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL,
    },
    'auditor': {
        WRITE_AUDIT, CLOSE_FINDINGS,
    },
    'auditee': set(),  # read-only + respond-to-own (handled by object/queryset scoping)
}


def has_capability(user, capability):
    """True if the authenticated user's role holds the given capability."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return capability in ROLE_CAPABILITIES.get(getattr(user, 'role', ''), set())


class HasCapability(BasePermission):
    """Base class: require a single capability for *write* methods.

    Safe methods (GET/HEAD/OPTIONS) are allowed for any authenticated user;
    unsafe methods require `required_capability`. Subclass and set the attribute,
    or use the ready-made subclasses below.
    """
    required_capability = None

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return has_capability(request.user, self.required_capability)


class CanManageUsers(HasCapability):
    required_capability = MANAGE_USERS


class CanManageSettings(HasCapability):
    required_capability = MANAGE_SETTINGS


class CanWriteAudit(HasCapability):
    """Create/edit audit records. Reads open to any authenticated user."""
    required_capability = WRITE_AUDIT


class CanViewAuditTrail(BasePermission):
    """The audit trail is sensitive; even reads require the capability."""
    def has_permission(self, request, view):
        return has_capability(request.user, VIEW_AUDIT_TRAIL)


class RequiresCapability(BasePermission):
    """Gate a specific @action by capability.

    Usage on a viewset action:
        @action(..., permission_classes=[RequiresCapability.for_(APPROVE_PLANS)])
    """
    capability = None

    def has_permission(self, request, view):
        return has_capability(request.user, self.capability)

    @classmethod
    def for_(cls, capability):
        return type(
            f'RequiresCapability_{capability}',
            (cls,),
            {'capability': capability},
        )


class InvolvedPartyOrCapability(BasePermission):
    """Allow capability holders, or the specific users named on the object itself.

    Auditees hold no capabilities, so a plain CanWriteAudit gate locks them out
    of the records that are *about* them — they cannot comment on their own
    finding or attach the evidence being asked of them. Rather than granting
    auditees WRITE_AUDIT across the app, this checks the object's own FK fields
    (``auditee``, ``assigned_to``, ``owner``, …) and lets those people through
    for that one record.

    Object-level only, so it must be used on actions that call
    ``self.get_object()`` — that is what triggers ``check_object_permissions``.

    Field names may traverse relations with dots, so a program's engagement lead
    counts as an involved party: ``for_('prepared_by', 'engagement.lead_auditor')``.

    Usage:
        @action(..., permission_classes=[
            InvolvedPartyOrCapability.for_('auditee', 'assigned_to')])
    """
    capability = WRITE_AUDIT
    object_fields = ()

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if has_capability(request.user, self.capability):
            return True
        return any(
            self._field_user_id(obj, field) == request.user.id
            for field in self.object_fields
        )

    @staticmethod
    def _field_user_id(obj, field):
        """The user id a (possibly dotted) field path points at, or None.

        Compares ``<field>_id`` rather than the related object so the common case
        costs no extra query; only the dotted segments before the last one are
        dereferenced, and a null anywhere along the path short-circuits to None
        instead of raising.
        """
        *path, leaf = field.split('.')
        for step in path:
            obj = getattr(obj, step, None)
            if obj is None:
                return None
        return getattr(obj, f'{leaf}_id', None)

    @classmethod
    def for_(cls, *object_fields, capability=WRITE_AUDIT):
        suffix = '_'.join(object_fields).replace('.', '__')
        return type(
            f'InvolvedPartyOrCapability_{suffix}',
            (cls,),
            {'capability': capability, 'object_fields': tuple(object_fields)},
        )
