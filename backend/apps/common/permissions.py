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
