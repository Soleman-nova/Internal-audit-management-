"""Tests for the Logto ID-token exchange and identity provisioning.

These run in Django's test database inside a transaction that is rolled back, which
is the whole reason they exist as tests rather than as a script against the live
database — an ad-hoc verification script with a `.delete()` in it removed a real
account during development.

The JWKS fetch is stubbed with a key pair generated here, so the suite never needs
a reachable Logto instance. That means the *signature* check is exercised for real
(against a key we control) while the key *discovery* is not — that part is covered
by the connection-error test below.
"""
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase

from apps.accounts import logto
from apps.accounts.models import AuditTrail, Role, User

# One key pair for the file: generating a P-384 key per test is slow and pointless,
# since every test wants the same "this is Logto's signing key" fiction.
LOGTO_KEY = ec.generate_private_key(ec.SECP384R1())
# A second, unrelated key. Anything signed with this must be rejected.
ATTACKER_KEY = ec.generate_private_key(ec.SECP384R1())

ISSUER = settings.LOGTO_ISSUER
AUDIENCE = settings.LOGTO_APP_ID

EXCHANGE_URL = '/api/auth/logto/exchange/'


class _StubKey:
    def __init__(self, key):
        self.key = key


class _StubJwks:
    """Stands in for PyJWKClient, returning the public half of ``key``."""

    def __init__(self, key):
        self._key = key

    def get_signing_key_from_jwt(self, _token):
        return _StubKey(self._key.public_key())


def make_claims(**overrides):
    """A realistic claim set, including the JSON nulls this instance sends.

    Modelled on a real token from this Logto instance: `name` is null, `middle_name`
    is empty, and the staff number lives only in `custom_data.EEUID`.
    """
    claims = {
        'sub': '0lr6gxnqvelg',
        'iss': ISSUER,
        'aud': AUDIENCE,
        'iat': 0,
        'exp': 9_999_999_999,
        'username': 'rg00579339',
        'email': 'robel.gulima@eeu.et',
        'email_verified': True,
        'given_name': 'robel',
        'middle_name': '',
        'family_name': 'Gulima',
        'name': None,
        'phone_number': '251910118088',
        'custom_data': {'EEUID': '579339', 'JobPosition': 'software Developer',
                        'Region': 'Head Office', 'CSC': ''},
    }
    claims.update(overrides)
    return claims


def encode(claims, key=None):
    return pyjwt.encode(claims, key or LOGTO_KEY, algorithm='ES384', headers={'kid': 'test-key'})


