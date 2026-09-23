"""Verification of Logto-issued ID tokens, and the mapping from a Logto identity
onto an ``accounts.User``.

Kept out of ``views.py`` because it is the one place in this integration where a
mistake turns into "anyone on the network is an auditor". It is short on purpose.

The frontend never verifies these tokens — that is the whole point of the exchange
in ``LogtoExchangeView``. The browser gets an ID token back from Logto and hands it
to us; this module is what decides whether to believe it.
"""
import logging

import jwt
from django.conf import settings
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Where this deployment stashes the EEU employee ID inside Logto's `custom_data`.
# Logto's `custom_data` is a free-form per-user JSON blob, so the key name is a
# convention this system and the Logto directory have to agree on.
IDENTITY_CUSTOM_DATA_KEY = 'EEUID'

# Cache the JWKS client for the life of the process. PyJWKClient caches the fetched
# keys internally, so building a new one per request would refetch Logto's JWKS on
# every single sign-in — a network round trip in the login path, and one more thing
# to fail when Logto is slow.
_jwks_client = None


class LogtoNotConfigured(Exception):
    """Raised when LOGTO_ENDPOINT/LOGTO_APP_ID are unset.

    Distinct from a verification failure so the view can answer 503 (this
    deployment has no Logto) rather than 401 (your token is bad) — otherwise a
    missing env var is indistinguishable from an attack in the logs.
    """


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(f"{settings.LOGTO_ISSUER}/jwks", cache_keys=True)
    return _jwks_client


def verify_logto_id_token(raw_token):
    """Return the verified ID-token claims, or raise.

    Checks the ES384 signature against Logto's published JWKS *and* the `iss`,
    `aud` and `exp` claims, all inside `jwt.decode`. Passing the key explicitly
    rather than letting PyJWT resolve it keeps the algorithm list below the only
    thing that decides which signatures are acceptable.

    Raises ``LogtoNotConfigured`` when the deployment has no Logto, and
    ``jwt.PyJWTError`` for anything wrong with the token itself.
    """
    if not settings.LOGTO_ENDPOINT or not settings.LOGTO_APP_ID:
        raise LogtoNotConfigured()

    signing_key = _get_jwks_client().get_signing_key_from_jwt(raw_token)

    return jwt.decode(
        raw_token,
        signing_key.key,
        # Both are what this Logto instance has used; list them explicitly so a
        # `none`-algorithm or HMAC-signed forgery has nothing to match against.
        algorithms=['ES384', 'RS256'],
        audience=settings.LOGTO_APP_ID,
        issuer=settings.LOGTO_ISSUER,
        # Without this a token carrying no `exp` would decode happily and never
        # expire. PyJWT only *validates* claims that are present.
        options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
    )


def jwt_header(raw_token):
    """The *unverified* header of a JWT, or ``{}`` if it cannot be read.

    Safe to log: the header carries ``alg`` and ``kid`` — algorithm metadata, not
    claims or credentials. Reading it requires no key, which is exactly what makes
    it useful while debugging: it says what the token claims to be signed with
    before anything is trusted.
    """
    try:
        return jwt.get_unverified_header(raw_token)
    except jwt.PyJWTError:
        return {}


def identity_candidates(claims):
    """The values in ``claims`` that might name an ``accounts.User``, best first.

    ``custom_data.EEUID`` is the one this system is built around — it is the field
    the Logto directory is populated with, and it is the only candidate used to
    *create* an account (see ``resolve_or_provision_user``). The username and email
    fallbacks exist to find an account an administrator already created, so that a
    user whose Logto profile lacks the custom data is not locked out of a row that
    is plainly theirs.

    ``LOGTO_IDENTITY_CLAIM`` pins a single claim for deployments that would rather
    fail than fall back.
    """
    if settings.LOGTO_IDENTITY_CLAIM:
        pinned = claims.get(settings.LOGTO_IDENTITY_CLAIM)
        return [pinned] if pinned else []

    custom_data = claims.get('custom_data') or {}
    return [
        candidate
        for candidate in (
            custom_data.get(IDENTITY_CUSTOM_DATA_KEY),
            claims.get('username'),
            claims.get('email'),
        )
        if candidate
    ]


