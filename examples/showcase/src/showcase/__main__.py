"""Entry point — install the platform shims before anything imports uvicorn or
Django, then hand off to Toga's event loop. ``install()`` is idempotent and a
no-op on desktop.
"""

from djust_mobile_toga import shims

shims.install()

from showcase.app import main  # noqa: E402  (must follow shims.install)

if __name__ == "__main__":
    main().main_loop()
