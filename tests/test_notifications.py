"""Tests for the cross-platform local-notifications bridge.

Off-iOS / off-Android (desktop CI) every public function is a fail-soft no-op:
the module imports cleanly, ``is_available()`` is False, and
``schedule_local`` / ``cancel_local`` / ``request_permission`` never raise even
with real-looking arguments. The actual ``UNUserNotificationCenter`` (iOS) and
``NotificationManagerCompat`` (Android) paths can only be verified on a device
and are hand-verified, not covered here. A mocked-iOS dispatch test proves the
public wrappers route to the iOS backend without deep ObjC mocks.
"""

from __future__ import annotations

from djust_mobile_toga import notifications


def test_import_does_not_raise():
    assert notifications is not None


def test_is_available_false_off_platform():
    assert notifications.is_available() is False


def test_schedule_local_returns_false_off_platform():
    result = notifications.schedule_local(
        title="Your screening is due",
        body="Margaret, you're due for a colorectal cancer screening.",
        delay_seconds=30.0,
        identifier="screening-reminder",
    )
    assert result is False


def test_schedule_local_without_identifier_is_false():
    assert notifications.schedule_local(title="t", body="b", delay_seconds=5.0) is False


def test_schedule_local_zero_delay_is_false_off_platform():
    assert notifications.schedule_local(title="t", body="b", delay_seconds=0.0) is False


def test_request_permission_is_safe_noop():
    # No backend → logged no-op, never raises.
    notifications.request_permission()


def test_cancel_local_is_safe_noop():
    # Cancelling an unknown identifier off-platform must not raise.
    notifications.cancel_local("screening-reminder")
    notifications.cancel_local("never-scheduled")


def test_schedule_local_never_raises_on_odd_input():
    # Fail-soft: odd input returns False rather than propagating.
    assert notifications.schedule_local(title="", body="", delay_seconds=-1.0) is False


def test_request_permission_swallows_backend_error(monkeypatch):
    # Simulate "iOS backend resolved but the request raises" → must be caught,
    # never propagate.
    monkeypatch.setattr(notifications, "_IOS_AVAILABLE", True)

    def _boom():
        raise RuntimeError("objc blew up")

    monkeypatch.setattr(notifications, "_ios_request_permission", _boom)
    notifications.request_permission()  # must not raise


def test_schedule_local_swallows_backend_error_returns_false(monkeypatch):
    monkeypatch.setattr(notifications, "_IOS_AVAILABLE", True)

    def _boom(**kwargs):
        raise RuntimeError("objc blew up")

    monkeypatch.setattr(notifications, "_ios_schedule_local", _boom)
    assert notifications.schedule_local(title="t", body="b", delay_seconds=1.0) is False


def test_cancel_local_swallows_backend_error(monkeypatch):
    monkeypatch.setattr(notifications, "_IOS_AVAILABLE", True)

    def _boom(identifier):
        raise RuntimeError("objc blew up")

    monkeypatch.setattr(notifications, "_ios_cancel_local", _boom)
    notifications.cancel_local("x")  # must not raise


def test_schedule_local_routes_to_ios_backend(monkeypatch):
    # When the iOS backend is available, schedule_local must delegate to it and
    # pass the args through by keyword.
    monkeypatch.setattr(notifications, "_IOS_AVAILABLE", True)
    captured: dict = {}

    def _fake(*, title, body, delay_seconds, identifier):
        captured.update(title=title, body=body, delay_seconds=delay_seconds, identifier=identifier)
        return True

    monkeypatch.setattr(notifications, "_ios_schedule_local", _fake)
    result = notifications.schedule_local(title="t", body="b", delay_seconds=2.5, identifier="id-1")
    assert result is True
    assert captured == {
        "title": "t",
        "body": "b",
        "delay_seconds": 2.5,
        "identifier": "id-1",
    }


def test_is_available_true_when_android_backend(monkeypatch):
    monkeypatch.setattr(notifications, "_ANDROID_AVAILABLE", True)
    assert notifications.is_available() is True
