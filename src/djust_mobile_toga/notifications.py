"""Cross-platform on-device local notifications.

One API, three backends:

* **iOS** — ``UNUserNotificationCenter`` via ``rubicon-objc``. A real iOS
  local notification: fires offline (airplane mode), needs no Apple Push
  certificate, works the same on the Simulator as on a device. Identical to
  how a Swift/Obj-C app would schedule one.

* **Android** — ``NotificationManagerCompat`` + ``NotificationChannel`` +
  ``NotificationCompat.Builder`` via Chaquopy's ``java`` module. The
  delay is implemented with ``Handler.postDelayed`` (in-process timer) —
  this means the notification fires reliably while the app process is
  alive (foreground or recently backgrounded) but the OS may kill the
  process during longer backgrounds, in which case the timer is lost.
  For background-survival, switch to ``AlarmManager`` + a manifest-declared
  ``BroadcastReceiver`` (out of scope here because it needs a manifest
  registration in the consuming app).

* **Desktop / any other platform** — logged no-op. ``is_available()``
  returns ``False`` so consumers can do an early check.

Public API::

    from djust_mobile_toga import notifications

    notifications.is_available()                       # -> bool
    notifications.request_permission()                 # one-time platform prompt
    notifications.schedule_local(
        title="Your screening is due",
        body="Margaret, you're due for a colorectal cancer screening …",
        delay_seconds=30.0,
        identifier="screening-reminder",               # optional; for cancel
    )
    notifications.cancel_local("screening-reminder")   # optional

Every function is fail-soft: any backend-internal exception is caught and
logged but never propagates. Notifications are an "extra" — they must not
take the app down.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

LOG = logging.getLogger("djust_mobile_toga.notifications")

_IS_IOS = sys.platform == "ios"
_IS_ANDROID = hasattr(sys, "getandroidapilevel")


# ----------------------------------------------------------------------------
# iOS backend
# ----------------------------------------------------------------------------

_IOS_AVAILABLE = False
_ios: dict[str, Any] = {}
# Keeps rubicon ``Block`` wrappers alive for the process lifetime — iOS invokes
# the authorization completion handler asynchronously, long after the call
# returns, so the wrapper must not be garbage-collected in the meantime.
_ios_keepalive: list = []
# UNAuthorizationOptions bitmask (UserNotifications/UNNotificationSettings.h):
#   Badge = 1<<0, Sound = 1<<1, Alert = 1<<2.
_IOS_AUTH_BADGE_SOUND_ALERT = (1 << 0) | (1 << 1) | (1 << 2)

if _IS_IOS:
    try:
        import ctypes

        from rubicon.objc import Block, ObjCClass, ObjCInstance
        from rubicon.objc.runtime import load_library

        # UserNotifications is not auto-linked into a Toga app; load it
        # explicitly so the ObjC runtime can resolve UN* classes. On iOS
        # ctypes.util can't see system frameworks — rubicon's load_library has
        # the known-path fallback.
        load_library("UserNotifications")

        _ios["UNUserNotificationCenter"] = ObjCClass("UNUserNotificationCenter")
        _ios["UNMutableNotificationContent"] = ObjCClass("UNMutableNotificationContent")
        _ios["UNTimeIntervalNotificationTrigger"] = ObjCClass("UNTimeIntervalNotificationTrigger")
        _ios["UNNotificationRequest"] = ObjCClass("UNNotificationRequest")
        _ios["UNNotificationSound"] = ObjCClass("UNNotificationSound")
        _ios["Block"] = Block
        _ios["ObjCInstance"] = ObjCInstance
        _ios["ctypes"] = ctypes
        _IOS_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001 - any failure = "not on iOS or framework missing"
        LOG.info("iOS UserNotifications unavailable: %s", exc)


def _ios_request_permission() -> None:
    center = _ios["UNUserNotificationCenter"].currentNotificationCenter()

    def _on_auth(granted, error):  # runs on an iOS callback thread
        LOG.info("iOS notification authorization granted=%s", bool(granted))

    # void (^)(BOOL granted, NSError *error)
    callback = _ios["Block"](_on_auth, None, _ios["ctypes"].c_bool, _ios["ObjCInstance"])
    _ios_keepalive.append(callback)
    center.requestAuthorizationWithOptions(_IOS_AUTH_BADGE_SOUND_ALERT, completionHandler=callback)
    LOG.info("requested iOS notification authorization")


def _ios_schedule_local(
    *, title: str, body: str, delay_seconds: float, identifier: str | None
) -> bool:
    center = _ios["UNUserNotificationCenter"].currentNotificationCenter()
    content = _ios["UNMutableNotificationContent"].alloc().init()
    content.title = title
    content.body = body
    # `defaultSound` is a class *property* (not a method) — no parens.
    content.sound = _ios["UNNotificationSound"].defaultSound

    # repeats=False allows sub-60s intervals (the 60s floor is repeat-only).
    trigger = _ios["UNTimeIntervalNotificationTrigger"].triggerWithTimeInterval(
        float(delay_seconds), repeats=False
    )
    request = _ios["UNNotificationRequest"].requestWithIdentifier(
        identifier or "djust-mobile-toga-notification",
        content=content,
        trigger=trigger,
    )
    # withCompletionHandler: is nullable here — nil is safe.
    center.addNotificationRequest(request, withCompletionHandler=None)
    LOG.info("iOS scheduled local notification %r in %ss", identifier, delay_seconds)
    return True


def _ios_cancel_local(identifier: str) -> None:
    center = _ios["UNUserNotificationCenter"].currentNotificationCenter()
    # removePendingNotificationRequestsWithIdentifiers: takes an NSArray of NSString.
    # rubicon-objc autoboxes a Python list of str.
    center.removePendingNotificationRequestsWithIdentifiers([identifier])
    LOG.info("iOS cancelled local notification %r", identifier)


# ----------------------------------------------------------------------------
# Android backend
# ----------------------------------------------------------------------------

_ANDROID_AVAILABLE = False
_android: dict[str, Any] = {}
_ANDROID_CHANNEL_ID = "djust_mobile_toga_default"
_ANDROID_CHANNEL_NAME = "App notifications"
# Auto-increment IDs for posted notifications (Android NotificationManager.notify
# uses an int ID, NOT a string). The identifier-string API is mapped to int IDs
# via this dict so cancel_local can find them.
_android_id_map: dict[str, int] = {}
_android_next_id = 1

if _IS_ANDROID:
    try:
        from java import dynamic_proxy, jclass

        _android["jclass"] = jclass
        # Reach the Application context. Chaquopy exposes the live PyApplication
        # via ``com.chaquo.python.Python.getPlatform().getApplication()``, which
        # returns the Application instance (a Context) for the app's lifetime.
        Python = jclass("com.chaquo.python.Python")
        _android["context"] = Python.getPlatform().getApplication()
        _android["NotificationCompat$Builder"] = jclass(
            "androidx.core.app.NotificationCompat$Builder"
        )
        _android["NotificationManagerCompat"] = jclass(
            "androidx.core.app.NotificationManagerCompat"
        )
        _android["NotificationChannel"] = jclass("android.app.NotificationChannel")
        _android["NotificationManager"] = jclass("android.app.NotificationManager")
        _android["Handler"] = jclass("android.os.Handler")
        _android["Looper"] = jclass("android.os.Looper")
        _android["Build$VERSION"] = jclass("android.os.Build$VERSION")
        # android.R.drawable.ic_dialog_info — a built-in icon. NotificationCompat
        # requires a small icon; using a stock framework drawable means consumers
        # don't have to ship one in their resources for notifications to render.
        _android["R$drawable"] = jclass("android.R$drawable")

        # Chaquopy does NOT auto-wrap a Python callable as a Java Runnable —
        # `Handler.postDelayed(fn, ms)` raises TypeError. We need a proper
        # Runnable subclass; `dynamic_proxy` creates one at runtime without
        # declaring a static_proxy in pyproject.toml.
        _Runnable = jclass("java.lang.Runnable")

        # chaquopy's dynamic_proxy(...) returns a runtime-built base class mypy
        # can't model (Android-only path).
        class _CallableRunnable(dynamic_proxy(_Runnable)):  # type: ignore[misc]
            def __init__(self, fn):
                super().__init__()
                self._fn = fn

            def run(self):  # pragma: no cover - runs on Android UI thread
                try:
                    self._fn()
                except Exception:  # noqa: BLE001
                    LOG.exception("notification Runnable raised")

        _android["CallableRunnable"] = _CallableRunnable
        _ANDROID_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001 - any failure = "Chaquopy missing pieces"
        LOG.info("Android notifications unavailable: %s", exc)


def _android_ensure_channel() -> None:
    """Create the default notification channel (idempotent, API 26+ only)."""
    if _android.get("_channel_created"):
        return
    if _android["Build$VERSION"].SDK_INT >= 26:
        # IMPORTANCE_DEFAULT = 3 (NotificationManager constant).
        IMPORTANCE_DEFAULT = 3
        channel = _android["NotificationChannel"](
            _ANDROID_CHANNEL_ID, _ANDROID_CHANNEL_NAME, IMPORTANCE_DEFAULT
        )
        # Context.NOTIFICATION_SERVICE is the literal string "notification".
        # Using the literal avoids depending on static-field-via-instance
        # resolution which Chaquopy doesn't always support cleanly.
        manager = _android["context"].getSystemService("notification")
        manager.createNotificationChannel(channel)
    _android["_channel_created"] = True


def _android_request_permission() -> None:
    """On API 33+ (POST_NOTIFICATIONS runtime permission), Android requires
    an explicit user prompt. Pre-33 the permission is granted at install
    time (manifest only).

    Briefcase's generated AndroidManifest.xml does NOT include
    POST_NOTIFICATIONS by default; the consumer needs to add it via
    ``[tool.briefcase.app.<name>.android].permission`` in pyproject.toml.
    Without the manifest permission the runtime request is a no-op.

    This implementation ensures the channel exists and logs the API level —
    actually triggering the permission dialog (via
    ``ActivityCompat.requestPermissions``) would require routing the
    activity-result callback back, which Chaquopy can do but is
    consumer-specific. Doc'd as a known gap.
    """
    _android_ensure_channel()
    api = _android["Build$VERSION"].SDK_INT
    LOG.info(
        "Android API %d: notification permission %s",
        api,
        "is runtime-prompted (need POST_NOTIFICATIONS in manifest + ActivityCompat call)"
        if api >= 33
        else "is install-time (no runtime prompt needed)",
    )


def _android_schedule_local(
    *, title: str, body: str, delay_seconds: float, identifier: str | None
) -> bool:
    global _android_next_id
    _android_ensure_channel()

    ident = identifier or f"notification-{_android_next_id}"
    notification_id = _android_id_map.get(ident)
    if notification_id is None:
        notification_id = _android_next_id
        _android_next_id += 1
        _android_id_map[ident] = notification_id

    builder = _android["NotificationCompat$Builder"](_android["context"], _ANDROID_CHANNEL_ID)
    builder.setContentTitle(title)
    builder.setContentText(body)
    # Smallest required field — without a small icon, NotificationManager
    # silently drops the notification. ic_dialog_info is a stock framework
    # drawable available on every Android version.
    builder.setSmallIcon(_android["R$drawable"].ic_dialog_info)
    builder.setAutoCancel(True)
    notification = builder.build()
    manager = _android["NotificationManagerCompat"].from_(_android["context"])

    def _fire() -> None:  # pragma: no cover - runs on Android UI thread
        try:
            manager.notify(notification_id, notification)
            LOG.info("Android fired notification %r (id=%d)", ident, notification_id)
        except Exception:  # noqa: BLE001
            LOG.exception("Android notify failed")

    delay_ms = int(max(0, delay_seconds) * 1000)
    if delay_ms == 0:
        _fire()
    else:
        handler = _android["Handler"](_android["Looper"].getMainLooper())
        # postDelayed wants a java.lang.Runnable; wrap the Python callable
        # via Chaquopy's dynamic_proxy (see _CallableRunnable above).
        handler.postDelayed(_android["CallableRunnable"](_fire), delay_ms)
        LOG.info(
            "Android scheduled notification %r (id=%d) to fire in %ss",
            ident,
            notification_id,
            delay_seconds,
        )
    return True


def _android_cancel_local(identifier: str) -> None:
    notification_id = _android_id_map.get(identifier)
    if notification_id is None:
        LOG.info("Android cancel: no known notification with identifier %r", identifier)
        return
    manager = _android["NotificationManagerCompat"].from_(_android["context"])
    manager.cancel(notification_id)
    LOG.info("Android cancelled notification %r (id=%d)", identifier, notification_id)


# ----------------------------------------------------------------------------
# Public API — platform-dispatching wrappers
# ----------------------------------------------------------------------------


def is_available() -> bool:
    """True when running on a platform with a real notifications backend."""
    return _IOS_AVAILABLE or _ANDROID_AVAILABLE


def request_permission() -> None:
    """Ask the OS for permission to show notifications.

    iOS: one-time async prompt via UNUserNotificationCenter. The result
    arrives on a callback thread and is logged.

    Android: ensures the default notification channel exists (API 26+);
    logs guidance about manifest POST_NOTIFICATIONS for API 33+ (where the
    runtime permission dialog itself needs to be triggered by the
    consumer — see :func:`_android_request_permission` docstring).

    Desktop / other: logged no-op.
    """
    try:
        if _IOS_AVAILABLE:
            _ios_request_permission()
        elif _ANDROID_AVAILABLE:
            _android_request_permission()
        else:
            LOG.info("request_permission: no notifications backend on this platform")
    except Exception:  # noqa: BLE001 - must never crash the app
        LOG.exception("request_permission failed")


def schedule_local(
    *,
    title: str,
    body: str,
    delay_seconds: float,
    identifier: str | None = None,
) -> bool:
    """Schedule a local notification to fire after ``delay_seconds``.

    Returns True if the request was handed to the OS / scheduled. Returns
    False when no notifications backend is available.

    ``identifier`` is used to cancel the notification later (see
    :func:`cancel_local`). If omitted, a default identifier is generated.

    The notification appears as a banner when the app is backgrounded —
    that's the typical use case. On Android, see the module docstring for
    background-survival caveats (Handler.postDelayed-based delay vs
    AlarmManager).
    """
    try:
        if _IOS_AVAILABLE:
            return _ios_schedule_local(
                title=title, body=body, delay_seconds=delay_seconds, identifier=identifier
            )
        if _ANDROID_AVAILABLE:
            return _android_schedule_local(
                title=title, body=body, delay_seconds=delay_seconds, identifier=identifier
            )
        LOG.info(
            "schedule_local: no backend — would show %r in %ss (identifier=%r)",
            title,
            delay_seconds,
            identifier,
        )
        return False
    except Exception:  # noqa: BLE001 - must never crash the app
        LOG.exception("schedule_local failed")
        return False


def cancel_local(identifier: str) -> None:
    """Cancel a previously-scheduled local notification by identifier."""
    try:
        if _IOS_AVAILABLE:
            _ios_cancel_local(identifier)
        elif _ANDROID_AVAILABLE:
            _android_cancel_local(identifier)
        else:
            LOG.info("cancel_local: no backend (identifier=%r)", identifier)
    except Exception:  # noqa: BLE001
        LOG.exception("cancel_local failed")
