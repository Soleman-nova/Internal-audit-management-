"""
Seed demo OPEN findings across the in-flight 2026 engagements.

Why this exists: the dashboard's "Findings by Severity" donut and the "Open
Findings" KPI plot only findings with status ``open``. The live demo dataset had
advanced every finding to closed/draft, so those open-only panels rendered empty
for every role. Findings here default to ``open`` (see AuditFinding.status), so
a few realistic open rows bring the dashboard back to life.

Rerunnable: an engagement already carrying a finding with the same title is
skipped, and reference numbers come from the shared ``FND-YYYY-NNNN`` allocator
so they never collide.

Run:  python manage.py seed_demo_open_findings
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.audit_planning.models import AuditEngagement
from apps.common.reference_numbers import next_reference_number
from apps.findings.models import AuditFinding

# (engagement_number, severity, category, days_until_due, title, condition,
#  criteria, cause, effect, recommendation)
OPEN_FINDINGS = [
    # FPA ENG-2026-FPA-001 is in progress -> its findings drive the FPA scope.
    (
        'ENG-2026-FPA-001', 'critical', 'fraud', 30,
        'Cash Advances Liquidated Without Original Supporting Receipts',
        'Three of six sampled cash-advance liquidations in Q2 were approved '
        'against photocopies only; the original receipts were never obtained.',
        'EEU Finance Directive 03/2024 requires every liquidation to be backed '
        'by original receipts before the next advance is released.',
        'Advance holders are cleared without the cashier sighting originals, and '
        'the approving officer relies on the advance ledger alone.',
        'Duplicates and inflated claims can pass unnoticed; EEU has no assurance '
        'advances were spent on the intended activities.',
        'Withhold further advances until originals are seen, and have an '
        'independent officer sample-verify liquidations monthly.',
    ),
    (
        'ENG-2026-FPA-001', 'medium', 'control_deficiency', 45,
        'Vendor Master File Changes Approved Without Segregation of Duties',
        'Bank details for two vendors were entered and approved by the same '
        'officer in the finance module.',
        'Payment policy requires a different officer to authorise vendor master '
        'changes from the one who records them.',
        'A small finance team collapses record and approve onto one person when '
        'workload peaks.',
        'A compromised account could redirect a payment with no second person '
        'having noticed the change.',
        'Route vendor bank-detail edits to the finance manager for approval and '
        'review the audit trail each month.',
    ),
    # Technical Audit, currently in fieldwork.
    (
        'ENG-2026-TA-001', 'high', 'compliance', 35,
        'Contractor Substituted Specified Cables Without Engineer Approval',
        'Site inspection found a 4.2 km section energised with a lower-rated '
        'cable than the contract specified.',
        'Contract S-112 clause 14 prohibits substitution without the resident '
        "engineer's written approval.",
        'The contractor claimed a supply shortage and proceeded; the supervisor '
        'logged it informally rather than stopping the work.',
        'The installed cable is below design rating, risking overloads and '
        'premature failure across that network section.',
        'Enforce the specification, or document an approved engineering variance '
        'with a de-rating assessment.',
    ),
    # IT Audit, currently in progress.
    (
        'ENG-2026-ITA-001', 'high', 'it_security', 40,
        'Privileged Accounts Shared Across the Financial System Administration',
        'Five administrators sign into the ERP with one shared privileged '
        'account; password history shows no rotation in the last 90 days.',
        'IT security standard ISS-07 requires individual, named privileged '
        'accounts with periodic rotation.',
        'Legacy convenience: the account predates directory-based '
        'authentication and was never decomposed.',
        'No individual accountability for privileged actions; one leaked '
        'credential compromises the whole financial platform.',
        'Issue individual admin accounts, disable the shared one, and integrate '
        'with the corporate directory (SSO).',
    ),
    (
        'ENG-2026-ITA-001', 'medium', 'it_security', 30,
        'Annual User Access Recertification Not Performed for 2026',
        'No ERP access recertification has run since last year; 23 departed '
        'staff still hold active logins.',
        'ISS-04 mandates an annual recertification of all system access by the '
        'relevant data owners.',
        'Recertification was scheduled, but ownership of the process moved '
        'between units and was never re-assigned.',
        'Departees retain access to records they no longer need, widening the '
        'insider-risk surface.',
        'Run the 2026 recertification, disable orphaned accounts, and fix an '
        'accountable owner for the annual cycle.',
    ),
    # Legacy-style EEU Annual Audit Plan engagements, also in progress/fieldwork.
    (
        'ENG-2026-001', 'low', 'operational', 60,
        'Regional Pool Fuel Logs Reconciled Only Quarterly',
        'Regional fleet fuel logs are reconciled to bulk fuel withdrawals once a '
        'quarter rather than every month.',
        'Fleet management procedure requires monthly reconciliation of fuel '
        'drawn against mileage logs.',
        'The regional pool has no dedicated clerk, so reconciliation accumulates '
        'alongside other duties.',
        'Fuel losses or misappropriation can go undetected for up to three '
        'months.',
        'Move to monthly reconciliation and have the regional finance officer '
        'sign off each log.',
    ),
    (
        'ENG-2026-002', 'high', 'operational', 45,
        'Regional Warehouse Stock Counts Not Independently Verified',
        'Cycle counts at two regional warehouses were performed and recorded by '
        'the same storekeeper who holds the stock.',
        'Inventory policy requires counts to be verified by someone independent '
        'of custody.',
        'Field stations carry a single stores position with no rotation or '
        'cross-station verification arranged.',
        'Shortages or pilferage can be concealed by the counter, so the reported '
        'balances are unreliable.',
        'Arrange cross-station or mobile-team verification of counts and '
        'spot-check high-value items.',
    ),
]


class Command(BaseCommand):
    help = ('Seeds realistic OPEN findings across the in-flight 2026 demo '
            'engagements so the dashboard donut and KPIs are populated')

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        identified_by = User.objects.filter(employee_id='EEU-10004', is_active=True).first()
        auditee = User.objects.filter(employee_id='EEU-10005', is_active=True).first()
        if not identified_by or not auditee:
            self.stdout.write(self.style.WARNING(
                'Demo auditor (EEU-10004) / auditee (EEU-10005) not found; '
                'findings will be created without assigned users.'
            ))

        self.stdout.write(self.style.MIGRATE_HEADING('Seeding demo OPEN findings...'))
        created = skipped = missing = 0
        for row in OPEN_FINDINGS:
            (number, severity, category, days, title,
             condition, criteria, cause, effect, recommendation) = row
            engagement = AuditEngagement.objects.filter(engagement_number=number).first()
            if engagement is None:
                missing += 1
                self.stdout.write(self.style.WARNING(
                    f'  - skip {number}: engagement not found'
                ))
                continue
            if AuditFinding.objects.filter(engagement=engagement, title=title).exists():
                skipped += 1
                self.stdout.write(self.style.WARNING(
                    f'  - skip {engagement.engagement_number}: already has "{title[:40]}..."'
                ))
                continue
            AuditFinding.objects.create(
                engagement=engagement,
                finding_number=next_reference_number(
                    AuditFinding, 'finding_number', 'FND', year=today.year),
                title=title,
                description=f'{condition} {recommendation}',
                severity=severity,
                category=category,
                status='open',
                condition=condition,
                criteria=criteria,
                cause=cause,
                effect=effect,
                recommendation=recommendation,
                identified_by=identified_by,
                assigned_to=auditee,
                auditee=auditee,
                target_resolution_date=today + timezone.timedelta(days=days),
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  + created open {severity} finding on {number}'
            ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Done: {created} created, {skipped} already present, {missing} engagement(s) missing.'
        ))
