# Contributing to djust-mobile-toga

Thanks for helping! This is a small, focused library — embed djust as an
on-device loopback server inside a Toga + Briefcase mobile app. Contributions
that keep it small, well-typed, and fail-soft are very welcome.

## Dev setup

The project uses [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/djust-org/djust-mobile-toga
cd djust-mobile-toga
uv venv
uv pip install -e ".[dev]"
```

## The checks CI runs (run them before opening a PR)

```bash
uv run ruff check src tests        # lint
uv run ruff format --check src tests  # format (run `ruff format` to fix)
uv run mypy                        # type-check
uv run pytest -q                   # tests
uv build && uv run --with twine twine check dist/*   # packaging
```

CI (`.github/workflows/ci.yml`) runs all of these on py3.11–3.13 for every
push and PR. Keep them green.

## Conventions

- **Conventional commits**: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
- **Type hints on all public API.** The package ships `py.typed`; downstream
  apps type-check against us. `mypy` must stay clean.
- **Fail-soft is the contract.** Every public function that touches a platform
  capability (speech, wallet, notifications, the JS bridge, Apple Intelligence)
  must **never raise** off its target platform — it returns `False`/`None` or
  logs a no-op. Desktop, Android, older iOS, and "the native shim isn't
  compiled in" all degrade gracefully. New platform code must keep this.
- **Guard platform imports.** `rubicon-objc` (iOS) and Chaquopy's `java`
  (Android) are imported lazily *inside* the on-device code paths, never at
  module top level — that's why the package imports + tests on plain Linux.

## Testing the native bridges

The iOS/Android bridge bodies (`SFSpeechRecognizer`, PassKit, Foundation
Models, `UNUserNotificationCenter`, `WKScriptMessageHandler`, …) can only be
*fully* verified on a real device/simulator — those paths are hand-verified
and called out as device-only in the tests. What the test suite covers on CI:

- the **fail-soft guard paths** (off-platform → unavailable, never raises), and
- the **pure logic** (port selection, the uvicorn config, the `_multiprocessing`
  shim, the wallet-button HTML, the template tag) at full coverage.

When adding a bridge, add the off-platform fail-soft tests at minimum; mock the
`rubicon`/`java` surface for a wiring-contract test where it can be done without
brittle deep mocks (see `tests/test_bridge.py` for the pattern).

## Releasing

See [RELEASING.md](RELEASING.md) — versions are single-sourced from
`__version__`, and a `vX.Y.Z` tag publishes to PyPI via Trusted Publishing.
