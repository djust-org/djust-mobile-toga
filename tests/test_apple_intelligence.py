"""Tests for the Apple Intelligence bridge.

These run off-iOS (desktop CI), so they exercise the fail-soft guard paths:
the module must import cleanly, report unavailable, and never raise. The actual
on-device Foundation Models path can only be verified on an iOS 26+ device/sim
with Apple Intelligence enabled — that is hand-verified, not covered here.
"""

from djust_mobile_toga import apple_intelligence as ai


def test_import_does_not_raise():
    # Importing the module on any platform must be safe (it is, since we got here).
    assert ai is not None


def test_is_available_false_off_ios():
    # On the CI host (not iOS), the bridge is unavailable.
    assert ai.is_available() is False


def test_ask_returns_none_off_ios():
    assert ai.ask("What's my Part B premium?") is None


def test_ask_accepts_context_and_instructions_kwargs():
    # The keyword contract must hold even on the no-op path (callers always
    # pass context= / instructions=).
    assert ai.ask("q", context='{"a": 1}', instructions="be helpful") is None


def test_ask_never_raises_on_bad_input():
    # Fail-soft: even odd input returns None rather than propagating.
    assert ai.ask("") is None


def test_is_available_handles_flaky_bridge(monkeypatch):
    # Simulate "shim resolved but availability() raises" → must degrade to False,
    # never propagate.
    monkeypatch.setattr(ai, "_IOS_AVAILABLE", True)

    class _Boom:
        def available(self):
            raise RuntimeError("objc blew up")

    monkeypatch.setitem(ai._ios, "bridge", _Boom())
    assert ai.is_available() is False


def test_ask_short_circuits_when_unavailable(monkeypatch):
    # When is_available() is False, ask() must not attempt the ObjC path.
    monkeypatch.setattr(ai, "is_available", lambda: False)
    called = {"hit": False}

    def _boom(*a, **k):
        called["hit"] = True
        raise AssertionError("should not be called")

    monkeypatch.setattr(ai, "_ios_ask", _boom)
    assert ai.ask("q") is None
    assert called["hit"] is False
