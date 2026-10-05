"""Role-by-role tests for the corrective-action (CAPA) API.

Covers CAPA numbering and owner notification, the auditee's right to propose the
remediation plan for a finding that concerns them (and only for those), the
owner's right to respond to their own action, the split between the statuses an
owner may report and the ones the audit side records, ``verify-and-close`` as the
auditor's single act of verification and closure, the ownership gate on
``schedule-followup``, the auditor sign-off that ends ``pending_approval``, the
paginated ``overdue`` list and its due-date boundary, ``summary`` counts, and
both branches of the auditee read scoping.
"""
import datetime
import shutil
import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.checks import overdue_capas_are_still_open
from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_action, make_engagement, make_finding,
    notification_titles,
)
from apps.corrective_actions.models import ActionResponse, CorrectiveAction, FollowUp
from apps.findings.models import AuditFinding
from apps.notifications.models import Notification, SystemSetting

ACTIONS_URL = '/api/corrective/actions/'


class CorrectiveActionCreateTest(RoleFixtureMixin, TestCase):
    """Creation is WRITE_AUDIT; the number and the assigner are the server's."""

    def setUp(self):
        super().setUp()
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
        )

    def payload(self, **kwargs):
        data = {
            'finding': self.finding.id,
            'title': 'Reinstate the authorisation control',
            'description': 'Require dual approval on journal entries.',
            'recommendation': 'Configure the ERP approval workflow.',
            'owner': self.auditee.id,
            'priority': 'high',
            'due_date': (timezone.now().date() + datetime.timedelta(days=30)).isoformat(),
        }
        data.update(kwargs)
        return data

    def test_every_role_may_raise_a_capa_on_a_finding_that_concerns_them(self):
        """No role is refused here any more.

        The auditee used to be, on the class-level WRITE_AUDIT gate. They now
        reach creation through `CanProposeCorrectiveAction`, which asks the
        finding rather than the role — and this fixture's finding is scoped to
        their own directorate, so it is theirs. What the auditee may *not* do is
        covered by `AuditeeProposesCapaTest` and by the update/delete paths,
        which are still capability-gated.
        """
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 201,
        }, lambda client, role: client.post(
            ACTIONS_URL, self.payload(title=f'CAPA by {role}'), format='json',
        ))

    def test_server_assigns_the_number_and_the_assigner(self):
        response = self.as_user(self.auditor).post(
            ACTIONS_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        action = CorrectiveAction.objects.get(pk=response.data['id'])
        self.assertRegex(action.action_number, r'^CAPA-\d{4}-\d{4}$')
        self.assertEqual(action.assigned_by, self.auditor)

    def test_owner_is_notified_with_the_due_date(self):
        self.as_user(self.auditor).post(ACTIONS_URL, self.payload(), format='json')
        notification = Notification.objects.filter(
            user=self.auditee, notification_type='assigned',
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('due', notification.message)
        self.assertEqual(notification_titles(self.auditor), [])

    def test_reassignment_notifies_the_new_owner_only(self):
        action = make_action(
            finding=self.finding, owner=self.auditee, assigned_by=self.auditor,
        )
        newcomer = self.make_user(Role.AUDITEE, department=self.department)
        response = self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action.id}/', {'owner': newcomer.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(
                user=newcomer, notification_type='assigned',
            ).exists()
        )
        self.assertEqual(notification_titles(self.auditee), [])

    def test_crud_is_audit_logged(self):
        client = self.as_user(self.auditor)
        created = client.post(ACTIONS_URL, self.payload(), format='json')
        action_id = created.data['id']
        client.patch(f'{ACTIONS_URL}{action_id}/', {'status': 'in_progress'}, format='json')
        client.delete(f'{ACTIONS_URL}{action_id}/')

        entries = list(
            AuditTrail.objects
            .filter(model_name='CorrectiveAction', object_id=str(action_id))
            .order_by('timestamp')
        )
        self.assertCountEqual(
            [e.action for e in entries], ['CREATE', 'UPDATE', 'DELETE'],
        )
        update = next(e for e in entries if e.action == 'UPDATE')
        self.assertEqual(update.changes, {'status': ['open', 'in_progress']})


