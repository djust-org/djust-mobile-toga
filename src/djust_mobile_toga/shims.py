"""Cross-platform compatibility shims — install BEFORE importing uvicorn/Django.

Two environment fixes (both safe no-ops where they're not needed, so the same
call works on iOS, Android, and desktop), applied by :func:`install`:

1. **``_multiprocessing`` stub.** iOS's Python (Python-Apple-support) is built
   without the ``_multiprocessing`` C extension, because iOS forbids ``fork()``
   and subprocess creation. ``uvicorn`` imports ``multiprocessing`` (and
   transitively ``_multiprocessing``) at *module load time* — ``uvicorn.main``
   → ``uvicorn.supervisors._subprocess`` calls
   ``multiprocessing.allow_connection_pickling()`` at import. A single-process
   on-device server never needs multiprocessing, so a minimal stub satisfies
   the import-time references; the code paths that would call into it (the
   reload supervisor, worker-process spawning) are never reached when the
   server is driven via ``uvicorn.server.Server.serve()`` with one worker.

   On Android, Chaquopy installs its own ``_multiprocessing`` stub lazily on
   first import — but its ``_SemLock`` is missing ``SEM_VALUE_MAX``, which
   ``multiprocessing/synchronize.py`` reads at module import time. We
   pre-import ``multiprocessing.synchronize`` here while our patched stub is
   in place, so the cached module survives Chaquopy's later sys.modules swap.

2. **``mimetypes`` hardening.** Django's static-file handler calls
   ``mimetypes.guess_type()``, which triggers ``mimetypes.init()``. ``init()``
   walks a list of system mime files (``/etc/apache2/mime.types``,
   ``/etc/mime.types``, …) and ``open()``s each one that exists. On a Mac
   those files exist, but the iOS app sandbox denies reading them →
   ``PermissionError`` → the static handler returns 500 — fatally, on
   ``/static/djust/client.js``, which leaves the djust client unable to load.
   Pre-initializing the mimetypes database from Python's built-in type map,
   reading no system files, avoids the sandbox-forbidden ``open()`` entirely.

:func:`install` is idempotent and a no-op for any shim already satisfied
(e.g. the real ``_multiprocessing`` on the macOS dev build), so the same call
runs unchanged on desktop and on device.

Usage::

    from djust_mobile_toga import shims
    shims.install()                       # call BEFORE importing uvicorn/Django

Or for an even more explicit pattern::

    from djust_mobile_toga.shims import install
    install()
"""

import mimetypes
import sys
import types

# The static-file MIME types most djust apps serve over the loopback handler.
# All are present in Python 3.11+'s built-in ``types_map``; they are re-asserted
# explicitly so a correct ``Content-Type`` does not silently depend on the
# interpreter's built-in set.
_DEFAULT_MIME_TYPES = (
    ("text/javascript", ".js"),
    ("text/javascript", ".mjs"),
    ("text/css", ".css"),
    ("text/html", ".html"),
    ("application/json", ".json"),
    ("application/json", ".map"),
    ("image/svg+xml", ".svg"),
    ("image/png", ".png"),
    ("image/x-icon", ".ico"),
    ("font/woff2", ".woff2"),
)


def _harden_mimetypes() -> None:
    """Initialize the mimetypes database without reading system mime files.

    ``mimetypes.init(files=[])`` builds the global database from the built-in
    ``types_map`` and reads no files from disk. Once the database is set,
    later ``guess_type()`` calls reuse it instead of re-running ``init()`` —
    so the sandbox-forbidden ``open('/etc/apache2/mime.types')`` never runs.
    """
    mimetypes.init(files=[])
    for ctype, ext in _DEFAULT_MIME_TYPES:
        mimetypes.add_type(ctype, ext)


