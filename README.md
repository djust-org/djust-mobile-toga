# djust-mobile-toga

Embed djust as an on-device loopback server inside a Toga + Briefcase mobile
app. Extracted from a working reference app that runs the same Django +
djust codebase on iOS Simulator and Android emulator with no remote backend.

The core three pieces:

| Module                          | What it does                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `djust_mobile_toga.shims`       | Cross-platform compatibility shims (must run BEFORE importing uvicorn/Django).                                |
| `djust_mobile_toga.serve`       | Loopback-bound uvicorn helper that bypasses `uvicorn.supervisors` (iOS Python lacks `_multiprocessing`).      |
| `djust_mobile_toga.app`         | `BaseDjustApp(toga.App)` — handles writable data dir, background-thread Django prep, uvicorn boot, WebView.   |

…plus optional, fail-soft native bridges — `bridge` (JS↔Python), `passkit`
(Apple Wallet), `voice` (on-device STT/TTS), `apple_intelligence` (Foundation
Models), `notifications`. See **[docs/native-bridges.md](docs/native-bridges.md)**.

## Status

**Beta.** Typed (`py.typed`), CI-gated (ruff + mypy + pytest on py3.11–3.13),
and tested — the core (`serve`/`shims`/`apps`/`templatetags`/`bridge`) is at
~100% off-device coverage; the iOS/Android native bodies are hand-verified on a
device (see [docs/platform-support.md](docs/platform-support.md)). The public
API is stabilizing but may still evolve before a 1.0; pin a version.

## Documentation

- **[Getting started](docs/getting-started.md)** — the consuming-app shape, Django settings, building with Briefcase.
- **[Native bridges](docs/native-bridges.md)** — speech / wallet / Apple Intelligence / notifications + their `Info.plist` keys and Swift shims.
- **[Platform support](docs/platform-support.md)** — the capability matrix + the fail-soft contract.
- **[Contributing](CONTRIBUTING.md)** · **[Releasing](RELEASING.md)**

## Quick start

```python
# myapp/__main__.py
from djust_mobile_toga.app import BaseDjustApp


class MyApp(BaseDjustApp):
    asgi_app_path = "myapp.asgi:application"
    django_settings_module = "myapp.settings"
    status_bar_color_argb = 0xFF14457E  # opaque blue; remove for system default

    def on_app_ready(self):
        # Optional post-launch hook (notifications, analytics, etc.).
        pass


def main():
    return MyApp(
        formal_name="My App",
        app_id="org.example.myapp",
        app_name="myapp",
    )


if __name__ == "__main__":
    main().main_loop()
```

Then in your Toga app entry point (`__main__.py` for Briefcase), make sure
the shims install BEFORE anything else imports uvicorn/Django:

```python
from djust_mobile_toga import shims
shims.install()                   # CALL FIRST

from myapp.app import main
main().main_loop()
```

## What's still on you (the consumer)

This package handles the runtime glue. The consumer is responsible for:

1. **Cross-compiling djust** for iOS (`aarch64-apple-ios`,
   `aarch64-apple-ios-sim`) and/or Android (`aarch64-linux-android`,
   `x86_64-linux-android`). djust itself doesn't currently publish
   mobile wheels; the reference recipe is `maturin` + a BeeWare
   cross-platform venv for iOS, and `cibuildwheel --platform android`
   for Android (which manages the NDK download itself).

2. **Repackaging non-mobile native deps** — `msgpack` ships a pure-Python
   fallback that needs to be re-tagged with iOS/Android platform tags so
   pip will install it under `--platform`. A small script that walks an
   installed package's `__init__.py`, strips compiled `.so` files, and
   emits a `py3-none-ios_..._iphoneos.whl` / `…_android_21_arm64_v8a.whl`
   is enough.

3. **Briefcase scaffold patches** — at least on Android, the generated
   `pip-options.txt` needs an absolute path for `--find-links wheels` and
   the theme `colorPrimaryDark` in `res/values/colors.xml` needs to match
   `status_bar_color_argb` (the activity theme paints the status bar
   before any runtime `setStatusBarColor` call lands).

4. **POST_NOTIFICATIONS permission on Android 13+** if using
   `djust_mobile_toga.notifications` — declare it in your Briefcase
   `[tool.briefcase.app.<name>.android]` block as
   `permission."android.permission.POST_NOTIFICATIONS" = "..."`. Without
   it the system silently drops notifications.

5. **Settings module that respects `DJUST_MOBILE_DATA_DIR`** — your
   Django `settings.py` reads this env var (set by `BaseDjustApp` at
   startup) to place SQLite + collected static files somewhere writable.

## License

MIT.