class AuditeeProposesCapaTest(RoleFixtureMixin, TestCase):
    """Spec Step 11 — the auditee acknowledges the finding and formulates the plan.

    The class-level WRITE_AUDIT gate used to 403 this outright, so the audit
    team wrote the auditee's remediation plan on their behalf and the approval
    step that follows it had nothing of the auditee's to approve. Creation is
    the only write the auditee gains; `get_permissions` narrows the exception to
    `create`, so editing, reassigning and deleting stay capability-gated.
    """

    def setUp(self):
        super().setUp()
        # A second auditor so "lead auditor" and "whoever raised the finding"
        # are different people — otherwise the fallback test cannot tell them
        # apart and would pass whichever one the routing happened to pick.
        self.raiser = self.make_user(Role.AUDITOR, department=self.department)
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        self.finding = make_finding(
            engagement=self.engagement, identified_by=self.raiser,
            auditee=self.auditee, status=AuditFinding.AWAITING_AUDITEE,
        )

    def payload(self, **kwargs):
        data = {
            'finding': self.finding.id,
            'title': 'Reinstate the authorisation control',
            'description': 'Require dual approval on journal entries.',
            'recommendation': 'Configure the ERP approval workflow.',
            'priority': 'high',
            'due_date': (timezone.now().date() + datetime.timedelta(days=30)).isoformat(),
        }
        data.update(kwargs)
        return data

    def propose(self, **kwargs):
        return self.as_user(self.auditee).post(
            ACTIONS_URL, self.payload(**kwargs), format='json',
        )

    def proposed_action(self, **kwargs):
        response = self.propose(**kwargs)
        self.assertEqual(response.status_code, 201, response.data)
        return CorrectiveAction.objects.get(pk=response.data['id'])

    def test_the_auditee_can_propose_a_plan(self):
        self.assertIsNotNone(self.proposed_action())

    def test_the_proposal_lands_awaiting_approval_rather_than_live(self):
        self.assertEqual(self.proposed_action().status, 'pending_approval')

    def test_the_auditee_owns_their_own_proposal(self):
        self.assertEqual(self.proposed_action().owner, self.auditee)

    def test_the_plan_is_routed_to_the_lead_auditor_not_its_author(self):
        """`assigned_by` is the approve/verify gate, so it must name an auditor.

        Pointed at the auditee who wrote the plan it would be a self-approval
        loop; the lead auditor is who spec Step 12 has sign it off.
        """
        self.assertEqual(self.proposed_action().assigned_by, self.auditor)

    def test_routing_falls_back_to_whoever_raised_the_finding(self):
        self.engagement.lead_auditor = None
        self.engagement.save(update_fields=['lead_auditor'])
        self.assertEqual(self.proposed_action().assigned_by, self.raiser)

    def test_a_client_supplied_status_and_owner_are_ignored(self):
        """Both are writable model fields, so a POST carrying them would be a
        way to open a closed action — or, through the cascade, to close the
        finding behind it — in a single request."""
        action = self.proposed_action(
            status='closed', owner=self.supervisor.id,
        )
        self.assertEqual(action.status, 'pending_approval')
        self.assertEqual(action.owner, self.auditee)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, AuditFinding.AWAITING_AUDITEE)

    def test_the_lead_auditor_is_told_and_can_approve(self):
        action = self.proposed_action()
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='assigned',
            ).exists(),
            'the plan landed in nobody\'s queue',
        )
        response = self.as_user(self.auditor).post(
            f'{ACTIONS_URL}{action.id}/approve/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        action.refresh_from_db()
        self.assertEqual(action.status, 'open')
        self.assertEqual(action.approved_by, self.auditor)

    def test_the_auditee_cannot_approve_their_own_proposal(self):
        action = self.proposed_action()
        response = self.as_user(self.auditee).post(f'{ACTIONS_URL}{action.id}/approve/')
        self.assertEqual(response.status_code, 403, response.data)
        action.refresh_from_db()
        self.assertEqual(action.status, 'pending_approval')

    def test_a_finding_belonging_to_another_directorate_is_refused(self):
        theirs = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.other_department,
            ),
            identified_by=self.raiser,
        )
        response = self.propose(finding=theirs.id)
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(CorrectiveAction.objects.filter(finding=theirs).exists())

    def test_an_auditee_cannot_edit_or_delete_what_they_proposed(self):
        """The proposal is the whole of what they gain — otherwise they could
        PATCH the action straight to `closed` and settle the finding."""
        action = self.proposed_action()
        client = self.as_user(self.auditee)
        self.assertEqual(
            client.patch(f'{ACTIONS_URL}{action.id}/', {'status': 'closed'},
                         format='json').status_code,
            403,
        )
        self.assertEqual(client.delete(f'{ACTIONS_URL}{action.id}/').status_code, 403)
        action.refresh_from_db()
        self.assertEqual(action.status, 'pending_approval')


class StatusEditGateTest(RoleFixtureMixin, TestCase):
    """Which status moves an ordinary PATCH may not make.

    `perform_update` already refused a terminal status written by anyone the
    sign-off rule does not name. These are the rest: statuses whose owning route
    does more than write the status, so accepting them in an edit let a status
    write stand in for the thing that should have happened first.

    400 rather than 403 throughout — see the guard: these refusals are about the
    request asking an edit to do a transition's job, not about who is asking.
    """

    def setUp(self):
        super().setUp()
        self.auditor_two = self.make_user(Role.AUDITOR, department=self.department)
        self.finding = make_finding(identified_by=self.auditor)
        self.action = make_action(
            finding=self.finding, owner=self.auditee, assigned_by=self.auditor,
        )

    def patch_status(self, status, user=None, action=None):
        action = action or self.action
        return self.as_user(user or self.auditor).patch(
            f'{ACTIONS_URL}{action.id}/', {'status': status}, format='json',
        )

    # ── pending_approval: `approve` owns both ends of the transition ────────
    def test_a_proposal_cannot_be_opened_by_writing_the_status(self):
        """`approve` asks who is answering the proposal and stamps who and when.

        A PATCH asks nobody. Accepted, it let any auditor move a plan off
        `pending_approval` — opening work on an auditee's proposal that no one had
        agreed to, with no approver recorded and the owner never notified.
        """
        self.action.status = 'pending_approval'
        self.action.save(update_fields=['status'])

        response = self.patch_status('open')

        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'pending_approval')
        self.assertIsNone(self.action.approved_by)
        self.assertIsNone(self.action.approved_at)

    def test_an_open_action_cannot_be_put_back_into_awaiting_approval(self):
        response = self.patch_status('pending_approval')
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    def test_the_approve_route_still_works(self):
        """The positive control for the two tests above."""
        self.action.status = 'pending_approval'
        self.action.save(update_fields=['status'])

        response = self.as_user(self.supervisor).post(
            f'{ACTIONS_URL}{self.action.id}/approve/'
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    # ── The system-derived and outcome-assessment statuses ─────────────────
    def test_overdue_cannot_be_written_by_hand(self):
        """`flag_overdue_actions` derives it from the due date, and a due date
        moved forward by an ordinary edit is the only correction available."""
        response = self.patch_status('overdue')
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    def test_not_implemented_cannot_be_written_by_hand(self):
        """`verify-and-close` records it beside the follow-up visit that justifies
        calling the remedy a failure. Without the visit it is an assertion."""
        response = self.patch_status('not_implemented')
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    # ── Settled actions do not rewind ─────────────────────────────────────
    def test_a_closed_action_cannot_be_rewound(self):
        """There is no reopen route, and `_sync_parent` would carry the rewinding
        back to the finding: a settled action whose finding is suddenly open again
        is a record of an audit nobody knows happened."""
        self.action.status = 'closed'
        self.action.save(update_fields=['status'])
        self.finding.status = 'closed'
        self.finding.save(update_fields=['status'])

        response = self.patch_status('in_progress', user=self.supervisor)

        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'closed')

    def test_a_resolved_action_cannot_be_rewound_either(self):
        self.action.status = 'resolved'
        self.action.save(update_fields=['status'])
        response = self.patch_status('open', user=self.supervisor)
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'resolved')

    # ── What an edit must still be able to do ──────────────────────────────
    def test_progress_statuses_are_still_editable_by_the_audit_team(self):
        """The guard is about reserved transitions, not about writes in general.

        An auditor who is neither the assigner nor an approver still records
        progress on a colleague's action — that is what the edit is for.
        """
        response = self.patch_status('partially_resolved', user=self.auditor_two)
        self.assertEqual(response.status_code, 200, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'partially_resolved')

    def test_editing_other_fields_is_unaffected(self):
        response = self.as_user(self.auditor_two).patch(
            f'{ACTIONS_URL}{self.action.id}/',
            {'due_date': (timezone.now().date() + datetime.timedelta(days=60)).isoformat()},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.action.refresh_from_db()
        self.assertEqual(
            self.action.due_date, timezone.now().date() + datetime.timedelta(days=60),
        )

    def test_an_auditor_who_is_not_the_approver_still_cannot_settle_it(self):
        """The 403 half of the guard, now reachable by an auditor.

        Until this only an auditee had been caught here, and they were already
        refused at the class-level WRITE_AUDIT gate — so the sign-off rule had no
        test of its own and no auditor had ever been subject to it.
        """
        self.action.assigned_by = None
        self.action.save(update_fields=['assigned_by'])

        response = self.patch_status('closed', user=self.auditor_two)

        self.assertEqual(response.status_code, 403, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='eeu-capa-test-'))
