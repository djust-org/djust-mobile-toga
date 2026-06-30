# Releasing djust-mobile-toga

CI (`.github/workflows/ci.yml`) lints, type-checks, tests (py3.11–3.13), and
builds on every push/PR. Releases publish to PyPI on a `vX.Y.Z` tag via
`.github/workflows/release.yml` using **PyPI Trusted Publishing** (OIDC) — no
API token is stored in the repo.

## One-time setup (PyPI side — repo owner)

PyPI Trusted Publishing has to be configured once before the first publish:

1. Create the project on PyPI (or, for the very first release, use a *pending*
   publisher so the project is created on first publish):
   PyPI → **Your projects** → *(or)* **Publishing** → **Add a pending publisher**.
2. Fill in:
   - **PyPI project name**: `djust-mobile-toga`
   - **Owner**: `djust-org`
   - **Repository name**: `djust-mobile-toga`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
3. In the GitHub repo: **Settings → Environments → New environment → `pypi`**
   (optionally add required reviewers so a publish needs manual approval).

No `PYPI_API_TOKEN` secret is needed — `release.yml` requests an OIDC token
(`permissions: id-token: write`) and `pypa/gh-action-pypi-publish` exchanges it.

## Cutting a release

Version is single-sourced from `src/djust_mobile_toga/__init__.py` (`__version__`);
`pyproject.toml` reads it dynamically (hatch), so there is nothing else to bump.

1. Bump `__version__` in `src/djust_mobile_toga/__init__.py` (e.g. `0.5.3` → `0.5.4`).
2. Update the changelog / commit: `git commit -am "Bump version to 0.5.4"`.
3. Tag and push — the tag must match `__version__` (the workflow asserts it):

   ```bash
   git tag -a v0.5.4 -m "Release v0.5.4"
   git push origin main v0.5.4
   ```

4. The `Release` workflow builds the sdist + wheel, runs `twine check`, and
   publishes to PyPI. Confirm at <https://pypi.org/project/djust-mobile-toga/>.

> The existing `v0.4.0`–`v0.5.3` tags predate this pipeline (tagged but never
> published). The first PyPI publish happens on the next tag pushed *after* the
> trusted publisher is configured.

## Local checks (what CI runs)

```bash
uv venv && uv pip install -e ".[dev]"
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest -q
uv build && uv run --with twine twine check dist/*
```
