"""``BaseDjustApp`` — a ``toga.App`` subclass that runs a djust/Django backend
inside the app process, served over loopback, displayed in a WebView.

Subclass and override at least ``asgi_app_path`` and ``django_settings_module``::

    from djust_mobile_toga.app import BaseDjustApp

    class MyApp(BaseDjustApp):
        asgi_app_path = "myapp.asgi:application"
        django_settings_module = "myapp.settings"
        status_bar_color_argb = 0xFF14457E  # optional — tints iOS + Android

        def on_app_ready(self):
            # Optional hook, called once the WebView has loaded the home URL.
            # Use for app-specific post-launch work (notifications, analytics).
            ...

    def main():
        return MyApp(
            formal_name="My App",
            app_id="org.example.myapp",
            app_name="myapp",
        )

What ``BaseDjustApp.startup()`` does:

1. Picks the app sandbox's writable data dir (the bundle is read-only on
   both iOS and Android) and exports it via the env var named by
   ``data_dir_env_var``. Your Django ``settings.py`` reads this env var to
   decide where the SQLite db and collected static files live.
2. Sets ``DJANGO_SETTINGS_MODULE`` to ``django_settings_module``.
3. Starts a background thread that runs ``migrate`` + ``collectstatic``
   (synchronous-only commands that can't run on the iOS/Android UI loop),
   then boots an in-process uvicorn server on a free loopback port via
   :func:`djust_mobile_toga.serve.run_loopback_server`.
4. Builds the UI: a single ``toga.WebView`` inside a plain ``toga.Window``
   (no toga title bar — gives a full-screen, app-like presentation).
5. Tints the status bar to ``status_bar_color_argb`` on both iOS and
   Android, if that class attribute is set.
6. On a second background thread, polls the loopback port until the
   server is accepting, then sets ``webview.url`` to
   ``http://127.0.0.1:<port><start_path>`` on the UI thread.
7. Calls :meth:`on_app_ready` for consumer-specific post-launch work.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from typing import ClassVar, cast

import toga
from toga.style import Pack

from djust_mobile_toga import serve

LOG = logging.getLogger("djust_mobile_toga")

# Platform detection. iOS Python sets ``sys.platform`` to ``'ios'``; Chaquopy's
# Python 3.13 on Android keeps the linux platform name and adds
# ``sys.getandroidapilevel()`` (a Python 3.13+ feature in Android builds).
_IS_IOS = sys.platform == "ios"
_IS_ANDROID = hasattr(sys, "getandroidapilevel")

_HOST = "127.0.0.1"  # loopback ONLY — never 0.0.0.0


class BaseDjustApp(toga.App):
    """Base ``toga.App`` for a djust-on-device mobile app.

    Subclass and override the class attributes below; the default
    ``startup()`` handles the rest.
    """

    # ---- required overrides ------------------------------------------------
    #: Dotted module path + attribute for the ASGI application, e.g.
    #: ``"myapp.asgi:application"``. Passed to uvicorn's ``Config``.
    asgi_app_path: ClassVar[str] = ""

    #: Value to set for ``DJANGO_SETTINGS_MODULE`` before importing Django.
    django_settings_module: ClassVar[str] = ""

    # ---- optional overrides ------------------------------------------------
    #: Env var name to export with the writable data dir. Your ``settings.py``
    #: reads this to place the SQLite db / static-root somewhere writable
    #: (the iOS/Android app bundle is read-only). Default: ``DJUST_MOBILE_DATA_DIR``.
    data_dir_env_var: ClassVar[str] = "DJUST_MOBILE_DATA_DIR"

    #: Initial URL path the WebView loads after the server is up. Default: ``"/"``.
    start_path: ClassVar[str] = "/"

    #: 32-bit ARGB int for the status-bar tint, e.g. ``0xFF14457E`` for opaque
    #: blue. Applied to both iOS (via ``UIColor.colorWithRed``) and Android
    #: (via ``Window.setStatusBarColor``). Default: ``None`` — no tint.
    status_bar_color_argb: ClassVar[int | None] = None

    #: Whether to run ``collectstatic`` during startup. djust serves its
    #: ``client.js`` from ``/static/``, so on-device apps almost always need
    #: this. Default: ``True``.
    run_collectstatic: ClassVar[bool] = True

    #: Log level passed to uvicorn. Default: ``"info"``.
    uvicorn_log_level: ClassVar[str] = "info"

    # ---- internal state ----------------------------------------------------
    port: int = 0
    webview: toga.WebView | None = None
    _server_thread: threading.Thread | None = None
    _loader_thread: threading.Thread | None = None

    # ------------------------------------------------------------------------
    def startup(self) -> None:
        if not self.asgi_app_path or not self.django_settings_module:
            raise RuntimeError(
                "BaseDjustApp subclasses must set asgi_app_path and django_settings_module"
            )

        # 1. Writable data directory. The app bundle is read-only on both
        #    iOS and Android; Django's SQLite db + collected static files
        #    must live in a writable location. Toga exposes the sandbox
        #    paths via self.paths.
        data_dir = self.paths.data
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ[self.data_dir_env_var] = str(data_dir)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", self.django_settings_module)
        LOG.info("%s data dir: %s", self.formal_name, data_dir)

        self.port = serve.free_port(_HOST)

        # 2. Background thread for Django prep + uvicorn. Django's
        #    `migrate` / `collectstatic` are synchronous-only and raise
        #    SynchronousOnlyOperation if called while an asyncio event loop
        #    is running on the current thread. Toga's `startup()` runs ON
        #    the platform's UI event loop, so both Django prep AND uvicorn
        #    run on a plain background thread.
        self._server_thread = threading.Thread(
            target=self._prepare_and_serve, name="djust-server", daemon=True
        )
        self._server_thread.start()

        # 3. Build the UI: a single WebView in a plain toga.Window (no toga
        #    title bar). MainWindow on iOS gives a UINavigationController
        #    titlebar; a bare Window uses a RootContainer with no titlebar,
        #    so the UI runs edge-to-edge.
        self.webview = toga.WebView(style=Pack(flex=1))
        # iOS: let the web content draw under the status bar / home indicator.
        # WKWebView's scroll view auto-insets content for the safe area by
        # default; with `.never` (== 2) the page spans the whole screen and
        # the app's CSS can reclaim the safe area via env(safe-area-inset-*).
        # Android's WebView already draws into the safe area by default.
        if _IS_IOS:
            try:
                self.webview._impl.native.scrollView.contentInsetAdjustmentBehavior = 2
            except Exception:  # noqa: BLE001 - cosmetic; never block startup
                LOG.exception("could not disable WKWebView content-inset adjustment")

        window = toga.Window(title=self.formal_name)
        window.content = self.webview
        window.show()
        # toga's stubs type App.main_window as MainWindow | str | None, but a
        # plain Window is a valid main window; assign through a typed local.
        self.main_window = window  # type: ignore[assignment]

        # 4. Status-bar tint (if configured). Same RGB on both platforms;
        #    different APIs to apply it.
        if self.status_bar_color_argb is not None:
            self._tint_status_bar(self.status_bar_color_argb)

        # 5. Background thread: wait for the loopback server, then point the
        #    WebView at it. Done off-thread so startup() returns promptly
        #    and the UI event loop runs.
        self._loader_thread = threading.Thread(
            target=self._load_when_ready, name="djust-loader", daemon=True
        )
        self._loader_thread.start()

    # ------------------------------------------------------------------------
    def on_app_ready(self) -> None:
        """Hook called once the WebView has loaded the home URL.

        Override in your subclass for post-launch work (notifications,
        analytics, on-device migrations, etc.). Default: no-op.

        Called from the loader background thread — schedule UI work via
        ``self.loop.call_soon_threadsafe`` if you need to touch native UI.
        """

    # ------------------------------------------------------------------------
    def _prepare_and_serve(self) -> None:
        """Background thread: prepare Django, then run the ASGI server.

        Runs entirely off the platform UI event loop so the synchronous-only
        Django management commands (``migrate``, ``collectstatic``) are
        allowed.
        """
        try:
            self._prepare_django()
            self._run_server()
        except Exception:  # noqa: BLE001 - surface any boot failure
            LOG.exception("on-device server failed to start")

    def _prepare_django(self) -> None:
        """Run migrate (+ optionally collectstatic) against the writable data dir."""
        import django

        django.setup()
        from django.core.management import call_command

        LOG.info("running migrate ...")
        call_command("migrate", "--noinput", verbosity=0)
        if self.run_collectstatic:
            LOG.info("running collectstatic ...")
            call_command("collectstatic", "--noinput", verbosity=0)
        LOG.info("django prepared")

    def _run_server(self) -> None:
        """Run uvicorn — loopback-bound, single-process, wsproto."""
        LOG.info("starting uvicorn (in-process) on %s:%s", _HOST, self.port)
        serve.run_loopback_server(
            self.asgi_app_path,
            port=self.port,
            host=_HOST,
            log_level=self.uvicorn_log_level,
        )

    def _load_when_ready(self) -> None:
        """Poll the loopback port, then point the WebView at it."""
        deadline = time.time() + 30
        url = f"http://{_HOST}:{self.port}{self.start_path}"
        while time.time() < deadline:
            try:
                with socket.create_connection((_HOST, self.port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            LOG.error("server did not come up within 30s")
            return
        LOG.info("server is up; loading %s", url)
        # WebView.url must be set from the UI thread.
        self.loop.call_soon_threadsafe(lambda: setattr(self.webview, "url", url))

        try:
            self.on_app_ready()
        except Exception:  # noqa: BLE001 - never block on consumer code
            LOG.exception("on_app_ready hook raised")

    # ------------------------------------------------------------------------
    def _tint_status_bar(self, argb: int) -> None:
        """Tint the status bar to ``argb`` (0xAARRGGBB) on iOS / Android."""
        if _IS_IOS:
            self._tint_status_bar_ios(argb)
        elif _IS_ANDROID:
            self._tint_status_bar_android(argb)

    def _tint_status_bar_ios(self, argb: int) -> None:
        """iOS: color the window + root container so the status-bar strip
        sits over the consumer's chosen colour.

        toga lays the WebView out *below* the status bar (it sets a top
        inset equal to the status bar height), so colouring the window
        background lets the chosen colour show through that strip.
        """
        try:
            from rubicon.objc import ObjCClass

            a = ((argb >> 24) & 0xFF) / 255.0
            r = ((argb >> 16) & 0xFF) / 255.0
            g = ((argb >> 8) & 0xFF) / 255.0
            b = (argb & 0xFF) / 255.0
            ui_color = ObjCClass("UIColor")
            colour = ui_color.colorWithRed(r, green=g, blue=b, alpha=a)
            window = cast("toga.Window", self.main_window)
            window._impl.native.backgroundColor = colour
            window._impl.container.native.backgroundColor = colour
        except Exception:  # noqa: BLE001 - cosmetic; never block startup
            LOG.exception("could not set iOS status-bar colour")

    def _tint_status_bar_android(self, argb: int) -> None:
        """Android: call ``Window.setStatusBarColor`` on the MainActivity.

        ``setStatusBarColor`` takes a signed 32-bit ARGB int. Chaquopy's
        ``jint`` conversion rejects positive Python ints ≥ 2^31, so we
        convert to two's-complement. Also note: the Briefcase Android
        template's theme hard-codes ``colorPrimaryDark`` which Android
        applies BEFORE this runtime call — for full effect you typically
        also need to patch ``colors.xml`` in the generated scaffold (see
        the project's build scripts).
        """
        try:
            signed = argb if argb < 0x80000000 else argb - 0x100000000
            # toga-android's app._impl.native is the MainActivity instance
            # (set via MainActivity.singletonThis, see toga_android/app.py).
            # startup() runs on Android's UI thread (called from onCreate),
            # so setStatusBarColor is safe to call directly.
            self._impl.native.getWindow().setStatusBarColor(signed)
        except Exception:  # noqa: BLE001 - cosmetic; never block startup
            LOG.exception("could not set Android status-bar colour")
