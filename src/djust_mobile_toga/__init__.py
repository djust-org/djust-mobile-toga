"""djust-mobile-toga — embed djust as an on-device server in a Toga + Briefcase app.

Six submodules, all independent — import only what you need:

* ``djust_mobile_toga.shims`` — cross-platform compatibility shims (must run
  BEFORE importing uvicorn/Django). Safe no-ops on platforms that don't need
  them; required on iOS and Android.

* ``djust_mobile_toga.serve`` — loopback-bound uvicorn helper. Bypasses
  ``uvicorn.main`` / ``uvicorn.supervisors`` (which import ``_multiprocessing``
  at load time and can't load on iOS), drives an in-process single-worker
  server with ``ws="wsproto"``.

* ``djust_mobile_toga.app`` — ``BaseDjustApp(toga.App)``. Override
  ``asgi_app_path`` and (optionally) ``start_path``, ``status_bar_color_argb``,
  ``data_dir_env_var``, ``on_app_ready()``. The base class handles writable
  data dir selection, background-thread ``migrate`` + ``collectstatic``,
  uvicorn boot, WebView pointing at loopback, iOS/Android status-bar tinting.

* ``djust_mobile_toga.notifications`` — cross-platform on-device local
  notifications. ``is_available()`` / ``request_permission()`` /
  ``schedule_local(title=..., body=..., delay_seconds=..., identifier=...)``
  / ``cancel_local(identifier)``. Backed by ``UNUserNotificationCenter`` on
  iOS and ``NotificationManagerCompat`` (via Chaquopy's ``java`` module) on
  Android; logged no-op on desktop.

* ``djust_mobile_toga.bridge`` — register JavaScript-to-Python callbacks
  on the WKWebView via ``WKScriptMessageHandler``. Generic mechanism the
  PassKit / vCard / .ics integrations build on. iOS-only (Android equivalent
  via ``addJavascriptInterface`` is future work).

* ``djust_mobile_toga.passkit`` — ``enable_apple_wallet(app)`` wires the
  pkpass install handler. Pair with the ``{% wallet_add_button url %}``
  template tag (in ``djust_mobile_toga.templatetags.djust_mobile_toga``)
  for the in-page button. Requires ``"djust_mobile_toga"`` in
  ``INSTALLED_APPS`` to load the template tag library.

* ``djust_mobile_toga.apple_intelligence`` — on-device Apple Intelligence
  (Foundation Models) Q&A. ``is_available()`` / ``ask(prompt, context=...,
  instructions=...)``. iOS 26+ via a Swift ``@objc`` shim the consuming app
  compiles in (Foundation Models is Swift-only, so rubicon can't reach it
  directly); fail-soft no-op (``ask`` -> ``None``) on desktop / Android /
  older iOS / when the shim is absent.

* ``djust_mobile_toga.voice`` — on-device speech. ``stt_available()`` /
  ``start_dictation(on_partial=, on_final=)`` / ``stop_dictation()`` and
  ``tts_available()`` / ``speak(text)`` / ``stop_speaking()``. iOS speech
  frameworks (``SFSpeechRecognizer``, ``AVSpeechSynthesizer``) are ObjC-API so
  rubicon reaches them DIRECTLY — no Swift shim. On-device recognition
  (``requiresOnDeviceRecognition``) keeps audio on the phone. Fail-soft no-op on
  desktop / Android / older iOS. Needs ``NSMicrophoneUsageDescription`` +
  ``NSSpeechRecognitionUsageDescription`` in the consuming app's Info.plist.
"""

__version__ = "0.5.1"

# Convenience for Django integration. Pointing INSTALLED_APPS at the package
# (vs. the AppConfig) auto-discovers `apps.DjustMobileTogaConfig`.
default_app_config = "djust_mobile_toga.apps.DjustMobileTogaConfig"
