"""WebSocket routing for the djust LiveView consumer.

Every djust LiveView talks to the server over a single WebSocket endpoint;
the consumer routes events to the right view by URL.
"""

from django.urls import path
from djust.websocket import LiveViewConsumer

websocket_urlpatterns = [
    path("ws/live/", LiveViewConsumer.as_asgi()),
]
