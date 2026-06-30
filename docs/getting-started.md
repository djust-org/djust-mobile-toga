# Getting started

`djust-mobile-toga` runs your Django + djust app as an **on-device loopback
server** inside a [Toga](https://toga.readthedocs.io/) +
[Briefcase](https://briefcase.readthedocs.io/) shell, with a `WebView` pointed
at `http://127.0.0.1:<port>`. No remote backend — the same Django codebase runs
on the iOS Simulator and Android emulator.

## Install

```bash
pip install djust-mobile-toga
```

`djust` itself is **not** a hard dependency — install it separately. The mobile
build needs platform-specific cross-compiled wheels that aren't on PyPI, so we
don't make pip try to resolve `djust` from an index it can't find.

## The shape of a consuming app

A Briefcase app whose `__main__` subclasses `BaseDjustApp`:

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
    return MyApp(formal_name="My App", app_id="org.example.myapp")
```

`BaseDjustApp` handles, in order:

1. **Shims first.** `djust_mobile_toga.shims.install()` patches the
   `_multiprocessing` / `mimetypes` gaps that uvicorn + Django read at import
   time on iOS. This must run *before* uvicorn/Django import — the base class
   does it for you.
2. **A writable data dir** for the SQLite DB / media (iOS app sandbox, Android
   app storage), exported via an env var your `settings.py` reads.
3. **Background-thread Django prep** — `migrate` + `collectstatic` off the UI
   thread so the splash isn't blocked.
4. **The loopback server** — a single-worker uvicorn (via
   `djust_mobile_toga.serve`) bound to `127.0.0.1`, using `ws="wsproto"` (pure
   Python) since uvicorn-core ships no WebSocket implementation and iOS lacks
   the C ones.
5. **The WebView**, pointed at the loopback root (override `start_path` to land
   elsewhere), with iOS/Android status-bar tinting.

## Django settings notes

- Your `settings.py` should read the writable data dir from the env var
  (`data_dir_env_var`, default documented on `BaseDjustApp`) for `DATABASES`
  and `MEDIA_ROOT`.
- Add `"djust_mobile_toga"` to `INSTALLED_APPS` **only if** you use the Apple
  Wallet template tag (it loads the `{% wallet_add_button %}` library).
- Use djust as usual (`channels`, the ASGI app) — the loopback server speaks
  HTTP + WebSocket exactly like a normal deployment.

## Building with Briefcase

This package is the Python side. The native build (signing, `Info.plist`
permission strings, optional Swift shims) lives in your app's
`pyproject.toml` Briefcase tables. See [native-bridges.md](native-bridges.md)
for the per-feature `Info.plist` keys and the Apple Intelligence Swift shim,
and [platform-support.md](platform-support.md) for the capability matrix.
