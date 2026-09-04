"""
Centralized audit-trail logging utilities.
"""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def log_audit(request, action, instance, changes=None, object_repr=None, user=None,
              model_name=None):
    """
    Centralized audit-trail logger.

    Args:
        request: DRF Request (for user, IP, user_agent). May be None.
        action: str, one of AuditTrail.ACTION_CHOICES (CREATE/UPDATE/DELETE/APPROVE/REJECT/...)
        instance: model instance being acted on. May be None for bulk actions
            (bulk export/import of many records at once) that log one aggregate
            entry rather than one per record.
        changes: optional dict of {field: (old, new)} for UPDATE actions
        object_repr: optional str to override the default str(instance) representation
        user: optional User to attribute the action to (defaults to request.user)
        model_name: optional model label to use when ``instance`` is None
            (e.g. 'AuditUniverse' for a bulk universe import); ignored otherwise.

    Returns:
        AuditTrail instance or None (best-effort, never raises)
    """
    from apps.accounts.models import AuditTrail

    try:
        if user is None and request is not None:
            user = request.user if request.user.is_authenticated else None
        meta = getattr(request, 'META', {}) or {}
        # Savepoint, so a failed insert here rolls back only itself. Callers now
        # run inside transaction.atomic(); without this the failed query would
        # mark the whole transaction for rollback and every statement after it
        # would raise TransactionManagementError — turning best-effort logging
        # into the thing that blocks the business operation.
        with transaction.atomic():
            return AuditTrail.objects.create(
                user=user,
                action=action,
                model_name=model_name or (instance.__class__.__name__ if instance else ''),
                object_id=str(instance.pk) if instance else '',
                object_repr=(object_repr or str(instance) if instance else object_repr or '')[:300],
                changes=changes or {},
                ip_address=meta.get('REMOTE_ADDR'),
                user_agent=meta.get('HTTP_USER_AGENT', '')[:500],
            )
    except Exception:
        # Best-effort; never block the business operation
        logger.exception(
            'Failed to log audit trail for %s %s',
            action, getattr(instance, '__class__', None) or model_name,
        )
        return None