class LogtoExchangeTests(TestCase):
    def setUp(self):
        # DRF's login-scope throttle is 30/min and its counters live in the cache,
        # which persists across tests in one process. Without this, a suite run
        # starts answering 429 partway through and looks like a logic failure.
        cache.clear()
        self.client = Client()
        self._real_jwks = logto._jwks_client
        logto._jwks_client = _StubJwks(LOGTO_KEY)

    def tearDown(self):
        logto._jwks_client = self._real_jwks

    def post(self, token):
        return self.client.post(EXCHANGE_URL, {'id_token': token}, content_type='application/json')

    def exchange(self, claims, key=None):
        return self.post(encode(claims, key))

    # ── Token verification ────────────────────────────────────────────────

    def test_rejects_signature_from_another_key(self):
        """A token minted with a key Logto does not hold must not authenticate."""
        response = self.exchange(make_claims(), key=ATTACKER_KEY)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.filter(employee_id='579339').exists())

    def test_rejects_symmetric_algorithm_confusion(self):
        """HS256 must be refused even though it would verify against the JWKS *bytes*.

        This is the classic attack: sign with HMAC using the public key as the
        shared secret. It only lands if the verifier honours the token's own `alg`
        header — which is why `algorithms` is pinned in `verify_logto_id_token`.
        """
        token = pyjwt.encode(make_claims(), 'attacker-secret', algorithm='HS256',
                             headers={'kid': 'test-key'})
        self.assertEqual(self.post(token).status_code, 401)

    def test_rejects_wrong_issuer(self):
        response = self.exchange(make_claims(iss='http://evil.example/oidc'))
        self.assertEqual(response.status_code, 401)

    def test_rejects_wrong_audience(self):
        """Another application's token must not be usable here."""
        response = self.exchange(make_claims(aud='some-other-app'))
        self.assertEqual(response.status_code, 401)

    def test_rejects_expired_token(self):
        self.assertEqual(self.exchange(make_claims(exp=1000)).status_code, 401)

    def test_rejects_token_without_exp(self):
        """`require` in the decode options is what makes this fail.

        PyJWT only *validates* claims that are present, so without it a token
        carrying no `exp` would decode happily and never expire.
        """
        claims = make_claims()
        del claims['exp']
        self.assertEqual(self.exchange(claims).status_code, 401)

    def test_rejects_missing_id_token(self):
        response = self.client.post(EXCHANGE_URL, {}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_unreachable_jwks_is_503_not_401(self):
        """An outage must not be reported as a bad token.

        `PyJWKClientConnectionError` subclasses `PyJWTError`, so catching the
        broader one first would tell the user their credential is invalid and send
        whoever debugs it off to inspect tokens instead of the network.
        """
        from jwt import PyJWKClientConnectionError

        class Unreachable:
            def get_signing_key_from_jwt(self, _token):
                raise PyJWKClientConnectionError('connection refused')

        logto._jwks_client = Unreachable()
        self.assertEqual(self.exchange(make_claims()).status_code, 503)

    # ── Identity resolution ───────────────────────────────────────────────

    def make_user(self, employee_id, **kwargs):
        defaults = {
            'username': employee_id,
            'email': f'{employee_id}@eeu.et',
            'role': Role.AUDITOR,
            'is_active': True,
        }
        defaults.update(kwargs)
        return User.objects.create_user(employee_id=employee_id, **defaults)

    def test_existing_user_authenticates_and_gets_our_jwt(self):
        user = self.make_user('579339')

        response = self.exchange(make_claims())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        # The Logto token is spent here; what comes back is this system's own pair.
        self.assertIn('access', body)
        self.assertIn('refresh', body)
        self.assertEqual(pyjwt.decode(body['access'], options={'verify_signature': False})['user_id'],
                         str(user.pk))
        self.assertEqual(User.objects.filter(employee_id='579339').count(), 1)

    def test_provisions_unknown_identity_with_lowest_role(self):
        response = self.exchange(make_claims())

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(employee_id='579339')
        self.assertEqual(user.role, Role.AUDITEE)
        self.assertEqual(user.username, '579339')
        # Provisioned accounts must not be password-loginable.
        self.assertFalse(user.has_usable_password())

    def test_provisioned_account_takes_name_and_phone_from_claims(self):
        """`name` is null on this instance, so the parts are the only source."""
        self.exchange(make_claims())

        user = User.objects.get(employee_id='579339')
        self.assertEqual(user.first_name, 'robel')
        self.assertEqual(user.last_name, 'Gulima')
        self.assertEqual(user.email, 'robel.gulima@eeu.et')
        self.assertEqual(user.phone, '251910118088')
        self.assertTrue(user.full_name.strip(), 'a provisioned account must not be nameless')

    def test_provisioning_is_recorded_on_the_audit_trail(self):
        """An account nobody asked for must at least leave a trace."""
        self.exchange(make_claims())

        created = AuditTrail.objects.get(action='CREATE', object_repr__startswith='Auto-provisioned')
        self.assertEqual(created.user.employee_id, '579339')
        self.assertEqual(created.action, 'CREATE')
        self.assertTrue(AuditTrail.objects.filter(action='LOGIN', user=created.user).exists())

    def test_refuses_unknown_identity_without_eeuid(self):
        """The handle and email are mutable; they must not be able to create a user."""
        claims = make_claims()
        claims['custom_data'] = {'JobPosition': 'software Developer'}  # no EEUID
        claims['username'] = 'not-a-known-user'
        claims['email'] = 'nobody@eeu.et'

        self.assertEqual(self.exchange(claims).status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    def test_refuses_provisioning_without_email(self):
        """No placeholder is invented — an unreachable account is worse than a refusal."""
        claims = make_claims(email=None)
        claims['custom_data'] = {'EEUID': '777777'}

        self.assertEqual(self.exchange(claims).status_code, 403)
        self.assertFalse(User.objects.filter(employee_id='777777').exists())
        self.assertFalse(User.objects.filter(email__endswith='@eeu.local').exists())

    def test_deactivated_account_is_refused_and_stays_deactivated(self):
        """Deactivation is the off switch; signing in must not quietly undo it."""
        user = self.make_user('579339', is_active=False)

        self.assertEqual(self.exchange(make_claims()).status_code, 403)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_matches_by_username_when_employee_id_differs(self):
        """An imported account may carry the staff number in `username`."""
        user = self.make_user('OLD-0001', username='579339', email='other@eeu.et')

        self.assertEqual(self.exchange(make_claims()).status_code, 200)
        self.assertEqual(User.objects.filter(employee_id='579339').count(), 0)
        self.assertEqual(User.objects.get(pk=user.pk).employee_id, 'OLD-0001')

    # ── Directory sync ────────────────────────────────────────────────────

    def test_syncs_directory_fields_on_sign_in(self):
        """Logto owns name/phone/email, so a Console correction must reach us."""
        user = self.make_user('579339', first_name='Stale', last_name='Name',
                              phone='', email='old.address@eeu.et')

        self.assertEqual(self.exchange(make_claims()).status_code, 200)

        user.refresh_from_db()
        self.assertEqual(user.first_name, 'robel')
        self.assertEqual(user.last_name, 'Gulima')
        self.assertEqual(user.phone, '251910118088')
        # Email moved too — the old address was the user's own, not someone else's.
        self.assertEqual(user.email, 'robel.gulima@eeu.et')

    def test_sync_does_not_change_role(self):
        """Role is this system's decision; a sign-in must not rewrite it."""
        user = self.make_user('579339', role=Role.ADMIN)

        self.assertEqual(self.exchange(make_claims()).status_code, 200)

        user.refresh_from_db()
        self.assertEqual(user.role, Role.ADMIN,
                         'signing in must never change a user\'s permissions')

    def test_sync_skips_email_owned_by_another_account(self):
        """A recycled address must not fail the sign-in or steal a row."""
        self.make_user('OTHER-1', email='robel.gulima@eeu.et')
        user = self.make_user('579339', email='robel.old@eeu.et')

        self.assertEqual(self.exchange(make_claims()).status_code, 200)

        user.refresh_from_db()
        self.assertEqual(user.email, 'robel.old@eeu.et', 'the clashing address must be left alone')

    def test_sync_does_not_reactivate_or_touch_is_active(self):
        """`is_active` is not a Logto-owned field, whatever the claims say."""
        user = self.make_user('579339')
        claims = make_claims()
        claims['is_active'] = False

        self.assertEqual(self.exchange(claims).status_code, 200)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
