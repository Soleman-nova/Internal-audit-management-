"""Role-by-role tests for the risk-assessment API.

Covers the MANAGE_SETTINGS gate on risk parameters, the WRITE_AUDIT gate on
assessments, ``heatmap``/``summary``, and — the reason this suite exists — the
self-assessment lock-down: every role may submit one, only APPROVE_PLANS holders
may mark one reviewed, and nobody can reach ``status='reviewed'`` through a plain
PATCH.

The second half covers the versioned-policy rework: the parameter set is a
*policy* whose digest is frozen onto every scored row, a parameter edit
recomputes the register inline, and an ambiguous department (more than one
auditable entity) is refused rather than guessed at.
"""
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_risk_assessment, make_self_assessment, make_universe,
    notification_titles,
)
from apps.notifications.models import Notification
from apps.risk_assessment.models import (
    RiskAssessment, RiskParameter, SelfAssessment, active_policy,
)

PARAMETERS_URL = '/api/risk/parameters/'
ASSESSMENTS_URL = '/api/risk/assessments/'
SELF_URL = '/api/risk/self-assessments/'
POLICY_URL = f'{PARAMETERS_URL}policy/'
RECOMPUTE_URL = f'{ASSESSMENTS_URL}recompute/'


class RiskParameterTest(RoleFixtureMixin, TestCase):
    """Parameters drive every score, so writing them is MANAGE_SETTINGS."""

    def payload(self, **kwargs):
        data = {
            'name': 'Financial materiality',
            'category': 'financial',
            'description': 'Exposure relative to the annual budget.',
            'weight': '1.50',
        }
        data.update(kwargs)
        return data

    def test_every_role_can_read_the_parameters(self):
        """Reads stay open — an auditor scoring a department has to see the
        weights they are being scored against."""
        RiskParameter.objects.create(name='Compliance', category='compliance')
        self.assert_status_by_role(
            {role: 200 for role in self.users},
            lambda client, role: client.get(PARAMETERS_URL),
        )

    def test_only_manage_settings_roles_can_create(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 403,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            PARAMETERS_URL, self.payload(name=f'Parameter for {role}'), format='json',
        ))

    def test_only_manage_settings_roles_can_edit_or_delete(self):
        param = RiskParameter.objects.create(name='Strategic', category='strategic')
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 403,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.patch(
            f'{PARAMETERS_URL}{param.id}/', {'weight': '2.00'}, format='json',
        ), msg='patch')
        self.assertEqual(
            self.as_user(self.supervisor).delete(f'{PARAMETERS_URL}{param.id}/').status_code,
            403,
        )
        self.assertEqual(
            self.as_user(self.admin).delete(f'{PARAMETERS_URL}{param.id}/').status_code,
            204,
        )

    def test_create_records_the_author_and_is_audit_logged(self):
        response = self.as_user(self.manager).post(
            PARAMETERS_URL, self.payload(), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            RiskParameter.objects.get(pk=response.data['id']).created_by, self.manager,
        )
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='RiskParameter', object_id=str(response.data['id']),
                action='CREATE',
            ).exists()
        )