def _unique_username(identity):
    """``identity``, or the first free variant of it.

    ``username`` is inherited from ``AbstractUser`` and unused by this app — login
    is by ``employee_id`` — but it is still unique at the database level, so a row
    an administrator created with this username but a different employee ID would
    otherwise turn a first sign-in into an IntegrityError.
    """
    from .models import User

    if not User.objects.filter(username__iexact=identity).exists():
        return identity

    suffix = 1
    while User.objects.filter(username__iexact=f'{identity}{suffix}').exists():
        suffix += 1
    return f'{identity}{suffix}'


def _text(value):
    """A claim as a trimmed string, with JSON null becoming ''.

    Logto sends explicit nulls — ``"name": null`` on this instance — and Python's
    ``dict.get(key, '')`` returns ``None`` for a key that is *present with a null
    value*; the default only covers an absent key. Every claim read goes through
    here so that trap is handled once rather than at each call site.
    """
    if value is None:
        return ''
    return str(value).strip()


# The Logto `custom_data` keys carrying EEU directory attributes. Free-form on
# Logto's side, so the names are simply a convention the two systems share.
CUSTOM_DATA_FIELDS = {
    'JobPosition': 'title',
    'Region': 'region',
    'CSC': 'csc',
}


def _directory_claims(claims):
    """The Logto-owned directory fields, normalised for the ``User`` model.

    ``given_name``/``middle_name``/``family_name`` are the real source: this Logto
    instance leaves ``name`` null, so splitting ``name`` alone produced an account
    with no name at all — which renders blank everywhere a user is shown, the audit
    trail included. ``name`` is consulted only for directories that populate it and
    nothing else.

    ``middle_name`` has no column of its own, so it is folded into ``first_name``:
    ``User.full_name`` is a property over first + last, so dropping the middle name
    would silently lose it from every screen that renders a user.
    """
    given = _text(claims.get('given_name'))
    middle = _text(claims.get('middle_name'))
    family = _text(claims.get('family_name'))

    if not (given or family):
        head, _, tail = _text(claims.get('name')).partition(' ')
        given, family = head.strip(), tail.strip()

    return {
        'first_name': ' '.join(part for part in (given, middle) if part),
        'last_name': family,
        'email': _text(claims.get('email')),
        # Truncated rather than trusted: SQLite does not enforce varchar lengths and
        # Postgres does, so an over-long claim would pass every local run and fail
        # only in production.
        'phone': _text(claims.get('phone_number'))[:20],
    }


def _unmapped_custom_data(claims):
    """custom_data values this model has nowhere to put.

    Every key in ``CUSTOM_DATA_FIELDS`` is listed here precisely because it does not
    map: ``User`` has no ``title`` or ``csc`` column, and ``region``/``service_center``
    are foreign keys to ``Department``, not free text. Logging them keeps the values
    visible — and recoverable from the log — rather than silently discarded while
    that schema question is still open.
    """
    custom_data = claims.get('custom_data') or {}
    return {
        key: _text(custom_data.get(key))
        for key in CUSTOM_DATA_FIELDS
        if _text(custom_data.get(key))
    }


def _provision_user(identity, claims):
    """Create an ``accounts.User`` for ``identity``, with the lowest-privilege role.

    The role is hardcoded to ``auditee`` rather than taken from any Logto claim.
    Roles are this system's authority, and a self-service sign-in must never be able
    to grant itself more than the role with no capabilities — an administrator
    promotes the account afterwards, in Django, on the audit trail.

    The caller guarantees ``claims`` carries an email; see ``resolve_or_provision_user``
    for why one is required rather than invented.
    """
    from django.db import IntegrityError, transaction

    from .models import Role, User

    directory = _directory_claims(claims)

    try:
        with transaction.atomic():
            return User.objects.create_user(
                username=_unique_username(identity),
                employee_id=identity,
                email=directory['email'],
                first_name=directory['first_name'],
                last_name=directory['last_name'],
                phone=directory['phone'],
                role=Role.AUDITEE,
                is_active=True,
            )
    except IntegrityError:
        # Two first sign-ins racing on one identity. Whoever lost re-reads the
        # winner's row instead of failing a sign-in that is, in fact, fine now.
        existing = User.objects.filter(employee_id__iexact=identity).first()
        if existing is not None:
            return existing
        raise


