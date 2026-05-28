"""Apple Wallet (.pkpass) integration for djust mobile apps.

WKWebView silently drops ``application/vnd.apple.pkpass`` responses
(mobile Safari special-cases the MIME via a private system path; embedded
third-party WKWebViews don't). The fix is to handle pkpass URLs from
the host app side: download the bytes via NSURLSession / NSData, build a
``PKPass``, and present ``PKAddPassesViewController`` modally.

This module wraps the generic ``djust_mobile_toga.bridge`` to register
a handler named ``"addToWallet"``. Pair it with the
``{% wallet_add_button %}`` template tag (in
``djust_mobile_toga.templatetags.djust_mobile_toga``) for a ready-made
"Add to Apple Wallet" button on the in-page side.

The pass-signing pipeline (building the ``.pkpass`` itself — pass.json,
manifest, icons, CMS signature) is out of scope here; the consuming
app is expected to produce a ``.pkpass`` served by their backend at
some URL. The bridge does the runtime install.

Usage::

    # In your BaseDjustApp subclass:
    def on_app_ready(self):
        if sys.platform == "ios":
            self.loop.call_soon_threadsafe(enable_apple_wallet, self)

    # In the template:
    {% load djust_mobile_toga %}
    {% wallet_add_button '/card/wallet.pkpass' %}

No-op on Android (no equivalent Wallet API in the same shape; Google
Wallet uses a different model based on JWT-signed save links).
"""

from __future__ import annotations

import ctypes
import sys
import traceback

from djust_mobile_toga.bridge import register_script_handler

_IS_IOS = sys.platform == "ios"

# Default handler name. Consumers shouldn't need to change this — the
# matching template tag emits a JS bridge that posts to the same name.
HANDLER_NAME = "addToWallet"


def enable_apple_wallet(app, handler_name: str = HANDLER_NAME) -> None:
    """Register the Apple Wallet script-message handler on ``app``'s WebView.

    JavaScript calls
    ``window.webkit.messageHandlers.<handler_name>.postMessage(url)``
    where ``url`` is the .pkpass URL; this handler downloads it and
    presents the system Add-to-Wallet sheet.

    Must be invoked on the main thread. From ``on_app_ready()`` (which
    runs on the loader background thread), marshal via
    ``self.loop.call_soon_threadsafe(enable_apple_wallet, self)``.

    No-op on Android and desktop.
    """
    if not _IS_IOS:
        return

    # PassKit isn't linked into Briefcase iOS scaffolds by default —
    # the scaffold auto-links only what Toga itself needs. dlopen it so
    # the PK* Obj-C class symbols are visible to rubicon's ObjCClass
    # lookups. No entitlement required (entitlements only gate
    # iCloud-synced pass storage).
    try:
        ctypes.CDLL(
            "/System/Library/Frameworks/PassKit.framework/PassKit",
            mode=ctypes.RTLD_GLOBAL,
        )
    except OSError:
        print(
            "[djust_mobile_toga.passkit] could not dlopen PassKit — "
            "Add-to-Wallet handler not installed",
            flush=True,
        )
        return

    register_script_handler(app, handler_name, _present_pass_from_url)


def _present_pass_from_url(_app, url_str: str | None) -> None:
    """Handler callback: download URL, build PKPass, present
    PKAddPassesViewController.

    Runs on the main thread (the bridge marshals every callback there).
    """
    if not url_str:
        return
    try:
        from rubicon.objc import ObjCClass

        PKPass = ObjCClass("PKPass")
        PKAddPassesViewController = ObjCClass("PKAddPassesViewController")
        NSData = ObjCClass("NSData")
        NSURL = ObjCClass("NSURL")
        UIApplication = ObjCClass("UIApplication")

        nsurl = NSURL.URLWithString_(url_str)
        data = NSData.dataWithContentsOfURL_(nsurl)
        if not data:
            print(
                f"[djust_mobile_toga.passkit] could not read data from {url_str}",
                flush=True,
            )
            return

        pkpass = PKPass.alloc().initWithData_error_(data, None)
        if not pkpass:
            print(
                "[djust_mobile_toga.passkit] PKPass init returned nil "
                "— probably an invalid / unsigned / wrong-cert pkpass",
                flush=True,
            )
            return

        add_vc = PKAddPassesViewController.alloc().initWithPass_(pkpass)
        if not add_vc:
            print(
                "[djust_mobile_toga.passkit] PKAddPassesViewController "
                "init returned nil",
                flush=True,
            )
            return

        # Present from the topmost view controller. Walking
        # presentedViewController handles the case where something
        # else is already modal.
        ui_app = UIApplication.sharedApplication
        root = ui_app.keyWindow.rootViewController
        while root.presentedViewController is not None:
            root = root.presentedViewController
        root.presentViewController_animated_completion_(add_vc, True, None)
        print(
            f"[djust_mobile_toga.passkit] presented Add-to-Wallet sheet "
            f"for {url_str}",
            flush=True,
        )
    except Exception:
        print(
            "[djust_mobile_toga.passkit] handler raised:", flush=True
        )
        traceback.print_exc()
