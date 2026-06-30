"""Tests for the WKScriptMessageHandler bridge.

Off-iOS (desktop CI) the public ``register_script_handler`` is a guarded no-op
that must never raise. The real ObjC wiring only runs on an iOS device; we
cover the wiring CONTRACT with a minimal fake ``rubicon.objc`` (NOT a deep ObjC
mock) — enough to prove the handler lands in the per-app registry, the
WKWebView's userContentController is told about it, a second handler doesn't
collide (the PR #4 fix), and the dispatch method coerces the body + swallows
callback exceptions. The genuine PyObjC surface is hand-verified on-device.
"""

from __future__ import annotations

import sys
import types

import pytest

from djust_mobile_toga import bridge


def test_import_does_not_raise():
    assert bridge is not None


def test_register_is_noop_off_ios():
    # Off-iOS the function returns before touching app internals — passing an
    # object with no webview must not raise.
    bridge.register_script_handler(object(), "speak", lambda app, body: None)


def test_register_off_ios_never_raises_with_real_looking_args():
    class _App:
        # Deliberately no .webview — the off-iOS guard returns before access.
        pass

    bridge.register_script_handler(_App(), "addToWallet", lambda a, b: None)


def test_register_ios_but_rubicon_missing_is_fail_soft(monkeypatch):
    # Simulate "really iOS, but rubicon.objc not importable" → print + return,
    # never raise. rubicon isn't installed in the dev env, so the import fails
    # naturally once we flip the platform flag.
    monkeypatch.setattr(bridge, "_IS_IOS", True)
    monkeypatch.setitem(sys.modules, "rubicon", None)
    monkeypatch.setitem(sys.modules, "rubicon.objc", None)
    bridge.register_script_handler(object(), "speak", lambda a, b: None)


# --- mocked-iOS wiring contract -------------------------------------------------


def _install_fake_rubicon(monkeypatch):
    """Inject a minimal fake ``rubicon.objc`` so the iOS branch can run.

    NSObject.alloc() returns a real instance of the dynamically-built
    _ScriptMessageHandler subclass so its objc_method is reachable for the
    dispatch test. This is the smallest surface that exercises the real wiring
    code path — not a model of PyObjC.
    """

    class _NSObject:
        def __init_subclass__(cls, **kwargs):  # swallow auto_rename=True
            super().__init_subclass__()

        @classmethod
        def alloc(cls):
            return cls.__new__(cls)

        def init(self):
            return self

    def _objc_method(fn):
        return fn

    fake = types.ModuleType("rubicon.objc")
    fake.NSObject = _NSObject
    fake.objc_method = _objc_method
    fake.ObjCClass = type("ObjCClass", (), {})

    rubicon_pkg = types.ModuleType("rubicon")
    rubicon_pkg.objc = fake
    monkeypatch.setitem(sys.modules, "rubicon", rubicon_pkg)
    monkeypatch.setitem(sys.modules, "rubicon.objc", fake)


class _FakeUCC:
    def __init__(self):
        self.calls: list = []

    def addScriptMessageHandler_name_(self, handler, name):
        self.calls.append((handler, name))


def _fake_app():
    ns = types.SimpleNamespace
    ucc = _FakeUCC()
    app = ns(webview=ns(_impl=ns(native=ns(configuration=ns(userContentController=ucc)))))
    return app, ucc


@pytest.fixture
def clean_registry():
    """Keep the module-global handler registry from leaking between tests."""
    before = dict(bridge._REGISTERED_HANDLERS)
    try:
        yield
    finally:
        bridge._REGISTERED_HANDLERS.clear()
        bridge._REGISTERED_HANDLERS.update(before)


def test_register_ios_wires_handler(monkeypatch, clean_registry):
    monkeypatch.setattr(bridge, "_IS_IOS", True)
    _install_fake_rubicon(monkeypatch)
    app, ucc = _fake_app()

    bridge.register_script_handler(app, "speak", lambda a, b: None)

    # Retained against the app instance so ARC doesn't free it.
    assert "speak" in bridge._REGISTERED_HANDLERS[id(app)]
    # Registered with the WKWebView's userContentController under the same name.
    assert len(ucc.calls) == 1
    assert ucc.calls[0][1] == "speak"


def test_register_ios_two_handlers_no_collision(monkeypatch, clean_registry):
    # The PR #4 fix: a second register call must not collide on the ObjC class
    # name (auto_rename); both handlers end up registered.
    monkeypatch.setattr(bridge, "_IS_IOS", True)
    _install_fake_rubicon(monkeypatch)
    app, ucc = _fake_app()

    bridge.register_script_handler(app, "addToWallet", lambda a, b: None)
    bridge.register_script_handler(app, "speak", lambda a, b: None)

    assert set(bridge._REGISTERED_HANDLERS[id(app)]) == {"addToWallet", "speak"}
    assert [name for _h, name in ucc.calls] == ["addToWallet", "speak"]


def test_dispatch_coerces_body_and_invokes_callback(monkeypatch, clean_registry):
    monkeypatch.setattr(bridge, "_IS_IOS", True)
    _install_fake_rubicon(monkeypatch)
    app, _ucc = _fake_app()
    seen: dict = {}

    bridge.register_script_handler(app, "speak", lambda a, b: seen.update(app=a, body=b))
    handler = bridge._REGISTERED_HANDLERS[id(app)]["speak"]

    msg = types.SimpleNamespace(body="/x.pkpass")
    handler.userContentController_didReceiveScriptMessage_(None, msg)
    assert seen == {"app": app, "body": "/x.pkpass"}

    # A None body coerces to None (not the string "None").
    seen.clear()
    handler.userContentController_didReceiveScriptMessage_(None, types.SimpleNamespace(body=None))
    assert seen == {"app": app, "body": None}


def test_dispatch_swallows_callback_exception(monkeypatch, clean_registry):
    monkeypatch.setattr(bridge, "_IS_IOS", True)
    _install_fake_rubicon(monkeypatch)
    app, _ucc = _fake_app()

    def _boom(_app, _body):
        raise RuntimeError("callback blew up")

    bridge.register_script_handler(app, "boom", _boom)
    handler = bridge._REGISTERED_HANDLERS[id(app)]["boom"]
    # Must be caught + printed, never propagate to the WebView.
    handler.userContentController_didReceiveScriptMessage_(None, types.SimpleNamespace(body="z"))
