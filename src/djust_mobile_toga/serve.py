"""Loopback-bound uvicorn helper for on-device djust apps.

Public API:

* :func:`run_loopback_server` — blocking call that runs uvicorn in the
  current thread, bound to ``127.0.0.1``, single-worker, ``ws="wsproto"``.
  Bypasses ``uvicorn.main`` / ``uvicorn.supervisors`` because those import
  ``_multiprocessing`` at load time (which iOS Python doesn't ship).
* :func:`free_port` — grab an unused TCP port on a loopback interface.

The single-process design is correct for on-device: there's nothing to fork
to, and Toga's WebView talks to a single backend.

Call :func:`djust_mobile_toga.shims.install` BEFORE this module imports any
uvicorn code (i.e. before :func:`run_loopback_server` is called for the
first time) so the ``_multiprocessing`` shim is in place when uvicorn loads.
"""

from __future__ import annotations

import asyncio
import socket


DEFAULT_HOST = "127.0.0.1"


def free_port(host: str = DEFAULT_HOST) -> int:
    """Grab an unused TCP port on ``host``.

    Uses ``bind(host, 0)`` to ask the kernel for an ephemeral port, then
    closes the socket — there is a tiny race window before the caller binds
    the same port, but it's the standard pattern for "give me any free port"
    on POSIX systems.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def run_loopback_server(
    asgi_app_path: str,
    port: int,
    host: str = DEFAULT_HOST,
    log_level: str = "info",
) -> None:
    """Run uvicorn loopback-bound, single-worker, in this thread (blocking).

    ``asgi_app_path`` is a dotted module path + attribute, e.g.
    ``"myapp.asgi:application"``. Passed straight to uvicorn's ``Config``.

    This function:

    * Creates a fresh asyncio event loop and binds it to the current thread.
    * Constructs ``uvicorn.config.Config`` and ``uvicorn.server.Server``
      directly — NOT via ``uvicorn.main`` or ``uvicorn.run``. Those import
      ``uvicorn.supervisors``, whose reload/multiprocess machinery imports
      ``_multiprocessing`` at module load and so cannot be imported on iOS
      (where ``_multiprocessing`` doesn't exist) without a shim.
    * Pins ``workers=1``, ``loop="asyncio"``, ``ws="wsproto"`` —
      ``wsproto`` is the pure-Python WebSocket protocol that installs on
      iOS and Android (the ``websockets`` lib has an optional C
      ``speedups.so`` that doesn't cross-compile cleanly).

    Blocks until the server exits (typically: never, on-device). Run from a
    background thread if the caller has an event loop on the main thread
    (e.g. Toga's UI event loop).
    """
    from uvicorn.config import Config
    from uvicorn.server import Server

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = Config(
        asgi_app_path,
        host=host,
        port=port,
        log_level=log_level,
        workers=1,
        loop="asyncio",
        ws="wsproto",
    )
    server = Server(config)
    loop.run_until_complete(server.serve())
