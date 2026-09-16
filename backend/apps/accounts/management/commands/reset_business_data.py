"""Empty every transactional table while keeping the accounts and configuration.

The demo seeds and months of hand-entered work have filled the business tables.
``manage.py flush`` cannot clear them because it would take ``accounts.User`` and
``accounts.Role`` with it — the accounts are the one thing worth keeping, since
the org tree, the demo credentials, and every login password hash represent real
setup effort. This command deletes only the transactional rows.

What survives, and why:

* ``User`` / ``Role`` — the point of the exercise.
* ``Department`` — the org tree (executive / corporate / region / service centre /
  audit directorate). Almost every business row points at it via ``SET_NULL``, so
  no delete ordering depends on it, but re-seeding it by hand is the expensive
  part of a rebuild.
* ``ReportTemplate`` / ``SystemSetting`` — configuration. Report generation reads
  templates, so an empty table breaks reporting rather than merely emptying it.
* ``Project`` / ``RiskParameter`` — reference data. ``Project`` auto-fills audit
  universe rows and ``RiskParameter`` weights drive ``RiskAssessment`` scoring.

Deletion order runs leaves-first, so each ``CASCADE`` fires against an
already-empty child and the only rows removed are the listed ones. Two
``SET_NULL`` links would otherwise orphan rows instead of removing them —
``GeneratedReport.engagement`` and ``RiskAssessment.audit_universe`` — so both
models are listed explicitly rather than reached through a cascade.

``RiskAssessment`` overrides ``delete()`` to re-propagate scores into
``AuditUniverse``. ``QuerySet.delete()`` bypasses model ``delete()``, so this
command skips that work entirely; there is nothing left to propagate to.

PK sequences are deliberately NOT reset. Reference numbers (``FND-2026-0001``,
``CAPA-2026-0001``) come from ``apps.common.reference_numbers``, which reads
``Max()`` over existing rows rather than a database sequence — so numbering
restarts at 0001 on its own once the tables are empty. Resetting sequences would
add nothing.

Run ``--dry-run`` first. Every real run ends with a verification pass that
asserts the surviving roles, org tree, and configuration are intact.
"""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import AuditTrail, Department, Role, User
from apps.audit_execution.models import AuditProcedure, AuditProgram, WorkingPaper
from apps.audit_planning.models import (
    AuditEngagement, AuditPlan, AuditTeamMember, AuditUniverse, Project,
)
from apps.common.permissions import ROLE_CAPABILITIES
from apps.corrective_actions.models import ActionResponse, CorrectiveAction, FollowUp
from apps.findings.models import AuditFinding, Evidence, FindingComment
from apps.notifications.models import Notification, SystemSetting
from apps.reports.models import GeneratedReport, ReportTemplate
from apps.risk_assessment.models import RiskAssessment, RiskParameter, SelfAssessment


# Leaves first. Each entry's children are already empty by the time it runs, so
# the returned count is that table's own row count and nothing cascades sideways
# into a model that is still holding rows.
WIPE_TARGETS = [
    (FollowUp, 'capa.FollowUp'),
    (ActionResponse, 'capa.ActionResponse'),
    (CorrectiveAction, 'capa.CorrectiveAction'),
    (FindingComment, 'findings.FindingComment'),
    (Evidence, 'findings.Evidence'),
    (AuditFinding, 'findings.AuditFinding'),
    (WorkingPaper, 'execution.WorkingPaper'),
    (AuditProcedure, 'execution.AuditProcedure'),
    (AuditProgram, 'execution.AuditProgram'),
    (AuditTeamMember, 'planning.AuditTeamMember'),
    (AuditEngagement, 'planning.AuditEngagement'),
    (AuditPlan, 'planning.AuditPlan'),
    (AuditUniverse, 'planning.AuditUniverse'),
    (SelfAssessment, 'risk.SelfAssessment'),
    (RiskAssessment, 'risk.RiskAssessment'),
    (GeneratedReport, 'reports.GeneratedReport'),
    (Notification, 'notifications.Notification'),
    (AuditTrail, 'accounts.AuditTrail'),
]

# Snapshotted before the wipe and re-asserted after, so a cascade that reaches
# further than intended is caught rather than discovered later by a missing
# department or a vanished report template.
KEEP_TARGETS = [
    (User, 'accounts.User'),
    (Role, 'accounts.Role'),
    (Department, 'accounts.Department'),
    (ReportTemplate, 'reports.ReportTemplate'),
    (SystemSetting, 'notifications.SystemSetting'),
    (Project, 'planning.Project'),
    (RiskParameter, 'risk.RiskParameter'),
]

