# djust Counter — a djust-mobile-toga demo

The smallest end-to-end example of [`djust-mobile-toga`](../../README.md): one
djust `LiveView` (a counter) served by an **on-device loopback uvicorn server**
and shown in a native WebView. Tapping **+** / **−** round-trips over a loopback
WebSocket; all state lives in Python. No remote backend, no client JavaScript.

```
src/counter_demo/
  __main__.py      installs the platform shims, then starts the app
  app.py           CounterApp(BaseDjustApp) — the whole mobile shell
  asgi.py          Django ASGI app (HTTP + WebSocket via channels)
  settings.py      minimal Django settings (reads DJUST_MOBILE_DATA_DIR)
  urls.py          one route -> CounterView
  routing.py       the djust LiveView WebSocket consumer
  views.py         CounterView — mount + increment/decrement/reset
  templates/
    counter.html   the page (client.js lives OUTSIDE dj-root)
pyproject.toml     Briefcase config (desktop + iOS + Android)
```

`app.py` is the entire mobile side — everything else is an ordinary Django +
djust app:

```python
from djust_mobile_toga.app import BaseDjustApp

class CounterApp(BaseDjustApp):
    asgi_app_path = "counter_demo.asgi:application"
    django_settings_module = "counter_demo.settings"
    status_bar_color_argb = 0xFF0B1F3A
```

## Run it on the web (fastest — no GUI needed)

`asgi.py` is a standard ASGI app, so you can run the exact same code djust
serves on-device as a plain web server and open it in your browser:

```bash
cd examples/counter
python -m venv .venv && source .venv/bin/activate
pip install djust djust-mobile-toga uvicorn wsproto
PYTHONPATH=src python -m django migrate --settings counter_demo.settings
PYTHONPATH=src python -m uvicorn counter_demo.asgi:application --port 8000
# open http://127.0.0.1:8000
```

(`DJUST_MOBILE_DATA_DIR` is unset here, so the SQLite DB lands in
`src/counter_demo/`. On device, `BaseDjustApp` sets it to the app sandbox.)

## Run it as a desktop window

[Briefcase](https://briefcase.readthedocs.io/) runs the real Toga shell on your
desktop — same `WebView`, same loopback server as the phone build:

```bash
pip install briefcase djust          # djust on PyPI works for desktop
cd examples/counter
briefcase dev
```

## Build for mobile

```bash
briefcase create iOS && briefcase build iOS && briefcase run iOS      # or: android
```

**The one thing you must supply: a cross-compiled `djust`.** djust ships a Rust
extension; the iOS/Android builds need a wheel cross-compiled for that platform,
which isn't on PyPI. So `djust` is deliberately left out of `pyproject.toml`'s
`requires`. Build the wheel for your target (Python-Apple-support / Chaquopy
toolchain) and add it to the per-platform `requires` list in `pyproject.toml`
(the `[tool.briefcase.app.counter_demo.iOS]` / `.android` tables have a marked
spot). See the top-level [getting-started](../../docs/getting-started.md) and
[platform-support](../../docs/platform-support.md) docs.

## How a tap flows

1. The WebView loads `http://127.0.0.1:<port>/`; djust's `client.js` opens a
   WebSocket back to the same loopback server and mounts `CounterView`.
2. A tap on **+** fires `dj-click="increment"` → a WS frame → `CounterView.increment()`
   runs in Python, `self.count += 1`.
3. djust diffs the render and sends back just the changed `{{ count }}` — the
   WebView patches the DOM in place. State never leaves Python.
