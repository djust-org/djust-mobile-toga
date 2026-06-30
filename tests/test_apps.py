"""Tests for the Django ``AppConfig``.

``DjustMobileTogaConfig`` is an empty contract whose only job is to make the
package an installed Django app so its ``templatetags/`` package is discovered.
A configured Django is provided by ``conftest.py``.
"""

from __future__ import annotations

from django.apps import AppConfig

import djust_mobile_toga
from djust_mobile_toga.apps import DjustMobileTogaConfig


def test_is_appconfig_subclass():
    assert issubclass(DjustMobileTogaConfig, AppConfig)


def test_name_is_the_package():
    # Must match the dotted package path so Django can import it.
    assert DjustMobileTogaConfig.name == "djust_mobile_toga"


def test_verbose_name():
    assert DjustMobileTogaConfig.verbose_name == "djust mobile toga"


def test_default_auto_field_reads_settings():
    # default_auto_field is inherited from AppConfig and resolves from settings;
    # conftest sets DEFAULT_AUTO_FIELD to BigAutoField.
    cfg = DjustMobileTogaConfig("djust_mobile_toga", djust_mobile_toga)
    assert cfg.default_auto_field == "django.db.models.BigAutoField"


def test_app_is_registered():
    # django.setup() in conftest registers the app from INSTALLED_APPS.
    from django.apps import apps

    cfg = apps.get_app_config("djust_mobile_toga")
    assert isinstance(cfg, DjustMobileTogaConfig)