class RiskAssessmentTest(RoleFixtureMixin, TestCase):
    """Scoring a department is WRITE_AUDIT; the score itself is the model's."""

    # One period per role. A department holds at most one unlinked assessment per
    # (year, period) — see the unique_assessment_per_dept_period constraint — so a
    # loop that POSTs five times for the same department has to vary the period or
    # it is really testing the constraint.
    PERIODS = {
        Role.ADMIN: 'Q1',
        Role.AUDIT_MANAGER: 'Q2',
        Role.SUPERVISOR: 'Q3',
        Role.AUDITOR: 'Q4',
        Role.AUDITEE: 'Annual',
    }

    def payload(self, **kwargs):
        data = {
            'department': self.department.id,
            'year': timezone.now().year,
            'assessment_period': 'Annual',
            'likelihood': 4,
            'impact': 4,
            'control_effectiveness': 3,
            'notes': 'Manual journal entries are not independently reviewed.',
        }
        data.update(kwargs)
        return data

    def test_only_write_audit_roles_can_score_a_department(self):
        self.assert_status_by_role({
            Role.ADMIN: 201,
            Role.AUDIT_MANAGER: 201,
            Role.SUPERVISOR: 201,
            Role.AUDITOR: 201,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(
            ASSESSMENTS_URL,
            self.payload(notes=f'Scored by {role}', assessment_period=self.PERIODS[role]),
            format='json',
        ))

    def test_the_server_computes_the_score_and_the_rating(self):
        """``risk_score``/``risk_rating``/``residual_risk`` are read-only: a
        client that sent its own numbers would put the heat map out of step with
        the parameter weights."""
        response = self.as_user(self.auditor).post(
            ASSESSMENTS_URL,
            self.payload(risk_score='1.00', risk_rating='low'),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        assessment = RiskAssessment.objects.get(pk=response.data['id'])
        self.assertEqual(float(assessment.risk_score), 16.0)
        self.assertEqual(assessment.risk_rating, 'high')
        self.assertEqual(assessment.assessed_by, self.auditor)

    def test_the_score_reaches_the_universe_only_once_approved(self):
        """The entity's risk score is the reviewer's call, not the assessor's.

        A draft that overwrote the universe would let the assessor put an entity's
        score onto the risk register on their own by pressing save — which is the
        thing the approval step exists to prevent.
        """
        universe = make_universe(department=self.department, risk_score=1)
        created = self.as_user(self.auditor).post(
            ASSESSMENTS_URL, self.payload(audit_universe=universe.id), format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['status'], 'draft')

        universe.refresh_from_db()
        self.assertEqual(
            float(universe.risk_score), 1.0, 'a draft moved the entity risk score',
        )

        response = self.as_user(self.supervisor).post(
            f'{ASSESSMENTS_URL}{created.data["id"]}/approve/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        universe.refresh_from_db()
        self.assertEqual(float(universe.risk_score), 16.0)

    def test_crud_is_audit_logged(self):
        client = self.as_user(self.auditor)
        created = client.post(ASSESSMENTS_URL, self.payload(), format='json')
        assessment_id = created.data['id']
        client.patch(
            f'{ASSESSMENTS_URL}{assessment_id}/', {'impact': 5}, format='json',
        )
        client.delete(f'{ASSESSMENTS_URL}{assessment_id}/')
        actions = list(
            AuditTrail.objects
            .filter(model_name='RiskAssessment', object_id=str(assessment_id))
            .values_list('action', flat=True)
        )
        self.assertCountEqual(actions, ['CREATE', 'UPDATE', 'DELETE'])


class ScoreBoundaryTest(RoleFixtureMixin, TestCase):
    """The 1–5 scale, on both paths into the data.

    ``choices`` only guards the serializer: it rejects a 6 as "not a valid
    choice" on the way in over HTTP and does nothing at all for a direct ORM
    write, a fixture or a data migration. A 9 stored that way would push the
    score past the 25-point ceiling the heat map is drawn on, so the model
    carries explicit min/max validators too. Both are pinned here.
    """

    SCORING_FIELDS = ['likelihood', 'impact', 'control_effectiveness']

    def payload(self, **kwargs):
        data = {
            'department': self.department.id,
            'year': timezone.now().year,
            'assessment_period': 'Annual',
            'likelihood': 3,
            'impact': 3,
            'control_effectiveness': 3,
        }
        data.update(kwargs)
        return data

    def test_the_api_refuses_a_score_outside_one_to_five(self):
        for field in self.SCORING_FIELDS:
            for value in (0, 6, -1):
                with self.subTest(field=field, value=value):
                    response = self.as_user(self.auditor).post(
                        ASSESSMENTS_URL, self.payload(**{field: value}), format='json',
                    )
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn(field, response.data)

    def test_a_fractional_score_is_refused(self):
        """The scale is integers — 3.5 is not a point on it."""
        response = self.as_user(self.auditor).post(
            ASSESSMENTS_URL, self.payload(impact=3.5), format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('impact', response.data)

    def test_both_ends_of_the_scale_are_accepted(self):
        # Distinct periods for the two POSTs: a department holds at most one
        # unlinked assessment per (year, period).
        for period, value in (('Q1', 1), ('Q2', 5)):
            with self.subTest(value=value):
                response = self.as_user(self.auditor).post(
                    ASSESSMENTS_URL,
                    self.payload(
                        likelihood=value, impact=value,
                        control_effectiveness=value, assessment_period=period,
                    ),
                    format='json',
                )
                self.assertEqual(response.status_code, 201, response.data)

    def test_the_model_itself_refuses_an_out_of_range_score(self):
        """The path ``choices`` does not cover: a direct ORM write."""
        assessment = make_risk_assessment(department=self.department)
        for field in self.SCORING_FIELDS:
            with self.subTest(field=field):
                original = getattr(assessment, field)
                setattr(assessment, field, 6)
                with self.assertRaises(ValidationError):
                    assessment.full_clean()
                setattr(assessment, field, original)


class HeatmapAndSummaryTest(RoleFixtureMixin, TestCase):
    """The two read-only endpoints the risk page renders its charts from."""

    def setUp(self):
        super().setUp()
        self.this_year = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            year=2025, likelihood=5, impact=5,
        )
        self.last_year = make_risk_assessment(
            department=self.other_department, assessed_by=self.auditor,
            year=2024, likelihood=1, impact=1,
        )

    def test_heatmap_returns_a_cell_per_assessment(self):
        response = self.as_user(self.auditor).get(f'{ASSESSMENTS_URL}heatmap/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        cell = next(row for row in response.data if row['likelihood'] == 5)
        self.assertEqual(cell['impact'], 5)
        self.assertEqual(cell['department__name'], self.department.name)

    def test_heatmap_is_scoped_to_the_auditees_own_department(self):
        """The heat map is the EEU-wide risk register, so for an auditee it has to
        narrow to their own department.

        Read as the whole organisation it tells the party being assessed which
        directorates are rated critical — and, since the universe is ordered by
        risk, effectively what is audited next. One cell is `this_year` (their
        department); `last_year` belongs to `other_department` and must not appear.
        """
        response = self.as_user(self.auditee).get(f'{ASSESSMENTS_URL}heatmap/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['department__name'], self.department.name)

    def test_heatmap_respects_the_year_filter(self):
        response = self.as_user(self.auditor).get(f'{ASSESSMENTS_URL}heatmap/?year=2024')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['likelihood'], 1)

    def test_summary_counts_by_rating(self):
        response = self.as_user(self.auditor).get(f'{ASSESSMENTS_URL}summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 2)
        # 5x5 = 25 -> critical; 1x1 = 1 -> low.
        self.assertEqual(response.data['critical'], 1)
        self.assertEqual(response.data['low'], 1)
        self.assertEqual(response.data['high'], 0)
        by_rating = {row['risk_rating']: row['count'] for row in response.data['by_rating']}
        self.assertEqual(by_rating, {'critical': 1, 'low': 1})
        self.assertAlmostEqual(float(response.data['avg_score']), 13.0)


class SelfAssessmentSubmitTest(RoleFixtureMixin, TestCase):
    """Submitting is open to every role, including the auditee."""

    # Distinct periods so the four extra parents do not collide with each other
    # or with the Annual one built in setUp — a department holds at most one
    # unlinked assessment per (year, period).
    PERIODS = {
        Role.ADMIN: 'Q1',
        Role.AUDIT_MANAGER: 'Q2',
        Role.SUPERVISOR: 'Q3',
        Role.AUDITOR: 'Q4',
    }

    def setUp(self):
        super().setUp()
        self.parent = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
        )

    def payload(self, parent=None, **kwargs):
        data = {
            'risk_assessment': (parent or self.parent).id,
            'likelihood_self': 3,
            'impact_self': 4,
            'control_effectiveness_self': 4,
            'justification': 'Dual approval is applied to every journal entry.',
            'mitigating_controls': 'Monthly reconciliation reviewed by the head.',
        }
        data.update(kwargs)
        return data

    def test_every_role_can_submit_a_self_assessment(self):
        # SelfAssessment.risk_assessment is a OneToOne, so each role needs its
        # own parent assessment. The auditee reuses the Annual row setUp already
        # built; the other four take a period each.
        parents = {role: make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            assessment_period=period,
        ) for role, period in self.PERIODS.items()}
        parents[Role.AUDITEE] = self.parent
        self.assert_status_by_role(
            {role: 201 for role in self.users},
            lambda client, role: client.post(
                SELF_URL, self.payload(parent=parents[role]), format='json',
            ),
        )

    def test_the_submitter_is_stamped_from_the_token(self):
        """``submitted_by`` is writable on the serializer, so a client could name
        somebody else — ``perform_create`` overwrites it with the caller."""
        response = self.as_user(self.auditee).post(
            SELF_URL, self.payload(submitted_by=self.auditor.id), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            SelfAssessment.objects.get(pk=response.data['id']).submitted_by, self.auditee,
        )

    def test_submission_flags_the_parent_assessment(self):
        """An auditee holds no WRITE_AUDIT, so a client PATCHing RiskAssessment
        to set this flag would 403 and make a successful submission look failed."""
        self.assertFalse(self.parent.is_self_assessment)
        self.as_user(self.auditee).post(SELF_URL, self.payload(), format='json')
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.is_self_assessment)

    def test_reviewers_are_notified_and_the_submitter_is_not(self):
        self.as_user(self.auditee).post(SELF_URL, self.payload(), format='json')
        for reviewer in (self.manager, self.supervisor):
            self.assertTrue(
                Notification.objects.filter(user=reviewer, notification_type='system').exists(),
                f'{reviewer.role} was not told a self-assessment arrived',
            )
        self.assertEqual(notification_titles(self.auditee), [])

    def test_a_reviewer_submitting_does_not_notify_themselves(self):
        self.as_user(self.supervisor).post(SELF_URL, self.payload(), format='json')
        self.assertEqual(notification_titles(self.supervisor), [])
        self.assertTrue(notification_titles(self.manager))

    def test_submission_is_audit_logged(self):
        response = self.as_user(self.auditee).post(SELF_URL, self.payload(), format='json')
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='SelfAssessment', object_id=str(response.data['id']),
                action='CREATE',
            ).exists()
        )


