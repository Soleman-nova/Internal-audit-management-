"""End-to-end tests for the notification feature.

Covers the service-layer generation helpers and the REST API surface
(list, mark-read, mark-all-read, unread-count) that the frontend consumes.
"""
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Notification, SystemSetting
from .services import notify, notify_many, notify_roles

User = get_user_model()


def make_user(employee_id, role='auditor', **extra):
    return User.objects.create_user(
        employee_id=employee_id,
        username=employee_id,
        email=f'{employee_id}@example.com',
        password='pass12345',
        first_name=employee_id.title(),
        last_name='Test',
        role=role,
        **extra,
    )


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.owner = make_user('owner1')
        self.manager = make_user('mgr1', role='audit_manager')
        self.admin = make_user('admin1', role='admin')

    def test_notify_creates_record(self):
        n = notify(self.owner, 'assigned', 'Title', 'Body', '/findings?id=1')
        self.assertIsNotNone(n)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(n.user, self.owner)
        self.assertEqual(n.notification_type, 'assigned')
        self.assertFalse(n.is_read)
        self.assertEqual(n.link, '/findings?id=1')

    def test_notify_none_user_is_noop(self):
        self.assertIsNone(notify(None, 'system', 'x', 'y'))
        self.assertEqual(Notification.objects.count(), 0)

    def test_notify_many_dedupes(self):
        created = notify_many(
            [self.owner, self.owner, self.manager, None],
            'system', 'Hi', 'msg',
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(Notification.objects.count(), 2)

    def test_notify_roles_targets_roles_and_excludes_actor(self):
        created = notify_roles(
            ['admin', 'audit_manager'],
            'approval_needed', 'Approve', 'please',
            exclude=self.admin,
        )
        # admin is excluded, only the manager should be notified
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].user, self.manager)


class NotificationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('apiuser')
        self.other = make_user('other')
        self.client.force_authenticate(user=self.user)

    def test_list_only_returns_own_notifications(self):
        notify(self.user, 'system', 'Mine', 'a')
        notify(self.other, 'system', 'Theirs', 'b')
        resp = self.client.get('/api/notifications/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data.get('results', resp.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Mine')
        self.assertEqual(data[0]['type_display'], 'System')

    def test_unread_count(self):
        notify(self.user, 'system', 'A', 'a')
        notify(self.user, 'system', 'B', 'b')
        resp = self.client.get('/api/notifications/unread-count/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['unread'], 2)

    def test_mark_read(self):
        n = notify(self.user, 'system', 'A', 'a')
        resp = self.client.post(f'/api/notifications/{n.id}/mark-read/')
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)

    def test_mark_all_read(self):
        notify(self.user, 'system', 'A', 'a')
        notify(self.user, 'system', 'B', 'b')
        resp = self.client.post('/api/notifications/mark-all-read/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            Notification.objects.filter(user=self.user, is_read=False).count(), 0
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/notifications/')
        self.assertIn(resp.status_code, (401, 403))


class EmailChannelTests(TestCase):
    """The email half of `notify()`, gated by the `enable_email_alerts` setting.

    Off unless asked for in two separate senses: the setting must be on, *and* the
    caller must pass `email=True`. Both are pinned below, because either one alone
    would turn a quiet feature into an inbox full of mail nobody opted into.
    """

    def setUp(self):
        self.user = make_user('E-9001')

    def enable(self, value='True'):
        SystemSetting.objects.update_or_create(
            key='enable_email_alerts', defaults={'value': value},
        )

    def send(self, **kwargs):
        """Call `notify`, then run whatever it deferred to commit.

        `notify` defers the send with `transaction.on_commit` so an email can never
        outlive a rolled-back write — but `TestCase` never commits, so without this
        the callback would silently not run and every assertion below would pass for
        the wrong reason.
        """
        with self.captureOnCommitCallbacks(execute=True):
            return notify(
                self.user, 'action_due', 'A title', 'A message', '/capa/7', **kwargs,
            )

    def test_no_email_when_the_setting_is_absent(self):
        """Never seeded means never configured, which reads as off. The opposite
        default would turn "we never set this up" into unprompted mail."""
        self.send(email=True)
        self.assertEqual(mail.outbox, [])

    def test_email_sent_when_the_setting_is_on(self):
        self.enable()
        self.send(email=True)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertEqual(mail.outbox[0].subject, 'A title')

    def test_email_is_opt_in_per_call(self):
        """Setting on, caller didn't ask -> in-app only."""
        self.enable()
        self.send()
        self.assertEqual(mail.outbox, [])

    def test_the_body_carries_an_absolute_link(self):
        """The stored link is an app path (/capa/7), which is useless in an inbox."""
        self.enable()
        self.send(email=True)
        self.assertIn('A message', mail.outbox[0].body)
        self.assertIn(
            f'{settings.FRONTEND_URL.rstrip("/")}/capa/7', mail.outbox[0].body,
        )

    def test_a_user_without_an_email_is_skipped_quietly(self):
        """Accounts are keyed on employee_id, so an email is not guaranteed."""
        self.enable()
        self.user.email = ''
        self.user.save(update_fields=['email'])
        self.assertEqual(self.send(email=True) is not None, True)
        self.assertEqual(mail.outbox, [])

    def test_the_setting_value_is_parsed_not_trusted(self):
        """It is a TextField holding whatever an administrator typed."""
        for truthy in ('True', 'true', 'YES', '1', 'on', ' True '):
            with self.subTest(value=truthy):
                self.enable(truthy)
                self.send(email=True)
                self.assertEqual(len(mail.outbox), 1)
                mail.outbox.clear()

        for falsy in ('False', 'false', 'no', '0', 'off', ''):
            with self.subTest(value=falsy):
                self.enable(falsy)
                self.send(email=True)
                self.assertEqual(mail.outbox, [])

    def test_a_mail_failure_never_breaks_the_caller(self):
        """Best-effort, like the in-app channel: a dead SMTP host must not fail the
        finding or CAPA write that triggered the notification."""
        self.enable()
        with mock.patch(
            'apps.notifications.services.send_mail', side_effect=OSError('smtp down'),
        ):
            created = self.send(email=True)
        self.assertIsNotNone(created)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
