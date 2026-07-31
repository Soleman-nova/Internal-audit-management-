"""Notification generation helpers.

Central place for creating Notification records from domain events so the
ViewSets stay thin and consistent. Failures here must never break the
underlying business operation (creating a finding, approving a plan, etc.),
so every public helper swallows and logs errors.
"""
import logging

from django.contrib.auth import get_user_model

from .models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()


def notify(user, notification_type, title, message, link=''):
    """Create a single notification for a user.

    Returns the created Notification or None. Never raises: notification
    delivery is best-effort and must not roll back the triggering action.
    """
    if user is None:
        return None
    try:
        return Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link or '',
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception('Failed to create notification for user %s', getattr(user, 'id', None))
        return None


def notify_many(users, notification_type, title, message, link=''):
    """Create the same notification for several users, de-duplicated by id."""
    created = []
    seen = set()
    for user in users:
        if user is None:
            continue
        uid = getattr(user, 'id', None)
        if uid in seen:
            continue
        seen.add(uid)
        obj = notify(user, notification_type, title, message, link)
        if obj is not None:
            created.append(obj)
    return created


def notify_roles(roles, notification_type, title, message, link='', exclude=None):
    """Notify every active user whose role is in ``roles``.

    ``exclude`` is an optional user to skip (e.g. the actor who triggered
    the event and shouldn't be notified about their own action).
    """
    try:
        qs = User.objects.filter(role__in=list(roles), is_active=True)
        if exclude is not None and getattr(exclude, 'id', None) is not None:
            qs = qs.exclude(id=exclude.id)
        return notify_many(list(qs), notification_type, title, message, link)
    except Exception:  # pragma: no cover - defensive
        logger.exception('Failed to notify roles %s', roles)
        return []