class AddResponseTest(RoleFixtureMixin, TestCase):
    """The owner answers for their own action — including auditees."""

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.action = make_action(owner=self.auditee, assigned_by=self.auditor)
        self.url = f'{ACTIONS_URL}{self.action.id}/add-response/'

    def respond_as(self, user, status_update='in_progress', with_file=False,
                   filename='proof.txt'):
        data = {
            'response_text': 'Workflow configured; awaiting the next cycle.',
            'status_update': status_update,
        }
        if with_file:
            data['evidence_file'] = SimpleUploadedFile(
                filename, b'configuration export', content_type='text/plain',
            )
            return self.as_user(user).post(self.url, data, format='multipart')
        return self.as_user(user).post(self.url, data, format='json')

    def test_owner_can_respond_and_the_status_moves(self):
        response = self.respond_as(self.auditee)
        self.assertEqual(response.status_code, 201, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'in_progress')
        self.assertEqual(
            ActionResponse.objects.get(pk=response.data['id']).responder, self.auditee,
        )

    def test_owner_can_attach_evidence_to_their_response(self):
        response = self.respond_as(self.auditee, with_file=True)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(ActionResponse.objects.get(pk=response.data['id']).evidence_file)

    def test_an_executable_cannot_be_attached_to_a_response(self):
        """The auditee-reachable upload path on this app. ActionResponse.evidence_file
        was a bare FileField — see apps/common/validators.py."""
        response = self.respond_as(self.auditee, with_file=True, filename='macro.exe')
        self.assertEqual(response.status_code, 400)
        self.assertIn('evidence_file', response.data)
        self.assertFalse(ActionResponse.objects.exists())
        # The action's status must not move on a rejected response either.
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    def test_response_notifies_the_auditor_who_raised_it(self):
        self.respond_as(self.auditee)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='follow_up',
            ).exists()
        )

    def test_status_change_is_audit_logged(self):
        self.respond_as(self.auditee, status_update='partially_resolved')
        entry = AuditTrail.objects.filter(
            model_name='CorrectiveAction', object_id=str(self.action.id),
        ).first()
        self.assertEqual(entry.changes, {'status': ['open', 'partially_resolved']})

    def test_the_owner_cannot_report_a_status_the_auditor_owns(self):
        """The owner reports progress; the outcome is the auditor's to record.

        `closed` here would settle the action and, through the cascade, the
        finding behind it — an auditee posting it awarded themselves the
        verification the flow reserves for the auditor, in a single request.
        """
        for forbidden in ('closed', 'resolved', 'open', 'not_implemented',
                          'overdue', 'pending_approval'):
            with self.subTest(status=forbidden):
                self.action.status = 'open'
                self.action.save(update_fields=['status'])
                response = self.respond_as(self.auditee, status_update=forbidden)
                self.assertEqual(response.status_code, 403, response.data)
                # Refused before anything is written, so there is no half-applied
                # response explaining a status that never moved.
                self.action.refresh_from_db()
                self.assertEqual(self.action.status, 'open')
                self.assertFalse(ActionResponse.objects.exists())

    def test_the_owner_can_report_the_evidence_as_submitted(self):
        """The handoff state is theirs to set — it is a claim, not a conclusion."""
        response = self.respond_as(self.auditee, status_update='evidence_submitted')
        self.assertEqual(response.status_code, 201, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'evidence_submitted')

    def test_the_audit_side_may_still_write_any_status(self):
        """The restriction is about who may report an outcome, not the value."""
        self.assertEqual(
            self.respond_as(self.supervisor, status_update='closed').status_code, 201,
        )
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'closed')

    def test_a_plan_awaiting_approval_cannot_be_advanced_by_a_response(self):
        """`pending_approval` is the one state `approve` accepts.

        An owner reporting progress against their own unapproved plan walked it
        out of that state, so the auditor's sign-off became unreachable and the
        plan approved itself. The status posted is a legitimate owner-reportable
        one — it is the *stage* that is wrong, which is why the status gate alone
        does not catch this.
        """
        self.action.status = 'pending_approval'
        self.action.save(update_fields=['status'])
        response = self.respond_as(self.auditee)
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'pending_approval')
        self.assertFalse(ActionResponse.objects.exists())

    def test_the_auditor_can_still_approve_after_that_refusal(self):
        """The positive control: what the refusal above is protecting."""
        self.action.status = 'pending_approval'
        self.action.save(update_fields=['status'])
        self.respond_as(self.auditee)
        approval = self.as_user(self.auditor).post(
            f'{ACTIONS_URL}{self.action.id}/approve/',
        )
        self.assertEqual(approval.status_code, 200, approval.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'open')

    def test_capability_holders_can_respond_on_any_action(self):
        self.assertEqual(self.respond_as(self.supervisor).status_code, 201)

    def test_an_auditee_elsewhere_cannot_see_or_answer_the_action(self):
        outsider = self.make_user(Role.AUDITEE, department=self.other_department)
        self.assertEqual(self.respond_as(outsider).status_code, 404)


