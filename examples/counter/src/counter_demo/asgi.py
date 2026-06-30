"""ASGI entry point.

HTTP is wrapped with ``ASGIStaticFilesHandler`` so ``/static/djust/client.js``
(and any other static asset) is served by the same loopback process — no
separate static server on device. The WebSocket leg routes to djust's
LiveView consumer, guarded by ``AllowedHostsOriginValidator`` (rejects
handshakes whose Origin isn't in ``ALLOWED_HOSTS``).
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "counter_demo.settings")

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

import counter_demo.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": ASGIStaticFilesHandler(get_asgi_application()),
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(counter_demo.routing.websocket_urlpatterns))
        ),
    }
)
