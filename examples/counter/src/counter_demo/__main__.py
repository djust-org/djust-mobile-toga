"""Entry point.

``shims.install()`` MUST run before anything imports uvicorn or Django — on
iOS the ``_multiprocessing`` C extension is absent and uvicorn references it at
import time. We install the shims here, before importing the app module (which
pulls in the server stack), then hand off to Toga's event loop. ``install()``
is idempotent and a no-op on desktop.
"""

from djust_mobile_toga import shims

shims.install()

from counter_demo.app import main  # noqa: E402  (must follow shims.install)

if __name__ == "__main__":
    main().main_loop()