class SelfAssessmentReviewTest(RoleFixtureMixin, TestCase):
    """``review`` is the only route to ``status='reviewed'``."""

    def setUp(self):
        super().setUp()
        self.submission = make_self_assessment(
            risk_assessment=make_risk_assessment(
                department=self.department, assessed_by=self.auditor,
            ),
            submitted_by=self.auditee,
        )
        self.url = f'{SELF_URL}{self.submission.id}/review/'

    def test_review_stamps_the_reviewer_and_their_notes(self):
        response = self.as_user(self.supervisor).post(
            self.url, {'comments': 'Rating accepted; controls corroborated.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, 'reviewed')
        self.assertEqual(self.submission.reviewed_by, self.supervisor)
        self.assertIsNotNone(self.submission.reviewed_at)
        self.assertEqual(
            self.submission.reviewer_notes, 'Rating accepted; controls corroborated.',
        )

    def test_review_without_comments_keeps_the_existing_notes(self):
        self.submission.reviewer_notes = 'Earlier note.'
        self.submission.save(update_fields=['reviewer_notes'])
        self.as_user(self.manager).post(self.url, {}, format='json')
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.reviewer_notes, 'Earlier note.')

    def test_review_is_gated_by_approve_plans(self):
        self.assert_status_by_role({
            Role.ADMIN: 200,
            Role.AUDIT_MANAGER: 200,
            Role.SUPERVISOR: 200,
            Role.AUDITOR: 403,
            Role.AUDITEE: 403,
        }, lambda client, role: client.post(self.url, {'comments': role}, format='json'))

    def test_review_notifies_the_submitter(self):
        self.as_user(self.supervisor).post(self.url, {}, format='json')
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditee, notification_type='approved',
            ).exists()
        )

    def test_review_is_audit_logged(self):
        self.as_user(self.supervisor).post(self.url, {}, format='json')
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='SelfAssessment', object_id=str(self.submission.id),
                action='UPDATE',
            ).exists()
        )