class ScheduleFollowupTest(RoleFixtureMixin, TestCase):
    """Verification belongs to whoever raised the action, plus approvers."""

    def setUp(self):
        super().setUp()
        self.action = make_action(owner=self.auditee, assigned_by=self.auditor)
        self.url = f'{ACTIONS_URL}{self.action.id}/schedule-followup/'

    def schedule_as(self, user):
        return self.as_user(user).post(self.url, {
            'scheduled_date': (
                timezone.now().date() + datetime.timedelta(days=14)
            ).isoformat(),
            'notes': 'Re-test the approval workflow.',
        }, format='json')

    def test_the_auditor_who_raised_it_can_schedule(self):
        response = self.schedule_as(self.auditor)
        self.assertEqual(response.status_code, 201, response.data)
        follow_up = FollowUp.objects.get(pk=response.data['id'])
        self.assertEqual(follow_up.corrective_action, self.action)
        self.assertEqual(follow_up.conducted_by, self.auditor)

    def test_an_uninvolved_auditor_cannot_sign_off_a_colleagues_capa(self):
        stranger = self.make_user(Role.AUDITOR, department=self.department)
        self.assertEqual(self.schedule_as(stranger).status_code, 403)
        self.assertFalse(FollowUp.objects.filter(corrective_action=self.action).exists())

    def test_approve_plans_holders_verify_across_engagements(self):
        self.assertEqual(self.schedule_as(self.supervisor).status_code, 201)

    def test_the_owner_cannot_verify_their_own_action(self):
        """The auditee may respond, but signing the verification off would let
        them close the loop on themselves."""
        self.assertEqual(self.schedule_as(self.auditee).status_code, 403)

    def test_the_owner_is_notified_that_a_follow_up_is_coming(self):
        self.schedule_as(self.auditor)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='follow_up',
            ).exists()
        )


