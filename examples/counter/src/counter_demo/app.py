"""The Toga app shell — wraps the Django + djust counter in a native WebView.

This is the entire mobile side: subclass ``BaseDjustApp``, point it at the
ASGI app and settings module, and the base class handles shims, the writable
data dir, background Django prep (migrate), the loopback uvicorn server, and
the WebView. See ``__main__.py`` for the entry point.
"""

from djust_mobile_toga.app import BaseDjustApp


class CounterApp(BaseDjustApp):
    asgi_app_path = "counter_demo.asgi:application"
    django_settings_module = "counter_demo.settings"
    status_bar_color_argb = 0xFF0B1F3A  # opaque navy — matches the page background


def main() -> CounterApp:
    return CounterApp(formal_name="djust Counter", app_id="org.djust.examples.counter_demo")
