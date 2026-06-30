# djust-mobile-toga

[![PyPI](https://img.shields.io/pypi/v/djust-mobile-toga.svg)](https://pypi.org/project/djust-mobile-toga/)
[![Python](https://img.shields.io/pypi/pyversions/djust-mobile-toga.svg)](https://pypi.org/project/djust-mobile-toga/)
[![CI](https://github.com/djust-org/djust-mobile-toga/actions/workflows/ci.yml/badge.svg)](https://github.com/djust-org/djust-mobile-toga/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Ship your Django + [djust](https://github.com/djust-org/djust) app as a native
iOS / Android app that runs entirely on the device — no backend server.**

`djust-mobile-toga` runs your existing Django codebase as an on-device loopback
server inside a [Toga](https://toga.readthedocs.io/) +
[Briefcase](https://briefcase.readthedocs.io/) shell and points a native WebView
at it. The same code that serves your website serves the phone: offline, private
(the SQLite database stays in the app's sandbox), and reactive through djust's
LiveView-style server rendering over a local WebSocket. No REST API to build, no
servers to run.

## How it works

When the app launches, `BaseDjustApp` starts a single-worker `uvicorn` bound to
`127.0.0.1` serving your Django + djust ASGI app, then opens a native WebView
pointed at that loopback URL:

```
+-------------------------- phone ---------------------------+
|                                                            |
|  +------------+   http://127.0.0.1:<port>                  |
|  |  WebView   | ----- HTTP / WebSocket ------+             |
|  | (your UI)  | <---- HTML / WS frames ---+  |             |
|  +-----+------+                           |  v             |
|        | JS <-> Python bridges       +----+-----------+    |
|        v                             | uvicorn        |    |
|  wallet / voice / AI / notifs        | loopback,1 wkr |    |
|                                      +-------+--------+    |
|                                              v             |
|                                      +----------------+    |
|                                      | Django + djust |    |
|                                      | ASGI / SQLite  |    |
|                                      +----------------+    |
|                                                            |
|            No network.   No remote backend.                |
+------------------------------------------------------------+
```

It handles the parts that make "run Django on a phone" hard: the stdlib gaps
uvicorn + Django hit at import time on mobile (`_multiprocessing`, `mimetypes`),
a WebSocket implementation iOS can actually run (`wsproto`), a writable per-platform
data directory, off-the-UI-thread `migrate` + `collectstatic`, and status-bar
tinting. Optional native bridges let in-page JavaScript reach device capabilities.

## What you get

The core shell — three modules:

| Module | Role |
|---|---|
| `app` | `BaseDjustApp(toga.App)` — data dir, Django prep, uvicorn boot, WebView, status bar. **Your entry point.** |
| `serve` | Loopback uvicorn helper (bypasses `uvicorn.supervisors`; single worker; `ws=wsproto`). |
| `shims` | The `_multiprocessing` / `mimetypes` compatibility patches uvicorn + Django need on iOS/Android. **Install first.** |

Plus optional, **fail-soft** native bridges — off their target platform (or when
the native shim isn't compiled in) they report unavailable and no-op, so you can
call them unconditionally and they never raise:

| Bridge | Capability | Platform |
|---|---|---|
| `bridge` | JavaScript ↔ Python calls (the mechanism the others build on) | iOS |
| `passkit` | Add-to-Apple-Wallet (`.pkpass`) + a `{% wallet_add_button %}` tag | iOS |
| `voice` | On-device speech-to-text + text-to-speech | iOS |
| `apple_intelligence` | On-device Foundation Models Q&A | iOS 26+ |
| `notifications` | Local notifications | iOS · Android |

→ [Native bridges guide](docs/native-bridges.md) · [Platform matrix](docs/platform-support.md)

## Install

```bash
pip install djust-mobile-toga
```

> `djust` itself is **not** a hard dependency — install it separately. The mobile
> build needs platform-specific cross-compiled wheels that aren't on PyPI, so we
> don't make pip try to resolve `djust` from an index it can't find.

## Quick start

Your app subclasses `BaseDjustApp` and points it at your ASGI app + settings:

```python
# myapp/app.py
from djust_mobile_toga.app import BaseDjustApp


class MyApp(BaseDjustApp):
    asgi_app_path = "myapp.asgi:application"
    django_settings_module = "myapp.settings"
    status_bar_color_argb = 0xFF14457E  # opaque blue; omit for the system default

    def on_app_ready(self) -> None:
        # Optional post-launch hook (notifications, analytics, …).
        pass


def main() -> MyApp:
    return MyApp(formal_name="My App", app_id="org.example.myapp", app_name="myapp")
```

In the Briefcase entry point, install the shims **before anything imports
uvicorn/Django**, then launch:

```python
# myapp/__main__.py
from djust_mobile_toga import shims

shims.install()  # CALL FIRST

from myapp.app import main

main().main_loop()
```

Your `settings.py` reads `DJUST_MOBILE_DATA_DIR` (set by `BaseDjustApp` at
startup) for `DATABASES` / `MEDIA_ROOT`, and otherwise it's an ordinary Django +
djust app.

→ [Full getting-started guide](docs/getting-started.md)

## What's still on you (the consumer)

This package is the **Python runtime glue**. The native build is yours:

1. **Cross-compile djust** for iOS (`aarch64-apple-ios`, `aarch64-apple-ios-sim`)
   and/or Android (`aarch64-linux-android`, `x86_64-linux-android`). djust doesn't
   currently publish mobile wheels; the reference recipe is `maturin` + a BeeWare
   cross-platform venv for iOS, and `cibuildwheel --platform android` for Android.

2. **Repackage non-mobile native deps** — e.g. `msgpack`'s pure-Python fallback
   needs re-tagging with iOS/Android platform tags so pip installs it under
   `--platform` (strip the `.so`s, emit `…_iphoneos.whl` / `…_android_21_arm64_v8a.whl`).

3. **Briefcase scaffold patches** — on Android, the generated `pip-options.txt`
   needs an absolute `--find-links wheels` path, and `res/values/colors.xml`'s
   `colorPrimaryDark` should match `status_bar_color_argb` (the activity theme
   paints the bar before any runtime call lands).

4. **`POST_NOTIFICATIONS` permission on Android 13+** if using `notifications` —
   declare it in your Briefcase `[…android]` block, or the system silently drops them.

5. **A settings module that respects `DJUST_MOBILE_DATA_DIR`** (see Quick start).

Per-feature `Info.plist` keys and the Apple Intelligence Swift shim are in the
[native bridges guide](docs/native-bridges.md).

## Status

**Beta.** Typed (`py.typed`), CI-gated (ruff + mypy + pytest on Python 3.11–3.13),
and tested — the core (`serve` / `shims` / `apps` / `templatetags` / `bridge`) is
at ~100% off-device coverage; the iOS/Android native bodies are hand-verified on
a device. The public API is stabilizing but may still evolve before 1.0 — pin a
version.

## Documentation

- **[Getting started](docs/getting-started.md)** — consuming-app shape, Django settings, building with Briefcase.
- **[Native bridges](docs/native-bridges.md)** — speech / wallet / Apple Intelligence / notifications, with `Info.plist` keys and Swift shims.
- **[Platform support](docs/platform-support.md)** — capability matrix + the fail-soft contract.
- **[Contributing](CONTRIBUTING.md)** · **[Releasing](RELEASING.md)**

## License

MIT — see [LICENSE](LICENSE).
