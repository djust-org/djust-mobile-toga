"""Apple Wallet (.pkpass) integration for djust mobile apps.

Public API:

* :func:`enable_apple_wallet` — call once at app startup to register the
  WKScriptMessageHandler.
* :func:`render_wallet_button_html` — plain Python helper returning the
  button HTML, so views can pass it as a context variable. djust's Rust
  template engine doesn't know about custom Django template tags, so
  consumers on djust render the button from their view rather than via
  the ``{% wallet_add_button %}`` tag (which still works for vanilla
  Django consumers using the standard template engine).

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
import html as _html_lib
import sys
import traceback

from djust_mobile_toga.bridge import register_script_handler

_IS_IOS = sys.platform == "ios"

# Default handler name. Consumers shouldn't need to change this — the
# matching template tag emits a JS bridge that posts to the same name.
HANDLER_NAME = "addToWallet"


# Apple's mark, inline SVG. Embedded here (not as a static asset) so
# the rendered button has zero external dependencies.
_APPLE_LOGO_SVG = (
    '<svg class="wallet-add-button__logo" '
    'viewBox="0 0 20 24" aria-hidden="true">'
    '<path fill="currentColor" d="'
    "M16.4 12.7c0-2.4 1.95-3.55 2.04-3.6-1.11-1.62-2.85-1.85-3.46-1.87"
    "-1.47-.15-2.87.86-3.62.86-.76 0-1.91-.85-3.14-.83-1.62.02-3.11.94"
    "-3.95 2.39-1.68 2.92-.43 7.23 1.22 9.6.8 1.16 1.76 2.46 3 2.41"
    " 1.2-.05 1.66-.78 3.12-.78s1.87.78 3.14.75c1.3-.02 2.12-1.17 2.92"
    "-2.34.92-1.35 1.3-2.65 1.32-2.72-.03-.01-2.53-.97-2.56-3.86z"
    "M14.05 5.39c.65-.78 1.09-1.87.97-2.96-.94.04-2.07.63-2.74 1.41"
    "-.6.7-1.13 1.81-.99 2.88 1.05.08 2.11-.53 2.76-1.33z"
    '"/></svg>'
)

# Bridge JS. When the in-app WKScriptMessageHandler is registered,
# ``window.webkit.messageHandlers.addToWallet`` is defined and we route
# through it. When absent (desktop browser, mobile Safari), ``href``
# fires normally — mobile Safari handles the pkpass MIME natively, and
# desktop downloads the file.
_BRIDGE_JS = (
    "if(window.webkit&&window.webkit.messageHandlers&&"
    "window.webkit.messageHandlers.addToWallet){"
    "window.webkit.messageHandlers.addToWallet.postMessage(this.href);"
    "return false;}"
)


def render_wallet_button_html(
    url: str,
    css_class: str = "wallet-add-button",
    aria_label: str = "Add to Apple Wallet",
) -> str:
    """Render the "Add to Apple Wallet" anchor HTML.

    Plain Python — call from your view, pass the result as a template
    context variable, render with ``{{ wallet_button|safe }}``. Used by
    consumers on djust's Rust template engine (which doesn't know about
    Django custom template tags). Vanilla Django consumers can use the
    matching ``{% wallet_add_button %}`` tag instead.

    Args:
        url:        the .pkpass URL to install (serialized to ``href``).
        css_class:  outer ``<a>`` class. Defaults to
                    ``"wallet-add-button"``. Pass ``""`` to omit.
        aria_label: accessible label. Defaults to "Add to Apple Wallet".

    Returns:
        HTML string ready to inject into a template via the ``|safe``
        filter or equivalent. Output is XSS-safe — ``url`` and labels
        are HTML-escaped on output, the SVG + JS bridge are static
        literals.
    """
    safe_url = _html_lib.escape(url, quote=True)
    safe_class = _html_lib.escape(css_class, quote=True)
    safe_aria = _html_lib.escape(aria_label, quote=True)
    class_attr = f' class="{safe_class}"' if css_class else ""
    return (
        f'<a{class_attr} href="{safe_url}" '
        f'onclick="{_BRIDGE_JS}" '
        f'aria-label="{safe_aria}">'
        f"{_APPLE_LOGO_SVG}"
        f'<span class="wallet-add-button__text">'
        f'<span class="wallet-add-button__small">Add to</span>'
        f'<span class="wallet-add-button__big">Apple Wallet</span>'
        f"</span>"
        f"</a>"
    )


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
