"""Role-by-role tests for the risk-assessment API.

Covers the MANAGE_SETTINGS gate on risk parameters, the WRITE_AUDIT gate on
assessments, ``heatmap``/``summary``, and — the reason this suite exists — the
self-assessment lock-down: every role may submit one, only APPROVE_PLANS holders
may mark one reviewed, and nobody can reach ``status='reviewed'`` through a plain
PATCH.
"""
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import AuditTrail, Role
from apps.common.role_fixtures import (
    RoleFixtureMixin, make_risk_assessment, make_self_assessment, make_universe,
    notification_titles,
)
from apps.notifications.models import Notification
from apps.risk_assessment.models import RiskAssessment, RiskParameter, SelfAssessment

PARAMETERS_URL = '/api/risk/parameters/'
ASSESSMENTS_URL = '/api/risk/assessments/'
SELF_URL = '/api/risk/self-assessments/'


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
            ASSESSMENTS_URL, self.payload(notes=f'Scored by {role}'), format='json',
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

    def test_the_score_is_propagated_onto_the_audit_universe(self):
        universe = make_universe(department=self.department, risk_score=1)
        self.as_user(self.auditor).post(
            ASSESSMENTS_URL, self.payload(audit_universe=universe.id), format='json',
        )
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
        response = self.as_user(self.auditee).get(f'{ASSESSMENTS_URL}heatmap/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        cell = next(row for row in response.data if row['likelihood'] == 5)
        self.assertEqual(cell['impact'], 5)
        self.assertEqual(cell['department__name'], self.department.name)

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
        # own parent assessment.
        parents = {
            role: make_risk_assessment(
                department=self.department, assessed_by=self.auditor,
            )
            for role in self.users
        }
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
