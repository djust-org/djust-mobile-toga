# Native bridges

Optional on-device capabilities. **All are fail-soft**: off their target
platform (or when the native shim isn't compiled in) the availability check
returns `False` and the actions are logged no-ops — so your app degrades to a
text box / on-screen fallback. Import only what you use.

## JavaScript ↔ Python bridge — `bridge`

iOS-only (Android `addJavascriptInterface` is future work). Registers a
`WKScriptMessageHandler` so in-page JS can call into Python.

```python
from djust_mobile_toga import bridge

bridge.register_script_handler(app, "myChannel", lambda app, body: ...)
# JS: window.webkit.messageHandlers.myChannel.postMessage("payload")
```

This is the mechanism PassKit / vCard / `.ics` integrations build on. Multiple
handlers can be registered without name collisions.

## Apple Wallet — `passkit`

```python
from djust_mobile_toga.passkit import enable_apple_wallet
enable_apple_wallet(app)   # wires the .pkpass install handler
```

In a template (requires `"djust_mobile_toga"` in `INSTALLED_APPS`):

```django
{% load djust_mobile_toga %}
{% wallet_add_button url="/passes/membership.pkpass" %}
```

`render_wallet_button_html(url, ...)` is also callable directly if you build the
markup yourself.

## On-device speech — `voice`

`SFSpeechRecognizer` (STT, on-device only — audio never leaves the phone) +
`AVSpeechSynthesizer` (TTS). ObjC-API, so rubicon reaches them directly — no
Swift shim.

```python
from djust_mobile_toga import voice
voice.stt_available()                      # -> bool
voice.start_dictation(on_partial=cb, on_final=cb)
voice.stop_dictation()
voice.speak("Your Part B premium is …")
voice.stop_speaking()
```

**`Info.plist` (Briefcase `iOS.info`):** `NSMicrophoneUsageDescription` and
`NSSpeechRecognitionUsageDescription`.

## Apple Intelligence — `apple_intelligence`

On-device Foundation Models Q&A (iOS 26+). Foundation Models is **Swift-only**,
so rubicon can't reach it directly: your app compiles a tiny
`@objc(MaxLLMBridge)` `NSObject` Swift shim into the Briefcase binary exposing
a `BOOL available()` + completion-handler `generate(...)`. This module resolves
that shim by name.

```python
from djust_mobile_toga import apple_intelligence
apple_intelligence.is_available()                  # -> bool
apple_intelligence.ask(prompt, context=..., instructions=...)  # -> str | None
```

Returns `None` everywhere the shim/model isn't present — fall back to your own
non-AI path.

## Local notifications — `notifications`

```python
from djust_mobile_toga import notifications
notifications.is_available()
notifications.request_permission()
notifications.schedule_local(title=..., body=..., delay_seconds=..., identifier=...)
notifications.cancel_local(identifier)
```

`UNUserNotificationCenter` on iOS, `NotificationManagerCompat` (Chaquopy `java`)
on Android, logged no-op on desktop.

---

See [platform-support.md](platform-support.md) for which of these resolve on
each platform.
