"""djust-mobile-toga — embed djust as an on-device server in a Toga + Briefcase app.

Three submodules, all independent — import only what you need:

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
"""

__version__ = "0.1.0"
