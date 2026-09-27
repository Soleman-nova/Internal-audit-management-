"""Notification generation helpers.

Central place for creating Notification records from domain events so the
ViewSets stay thin and consistent. Failures here must never break the
underlying business operation (creating a finding, approving a plan, etc.),
so every public helper swallows and logs errors.

An email channel sits alongside the in-app one, off by default and switched on by
the `enable_email_alerts` SystemSetting. It is opt-in per call (`email=True`)
rather than a rule keyed on `notification_type`: the caller knows whether an event
is worth someone's inbox, and a type allowlist silently stops covering new types
as they are added.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction

from .models import Notification, SystemSetting

logger = logging.getLogger(__name__)
User = get_user_model()

EMAIL_ALERTS_SETTING = 'enable_email_alerts'


def email_alerts_enabled():
    """Whether the CAPA email channel is switched on.

    The value is a `TextField` holding whatever an administrator typed ("True",
    "yes", "1"), so it is parsed rather than trusted.

    A missing row means the setting was never seeded, and that reads as **off**:
    starting to send mail nobody asked for is a worse failure than not sending it,
    and the opposite default would turn "we never configured this" into a surprise.
    Read per call rather than cached so toggling it in Settings takes effect without
    a restart.
    """
    try:
        raw = (
            SystemSetting.objects
            .filter(key=EMAIL_ALERTS_SETTING)
            .values_list('value', flat=True)
            .first()
        )
    except Exception:  # pragma: no cover - defensive, mirrors notify()
        logger.exception('Could not read the %s setting', EMAIL_ALERTS_SETTING)
        return False

    if raw is None:
        return False
    return str(raw).strip().lower() in {'true', '1', 'yes', 'on'}


def send_notification_email(user, title, message, link=''):
    """Email one notification. Never raises, for the same reason `notify` doesn't.

    Best-effort like the in-app channel: a mail server that is down must not fail
    the finding or CAPA write that triggered this.

    Sent synchronously, once it runs. That is acceptable at this volume — a handful
    of messages a day from a scheduled job or one user action — and it is what keeps
    the feature deployable with no broker. If volume grows, this is the function to
    move onto a queue; `celery` is already pinned in requirements.txt.
    """
    address = getattr(user, 'email', '')
    if not address:
        # Accounts are keyed on employee_id and an email is not guaranteed. Skipping
        # is right; inventing an address or raising is not.
        return False

    try:
        body = message
        if link:
            # The stored link is an app-relative path (/capa/12), which is
            # meaningless in an inbox — the recipient needs the absolute URL.
            body = f'{message}\n\n{settings.FRONTEND_URL.rstrip("/")}{link}'
        send_mail(
            subject=title,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[address],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception('Failed to email a notification to %s', address)
        return False


def notify(user, notification_type, title, message, link='', email=False):
    """Create a single notification for a user.

    Returns the created Notification or None. Never raises: notification
    delivery is best-effort and must not roll back the triggering action.

    ``email=True`` also mirrors it to the user's address, when the
    `enable_email_alerts` setting is on.
    """
    if user is None:
        return None
    try:
        # Savepoint: callers wrap their writes in transaction.atomic(), and a
        # failure here must not poison that transaction. Without it, a bad
        # notification would take the finding/CAPA down with it — the opposite
        # of the best-effort contract in this module's docstring.
        with transaction.atomic():
            created = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                message=message,
                link=link or '',
            )

        # Registered *outside* the atomic block above, and deferred by on_commit.
        # Email is not transactional: sending it while the caller's own atomic
        # block is still open would deliver mail about a change that then rolled
        # back. on_commit runs it only once the outermost transaction commits —
        # or immediately when there is no transaction, which is why this sits
        # after the savepoint rather than inside it.
        if email and email_alerts_enabled():
            transaction.on_commit(
                lambda: send_notification_email(user, title, message, link or '')
            )

        return created
    except Exception:  # pragma: no cover - defensive
        logger.exception('Failed to create notification for user %s', getattr(user, 'id', None))
        return None


def notify_many(users, notification_type, title, message, link='', email=False):
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
        obj = notify(user, notification_type, title, message, link, email=email)
        if obj is not None:
            created.append(obj)
    return created


def notify_roles(roles, notification_type, title, message, link='', exclude=None, email=False):
    """Notify every active user whose role is in ``roles``.

    ``exclude`` is an optional user to skip (e.g. the actor who triggered
    the event and shouldn't be notified about their own action).
    """
    try:
        qs = User.objects.filter(role__in=list(roles), is_active=True)
        if exclude is not None and getattr(exclude, 'id', None) is not None:
            qs = qs.exclude(id=exclude.id)
        return notify_many(list(qs), notification_type, title, message, link, email=email)
    except Exception:  # pragma: no cover - defensive
        logger.exception('Failed to notify roles %s', roles)
        return []
