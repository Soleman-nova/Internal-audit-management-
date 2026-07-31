"""End-to-end tests for the notification feature.

Covers the service-layer generation helpers and the REST API surface
(list, mark-read, mark-all-read, unread-count) that the frontend consumes.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import Notification
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
