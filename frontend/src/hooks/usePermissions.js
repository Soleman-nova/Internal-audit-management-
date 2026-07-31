// Frontend mirror of backend/apps/common/permissions.py.
// This drives UI gating ONLY (hiding buttons/nav, guarding routes). The backend
// capability matrix remains the real enforcement — keep the two in sync.

export const CAPABILITIES = {
  MANAGE_USERS: 'manage_users',
  MANAGE_SETTINGS: 'manage_settings',
  APPROVE_PLANS: 'approve_plans',
  WRITE_AUDIT: 'write_audit',
  CLOSE_FINDINGS: 'close_findings',
  VIEW_AUDIT_TRAIL: 'view_audit_trail',
};

const {
  MANAGE_USERS, MANAGE_SETTINGS, APPROVE_PLANS,
  WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL,
} = CAPABILITIES;

export const ROLE_CAPABILITIES = {
  admin: [MANAGE_USERS, MANAGE_SETTINGS, APPROVE_PLANS, WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL],
  audit_manager: [MANAGE_SETTINGS, APPROVE_PLANS, WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL],
  supervisor: [APPROVE_PLANS, WRITE_AUDIT, CLOSE_FINDINGS, VIEW_AUDIT_TRAIL],
  auditor: [WRITE_AUDIT, CLOSE_FINDINGS],
  auditee: [],
};

export function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}');
  } catch {
    return {};
  }
}

export function hasCapability(user, capability) {
  if (!user) return false;
  if (user.is_superuser) return true;
  const caps = ROLE_CAPABILITIES[user.role] || [];
  return caps.includes(capability);
}

// Hook: returns the current user's capability helpers. Reads from localStorage,
// matching how the rest of the app resolves the logged-in user.
export function usePermissions() {
  const user = getCurrentUser();
  const can = (capability) => hasCapability(user, capability);
  return {
    user,
    role: user.role,
    can,
    canManageUsers: can(MANAGE_USERS),
    canManageSettings: can(MANAGE_SETTINGS),
    canApprovePlans: can(APPROVE_PLANS),
    canWriteAudit: can(WRITE_AUDIT),
    canCloseFindings: can(CLOSE_FINDINGS),
    canViewAuditTrail: can(VIEW_AUDIT_TRAIL),
  };
}

export default usePermissions;
