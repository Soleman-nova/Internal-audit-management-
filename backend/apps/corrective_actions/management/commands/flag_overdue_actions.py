"""
Management command to detect overdue and due-soon corrective actions.

Transitions past-due CAPAs to 'overdue', emits notifications for overdue items,
due-soon reminders (within N days), and scheduled follow-ups.

Idempotent: safe to run multiple times per day. Intended to be scheduled via
Windows Task Scheduler / cron (e.g. daily at 8 AM):

    python manage.py flag_overdue_actions
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.corrective_actions.models import CorrectiveAction, FollowUp
from apps.notifications.services import notify

DUE_SOON_DAYS = 3


class Command(BaseCommand):
    help = 'Flag overdue corrective actions and emit due/overdue/follow-up notifications.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=DUE_SOON_DAYS,
            help=f'Days-ahead window for due-soon reminders (default {DUE_SOON_DAYS}).',
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        due_soon_window = today + timedelta(days=options['days'])

        overdue_count = 0
        due_soon_count = 0
        followup_count = 0

        # Active corrective actions that could be overdue or due soon.
        active = CorrectiveAction.objects.filter(
            status__in=['open', 'in_progress']
        ).select_related('owner', 'finding')

        for action in active:
            effective_due = action.extended_due_date or action.due_date
            if effective_due is None:
                continue

            link = f'/follow-up?action={action.id}'

            if effective_due < today:
                # Past due -> flip to overdue and notify the owner.
                action.status = 'overdue'
                action.save(update_fields=['status', 'updated_at'])
                overdue_count += 1
                notify(
                    action.owner,
                    'action_overdue',
                    f'Corrective action overdue: {action.action_number}',
                    f'The corrective action "{action.title}" was due on '
                    f'{effective_due.isoformat()} and is now overdue.',
                    link,
                )
            elif effective_due <= due_soon_window and not action.due_reminder_sent:
                # Due within the window and not yet reminded.
                due_soon_count += 1
                action.due_reminder_sent = True
                action.save(update_fields=['due_reminder_sent', 'updated_at'])
                notify(
                    action.owner,
                    'action_due',
                    f'Corrective action due soon: {action.action_number}',
                    f'The corrective action "{action.title}" is due on '
                    f'{effective_due.isoformat()}.',
                    link,
                )

        # Scheduled follow-ups that are due -> remind the corrective-action owner.
        follow_ups = FollowUp.objects.filter(
            scheduled_date__lte=today, status='scheduled'
        ).select_related('corrective_action', 'corrective_action__owner')

        for follow_up in follow_ups:
            capa = follow_up.corrective_action
            followup_count += 1
            notify(
                capa.owner if capa else None,
                'follow_up',
                f'Follow-up due: {capa.action_number if capa else ""}',
                f'A follow-up scheduled for {follow_up.scheduled_date.isoformat()} '
                f'on "{capa.title if capa else ""}" is due.',
                f'/follow-up?action={capa.id}' if capa else '',
            )

        self.stdout.write(self.style.SUCCESS(
            f'Overdue flagged: {overdue_count} | '
            f'Due-soon reminders: {due_soon_count} | '
            f'Follow-up reminders: {followup_count}'
        ))
