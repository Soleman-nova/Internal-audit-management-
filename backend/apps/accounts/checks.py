"""Startup checks for the Logto integration.

Django runs these on `manage.py check`, on `runserver`, and in CI. That matters
because the failure they guard against is otherwise invisible: PyJWT decides
whether it can verify ES384 **once, at import**, and caches the answer. A venv
missing `cryptography` therefore produces a running server that rejects every
valid Logto token with:

    Rejected Logto ID token: ES384 requires 'cryptography' to be installed.

which reaches the user as a 401 "Logto token could not be verified" — a message
that points at the token, the audience, or an attacker, and never at the missing
package. Worse, a server already running when the package is installed keeps the
stale answer until it is restarted, so "I installed it" and "it still fails" are
both true at once.

Checking here turns all of that into a startup error naming the real cause.
"""
from django.conf import settings
from django.core.checks import Error, register


@register()
def logto_crypto_available(app_configs, **kwargs):
    """Error when Logto is configured but ES384 verification is impossible."""
    # Nothing to verify against means nothing to warn about: an environment with no
    # Logto (CI, a fresh clone) is a supported state, not a misconfiguration.
    if not settings.LOGTO_ENDPOINT:
        return []

    try:
        import cryptography  # noqa: F401
    except ImportError:
        return [
            Error(
                'Logto is configured (LOGTO_ENDPOINT is set) but the `cryptography` '
                'package is missing, so ES384 ID-token signatures cannot be verified. '
                'Every Logto sign-in will fail with a 401 "Logto token could not be '
                'verified", which reads as a bad token rather than a missing package.',
                hint='Install it (pinned in requirements.txt): '
                     'pip install -r requirements.txt',
                id='accounts.E001',
            )
        ]

    return []
