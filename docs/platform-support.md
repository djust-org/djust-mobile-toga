# Platform support

The **core** (loopback server + Toga WebView shell) targets iOS and Android via
Briefcase; it also imports and runs on desktop for development. The **native
bridges** resolve only on their target platform and fail-soft everywhere else.

## Capability matrix

| Capability | iOS | Android | Desktop | Notes |
|---|:---:|:---:|:---:|---|
| Loopback server + WebView (`app`, `serve`, `shims`) | ✅ | ✅ | ✅ (dev) | The shims patch iOS/Android stdlib gaps; no-ops elsewhere |
| JS↔Python bridge (`bridge`) | ✅ | ⛔ | ⛔ | Android `addJavascriptInterface` is future work |
| Apple Wallet (`passkit`) | ✅ | ⛔ | ⛔ | `render_wallet_button_html` (HTML) works anywhere |
| Speech STT/TTS (`voice`) | ✅ | ⛔ | ⛔ | On-device only; needs the `Info.plist` keys |
| Apple Intelligence (`apple_intelligence`) | ✅ iOS 26+ ¹ | ⛔ | ⛔ | Needs the Swift `@objc` shim compiled in |
| Local notifications (`notifications`) | ✅ | ✅ | ⛔ | Logged no-op on desktop |

✅ = resolves · ⛔ = fail-soft (available-check `False`, actions are no-ops)

¹ Also requires the device to have Apple Intelligence enabled and the Swift
shim present; otherwise fail-soft.

## The fail-soft contract

Off-target-platform, every bridge's availability check returns `False` and its
action methods log a no-op and return `False`/`None` — they **never raise**.
This is a hard guarantee (enforced by the test suite's fail-soft tests), so
consuming apps can call the bridges unconditionally and branch on the result:

```python
if voice.tts_available():
    voice.speak(answer)
else:
    show_text(answer)   # desktop / Android / older iOS
```

## Python versions

3.11, 3.12, 3.13 (tested in CI).

## What's verified where

- **CI (Linux):** the fail-soft guard paths + all pure logic (port selection,
  uvicorn config, the `_multiprocessing` shim, wallet-button HTML, the template
  tag) — 100% on `serve`/`apps`/`templatetags`/`bridge`, ~98% on `shims`.
- **Device-only (hand-verified):** the iOS/Android native bodies — the actual
  `SFSpeechRecognizer`/PassKit/Foundation-Models/`UNUserNotificationCenter`
  calls. These can't run on a Linux CI runner; they're exercised on a real
  device/simulator and called out as device-only in the tests.