class CapaApprovalTest(RoleFixtureMixin, TestCase):
    """The owner proposes a remedy; an auditor accepts the plan.

    Without this gate `pending_approval` had no exit, so an owner's proposed
    plan was indistinguishable from an agreed one.
    """

    def setUp(self):
        super().setUp()
        self.finding = make_finding(
            engagement=make_engagement(
                lead_auditor=self.auditor, department=self.department,
            ),
            identified_by=self.auditor,
        )

    def proposed(self, **kwargs):
        return make_action(
            finding=self.finding, owner=self.auditee,
            assigned_by=self.auditor, status='pending_approval', **kwargs,
        )

    def test_only_the_raiser_and_approvers_can_approve(self):
        """The owner cannot approve their own remediation plan.

        The raiser is included on purpose: approving the plan is the auditor's
        verification step, and the auditor who raised the CAPA is the one who
        judges whether the remedy addresses the finding. Mirrors
        `schedule-followup`, the other verification action.

        A fresh row per role: approving is a one-shot transition, so a shared one
        would let the first approver consume it and every later role read
        "not awaiting approval" instead of a permission answer.
        """
        for role, code in (
            (Role.ADMIN, 200), (Role.AUDIT_MANAGER, 200), (Role.SUPERVISOR, 200),
            (Role.AUDITOR, 200), (Role.AUDITEE, 403),
        ):
            with self.subTest(role=role):
                action_obj = self.proposed()
                response = self.as_user(self.users[role]).post(
                    f'{ACTIONS_URL}{action_obj.id}/approve/',
                )
                self.assertEqual(response.status_code, code, response.data)

    def test_an_unrelated_auditor_cannot_approve(self):
        """The gate is the *raiser*, not every auditor.

        Otherwise any auditor could sign off a colleague's remediation plan,
        which is the same hole the class-level WRITE_AUDIT gate left on
        `schedule-followup`.
        """
        action_obj = self.proposed()
        other = self.make_user(Role.AUDITOR, department=self.department)
        response = self.as_user(other).post(f'{ACTIONS_URL}{action_obj.id}/approve/')
        self.assertEqual(response.status_code, 403, response.data)

    def test_the_owner_cannot_approve_even_when_they_raised_it(self):
        """The guard behind the permission.

        `assigned_by` normally names an auditor, but nothing stops one raising
        an action owned by themselves — and then the permission's object branch
        matches and the sign-off would sail through. Raising a plan and
        accepting it is the same act either way.
        """
        action_obj = make_action(
            finding=self.finding, owner=self.auditor, assigned_by=self.auditor,
            status='pending_approval',
        )
        response = self.as_user(self.auditor).post(f'{ACTIONS_URL}{action_obj.id}/approve/')
        self.assertEqual(response.status_code, 403, response.data)
        action_obj.refresh_from_db()
        self.assertEqual(action_obj.status, 'pending_approval')

    def test_approving_moves_the_action_into_implementation(self):
        action_obj = self.proposed()
        response = self.as_user(self.auditor).post(
            f'{ACTIONS_URL}{action_obj.id}/approve/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        action_obj.refresh_from_db()
        self.assertEqual(action_obj.status, 'open')
        self.assertEqual(action_obj.approved_by, self.auditor)
        self.assertIsNotNone(action_obj.approved_at)

    def test_approving_twice_is_refused(self):
        action_obj = self.proposed()
        url = f'{ACTIONS_URL}{action_obj.id}/approve/'
        self.assertEqual(self.as_user(self.auditor).post(url).status_code, 200)
        self.assertEqual(self.as_user(self.auditor).post(url).status_code, 400)

    def test_an_action_that_was_never_proposed_cannot_be_approved(self):
        action_obj = make_action(
            finding=self.finding, owner=self.auditee,
            assigned_by=self.auditor, status='in_progress',
        )
        response = self.as_user(self.auditor).post(f'{ACTIONS_URL}{action_obj.id}/approve/')
        self.assertEqual(response.status_code, 400, response.data)

    def test_approval_notifies_the_owner(self):
        action_obj = self.proposed()
        self.as_user(self.auditor).post(f'{ACTIONS_URL}{action_obj.id}/approve/')
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='approved',
            ).exists(),
        )

    def test_approval_is_audit_logged_and_not_writable_by_patch(self):
        action_obj = self.proposed()
        self.as_user(self.auditor).post(f'{ACTIONS_URL}{action_obj.id}/approve/')
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='CorrectiveAction', object_id=str(action_obj.id),
                action='APPROVE',
            ).exists(),
        )
        # A plain PATCH must not be able to stamp the sign-off either.
        other = self.proposed()
        response = self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{other.id}/',
            {'approved_by': self.auditee.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        other.refresh_from_db()
        self.assertIsNone(other.approved_by_id)


class CapaFindingCascadeTest(RoleFixtureMixin, TestCase):
    """Closing the remedy closes the finding it remediates.

    The two lifecycles used to be independent: a CAPA could be closed while its
    finding stayed open indefinitely, because nothing carried the closure upward.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )

    def finding_and_action(self, finding_status='in_progress'):
        finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            status=finding_status,
        )
        return finding, make_action(
            finding=finding, owner=self.auditee, assigned_by=self.auditor,
            status='in_progress',
        )

    def test_closing_a_capa_closes_the_finding(self):
        finding, action_obj = self.finding_and_action()
        response = self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'closed'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'closed')
        self.assertIsNotNone(finding.actual_resolution_date)

    def test_resolving_a_capa_resolves_the_finding(self):
        finding, action_obj = self.finding_and_action()
        self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'resolved'}, format='json',
        )
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'resolved')

    def test_the_cascade_is_audit_logged_against_the_finding(self):
        finding, action_obj = self.finding_and_action()
        self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'closed'}, format='json',
        )
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='AuditFinding', object_id=str(finding.id), action='UPDATE',
            ).exists(),
            'the finding moved with no audit entry explaining why',
        )

    def test_a_non_terminal_status_leaves_the_finding_alone(self):
        for status in ('open', 'in_progress', 'partially_resolved', 'not_implemented'):
            with self.subTest(status=status):
                finding, action_obj = self.finding_and_action()
                self.as_user(self.auditor).patch(
                    f'{ACTIONS_URL}{action_obj.id}/', {'status': status}, format='json',
                )
                finding.refresh_from_db()
                self.assertEqual(finding.status, 'in_progress')

    def test_a_disputed_finding_is_not_settled_by_a_status_write(self):
        """An auditee's formal disagreement must not be closed out sideways.

        Otherwise the cascade becomes a way around `dispute`, which is the one
        route that records *why* the finding is contested.
        """
        finding, action_obj = self.finding_and_action(finding_status='disputed')
        self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'closed'}, format='json',
        )
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'disputed')

    def test_the_owners_route_cannot_settle_the_finding(self):
        """add-response cascades — which is exactly why the owner cannot write `closed`.

        The cascade on that route is real, so the status list on it is the only
        thing standing between an auditee and closing the finding about
        themselves. This is that list's teeth.
        """
        finding, action_obj = self.finding_and_action()
        response = self.as_user(self.auditee).post(
            f'{ACTIONS_URL}{action_obj.id}/add-response/',
            {
                'response_text': 'The control was reinstated and tested.',
                'status_update': 'closed',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403, response.data)
        finding.refresh_from_db()
        action_obj.refresh_from_db()
        self.assertEqual(action_obj.status, 'in_progress')
        self.assertEqual(finding.status, 'in_progress')

    def test_an_uninvolved_auditor_cannot_settle_by_a_status_patch(self):
        """The object-scoped sign-off gates had a class-scoped side door.

        `approve` and `schedule-followup` both refuse an auditor who is not the
        action's own, but the status PATCH is gated on WRITE_AUDIT alone — so the
        same person those two routes turned away could close a colleague's CAPA,
        and the finding behind it, with a single PATCH.
        """
        finding, action_obj = self.finding_and_action()
        stranger = self.make_user(Role.AUDITOR, department=self.department)
        response = self.as_user(stranger).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'closed'}, format='json',
        )
        self.assertEqual(response.status_code, 403, response.data)
        action_obj.refresh_from_db()
        finding.refresh_from_db()
        self.assertEqual(action_obj.status, 'in_progress')
        self.assertEqual(finding.status, 'in_progress')

    def test_an_uninvolved_auditor_may_still_edit_the_action(self):
        """The gate is on settling an action, not on the whole endpoint."""
        _, action_obj = self.finding_and_action()
        stranger = self.make_user(Role.AUDITOR, department=self.department)
        response = self.as_user(stranger).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'priority': 'high'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_a_reopened_capa_does_not_reopen_the_finding(self):
        """The cascade only moves forward — it must not un-close a settled finding."""
        finding, action_obj = self.finding_and_action()
        self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'closed'}, format='json',
        )
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'closed')

        self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action_obj.id}/', {'status': 'in_progress'}, format='json',
        )
        finding.refresh_from_db()
        self.assertEqual(finding.status, 'closed')


class VerifyAndCloseTest(RoleFixtureMixin, TestCase):
    """Verification and closure are one act, and the auditor's to perform.

    They were two, and neither half worked alone: `schedule-followup` recorded a
    visit and left the action exactly where it was, so a CAPA could be formally
    verified as effective and sit in `in_progress` indefinitely — while the only
    thing that actually closed one was a bare status write that recorded no
    verification at all.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )
        self.finding = make_finding(
            engagement=self.engagement, identified_by=self.auditor,
            status='in_progress',
        )
        self.action = make_action(
            finding=self.finding, owner=self.auditee, assigned_by=self.auditor,
            status='evidence_submitted',
        )
        self.url = f'{ACTIONS_URL}{self.action.id}/verify-and-close/'

    def verify_as(self, user, **payload):
        return self.as_user(user).post(self.url, payload, format='json')

    def test_the_assigned_auditor_verifies_and_closes(self):
        response = self.verify_as(self.auditor)
        self.assertEqual(response.status_code, 200, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'closed')
        self.assertIsNotNone(self.action.completed_date)

    def test_the_verification_is_recorded_as_a_completed_follow_up(self):
        """The record is the reason the two halves are one transaction."""
        self.verify_as(self.auditor)
        follow_up = FollowUp.objects.get(corrective_action=self.action)
        self.assertEqual(follow_up.status, 'completed')
        self.assertEqual(follow_up.conducted_by, self.auditor)
        self.assertEqual(follow_up.outcome, 'Implementation verified as effective')

    def test_closing_the_action_closes_the_finding(self):
        self.verify_as(self.auditor)
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.status, 'closed')
        self.assertIsNotNone(self.finding.actual_resolution_date)

    def test_the_notes_and_outcome_are_carried_onto_the_follow_up(self):
        self.verify_as(
            self.auditor,
            notes='Re-tested the approval workflow over a full cycle.',
            outcome='Control operating effectively since March.',
            scheduled_date='2026-09-01',
        )
        follow_up = FollowUp.objects.get(corrective_action=self.action)
        self.assertEqual(follow_up.notes, 'Re-tested the approval workflow over a full cycle.')
        self.assertEqual(follow_up.outcome, 'Control operating effectively since March.')
        self.assertEqual(follow_up.scheduled_date.isoformat(), '2026-09-01')

    def test_the_owner_cannot_verify_their_own_remedy(self):
        """Otherwise the closure the flow reserves for the auditor is self-awarded."""
        response = self.verify_as(self.auditee)
        self.assertEqual(response.status_code, 403, response.data)
        self.action.refresh_from_db()
        self.finding.refresh_from_db()
        self.assertEqual(self.action.status, 'evidence_submitted')
        self.assertEqual(self.finding.status, 'in_progress')
        self.assertFalse(FollowUp.objects.exists())

    def test_an_uninvolved_auditor_cannot_sign_off(self):
        stranger = self.make_user(Role.AUDITOR, department=self.department)
        self.assertEqual(self.verify_as(stranger).status_code, 403)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'evidence_submitted')

    def test_approve_plans_holders_verify_across_engagements(self):
        self.assertEqual(self.verify_as(self.supervisor).status_code, 200)

    def test_the_owner_is_told_the_remedy_was_verified(self):
        self.verify_as(self.auditor)
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='approved',
            ).exists()
        )

    def test_the_closure_is_audit_logged(self):
        self.verify_as(self.auditor)
        entry = AuditTrail.objects.filter(
            model_name='CorrectiveAction', object_id=str(self.action.id),
            action='APPROVE',
        ).first()
        self.assertIsNotNone(entry, 'the closure left no audit entry')
        self.assertEqual(entry.changes, {'status': ['evidence_submitted', 'closed']})

    def test_a_plan_that_was_never_approved_cannot_be_verified(self):
        """There is no implementation to verify until someone agreed the plan."""
        self.action.status = 'pending_approval'
        self.action.save(update_fields=['status'])
        response = self.verify_as(self.auditor)
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.assertEqual(self.action.status, 'pending_approval')

    def test_an_already_closed_action_cannot_be_verified_again(self):
        self.action.status = 'closed'
        self.action.save(update_fields=['status'])
        response = self.verify_as(self.auditor)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(FollowUp.objects.exists())

    def test_a_refused_request_leaves_the_action_untouched(self):
        """Validation runs before the transaction, so a bad date closes nothing."""
        response = self.verify_as(self.auditor, scheduled_date='not-a-date')
        self.assertEqual(response.status_code, 400, response.data)
        self.action.refresh_from_db()
        self.finding.refresh_from_db()
        self.assertEqual(self.action.status, 'evidence_submitted')
        self.assertEqual(self.finding.status, 'in_progress')
        self.assertFalse(FollowUp.objects.exists())