# Owned exclusively by the wiped rows. ``avatars/`` and ``report_templates/``
# belong to User and ReportTemplate, both kept, and are deliberately absent.
MEDIA_DIRS = ['evidence', 'working_papers', 'generated_reports', 'capa_evidence']

CONFIRMATION_WORD = 'wipe'


class Command(BaseCommand):
    help = (
        'Deletes every audit business record (planning, execution, findings, CAPA, '
        'risk, reports, notifications, audit trail) while keeping users, roles, the '
        'org structure, report templates, settings, projects, and risk parameters. '
        'Reference numbers restart at 0001 on their own — PK sequences are not reset.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be deleted and delete nothing.',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help=(
                'Run only the post-wipe integrity checks: business tables empty, '
                'roles and org tree intact. Exits non-zero on failure.'
            ),
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Skip the typed confirmation prompt, for scripted runs.',
        )
        parser.add_argument(
            '--purge-files',
            action='store_true',
            help=(
                'Also delete the uploaded files under media/ that belonged to the '
                'removed rows (evidence, working papers, generated reports, CAPA '
                'evidence). Irreversible.'
            ),
        )
        parser.add_argument(
            '--keep-files',
            action='store_true',
            help='Explicitly leave media/ untouched (the default).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verify_only = options['verify']
        no_input = options['no_input']
        purge_files = options['purge_files']

        if options['keep_files'] and purge_files:
            raise CommandError('--keep-files and --purge-files are mutually exclusive.')

        if verify_only:
            # No pre-wipe snapshot exists on a standalone verify, so the
            # kept-table comparison is skipped and the rest still runs.
            self._verify(kept_before=None)
            return

        kept_before = {label: model.objects.count() for model, label in KEEP_TARGETS}
        found = {label: model.objects.count() for model, label in WIPE_TARGETS}
        total_found = sum(found.values())

        self._report_plan(found, total_found, kept_before)

        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.NOTICE(
                'Dry run — nothing was deleted. Re-run without --dry-run to wipe.'
            ))
            return

        if total_found == 0:
            self.stdout.write('')
            self.stdout.write('Nothing to delete; the business tables are already empty.')
            self._verify(kept_before=kept_before)
            return

        if not no_input and not self._confirm():
            self.stdout.write(self.style.NOTICE('Aborted — nothing was deleted.'))
            return

        self.stdout.write('')
        deleted = {}
        # One transaction for the whole wipe: a failure part-way through rolls
        # back rather than leaving the audit chain half-removed.
        with transaction.atomic():
            for model, label in WIPE_TARGETS:
                rollup, _ = model.objects.all().delete()
                deleted[label] = rollup

        self._report_deleted(deleted)

        if purge_files:
            self._purge_media()
        else:
            self._note_media()

        self._verify(kept_before=kept_before)

    # ── Reporting ─────────────────────────────────────────────────────────
    def _report_plan(self, found, total_found, kept_before):
        width = max(len(label) for _, label in WIPE_TARGETS)
        self.stdout.write(self.style.MIGRATE_HEADING('Rows to delete'))
        for _, label in WIPE_TARGETS:
            self.stdout.write(f'  {label:<{width}}  {found[label]:>7}')
        self.stdout.write(f'  {"TOTAL":<{width}}  {total_found:>7}')

        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Kept, untouched'))
        kept_width = max(len(label) for _, label in KEEP_TARGETS)
        for _, label in KEEP_TARGETS:
            self.stdout.write(f'  {label:<{kept_width}}  {kept_before[label]:>7}')

    def _report_deleted(self, deleted):
        width = max(len(label) for label in deleted)
        self.stdout.write(self.style.MIGRATE_HEADING('Deleted'))
        for label, count in deleted.items():
            self.stdout.write(f'  {label:<{width}}  {count:>7}')
        self.stdout.write(f'  {"TOTAL":<{width}}  {sum(deleted.values()):>7}')
        self.stdout.write('')

    def _note_media(self):
        remaining = self._media_file_count()
        if remaining:
            self.stdout.write(self.style.WARNING(
                f'  {remaining} file(s) under media/ belonged to the deleted rows and '
                'were left on disk. Re-run with --purge-files to remove them.'
            ))
            self.stdout.write('')

    def _confirm(self):
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'This permanently deletes the rows listed above. It cannot be undone '
            'without a database backup.'
        ))
        try:
            answer = input(f'Type "{CONFIRMATION_WORD}" to confirm: ').strip()
        except EOFError:
            # No tty — refuse rather than deleting on an unanswered prompt.
            return False
        return answer == CONFIRMATION_WORD

    # ── Media ─────────────────────────────────────────────────────────────
    def _media_file_count(self):
        media_root = Path(settings.MEDIA_ROOT)
        count = 0
        for name in MEDIA_DIRS:
            target = media_root / name
            if target.exists():
                count += sum(1 for path in target.rglob('*') if path.is_file())
        return count

    def _purge_media(self):
        media_root = Path(settings.MEDIA_ROOT)
        removed = 0
        for name in MEDIA_DIRS:
            target = media_root / name
            if not target.exists():
                continue
            # Counted before rmtree because the directory goes with it.
            removed += sum(1 for path in target.rglob('*') if path.is_file())
            shutil.rmtree(target, ignore_errors=True)

        # Only the four business directories are touched; avatars/ and
        # report_templates/ survive with their parent rows.
        self.stdout.write(f'  Purged {removed} uploaded file(s) from media/.')
        self.stdout.write('')

    # ── Verification ──────────────────────────────────────────────────────
    def _verify(self, kept_before):
        """Post-wipe integrity checks. Raises ``CommandError`` on any failure.

        The point is to catch a wipe that silently damaged the ability to log in
        or administer the system — the failure mode that would otherwise surface
        as a support call rather than as a command error.
        """
        self.stdout.write(self.style.MIGRATE_HEADING('Verification'))
        failures = []

        def check(label, passed, detail=''):
            marker = self.style.SUCCESS('  ok  ') if passed else self.style.ERROR(' FAIL ')
            self.stdout.write(f'{marker} {label}{f" — {detail}" if detail else ""}')
            if not passed:
                failures.append(label)

        # 1. Every business table is empty.
        leftovers = {
            label: model.objects.count()
            for model, label in WIPE_TARGETS
            if model.objects.count()
        }
        check(
            'business tables are empty',
            not leftovers,
            ', '.join(f'{label}={n}' for label, n in leftovers.items()),
        )

        # 2. Nothing on the keep-list moved. Only meaningful with a snapshot.
        if kept_before is not None:
            drifted = {
                label: (kept_before[label], model.objects.count())
                for model, label in KEEP_TARGETS
                if model.objects.count() != kept_before[label]
            }
            check(
                'kept tables unchanged',
                not drifted,
                ', '.join(
                    f'{label} {before}->{after}' for label, (before, after) in drifted.items()
                ),
            )

        # 3. Every role still has someone who can exercise it. This is the check
        #    that catches a wipe that took the demo accounts with it.
        active_by_role = {}
        for role_value, _ in Role.ROLE_CHOICES:
            active_by_role[role_value] = User.objects.filter(
                role=role_value, is_active=True,
            ).count()
        missing_roles = [role for role, n in active_by_role.items() if n == 0]
        check(
            'every role has an active user',
            not missing_roles,
            f'no active user for: {", ".join(missing_roles)}' if missing_roles else
            ', '.join(f'{role}={n}' for role, n in active_by_role.items()),
        )

        # 4. At least one active admin, or User Management is unreachable and the
        #    mistake cannot be repaired from inside the app.
        admins = User.objects.filter(role=Role.ADMIN, is_active=True).count()
        check('an active admin remains', admins > 0, f'{admins} active admin(s)')

        # 5. The capability matrix knows every role the model can produce — a
        #    role added to Role.ROLE_CHOICES but not to ROLE_CAPABILITIES would
        #    silently hold zero capabilities.
        unmapped = [
            role for role, _ in Role.ROLE_CHOICES if role not in ROLE_CAPABILITIES
        ]
        check(
            'capability matrix covers every role',
            not unmapped,
            f'unmapped: {", ".join(unmapped)}' if unmapped else
            f'{len(ROLE_CAPABILITIES)} roles mapped',
        )

        # 6. The org tree survived with a root, since every department picker
        #    cascades down from it.
        departments = Department.objects.count()
        roots = Department.objects.filter(parent__isnull=True).count()
        check(
            'org structure intact',
            departments > 0 and roots > 0,
            f'{departments} unit(s), {roots} root(s)',
        )

        self.stdout.write('')
        if failures:
            raise CommandError(
                f'Verification failed ({len(failures)}): {"; ".join(failures)}'
            )
        self.stdout.write(self.style.SUCCESS('All checks passed.'))
