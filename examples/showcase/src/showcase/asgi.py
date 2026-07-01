"""ASGI entry point — HTTP (with static files) + the djust LiveView WebSocket."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "showcase.settings")

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

import showcase.routing  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": ASGIStaticFilesHandler(get_asgi_application()),
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(showcase.routing.websocket_urlpatterns))
        ),
    }
)