class OverdueEndpointTest(RoleFixtureMixin, TestCase):
    """``overdue`` is derived from the due date, and paginated."""

    def setUp(self):
        super().setUp()
        today = timezone.now().date()
        self.yesterday = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today - datetime.timedelta(days=1), status='open',
        )
        # Due today is not yet overdue — the boundary the endpoint has to get
        # right, since `due_date__lt=today` and `<= today` differ by one day of
        # somebody's grace period.
        self.today = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today, status='open',
        )
        self.settled = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today - datetime.timedelta(days=10), status='resolved',
        )
        self.in_progress = make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=today - datetime.timedelta(days=5), status='in_progress',
        )

    def overdue_ids(self, user, query=''):
        response = self.as_user(user).get(f'{ACTIONS_URL}overdue/{query}')
        self.assertEqual(response.status_code, 200)
        return response.data, {row['id'] for row in response.data['results']}

    def test_lists_lapsed_open_and_in_progress_actions_only(self):
        _, ids = self.overdue_ids(self.auditor)
        self.assertIn(self.yesterday.id, ids)
        self.assertIn(self.in_progress.id, ids)
        self.assertNotIn(self.today.id, ids)
        self.assertNotIn(self.settled.id, ids)

    def test_the_response_is_paginated(self):
        """An audit backlog runs to hundreds of rows; dumping the whole queryset
        is what this endpoint used to do."""
        payload, _ = self.overdue_ids(self.auditor)
        self.assertIn('count', payload)
        self.assertIn('results', payload)

    def test_page_size_is_honoured(self):
        payload, _ = self.overdue_ids(self.auditor, '?page_size=1')
        self.assertEqual(len(payload['results']), 1)
        self.assertEqual(payload['count'], 2)

    def test_the_status_flag_is_not_required(self):
        """Derived from due_date rather than status='overdue', so the tab is
        correct even before flag_overdue_actions has ever run."""
        self.assertEqual(
            CorrectiveAction.objects.filter(status='overdue').count(), 0,
        )
        _, ids = self.overdue_ids(self.auditor)
        self.assertEqual(len(ids), 2)

    def test_an_auditee_sees_only_their_own_overdue_actions(self):
        elsewhere = self.make_user(Role.AUDITEE, department=self.other_department)
        theirs = make_action(
            owner=elsewhere, assigned_by=self.auditor,
            due_date=timezone.now().date() - datetime.timedelta(days=3), status='open',
        )
        _, ids = self.overdue_ids(self.auditee)
        self.assertNotIn(theirs.id, ids)


