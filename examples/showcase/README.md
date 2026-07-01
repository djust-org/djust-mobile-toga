# djust Showcase — every native bridge, one tab each

A tour of all five [`djust-mobile-toga`](../../README.md) native bridges in a
single djust app. Each tab drives one bridge; every bridge is **fail-soft**, so
the app runs and degrades gracefully on desktop — the real native behaviour
fires on an iOS device/simulator.

| Tab | Bridge | Platform | On desktop |
|---|---|---|---|
| **Voice** | `voice` — SFSpeechRecognizer STT + AVSpeechSynthesizer TTS | iOS | badges show "off"; actions are no-ops |
| **AI** | `apple_intelligence.ask()` — on-device Foundation Models | iOS 26+ ¹ | returns a fallback message |
| **Wallet** | `passkit` — Add-to-Apple-Wallet button + install handler | iOS | button renders; tap does nothing |
| **Notify** | `notifications` — schedule/cancel local notifications | iOS + **Android** | logged no-op |
| **JS Bridge** | `bridge` — in-page JS → Python → back into the page | iOS | shows "iOS-only" message |

¹ Apple Intelligence also needs a small Swift `@objc` shim compiled into the iOS
binary (see [../../docs/native-bridges.md](../../docs/native-bridges.md)); without
it, the AI tab shows its fallback.

## What's where

```
src/showcase/
  app.py          ShowcaseApp(BaseDjustApp) — wires the two INBOUND bridges
                  (Apple Wallet install + JS message handler) on the main thread
  views.py        ShowcaseView — one event handler per bridge action, all fail-soft
  templates/showcase.html   the tabbed UI (bridge JS lives OUTSIDE dj-root)
  asgi.py · settings.py · urls.py · routing.py
pyproject.toml    Briefcase config (desktop + iOS + Android, incl. mic Info.plist keys)
```

Two directions of bridge are shown:

- **Python → native** (Voice, AI, Wallet-button, Notify): a `dj-click` event runs
  a `ShowcaseView` handler that calls the bridge.
- **Native → Python** (JS Bridge, Wallet-install): the OS or in-page JS calls into
  Python. These are registered on the app in `on_app_ready` and answer back into
  the page via `webview.evaluate_javascript`.

## Run it on the web (fastest — no GUI)

The UI + every fail-soft branch runs as a plain web server:

```bash
cd examples/showcase
python -m venv .venv && source .venv/bin/activate
pip install djust djust-mobile-toga uvicorn wsproto
PYTHONPATH=src python -m django migrate --settings showcase.settings
PYTHONPATH=src python -m uvicorn showcase.asgi:application --port 8000
# open http://127.0.0.1:8000  — tabs switch, actions show their off-platform state
```

## Run it as a desktop window

```bash
pip install briefcase djust
cd examples/showcase
briefcase dev
```

## Build for mobile

```bash
briefcase create iOS && briefcase build iOS && briefcase run iOS      # or: android
```

**You must supply a cross-compiled `djust`** (its Rust extension isn't on PyPI for
mobile) — add the wheel to the per-platform `requires` in `pyproject.toml` (marked
spots in the `.iOS` / `.android` tables). For the Voice tab, the mic/speech
`Info.plist` strings are already in `pyproject.toml`. For the AI tab, add the Swift
shim from [../../docs/native-bridges.md](../../docs/native-bridges.md). See also
[getting-started](../../docs/getting-started.md) and
[platform-support](../../docs/platform-support.md).

## Start smaller

If this is your first look, [`../counter`](../counter) is the minimal "hello
world" — one reactive counter, no native bridges.