def _sync_directory_fields(user, claims):
    """Apply the Logto-owned fields that have drifted. Returns the names changed.

    Logto is the source of truth for directory attributes, so these are re-applied on
    every sign-in rather than only when the local column happens to be empty —
    otherwise a name corrected in the Logto Console never reaches the audit system.

    Deliberately *not* applied, even when the claims carry them: ``role``,
    ``department``, ``region``, ``service_center``, ``employee_id`` and ``is_active``.
    Those are this system's decisions, and a sign-in must not be able to rewrite its
    own permissions or reactivate a disabled account.
    """
    from .models import User

    changed = []

    for field, value in _directory_claims(claims).items():
        if not value or getattr(user, field) == value:
            continue

        if field == 'email':
            # `email` is unique. Adopting an address another row already holds raises
            # IntegrityError and fails the entire sign-in, so the clash is skipped and
            # logged instead: a shared or recycled address must not be able to lock
            # someone out of their own account.
            if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
                logger.warning(
                    'Not syncing email for user %s: %r already belongs to another account.',
                    user.pk, value,
                )
                continue

        setattr(user, field, value)
        changed.append(field)

    if changed:
        # `updated_at` is auto_now, and with update_fields Django only refreshes it
        # when it is named explicitly.
        user.save(update_fields=changed + ['updated_at'])

    return changed


def resolve_or_provision_user(claims):
    """The ``accounts.User`` this Logto identity names. Returns ``(user, created)``.

    ``(None, False)`` means the sign-in is refused: the identity matches no account
    and carries no ``custom_data.EEUID`` to provision one from, or it matches an
    account that has been deactivated.

    Deactivated accounts are never reactivated. Deactivation is how this system
    switches someone off, and a sign-in that quietly undid it would make the
    off switch a no-op.
    """
    from .models import User

    for candidate in identity_candidates(claims):
        # employee_id first — it is the USERNAME_FIELD. `username` is tried next
        # because an account imported from an older directory may carry the staff
        # number there instead; email and phone follow as the weaker identifiers.
        user = User.objects.filter(employee_id__iexact=candidate).first()
        matched_on = 'employee_id'
        if user is None:
            user = User.objects.filter(username__iexact=candidate).first()
            matched_on = 'username'
        if user is None:
            user = User.objects.filter(email__iexact=candidate).first()
            matched_on = 'email'
        if user is None:
            # `phone` is not unique on this model, so it identifies someone only
            # when exactly one row carries it. A shared switchboard number must not
            # hand one person another's account.
            phone_matches = User.objects.filter(phone=candidate)
            if phone_matches.count() == 1:
                user, matched_on = phone_matches.first(), 'phone'

        if user is not None:
            if not user.is_active:
                logger.warning(
                    'Logto sign-in for %s refused: account %s is deactivated.',
                    candidate, user.pk,
                )
                return None, False

            changed = _sync_directory_fields(user, claims)
            logger.info(
                'Logto sign-in mapped %s -> user %s (by %s); synced: %s.',
                candidate, user.pk, matched_on, ', '.join(changed) or 'nothing',
            )
            return user, False

    identity = _text((claims.get('custom_data') or {}).get(IDENTITY_CUSTOM_DATA_KEY))
    email = _text(claims.get('email'))

    # An account is only ever created from the EEU staff number, never from the
    # Logto handle or email: those are mutable profile attributes, and keying a new
    # account off one would let a rename or a recycled address claim an identity.
    if not identity:
        # The `sub` is the only stable identifier Logto gives us, so it is what makes
        # this line actionable — it is what an admin searches the Console with.
        logger.warning(
            'Logto sign-in refused: no accounts.User matches %s and the token carries '
            'no custom_data.%s to provision from (sub=%s).',
            identity_candidates(claims), IDENTITY_CUSTOM_DATA_KEY, claims.get('sub'),
        )
        return None, False

    # Email is required rather than invented. An earlier version minted a
    # `<eeuid>@eeu.local` placeholder when the claim was absent, which produced
    # accounts no later sign-in could ever match by email — and this system uses
    # email for notification and for admin lookup. Refusing is honest; quietly
    # inventing an address creates a user nobody can reach.
    if not email:
        logger.warning(
            'Logto sign-in refused: %s is not a known account and the token carries no '
            'email claim to create one with (sub=%s).',
            identity, claims.get('sub'),
        )
        return None, False

    unmapped = _unmapped_custom_data(claims)
    if unmapped:
        # Not an error — data with nowhere to go yet. See _unmapped_custom_data.
        logger.info(
            'Logto custom_data for %s has no matching User column (dropped): %s',
            identity, unmapped,
        )

    user = _provision_user(identity, claims)
    logger.info(
        'Provisioned accounts.User %s (%s) from Logto with role %s.',
        user.pk, user.employee_id, user.role,
    )
    return user, True