class SummaryEndpointTest(RoleFixtureMixin, TestCase):
    """``summary`` — the follow-up page's KPI row."""

    def setUp(self):
        super().setUp()
        today = timezone.now().date()
        make_action(owner=self.auditee, assigned_by=self.auditor, status='open',
                    due_date=today + datetime.timedelta(days=5), priority='high')
        make_action(owner=self.auditee, assigned_by=self.auditor, status='in_progress',
                    due_date=today - datetime.timedelta(days=2), priority='high')
        make_action(owner=self.auditee, assigned_by=self.auditor, status='resolved',
                    due_date=today - datetime.timedelta(days=20), priority='low')

    def test_counts_by_status_and_priority(self):
        response = self.as_user(self.auditor).get(f'{ACTIONS_URL}summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 3)
        self.assertEqual(response.data['open'], 1)
        self.assertEqual(response.data['in_progress'], 1)
        self.assertEqual(response.data['resolved'], 1)
        # Only the in_progress action is both lapsed and unsettled.
        self.assertEqual(response.data['overdue'], 1)
        by_priority = {row['priority']: row['count'] for row in response.data['by_priority']}
        self.assertEqual(by_priority, {'high': 2, 'low': 1})

    def test_the_summary_respects_auditee_scoping(self):
        response = self.as_user(
            self.make_user(Role.AUDITEE, department=self.other_department)
        ).get(f'{ACTIONS_URL}summary/')
        self.assertEqual(response.data['total'], 0)


class CorrectiveActionScopingTest(RoleFixtureMixin, TestCase):
    """Both branches of the auditee scope: by department, then by owner."""

    def setUp(self):
        super().setUp()
        self.colleague = self.make_user(Role.AUDITEE, department=self.department)
        self.elsewhere = self.make_user(Role.AUDITEE, department=self.other_department)
        self.mine = make_action(owner=self.auditee, assigned_by=self.auditor)
        self.colleagues = make_action(owner=self.colleague, assigned_by=self.auditor)
        self.theirs = make_action(owner=self.elsewhere, assigned_by=self.auditor)

    def visible_ids(self, user):
        response = self.as_user(user).get(ACTIONS_URL)
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in response.data['results']}

    def test_auditee_sees_their_whole_department(self):
        """Deliberately department-wide, not owner-only: a department
        representative follows up on their unit's commitments, not only the ones
        with their own name on them."""
        visible = self.visible_ids(self.auditee)
        self.assertIn(self.mine.id, visible)
        self.assertIn(self.colleagues.id, visible)
        self.assertNotIn(self.theirs.id, visible)

    def test_auditee_without_a_department_falls_back_to_their_own_actions(self):
        floating = self.make_user(Role.AUDITEE, department=None)
        self.assertEqual(self.visible_ids(floating), set())
        mine = make_action(owner=floating, assigned_by=self.auditor)
        self.assertEqual(self.visible_ids(floating), {mine.id})

    def test_other_roles_see_every_action(self):
        for user in (self.admin, self.manager, self.supervisor, self.auditor):
            with self.subTest(role=user.role):
                visible = self.visible_ids(user)
                self.assertIn(self.mine.id, visible)
                self.assertIn(self.theirs.id, visible)

    def test_retrieving_an_out_of_scope_action_is_a_404(self):
        response = self.as_user(self.auditee).get(f'{ACTIONS_URL}{self.theirs.id}/')
        self.assertEqual(response.status_code, 404)


class ScheduledJobCheckTest(RoleFixtureMixin, TestCase):
    """`accounts.checks.overdue_capas_are_still_open` — the standing warning that
    `flag_overdue_actions` is not being scheduled.

    The failure it guards against leaves no trace of its own: a job that never runs
    writes no log line, so the only evidence is the state it failed to change. Each
    case below pins one of the ways that evidence can be misread.
    """

    def warnings(self):
        return overdue_capas_are_still_open(None)

    def past_due(self, **kwargs):
        return make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=timezone.now().date() - datetime.timedelta(days=5),
            **kwargs,
        )

    def test_warns_when_a_past_due_action_is_still_open(self):
        self.past_due()
        found = self.warnings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].id, 'accounts.W001')

    def test_is_quiet_when_nothing_is_past_due(self):
        make_action(
            owner=self.auditee, assigned_by=self.auditor,
            due_date=timezone.now().date() + datetime.timedelta(days=1),
        )
        self.assertEqual(self.warnings(), [])

    def test_is_quiet_when_an_extension_moves_the_due_date_out(self):
        """The subtle branch, and the one most likely to produce a false alarm.

        The command decides with `extended_due_date or due_date`, so an action with
        a past *original* due date and a future *extension* is correctly left open.
        The check has to mirror that or it cries wolf on every extended action.
        """
        self.past_due(extended_due_date=timezone.now().date() + datetime.timedelta(days=10))
        self.assertEqual(self.warnings(), [])

    def test_is_quiet_once_the_job_has_flipped_it(self):
        """A past-due action the job has already processed is `overdue`, so it is
        evidence the job *did* run, not that it did not."""
        self.past_due(status='overdue')
        self.assertEqual(self.warnings(), [])

    def test_is_a_warning_not_an_error(self):
        """Registered as a Warning on purpose: `manage.py test` runs the checks
        against an empty database, and an Error would make deployment state fail
        the suite."""
        from django.core.checks import Warning as CheckWarning

        self.past_due()
        self.assertIsInstance(self.warnings()[0], CheckWarning)


