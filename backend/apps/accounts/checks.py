"""Startup checks.

Django runs these on `manage.py check`, on `runserver`, and in CI, which makes
them the right place for failures that are otherwise invisible — a server that
starts cleanly but cannot do its job.

Two so far: the Logto dependency below, and the scheduled-CAPA-job check that
follows it.
"""
from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def logto_crypto_available(app_configs, **kwargs):
    """Error when Logto is configured but ES384 verification is impossible."""
    # Nothing to verify against means nothing to warn about: an environment with no
    # Logto (CI, a fresh clone) is a supported state, not a misconfiguration.
    if not settings.LOGTO_ENDPOINT:
        return []

    try:
        import cryptography  # noqa: F401
    except ImportError:
        return [
            Error(
                'Logto is configured (LOGTO_ENDPOINT is set) but the `cryptography` '
                'package is missing, so ES384 ID-token signatures cannot be verified. '
                'Every Logto sign-in will fail with a 401 "Logto token could not be '
                'verified", which reads as a bad token rather than a missing package.',
                hint='Install it (pinned in requirements.txt): '
                     'pip install -r requirements.txt',
                id='accounts.E001',
            )
        ]

    return []


@register()
def overdue_capas_are_still_open(app_configs, **kwargs):
    """Warn when past-due corrective actions are still open — the job is not running.

    `flag_overdue_actions` is the only thing that moves a past-due CAPA to
    `overdue` and emits the `action_overdue` / `action_due` / `follow_up`
    notifications. Nothing calls it on its own: the deployment has to schedule it
    (README "scheduled jobs", USER_MANUAL#scheduled-jobs). When nobody has, the
    entire feature is inert — and inert is indistinguishable from "nothing is
    overdue", so it goes unnoticed for as long as the deployment survives.

    **Derived, deliberately.** A past-due action still sitting in `open` /
    `in_progress` *is* the evidence that the job has not run, so this needs no new
    column, migration or bookkeeping — and there is no timestamp to forget to
    write.

    A Warning rather than an Error: the application is fully functional, it is the
    automation that is missing. An Error would also fail `manage.py test`, which
    runs these checks against an empty database.
    """
    from django.db.models import Q
    from django.db.utils import OperationalError, ProgrammingError
    from django.utils import timezone

    from apps.corrective_actions.models import CorrectiveAction

    try:
        today = timezone.now().date()
        stale = CorrectiveAction.objects.filter(
            # Mirrors the command's own notion of "past due": an extension wins
            # over the original due date, so an action with a past `due_date` and
            # a future `extended_due_date` is correctly left alone by the job and
            # must not be counted as evidence against it here.
            Q(extended_due_date__lt=today)
            | Q(extended_due_date__isnull=True, due_date__lt=today),
            status__in=['open', 'in_progress'],
        ).count()
    except (OperationalError, ProgrammingError):
        # `check` runs before `migrate` on a fresh database, and in CI. A table
        # that does not exist yet is not this check's business to report.
        return []

    if not stale:
        return []

    return [
        Warning(
            f'{stale} corrective action(s) are past due but still marked open, so '
            f'`flag_overdue_actions` is not being run on a schedule. They will never '
            f'flip to `overdue`, and their owners will never receive an overdue, '
            f'due-soon or follow-up notification.',
            hint='Schedule the job daily — see README.md "scheduled jobs" and '
                 'USER_MANUAL.md#scheduled-jobs for the Task Scheduler and cron '
                 'commands. Running it once by hand also clears this: '
                 'python manage.py flag_overdue_actions',
            id='accounts.W001',
        )
    ]
