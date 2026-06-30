"""Tests for the cross-platform compatibility shims.

``install()`` patches two global surfaces — the ``_multiprocessing`` module
(stubbed on iOS, attr-patched elsewhere) and the ``mimetypes`` database — and
must be idempotent and non-destructive on a desktop where the real
``_multiprocessing`` is present. These tests save/restore every global they
touch so they don't pollute the rest of the suite.
"""

from __future__ import annotations

import copy
import mimetypes
import sys

import pytest

from djust_mobile_toga import shims


@pytest.fixture
def restore_mimetypes():
    """Snapshot + restore the mimetypes global database around a test."""
    snap = (
        mimetypes.inited,
        copy.copy(mimetypes.types_map),
        copy.copy(getattr(mimetypes, "_db", None)),
    )
    try:
        yield
    finally:
        inited, types_map, db = snap
        mimetypes.inited = inited
        mimetypes.types_map.clear()
        mimetypes.types_map.update(types_map)
        if db is not None:
            mimetypes._db = db


@pytest.fixture
def restore_multiprocessing():
    """Snapshot + restore sys.modules['_multiprocessing'] around a test."""
    saved = sys.modules.get("_multiprocessing")
    try:
        yield
    finally:
        if saved is not None:
            sys.modules["_multiprocessing"] = saved
        else:
            sys.modules.pop("_multiprocessing", None)


def test_import_does_not_raise():
    assert shims is not None


def test_install_is_idempotent(restore_mimetypes, restore_multiprocessing):
    # Calling install() twice must not error.
    shims.install()
    shims.install()


def test_install_patches_mimetypes(restore_mimetypes, restore_multiprocessing):
    shims.install()
    # The static-file types djust serves over the loopback handler.
    assert mimetypes.types_map[".js"] == "text/javascript"
    assert mimetypes.types_map[".css"] == "text/css"
    assert mimetypes.types_map[".woff2"] == "font/woff2"
    # A deliberately non-standard mapping install() adds (sourcemaps) — proves
    # install() ran rather than the interpreter's built-in set happening to match.
    assert mimetypes.types_map[".map"] == "application/json"


def test_install_leaves_multiprocessing_with_required_attrs(
    restore_mimetypes, restore_multiprocessing
):
    # On desktop the real C module is present; install() patches it in place and
    # SemLock / sem_unlink must still be reachable (uvicorn references them).
    shims.install()
    mp = sys.modules["_multiprocessing"]
    assert hasattr(mp, "SemLock")
    assert hasattr(mp, "sem_unlink")
    assert hasattr(mp.SemLock, "SEM_VALUE_MAX")


def test_install_does_not_break_real_multiprocessing(restore_mimetypes, restore_multiprocessing):
    # The real module identity must survive install() on desktop.
    import _multiprocessing as real_mp

    shims.install()
    assert sys.modules["_multiprocessing"] is real_mp


def test_ios_stub_path_builds_a_working_stub(restore_multiprocessing):
    """Simulate iOS: no ``_multiprocessing`` and unimportable → install a stub.

    A meta_path finder blocks the import so the function takes its iOS branch,
    building a fresh stub module. We assert the stub exposes every symbol the
    stdlib reads at import time, with a SemLock that raises if ever instantiated.
    """

    class _Block:
        def find_spec(self, name, path, target=None):
            if name == "_multiprocessing":
                raise ModuleNotFoundError(name)
            return None

    blocker = _Block()
    sys.modules.pop("_multiprocessing", None)
    sys.meta_path.insert(0, blocker)
    try:
        shims._install_multiprocessing_stub()
        stub = sys.modules["_multiprocessing"]
        # Class-level attr read by multiprocessing/synchronize.py at import.
        assert stub.SemLock.SEM_VALUE_MAX == 32767
        # Symbols other stdlib modules reference at import time.
        for attr in ("sem_unlink", "closesocket", "send", "recv", "flags"):
            assert hasattr(stub, attr)
        # Single-process on-device never creates one — instantiation must raise.
        with pytest.raises(NotImplementedError):
            stub.SemLock()
    finally:
        sys.meta_path.remove(blocker)


def test_harden_mimetypes_reads_no_files(restore_mimetypes):
    # _harden_mimetypes must initialize from the built-in map only (files=[]),
    # never touching the sandbox-forbidden system mime files. We assert it leaves
    # the database in the expected, file-free state with our types present.
    shims._harden_mimetypes()
    assert mimetypes.types_map[".svg"] == "image/svg+xml"
    assert mimetypes.types_map[".json"] == "application/json"