class FollowUpReminderIsOnceOnlyTest(RoleFixtureMixin, TestCase):
    """`flag_overdue_actions` must not repeat itself, including on follow-ups.

    The command's docstring promises it is safe to run repeatedly. The two CAPA
    loops earn that by changing the row they select on — status flips, or
    `due_reminder_sent`. The follow-up loop could not: a follow-up stays
    `scheduled` until a person completes it, so it re-notified the owner on every
    daily run. `FollowUp.email_sent` is the field that records it has spoken.
    """

    def setUp(self):
        super().setUp()
        self.action = make_action(owner=self.auditee, assigned_by=self.auditor)
        # Due yesterday, `scheduled` — the state the loop selects on.
        self.follow_up = FollowUp.objects.create(
            corrective_action=self.action,
            scheduled_date=timezone.now().date() - datetime.timedelta(days=1),
        )

    def run_job(self):
        with self.captureOnCommitCallbacks(execute=True):
            call_command('flag_overdue_actions')

    def reminders(self):
        return Notification.objects.filter(
            user=self.auditee, notification_type='follow_up',
        ).count()

    def test_the_reminder_is_sent_once_and_then_not_again(self):
        self.run_job()
        self.assertEqual(self.reminders(), 1)

        # The regression: the follow-up is still `scheduled`, so this second run is
        # exactly the one that used to notify the owner all over again.
        self.run_job()
        self.assertEqual(self.reminders(), 1)

        self.follow_up.refresh_from_db()
        self.assertTrue(self.follow_up.email_sent)
        self.assertIsNotNone(self.follow_up.email_sent_at)

    def test_the_reminder_email_goes_out_when_the_setting_is_on(self):
        SystemSetting.objects.update_or_create(
            key='enable_email_alerts', defaults={'value': 'True'},
        )
        self.run_job()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.auditee.email])

    def test_no_email_when_the_setting_is_off(self):
        """The in-app reminder still lands; only the email is withheld."""
        self.run_job()
        self.assertEqual(self.reminders(), 1)
        self.assertEqual(mail.outbox, [])


class CapaOnUnendorsedFindingTest(RoleFixtureMixin, TestCase):
    """A corrective action may only be raised against an endorsed finding.

    The rule was enforced for the auditee — who cannot read an unendorsed finding
    at all — and *assumed* everywhere downstream: the register hides an action
    from the auditee while its finding is pre-publication, and the compiled report
    drops the finding and its actions together. What was missing was the moment of
    creation on the audit side, where a WRITE_AUDIT holder reached `create` before
    anything looked at the finding. The audit team could therefore raise an action
    the system would afterwards refuse to show anybody, while the report told its
    reader no corrective action had ever been defined. These tests pin the gate at
    creation, and pin that it is not retroactive.
    """

    def setUp(self):
        super().setUp()
        self.engagement = make_engagement(
            lead_auditor=self.auditor, department=self.department,
        )

    def unendorsed(self, status='draft'):
        """A finding of the engagement's own department, not yet endorsed.

        The department is the auditee's on purpose: it makes the finding theirs by
        every rule except publication, so a refusal can only be the publication
        gate and not a scoping accident.
        """
        return make_finding(
            engagement=self.engagement, identified_by=self.auditor, status=status,
        )

    def payload(self, finding, **kwargs):
        data = {
            'finding': finding.id,
            'title': 'Reinstate the authorisation control',
            'description': 'Require dual approval on journal entries.',
            'recommendation': 'Configure the ERP approval workflow.',
            'owner': self.auditee.id,
            'priority': 'high',
            'due_date': (timezone.now().date() + datetime.timedelta(days=30)).isoformat(),
        }
        data.update(kwargs)
        return data

    def test_the_audit_team_cannot_link_an_action_to_an_unendorsed_finding(self):
        finding = self.unendorsed()
        response = self.as_user(self.auditor).post(
            ACTIONS_URL, self.payload(finding), format='json',
        )
        self.assertEqual(response.status_code, 400)
        # Which finding and which state, because "invalid" on top of a picker the
        # reader cannot see the bottom of is not something they can act on. The
        # label is asserted rather than the stored value: it is the words the
        # auditor sees on the register that have to match.
        message = str(response.data['finding'][0])
        self.assertIn(finding.finding_number, message)
        self.assertIn('Pending Supervisor Review', message)
        self.assertFalse(
            CorrectiveAction.objects.filter(finding=finding).exists(),
            'the refused action was written anyway',
        )

    def test_a_finding_still_open_is_refused_too(self):
        """Both pre-publication statuses, not just the one in the demo."""
        response = self.as_user(self.auditor).post(
            ACTIONS_URL, self.payload(self.unendorsed(status='open')), format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Open', str(response.data['finding'][0]))

    def test_an_endorsed_finding_is_still_linkable(self):
        """The gate is publication, not the audit team's own findings."""
        finding = self.unendorsed(status=AuditFinding.AWAITING_AUDITEE)
        response = self.as_user(self.auditor).post(
            ACTIONS_URL, self.payload(finding), format='json',
        )
        self.assertEqual(response.status_code, 201)

    def test_the_auditee_is_refused_before_the_publication_check(self):
        """Their route still closes on the read scope, with its own message.

        A different refusal for the same finding, and deliberately so: for the
        auditee this is "not yours to answer", for the auditor it is "not ready".
        """
        finding = self.unendorsed()
        response = self.as_user(self.auditee).post(
            ACTIONS_URL, self.payload(finding, owner=self.auditee.id), format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_an_action_raised_while_the_hole_was_open_still_edits(self):
        """Not retroactive: history stays editable.

        Actions linked to an unendorsed finding exist in real databases. Refusing
        a PATCH that merely *carries* the existing link would brick them — the
        mistake worth stopping is re-pointing one, not correcting its title.
        """
        finding = self.unendorsed()
        action = make_action(
            finding=finding, owner=self.auditee, assigned_by=self.auditor,
        )
        response = self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action.id}/',
            {'title': 'Corrected title', 'finding': finding.id},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        action.refresh_from_db()
        self.assertEqual(action.title, 'Corrected title')

    def test_repointing_an_existing_action_at_an_unendorsed_finding_is_refused(self):
        """The same PATCH is refused when the link is what changes."""
        action = make_action(
            finding=self.unendorsed(status=AuditFinding.AWAITING_AUDITEE),
            owner=self.auditee, assigned_by=self.auditor,
        )
        response = self.as_user(self.auditor).patch(
            f'{ACTIONS_URL}{action.id}/',
            {'finding': self.unendorsed().id},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        action.refresh_from_db()
        self.assertNotIn(
            action.finding.status, AuditFinding.PRE_PUBLICATION_STATUSES,
            'the action was re-pointed at an unendorsed finding',
        )
