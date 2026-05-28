"""WKScriptMessageHandler bridge for iOS WebView.

Lets djust apps register Python callbacks that JavaScript in the
embedded WebView can post messages to. The native handler runs in the
Python iOS app process and has full access to PyObjC — so any platform
API (PassKit, EventKit, Contacts, CoreLocation, etc.) is reachable
without leaving Python.

The flow:

1. App startup calls ``register_script_handler(app, name, callback)``.
2. In-page JavaScript calls
   ``window.webkit.messageHandlers.<name>.postMessage(body)``.
3. The Python ``callback(app, body)`` runs on the main thread and can
   call any PyObjC API directly.

Must be invoked on the main thread; from a Toga ``startup()`` or
``on_app_ready()`` hook (which runs on the loader background thread),
marshal via ``app.loop.call_soon_threadsafe(register_script_handler, ...)``.

No-op on Android — Android WebView has a different bridging surface
(``WebView.addJavascriptInterface``) that this module doesn't (yet)
implement. The dispatch shape is similar enough that future work could
unify them behind one ``register_script_handler`` call; for v1 the
function silently returns on non-iOS so consumers can call it
unconditionally.
"""

from __future__ import annotations

import sys
import traceback
from typing import Any, Callable

_IS_IOS = sys.platform == "ios"

# id(app) → {name: handler_objc_instance}. Retains the handler against
# the Python app instance so ARC doesn't free the underlying NSObject
# while WKWebView holds a weak reference.
_REGISTERED_HANDLERS: dict[int, dict[str, Any]] = {}


def register_script_handler(
    app, name: str, callback: Callable[[Any, str | None], None]
) -> None:
    """Register a Python callback against a WKScriptMessageHandler name.

    ``callback(app, body)`` runs on the main thread whenever JavaScript
    calls ``window.webkit.messageHandlers.<name>.postMessage(body)``.

    ``body`` is the JS-posted value coerced to a Python ``str`` (most
    common case — URLs, JSON-encoded blobs). Arrays / dicts pass through
    as ``ObjCInstance`` for the callback to convert.

    Args:
        app:      the ``BaseDjustApp`` subclass instance (or any Toga
                  app whose ``self.webview._impl.native`` is a WKWebView)
        name:     the JS handler name; in-page JS uses
                  ``window.webkit.messageHandlers.<name>.postMessage(...)``
        callback: Python function ``(app, body) -> None``. Exceptions are
                  caught + printed; never propagate to the WebView.

    No-op on Android and desktop.
    """
    if not _IS_IOS:
        return

    try:
        from rubicon.objc import NSObject, ObjCClass, objc_method  # noqa: F401
    except Exception:
        print(
            f"[djust_mobile_toga.bridge] rubicon.objc not importable — "
            f"skipping handler '{name}'",
            flush=True,
        )
        return

    wkwebview = app.webview._impl.native
    user_content_controller = wkwebview.configuration.userContentController

    class _ScriptMessageHandler(NSObject):
        """``WKScriptMessageHandler`` Obj-C subclass — single method."""

        @objc_method
        def userContentController_didReceiveScriptMessage_(
            self, _controller, message
        ):
            try:
                body = message.body
                py_body = str(body) if body is not None else None
                callback(app, py_body)
            except Exception:
                print(
                    f"[djust_mobile_toga.bridge] '{name}' callback raised:",
                    flush=True,
                )
                traceback.print_exc()

    handler = _ScriptMessageHandler.alloc().init()
    # Retain on the per-app dict so the NSObject isn't freed while WK
    # holds it weak. Removing the app from the dict on app teardown is
    # consumer-responsibility for now; in practice the app instance
    # outlives the WebView so it doesn't matter.
    handlers = _REGISTERED_HANDLERS.setdefault(id(app), {})
    handlers[name] = handler

    user_content_controller.addScriptMessageHandler_name_(handler, name)
    print(
        f"[djust_mobile_toga.bridge] registered WKScriptMessageHandler '{name}'",
        flush=True,
    )
