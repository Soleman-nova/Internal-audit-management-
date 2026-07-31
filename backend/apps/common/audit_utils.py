"""
Centralized audit-trail logging utilities.
"""
import logging

logger = logging.getLogger(__name__)


def log_audit(request, action, instance, changes=None, object_repr=None, user=None):
    """
    Centralized audit-trail logger.

    Args:
        request: DRF Request (for user, IP, user_agent). May be None.
        action: str, one of AuditTrail.ACTION_CHOICES (CREATE/UPDATE/DELETE/APPROVE/REJECT/...)
        instance: model instance being acted on
        changes: optional dict of {field: (old, new)} for UPDATE actions
        object_repr: optional str to override the default str(instance) representation
        user: optional User to attribute the action to (defaults to request.user)

    Returns:
        AuditTrail instance or None (best-effort, never raises)
    """
    from apps.accounts.models import AuditTrail

    try:
        if user is None and request is not None:
            user = request.user if request.user.is_authenticated else None
        meta = getattr(request, 'META', {}) or {}
        return AuditTrail.objects.create(
            user=user,
            action=action,
            model_name=instance.__class__.__name__,
            object_id=str(instance.pk),
            object_repr=(object_repr or str(instance))[:300],
            changes=changes or {},
            ip_address=meta.get('REMOTE_ADDR'),
            user_agent=meta.get('HTTP_USER_AGENT', '')[:500],
        )
    except Exception:
        # Best-effort; never block the business operation
        logger.exception(
            'Failed to log audit trail for %s %s',
            action, instance.__class__.__name__
        )
        return None
