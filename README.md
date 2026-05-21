# djust-mobile-toga

Embed djust as an on-device loopback server inside a Toga + Briefcase mobile
app — the pattern used by [max-companion](../djust-mobile-poc) for both iOS
and Android.

This package gives you three pieces:

| Module                          | What it does                                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `djust_mobile_toga.shims`       | Cross-platform compatibility shims (must run BEFORE importing uvicorn/Django).                                |
| `djust_mobile_toga.serve`       | Loopback-bound uvicorn helper that bypasses `uvicorn.supervisors` (iOS Python lacks `_multiprocessing`).      |
| `djust_mobile_toga.app`         | `BaseDjustApp(toga.App)` — handles writable data dir, background-thread Django prep, uvicorn boot, WebView.   |

## Status

Alpha. Driven by the needs of [max-companion](../djust-mobile-poc). API may
churn until a second consumer surfaces.

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
   mobile wheels; see max-companion's `scratch/build_djust_ios.sh` and
   `scratch/build_djust_android.sh` for the recipe (maturin for iOS,
   cibuildwheel for Android).

2. **Repackaging non-mobile native deps** — `msgpack` ships a pure-Python
   fallback that needs to be re-tagged with iOS/Android platform tags so
   pip will install it under `--platform`. See max-companion's
   `scratch/build_wheelhouse.py`.

3. **Briefcase scaffold patches** — at least on Android, the generated
   `pip-options.txt` needs an absolute path for `--find-links wheels` and
   the theme `colorPrimaryDark` needs to match `status_bar_color_argb`.
   See max-companion's `scratch/patch_android_scaffold.sh`.

4. **Settings module that respects `DJUST_MOBILE_DATA_DIR`** — your
   Django `settings.py` reads this env var (set by `BaseDjustApp` at
   startup) to place SQLite + collected static files somewhere writable.

The max-companion project is the reference consumer for all four.

## License

MIT.
