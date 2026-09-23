from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        # Imported for its side effect: the @register() calls in checks.py add the
        # Logto startup checks to Django's registry. Django does not pick up an
        # app's checks.py on its own here, and an unregistered check is silently a
        # no-op — which is the worst possible outcome for a check whose whole job
        # is to be loud.
        from . import checks  # noqa: F401
