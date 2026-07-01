"""The Toga app shell for the showcase.

Beyond the base loopback-server + WebView setup, this wires the two bridges
that are *inbound* (the OS / in-page JS calls into Python): the Apple Wallet
install handler and the JS↔Python message handler. Both must be registered on
the main thread once the WebView exists, so we do it from ``on_app_ready`` via
``call_soon_threadsafe``. Everything here is a no-op off iOS.
"""

import json

from djust_mobile_toga import bridge, notifications
from djust_mobile_toga.app import BaseDjustApp
from djust_mobile_toga.passkit import enable_apple_wallet


def _on_bridge_ping(app, body):
    """Handle a JS ``postMessage`` and answer straight back into the page."""
    reply = json.dumps(f"Python received: {body}")
    app.webview.evaluate_javascript(
        f"document.getElementById('bridge-output').textContent = {reply};"
    )


class ShowcaseApp(BaseDjustApp):
    asgi_app_path = "showcase.asgi:application"
    django_settings_module = "showcase.settings"
    status_bar_color_argb = 0xFF0B1F3A

    def on_app_ready(self) -> None:
        # Runs on the loader background thread — marshal the native wiring
        # (which touches the WebView) onto the UI thread.
        self.loop.call_soon_threadsafe(self._wire_bridges)

    def _wire_bridges(self) -> None:
        enable_apple_wallet(self)  # registers the .pkpass install handler (iOS)
        bridge.register_script_handler(self, "bridgeDemo", _on_bridge_ping)  # iOS
        notifications.request_permission()  # ask once up front (no-op desktop)


def main() -> ShowcaseApp:
    return ShowcaseApp(formal_name="djust Showcase", app_id="org.djust.examples.showcase")