class SelfAssessmentLockDownTest(RoleFixtureMixin, TestCase):
    """The privilege-escalation hole this part of the plan closed.

    ``SelfAssessmentViewSet`` was ``[IsAuthenticated]`` with no object check and
    no queryset scoping, so any authenticated user could read every department's
    candid self-appraisal and PATCH any of them to ``status='reviewed'`` —
    side-stepping the APPROVE_PLANS gate on ``review`` entirely.
    """

    def setUp(self):
        super().setUp()
        self.mine = make_self_assessment(
            risk_assessment=make_risk_assessment(
                department=self.department, assessed_by=self.auditor,
            ),
            submitted_by=self.auditee,
        )
        self.other_auditee = self.make_user(Role.AUDITEE, department=self.department)
        self.theirs = make_self_assessment(
            risk_assessment=make_risk_assessment(
                department=self.other_department, assessed_by=self.auditor,
            ),
            submitted_by=self.other_auditee,
        )

    def visible_ids(self, user):
        response = self.as_user(user).get(SELF_URL)
        self.assertEqual(response.status_code, 200)
        return {row['id'] for row in response.data['results']}

    def test_a_submitter_sees_only_their_own_submission(self):
        self.assertEqual(self.visible_ids(self.auditee), {self.mine.id})
        self.assertEqual(self.visible_ids(self.other_auditee), {self.theirs.id})

    def test_an_auditor_sees_only_their_own_too(self):
        """An auditor holds WRITE_AUDIT but not APPROVE_PLANS: they score
        departments, they do not sit in the review queue."""
        self.assertEqual(self.visible_ids(self.auditor), set())

    def test_reviewers_see_the_whole_queue(self):
        for reviewer in (self.admin, self.manager, self.supervisor):
            with self.subTest(role=reviewer.role):
                visible = self.visible_ids(reviewer)
                self.assertIn(self.mine.id, visible)
                self.assertIn(self.theirs.id, visible)

    def test_reading_someone_elses_submission_is_a_404(self):
        response = self.as_user(self.auditee).get(f'{SELF_URL}{self.theirs.id}/')
        self.assertEqual(response.status_code, 404)

    def test_patching_someone_elses_submission_is_a_404_for_a_submitter(self):
        """The scoped queryset hides the row, so ``get_object`` never reaches the
        object check — a 404 rather than a 403, and no information leaked about
        whether the record exists."""
        response = self.as_user(self.auditee).patch(
            f'{SELF_URL}{self.theirs.id}/', {'justification': 'Rewritten.'}, format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(
            self.theirs.justification, 'Controls are documented and operating.',
        )

    def test_a_reviewer_can_read_but_not_rewrite_a_submission(self):
        """A supervisor sees the row, so this one gets as far as the object check
        — which refuses because they are not the submitter."""
        response = self.as_user(self.supervisor).patch(
            f'{SELF_URL}{self.theirs.id}/', {'justification': 'Rewritten.'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_the_submitter_can_still_correct_their_own_submission(self):
        response = self.as_user(self.auditee).patch(
            f'{SELF_URL}{self.mine.id}/',
            {'justification': 'Corrected: approval is dual above ETB 50,000.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.mine.refresh_from_db()
        self.assertIn('Corrected', self.mine.justification)

    def test_patch_cannot_promote_a_submission_to_reviewed(self):
        """The whole point of the lock-down: status is a workflow field, and the
        only way to move it is the APPROVE_PLANS-gated ``review`` action."""
        response = self.as_user(self.auditee).patch(
            f'{SELF_URL}{self.mine.id}/', {'status': 'reviewed'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.status, 'submitted')
        self.assertIsNone(self.mine.reviewed_by)
        self.assertIsNone(self.mine.reviewed_at)

    def test_a_reviewed_submission_can_no_longer_be_edited(self):
        self.as_user(self.supervisor).post(f'{SELF_URL}{self.mine.id}/review/', {}, format='json')
        response = self.as_user(self.auditee).patch(
            f'{SELF_URL}{self.mine.id}/', {'justification': 'Second thoughts.'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.mine.refresh_from_db()
        self.assertNotIn('Second thoughts', self.mine.justification)

    def test_a_submitter_cannot_delete_someone_elses_submission(self):
        self.assertEqual(
            self.as_user(self.auditee).delete(f'{SELF_URL}{self.theirs.id}/').status_code, 404,
        )
        self.assertTrue(SelfAssessment.objects.filter(pk=self.theirs.pk).exists())


# ── Versioned policy ────────────────────────────────────────────────────────
# The parameter set is a policy multiplier, not a global constant: with the 7
# canonical parameters installed every score is uplifted by min(1.35 × 0.2, 0.3)
# and 9 of the 25 cells in the 5×5 matrix land in a different rating band. These
# tests pin down the three consequences that matter: the policy is frozen on the
# row, a parameter edit reaches the data, and an assessment that cannot be
# attributed to an entity is refused instead of silently overwriting one.


class PolicyFreezeTest(RoleFixtureMixin, TestCase):
    """The policy that scored a row is recorded on the row."""

    def test_the_policy_is_frozen_on_the_row(self):
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.50',
        )
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )

        # weight_sum 1.50 → uplift min(0.30, 0.30) = 0.30 → 4×4 × 1.30 = 20.8.
        self.assertEqual(float(assessment.weight_sum), 1.5)
        self.assertEqual(float(assessment.uplift_applied), 0.3)
        self.assertEqual(float(assessment.risk_score), 20.8)
        self.assertEqual(len(assessment.policy_digest), 12)
        self.assertEqual(assessment.policy_digest, active_policy()['digest'])
        self.assertFalse(assessment.is_stale)

        # And it survives a re-read: it is a stored column, not a live calculation.
        assessment.refresh_from_db()
        self.assertEqual(assessment.policy_digest, active_policy()['digest'])
        self.assertFalse(assessment.is_stale)

    def test_an_empty_parameter_set_scores_exactly_likelihood_times_impact(self):
        """No active parameters is a policy with uplift 0, not a missing policy."""
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        self.assertEqual(float(assessment.weight_sum), 0)
        self.assertEqual(float(assessment.uplift_applied), 0)
        self.assertEqual(float(assessment.risk_score), 16.0)
        self.assertFalse(assessment.is_stale)

    def test_an_inactive_parameter_does_not_move_the_score(self):
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.50', is_active=False,
        )
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        self.assertEqual(float(assessment.risk_score), 16.0)
        self.assertEqual(float(assessment.uplift_applied), 0)


class ParameterEditReachesTheDataTest(RoleFixtureMixin, TestCase):
    """The P0: an edit must not leave the register scoring under a dead policy."""

    def test_editing_a_parameter_recomputes_existing_assessments_inline(self):
        param = RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='0.50',
        )
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        # weight_sum 0.50 → uplift 0.10 → 16 × 1.10 = 17.6.
        self.assertEqual(float(assessment.risk_score), 17.6)
        digest_before = assessment.policy_digest

        response = self.as_user(self.admin).patch(
            f'{PARAMETERS_URL}{param.id}/', {'weight': '2.00'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        assessment.refresh_from_db()
        # The stored score moved without anybody re-saving the assessment: this is
        # the bug where a weight-2.00 parameter left an old score in place until a
        # manual re-save. weight_sum 2.00 → uplift capped at 0.30 → 16 × 1.30.
        self.assertEqual(float(assessment.risk_score), 20.8)
        self.assertEqual(float(assessment.weight_sum), 2.0)
        self.assertEqual(float(assessment.uplift_applied), 0.3)
        # The digest is no longer the one it was frozen under — that mismatch is
        # what "stale" means — but the inline recompute has already re-frozen it,
        # so the row is current again rather than merely flagged.
        self.assertNotEqual(assessment.policy_digest, digest_before)
        self.assertEqual(assessment.policy_digest, active_policy()['digest'])
        self.assertFalse(assessment.is_stale)

    def test_creating_a_parameter_recomputes_existing_assessments(self):
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        self.assertEqual(float(assessment.risk_score), 16.0)

        self.as_user(self.manager).post(PARAMETERS_URL, {
            'name': 'Operational Disruption',
            'category': 'operational',
            'description': 'Interruption to supply.',
            'weight': '1.00',
        }, format='json')

        assessment.refresh_from_db()
        self.assertEqual(float(assessment.risk_score), 19.2)  # 16 × 1.20

    def test_deleting_a_parameter_recomputes_existing_assessments(self):
        param = RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        self.assertEqual(float(assessment.risk_score), 19.2)

        response = self.as_user(self.admin).delete(f'{PARAMETERS_URL}{param.id}/')
        self.assertEqual(response.status_code, 204)  # the count goes to the trail
        assessment.refresh_from_db()
        self.assertEqual(float(assessment.risk_score), 16.0)
        self.assertEqual(float(assessment.weight_sum), 0)

    def test_the_recompute_count_lands_on_the_audit_trail(self):
        """A 204 carries no body, so the recompute is recorded instead of returned."""
        make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        param = RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )
        digest_before = active_policy()['digest']
        updated_response = self.as_user(self.admin).patch(
            f'{PARAMETERS_URL}{param.id}/', {'weight': '1.50'}, format='json',
        )
        self.assertEqual(updated_response.status_code, 200, updated_response.data)

        entry = AuditTrail.objects.filter(
            model_name='RiskParameter', object_id=str(param.id), action='UPDATE',
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes['policy_digest'], [digest_before,
                                                          active_policy()['digest']])
        self.assertEqual(entry.changes['assessments_recomputed'][1], 1)
        self.assertEqual(entry.changes['assessments_scanned'][1], 1)

    def test_a_delete_audit_entry_keeps_its_object_id(self):
        param = RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )
        self.as_user(self.admin).delete(f'{PARAMETERS_URL}{param.id}/')
        self.assertTrue(AuditTrail.objects.filter(
            model_name='RiskParameter', object_id=str(param.id), action='DELETE',
        ).exists())


class RecomputeCommandTest(RoleFixtureMixin, TestCase):
    """``manage.py recompute_risk_scores`` — the out-of-band escape hatch."""

    def test_the_command_is_idempotent_and_dry_run_writes_nothing(self):
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        self.assertEqual(float(assessment.risk_score), 16.0)
        self.assertFalse(assessment.is_stale)

        # A parameter created out of band — the Django admin, a fixture, a data
        # migration. No API request, so nothing recomputed inline.
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )
        assessment.refresh_from_db()
        self.assertTrue(assessment.is_stale)
        self.assertEqual(float(assessment.risk_score), 16.0)

        out = StringIO()
        call_command('recompute_risk_scores', '--dry-run', stdout=out)
        self.assertIn('scanned 1, updated 1', out.getvalue())
        assessment.refresh_from_db()
        self.assertEqual(float(assessment.risk_score), 16.0)  # nothing written
        self.assertTrue(assessment.is_stale)

        out = StringIO()
        call_command('recompute_risk_scores', stdout=out)
        self.assertIn('scanned 1, updated 1', out.getvalue())
        assessment.refresh_from_db()
        self.assertEqual(float(assessment.risk_score), 19.2)  # 16 × 1.20
        self.assertFalse(assessment.is_stale)

        # Nothing left to change.
        out = StringIO()
        call_command('recompute_risk_scores', stdout=out)
        self.assertIn('scanned 1, updated 0', out.getvalue())
        self.assertEqual(float(assessment.risk_score), 19.2)


class UniversePropagationTest(RoleFixtureMixin, TestCase):
    """Which auditable entity a score lands on, and refusing to guess."""

    def approve(self, assessment_id):
        """Sign a score off — the step that puts it on the entity."""
        return self.as_user(self.supervisor).post(
            f'{ASSESSMENTS_URL}{assessment_id}/approve/',
        )

    def payload(self, **kwargs):
        data = {
            'department': self.department.id,
            'year': timezone.now().year,
            'assessment_period': 'Annual',
            'likelihood': 4,
            'impact': 4,
            'control_effectiveness': 3,
        }
        data.update(kwargs)
        return data

    def test_two_candidate_entities_are_refused_rather_than_guessed(self):
        first = make_universe(department=self.department, name='Grid assets', risk_score=20)
        second = make_universe(department=self.department, name='Billing', risk_score=2)

        response = self.as_user(self.auditor).post(ASSESSMENTS_URL, self.payload(), format='json')

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('audit_universe', response.data)
        # Neither guess is made: the old fallback ordered by -risk_score and
        # overwrote whichever row came first, quietly dragging a 20-scoring
        # entity down to this assessment's score.
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(float(first.risk_score), 20)
        self.assertEqual(float(second.risk_score), 2)

    def test_a_write_with_two_candidates_touches_neither_row(self):
        """The same refusal at the model layer, where no serializer can help."""
        first = make_universe(department=self.department, name='Grid assets', risk_score=20)
        second = make_universe(department=self.department, name='Billing', risk_score=2)

        make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(float(first.risk_score), 20)
        self.assertEqual(float(second.risk_score), 2)

    def test_a_single_candidate_entity_is_used_and_propagates(self):
        universe = make_universe(department=self.department, risk_score=1)
        response = self.as_user(self.auditor).post(ASSESSMENTS_URL, self.payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.approve(response.data['id']).status_code, 200)
        universe.refresh_from_db()
        self.assertEqual(float(universe.risk_score), 16.0)

    def test_a_department_with_no_entity_is_allowed_and_propagates_nowhere(self):
        response = self.as_user(self.auditor).post(ASSESSMENTS_URL, self.payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['audit_universe'])

    def test_an_explicit_link_wins_over_an_ambiguous_department(self):
        make_universe(department=self.department, name='Grid assets', risk_score=20)
        chosen = make_universe(department=self.department, name='Billing', risk_score=2)
        response = self.as_user(self.auditor).post(
            ASSESSMENTS_URL, self.payload(audit_universe=chosen.id), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.approve(response.data['id']).status_code, 200)
        chosen.refresh_from_db()
        self.assertEqual(float(chosen.risk_score), 16.0)

    def test_deleting_an_assessment_re_propagates_the_next_latest(self):
        universe = make_universe(department=self.department, risk_score=0)
        # Created oldest-first, both approved: each save propagates its own score,
        # so the universe ends up holding the newest assessment's 25.
        older = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            audit_universe=universe, year=2024, likelihood=2, impact=2,
            control_effectiveness=3, status=RiskAssessment.APPROVED,
        )
        newer = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            audit_universe=universe, year=2026, likelihood=5, impact=5,
            control_effectiveness=3, status=RiskAssessment.APPROVED,
        )
        universe.refresh_from_db()
        self.assertEqual(float(universe.risk_score), 25.0)

        newer.delete()
        universe.refresh_from_db()
        # The replacement is the next latest by (-year, -created_at) — the key the
        # delete path has always used, and never -risk_score, which is the field
        # being written.
        self.assertEqual(float(universe.risk_score), 4.0)

        older.delete()
        universe.refresh_from_db()
        self.assertEqual(float(universe.risk_score), 0)


class RiskAssessmentApprovalTest(RoleFixtureMixin, TestCase):
    """Assess → submit → approve, and the gates on each step.

    The assessor proposes a score; only a reviewer's approval makes it official
    and puts it on the auditable entity.
    """

    def payload(self, **kwargs):
        data = {
            'department': self.department.id,
            'year': timezone.now().year,
            'assessment_period': 'Annual',
            'likelihood': 4,
            'impact': 4,
            'control_effectiveness': 3,
        }
        data.update(kwargs)
        return data

    def create(self, **kwargs):
        response = self.as_user(self.auditor).post(
            ASSESSMENTS_URL, self.payload(**kwargs), format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_a_new_assessment_starts_as_a_draft(self):
        self.assertEqual(self.create()['status'], 'draft')

    def test_status_cannot_be_set_through_a_plain_patch(self):
        """Otherwise the assessor approves their own score in one request."""
        assessment = self.create()
        response = self.as_user(self.auditor).patch(
            f'{ASSESSMENTS_URL}{assessment["id"]}/',
            {'status': 'approved'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'draft')

    def test_only_the_assessor_or_an_approver_can_submit(self):
        assessment = self.create()
        url = f'{ASSESSMENTS_URL}{assessment["id"]}/submit/'
        other = self.make_user(Role.AUDITOR, department=self.department)
        self.assertEqual(self.as_user(other).post(url).status_code, 403)
        # The supervisor holds APPROVE_PLANS, so they may submit on the assessor's
        # behalf; the assessor may always submit their own.
        self.assertEqual(self.as_user(self.supervisor).post(url).status_code, 200)

    def test_submitting_notifies_the_reviewers_but_not_the_assessor(self):
        assessment = self.create()
        self.as_user(self.auditor).post(f'{ASSESSMENTS_URL}{assessment["id"]}/submit/')
        for reviewer in (self.supervisor, self.manager):
            self.assertTrue(
                Notification.objects.filter(
                    user=reviewer, notification_type='approval_needed',
                ).exists(),
                f'{reviewer.role} was not asked to approve',
            )
        self.assertEqual(notification_titles(self.auditor), [])

    def test_approval_is_gated_on_approve_plans(self):
        """A lead auditor signs off their own fieldwork but not their own risk score.

        A fresh row per role, and a distinct period each: approving is a one-shot
        transition, so sharing one assessment would let the first approver consume
        it and every later role read "already approved" instead of a permission
        answer — which would pass for the wrong reason.
        """
        periods = {
            Role.ADMIN: 'Q1', Role.AUDIT_MANAGER: 'Q2', Role.SUPERVISOR: 'Q3',
            Role.AUDITOR: 'Q4', Role.AUDITEE: 'Annual',
        }
        for role, code in (
            (Role.ADMIN, 200), (Role.AUDIT_MANAGER, 200), (Role.SUPERVISOR, 200),
            (Role.AUDITOR, 403), (Role.AUDITEE, 403),
        ):
            with self.subTest(role=role):
                assessment = self.create(assessment_period=periods[role])
                response = self.as_user(self.users[role]).post(
                    f'{ASSESSMENTS_URL}{assessment["id"]}/approve/',
                )
                self.assertEqual(response.status_code, code, response.data)

    def test_approving_stamps_the_reviewer_and_the_time(self):
        assessment = self.create()
        response = self.as_user(self.supervisor).post(
            f'{ASSESSMENTS_URL}{assessment["id"]}/approve/',
            {'review_notes': 'Agreed with the control rating.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        row = RiskAssessment.objects.get(pk=assessment['id'])
        self.assertEqual(row.status, RiskAssessment.APPROVED)
        self.assertEqual(row.reviewed_by, self.supervisor)
        self.assertIsNotNone(row.reviewed_at)
        self.assertEqual(row.review_notes, 'Agreed with the control rating.')

    def test_approving_twice_is_refused(self):
        assessment = self.create()
        url = f'{ASSESSMENTS_URL}{assessment["id"]}/approve/'
        self.assertEqual(self.as_user(self.supervisor).post(url).status_code, 200)
        self.assertEqual(self.as_user(self.supervisor).post(url).status_code, 400)

    def test_approval_notifies_the_assessor(self):
        assessment = self.create()
        self.as_user(self.supervisor).post(f'{ASSESSMENTS_URL}{assessment["id"]}/approve/')
        self.assertTrue(
            Notification.objects.filter(
                user=self.auditor, notification_type='approved',
            ).exists(),
        )

    def test_restating_the_numbers_sends_an_approved_row_back_to_draft(self):
        """The sign-off covers the numbers that were on the row at the time.

        Letting it survive an edit would mean the entity's propagated score
        carried an approval nobody gave.
        """
        universe = make_universe(department=self.department, risk_score=1)
        assessment = self.create(audit_universe=universe.id)
        self.as_user(self.supervisor).post(f'{ASSESSMENTS_URL}{assessment["id"]}/approve/')
        universe.refresh_from_db()
        self.assertEqual(float(universe.risk_score), 16.0)

        response = self.as_user(self.auditor).patch(
            f'{ASSESSMENTS_URL}{assessment["id"]}/', {'impact': 5}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'draft')
        self.assertIsNone(response.data['reviewed_by'])

    def test_rejecting_records_the_reason_and_leaves_the_entity_alone(self):
        universe = make_universe(department=self.department, risk_score=7)
        assessment = self.create(audit_universe=universe.id)
        self.as_user(self.auditor).post(f'{ASSESSMENTS_URL}{assessment["id"]}/submit/')
        response = self.as_user(self.supervisor).post(
            f'{ASSESSMENTS_URL}{assessment["id"]}/reject/',
            {'review_notes': 'The likelihood rating is not supported.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        row = RiskAssessment.objects.get(pk=assessment['id'])
        self.assertEqual(row.status, RiskAssessment.REJECTED)
        self.assertEqual(row.review_notes, 'The likelihood rating is not supported.')

        # The entity keeps the score an approved assessment last gave it.
        universe.refresh_from_db()
        self.assertEqual(float(universe.risk_score), 7.0)

    def test_a_rejected_assessment_can_be_corrected_and_resubmitted(self):
        assessment = self.create()
        self.as_user(self.supervisor).post(f'{ASSESSMENTS_URL}{assessment["id"]}/reject/')
        response = self.as_user(self.auditor).post(
            f'{ASSESSMENTS_URL}{assessment["id"]}/submit/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            RiskAssessment.objects.get(pk=assessment['id']).status,
            RiskAssessment.SUBMITTED,
        )

    def test_the_approval_actions_are_audit_logged(self):
        assessment = self.create()
        self.as_user(self.supervisor).post(f'{ASSESSMENTS_URL}{assessment["id"]}/approve/')
        self.assertTrue(
            AuditTrail.objects.filter(
                model_name='RiskAssessment', object_id=str(assessment['id']),
                action='APPROVE',
            ).exists(),
        )


class AssessmentUniquenessTest(RoleFixtureMixin, TestCase):
    """One assessment per entity per period, and one unlinked per department."""

    def test_a_duplicate_unlinked_assessment_is_rejected(self):
        make_risk_assessment(
            department=self.department, year=2026, assessment_period='Annual',
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_risk_assessment(
                department=self.department, year=2026, assessment_period='Annual',
            )

    def test_a_duplicate_linked_assessment_is_rejected(self):
        universe = make_universe(department=self.department)
        make_risk_assessment(
            department=self.department, year=2026, assessment_period='Annual',
            audit_universe=universe,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_risk_assessment(
                department=self.department, year=2026, assessment_period='Annual',
                audit_universe=universe,
            )

    def test_a_linked_and_an_unlinked_assessment_can_coexist(self):
        """Why the unlinked case needs its own partial index: NULLs never collide."""
        universe = make_universe(department=self.department)
        make_risk_assessment(
            department=self.department, year=2026, assessment_period='Annual',
            audit_universe=universe,
        )
        make_risk_assessment(
            department=self.department, year=2026, assessment_period='Annual',
        )
        self.assertEqual(
            RiskAssessment.objects.filter(
                department=self.department, year=2026, assessment_period='Annual',
            ).count(),
            2,
        )


class AdoptedSourceTest(RoleFixtureMixin, TestCase):
    """Whose numbers produced the score, and who can change that."""

    def setUp(self):
        super().setUp()
        self.parent = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=2, impact=2, control_effectiveness=4,
        )
        self.submission = make_self_assessment(
            risk_assessment=self.parent, submitted_by=self.auditee,
            likelihood_self=5, impact_self=5, control_effectiveness_self=1,
        )
        self.review_url = f'{SELF_URL}{self.submission.id}/review/'

    def test_reviewing_with_adopt_self_values_scores_from_the_submission(self):
        self.assertEqual(float(self.parent.risk_score), 4.0)  # 2 × 2, no parameters

        response = self.as_user(self.supervisor).post(self.review_url, {
            'adopt_self_values': True,
            'note': 'Auditee evidence corroborated by the site visit.',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'self_assessment')
        self.assertEqual(
            self.parent.adoption_note, 'Auditee evidence corroborated by the site visit.',
        )
        # 5 × 5 = 25, residual unreduced because the adopted CE is 1.
        self.assertEqual(float(self.parent.risk_score), 25.0)
        self.assertEqual(self.parent.risk_rating, 'critical')
        self.assertEqual(float(self.parent.residual_risk), 25.0)
        # The manager's own numbers are untouched, so the disagreement between the
        # two positions stays visible in the record.
        self.assertEqual(self.parent.likelihood, 2)
        self.assertEqual(self.parent.impact, 2)
        self.assertEqual(self.parent.control_effectiveness, 4)

    def test_reviewing_without_adopting_leaves_the_managers_numbers_driving(self):
        response = self.as_user(self.supervisor).post(
            self.review_url, {'comments': 'Rating accepted.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'manager')
        self.assertEqual(self.parent.adoption_note, '')
        self.assertEqual(float(self.parent.risk_score), 4.0)

    def test_explicitly_declining_to_adopt_does_not_reset_a_previous_adoption(self):
        """``adopt_self_values`` absent or false is "leave it alone", not "revert"."""
        self.as_user(self.supervisor).post(
            self.review_url, {'adopt_self_values': True}, format='json',
        )
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'self_assessment')

        self.as_user(self.manager).post(self.review_url, {'comments': 'Noted.'}, format='json')
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'self_assessment')

    def test_adopted_source_is_not_client_writable(self):
        response = self.as_user(self.auditor).patch(
            f'{ASSESSMENTS_URL}{self.parent.id}/',
            {'adopted_source': 'self_assessment', 'adoption_note': 'Forged.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'manager')
        self.assertEqual(self.parent.adoption_note, '')

    def test_a_reviewer_restating_the_numbers_takes_ownership_back(self):
        self.as_user(self.supervisor).post(
            self.review_url, {'adopt_self_values': True}, format='json',
        )
        self.parent.refresh_from_db()
        self.assertEqual(float(self.parent.risk_score), 25.0)

        response = self.as_user(self.auditor).patch(
            f'{ASSESSMENTS_URL}{self.parent.id}/', {'likelihood': 4}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'manager')
        # 4 × 2 = 8: the manager's numbers drive the score again.
        self.assertEqual(float(self.parent.risk_score), 8.0)

    def test_a_patch_that_does_not_restate_the_inputs_keeps_the_adoption(self):
        self.as_user(self.supervisor).post(
            self.review_url, {'adopt_self_values': True}, format='json',
        )
        self.as_user(self.auditor).patch(
            f'{ASSESSMENTS_URL}{self.parent.id}/', {'notes': 'Context added.'}, format='json',
        )
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.adopted_source, 'self_assessment')
        self.assertEqual(float(self.parent.risk_score), 25.0)

    def test_the_score_falls_back_to_the_managers_numbers_without_a_submission(self):
        """Flagged ``self_assessment`` with nothing behind it must not explode."""
        self.submission.delete()
        self.parent.adopted_source = 'self_assessment'
        self.parent.save()
        self.assertEqual(float(self.parent.risk_score), 4.0)


class PolicyEndpointTest(RoleFixtureMixin, TestCase):
    """``GET /api/risk/parameters/policy/`` and the recompute button beside it."""

    def test_it_reports_the_digest_uplift_and_the_stale_count(self):
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        self.assertFalse(assessment.is_stale)

        # Out of band again: the ORM bypasses the API's inline recompute.
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )

        response = self.as_user(self.auditor).get(POLICY_URL)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['digest'], active_policy()['digest'])
        self.assertEqual(response.data['weight_sum'], 1.0)
        self.assertEqual(response.data['uplift'], 0.2)
        self.assertEqual(response.data['active_count'], 1)
        self.assertEqual(response.data['stale_assessments'], 1)

    def test_recompute_clears_the_stale_count(self):
        make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )

        response = self.as_user(self.manager).post(RECOMPUTE_URL, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'updated': 1, 'total': 1})
        self.assertEqual(self.as_user(self.auditor).get(POLICY_URL).data['stale_assessments'], 0)

    def test_recompute_is_manage_settings_only(self):
        """A register-wide rewrite sits with the parameter editor, not with
        ordinary assessment writing."""
        self.assertEqual(self.as_user(self.auditor).post(RECOMPUTE_URL).status_code, 403)
        self.assertEqual(self.as_user(self.supervisor).post(RECOMPUTE_URL).status_code, 403)
        self.assertEqual(self.as_user(self.auditee).post(RECOMPUTE_URL).status_code, 403)
        self.assertEqual(self.as_user(self.admin).post(RECOMPUTE_URL).status_code, 200)


class ApiSurfaceTest(RoleFixtureMixin, TestCase):
    """The field names the frontend is written against."""

    def test_inherent_risk_is_gone_and_the_policy_fields_are_exposed(self):
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )
        response = self.as_user(self.auditor).post(ASSESSMENTS_URL, {
            'department': self.department.id,
            'year': timezone.now().year,
            'assessment_period': 'Annual',
            'likelihood': 4,
            'impact': 4,
            'control_effectiveness': 3,
            'inherent_risk': 99,
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('inherent_risk', response.data)
        self.assertEqual(response.data['weight_sum'], '1.00')
        self.assertEqual(response.data['uplift_applied'], '0.200')
        self.assertEqual(response.data['policy_digest'], active_policy()['digest'])
        self.assertFalse(response.data['is_stale'])
        self.assertEqual(response.data['adopted_source'], 'manager')
        self.assertEqual(response.data['adoption_note'], '')

    def test_a_stale_assessment_says_so_in_the_listing(self):
        assessment = make_risk_assessment(
            department=self.department, assessed_by=self.auditor,
            likelihood=4, impact=4, control_effectiveness=3,
        )
        RiskParameter.objects.create(
            name='Financial Impact', category='financial', weight='1.00',
        )
        response = self.as_user(self.auditor).get(f'{ASSESSMENTS_URL}{assessment.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['is_stale'])
