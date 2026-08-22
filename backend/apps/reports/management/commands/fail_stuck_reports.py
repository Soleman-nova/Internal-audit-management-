"""Fail forward reports left stuck on ``generating``.

Report compilation runs on a ``daemon=True`` thread (see apps/reports/jobs.py),
so a restart, a deploy, or a hard crash kills every in-flight job without
recording anything. The row keeps ``status='generating'`` forever and the
frontend keeps polling a status that will never change — the user is shown a
spinner with no end and no way to retry.

This command closes those out: anything still ``generating`` past a timeout is
marked ``failed`` with an explanatory message, and its requester is notified,
exactly as a genuine compile failure would be. That gives the UI a terminal
state to render and a Retry to offer.

Idempotent — a second run finds nothing, because the first run moved the rows
off ``generating``. Intended to be scheduled alongside ``flag_overdue_actions``
(Windows Task Scheduler / cron), and worth running once immediately after any
deployment, which is when these rows are created:

    python manage.py fail_stuck_reports
    python manage.py fail_stuck_reports --minutes 60 --dry-run

The timeout must exceed the slowest legitimate compile, or this will kill live
jobs. Thirty minutes is generous for a 1000-row PDF; raise it rather than lower
it if reports on this deployment are large.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify
from apps.reports.models import GeneratedReport

# Comfortably longer than any real compile, so a slow job is never mistaken for
# a dead one. A stuck row costs the user a spinner; a killed live job costs them
# the report.
STUCK_AFTER_MINUTES = 30


class Command(BaseCommand):
    help = 'Mark reports stuck on "generating" past a timeout as failed, and notify requesters.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=STUCK_AFTER_MINUTES,
            help=(
                'Age in minutes past which a still-generating report is considered '
                f'abandoned (default {STUCK_AFTER_MINUTES}).'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List what would be failed without writing anything.',
        )

    def handle(self, *args, **options):
        minutes = options['minutes']
        if minutes < 1:
            # A zero or negative window would put the cutoff at "now" and sweep
            # up reports enqueued this second, whose threads are running
            # perfectly well. CommandError rather than a message so a scheduled
            # run exits non-zero and gets noticed.
            raise CommandError('--minutes must be at least 1.')

        cutoff = timezone.now() - timedelta(minutes=minutes)
        # generated_at is auto_now_add, so it is the moment the request came in —
        # which is what "how long has this been generating" means.
        stuck = GeneratedReport.objects.filter(
            status='generating', generated_at__lt=cutoff,
        ).select_related('generated_by')

        message = (
            f'Generation did not complete within {minutes} minutes and was abandoned, '
            'most likely because the server restarted while the report was being built. '
            'Please request the report again.'
        )

        failed = 0
        for report in stuck:
            if options['dry_run']:
                self.stdout.write(
                    f'  would fail: #{report.id} "{report.title}" '
                    f'({report.format}, requested {report.generated_at.isoformat()})'
                )
                failed += 1
                continue

            # One unit per report rather than one for the whole sweep: a single
            # report that cannot be written must not roll back the ones already
            # cleared, and a long list should not hold a transaction open.
            with transaction.atomic():
                report.status = 'failed'
                report.error_message = message
                report.save(update_fields=['status', 'error_message'])
                # Same shape as a real failure in jobs.py, so the notification
                # is one the user already knows how to read. notify() opens its
                # own savepoint and swallows its errors, so a notification
                # problem cannot leave the status unwritten.
                notify(
                    report.generated_by,
                    'system',
                    f'Report generation failed: {report.title}',
                    f'Your report "{report.title}" could not be generated. {message}',
                    f'/reports?id={report.id}',
                )
            failed += 1

        prefix = 'Would fail' if options['dry_run'] else 'Failed'
        style = self.style.WARNING if failed else self.style.SUCCESS
        self.stdout.write(style(
            f'{prefix} {failed} report(s) stuck on generating for over {minutes} minute(s).'
        ))
