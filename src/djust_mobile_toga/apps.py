"""Django ``AppConfig`` for djust-mobile-toga.

Why this exists: the ``{% wallet_add_button %}`` template tag (and any
future tags in this package) must live inside an installed Django app's
``templatetags/`` package for Django's template engine to find them.
Add ``"djust_mobile_toga"`` to ``INSTALLED_APPS`` in your project's
``settings.py`` to opt in.

This AppConfig is otherwise an empty contract — no models, no signals.
The runtime PassKit/script-message wiring happens from your Toga
``app.py`` in ``on_app_ready()``, not at Django startup.
"""

from django.apps import AppConfig


class DjustMobileTogaConfig(AppConfig):
    """Django app config so the package's ``templatetags/`` are discovered.

    An empty contract — no models, no signals. Its only job is to register
    ``djust_mobile_toga`` as an installed app so Django's template engine can
    find the ``{% wallet_add_button %}`` tag. ``default_auto_field`` is left
    inherited (resolved from ``settings.DEFAULT_AUTO_FIELD``).
    """

    name = "djust_mobile_toga"
    verbose_name = "djust mobile toga"
