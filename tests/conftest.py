"""Shared pytest setup.

A handful of tests (``test_apps``, ``test_templatetags``) exercise Django
surface — the package ``AppConfig`` and the ``{% wallet_add_button %}``
template tag — which need a configured Django before they can run. Configure a
minimal in-memory settings object once at collection time. The platform-bridge
tests (voice / notifications / passkit / bridge / apple_intelligence / serve /
shims) don't touch Django and are unaffected.
"""

from __future__ import annotations

import django
from django.conf import settings


def pytest_configure() -> None:
    """Configure a minimal Django settings object before any test imports it."""
    if settings.configured:
        return
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "djust_mobile_toga",
        ],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": False,
                "OPTIONS": {"libraries": {}},
            }
        ],
        # A non-default value so test_apps can prove default_auto_field reads it.
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        DATABASES={},
        USE_TZ=True,
    )
    django.setup()