def _ensure_semlock_class_attrs(SemLock) -> None:
    """Ensure ``_SemLock`` exposes the class-level attributes ``multiprocessing``
    accesses at *import time*.

    ``multiprocessing/synchronize.py`` reads ``_multiprocessing.SemLock.SEM_VALUE_MAX``
    *during module import* — not when a semaphore is created. So a stub class
    without those attributes makes the module fail to import, which is what
    bites Django on Android when ``django.db.backends.sqlite3.creation`` pulls
    in ``multiprocessing.synchronize`` transitively (see Chaquopy's
    ``android/__init__.py initialize_multiprocessing`` hook).

    The value itself is the POSIX semaphore maximum; nothing on-device ever
    creates a semaphore, so any sensible upper bound works.
    """
    if not hasattr(SemLock, "SEM_VALUE_MAX"):
        SemLock.SEM_VALUE_MAX = 32767  # POSIX _SEM_VALUE_MAX lower bound


def _install_multiprocessing_stub() -> None:
    """Install or finish-installing the ``_multiprocessing`` stub.

    Three platform pictures to cover:

    * **Desktop / macOS** — the real C ``_multiprocessing`` is present; do nothing.
    * **iOS** — no ``_multiprocessing`` at all; install our own stub.
    * **Android (Chaquopy)** — Chaquopy installs its own stub on Python init,
      but its ``_SemLock`` is missing the class attributes that
      ``multiprocessing/synchronize.py`` reads at import time. Patch them on.
    """
    existing = sys.modules.get("_multiprocessing")
    if existing is None:
        try:
            import _multiprocessing as existing  # noqa: F401  -- real module
        except ModuleNotFoundError:
            existing = None

    if existing is not None:
        # Real or pre-installed (Chaquopy) module — just patch missing attrs.
        SemLock = getattr(existing, "SemLock", None)
        if SemLock is not None:
            _ensure_semlock_class_attrs(SemLock)
        return

    # iOS path — install a fresh stub.
    stub = types.ModuleType("_multiprocessing")

    class _SemLock:  # pragma: no cover - never instantiated on iOS
        """Placeholder for ``_multiprocessing.SemLock`` (named-semaphore lock).

        Single-process on-device servers never create one.
        """

        def __init__(self, *args, **kwargs):
            raise NotImplementedError(
                "_multiprocessing.SemLock is unavailable on this platform"
            )

    _ensure_semlock_class_attrs(_SemLock)

    def _unsupported(*_args, **_kwargs):  # pragma: no cover
        raise NotImplementedError("multiprocessing is unavailable on this platform")

    # Symbols `multiprocessing.connection` / `synchronize` reference at
    # import time. Functions are stubbed to raise only if actually called.
    stub.SemLock = _SemLock
    stub.sem_unlink = _unsupported
    stub.closesocket = _unsupported
    stub.send = _unsupported
    stub.recv = _unsupported
    stub.flags = {}

    sys.modules["_multiprocessing"] = stub


def _preimport_multiprocessing_synchronize() -> None:
    """Cache ``multiprocessing.synchronize`` while our ``_SemLock`` is in place.

    On Android, Chaquopy installs its own ``_multiprocessing`` stub *later* —
    lazily, the first time something imports ``multiprocessing`` (e.g. Django's
    ``sqlite3.creation`` triggers Chaquopy's ``initialize_multiprocessing``).
    That stub's ``_SemLock`` is missing the class attributes that
    ``multiprocessing/synchronize.py`` reads at import time, so the lazy
    import fails — even though our shim above pre-installed a fixed stub,
    Chaquopy overwrites ``sys.modules['_multiprocessing']`` first.

    The fix: pre-import ``multiprocessing.synchronize`` here, while *our*
    ``_SemLock`` is the one being looked up. The module ends up in
    ``sys.modules`` and Chaquopy's later import becomes a no-op cache hit.
    Nothing in a djust on-device app actually uses semaphores, so it doesn't
    matter that the cached class attributes came from our stub.
    """
    try:
        import multiprocessing.synchronize  # noqa: F401
    except Exception:  # pragma: no cover - defensive
        pass


def install() -> None:
    """Install all platform shims. Idempotent; safe on iOS, Android, and desktop."""
    _install_multiprocessing_stub()
    _preimport_multiprocessing_synchronize()
    _harden_mimetypes()
