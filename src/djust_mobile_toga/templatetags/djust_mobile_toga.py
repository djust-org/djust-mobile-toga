"""Template tags for djust_mobile_toga.

Load in your templates with::

    {% load djust_mobile_toga %}

Then use the tags below. Currently provides:

* ``{% wallet_add_button url %}`` — renders the "Add to Apple Wallet"
  button with the JS bridge that posts to the WKScriptMessageHandler
  registered by :func:`djust_mobile_toga.passkit.enable_apple_wallet`.

The library doesn't ship CSS — the button is class-targetable so
consumers style ``.wallet-add-button`` (and its child elements) to fit
their app. The default Apple human-interface guidance is a black pill
with white "Add to / Apple Wallet" text and the Apple logo on the
left; consumers are free to deviate, but Apple does have explicit
brand-protection rules — see
https://developer.apple.com/wallet/Add-to-Apple-Wallet-Guidelines.pdf
before doing anything other than the standard mark.
"""

from __future__ import annotations

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


# Apple's mark in inline SVG form (24x24 viewBox, single path). Embedded
# inline so the tag renders without any external asset dependency or
# extra HTTP request.
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
# `window.webkit.messageHandlers.addToWallet` is defined and we route
# through it. When absent (desktop browser, mobile Safari), `href`
# fires normally — mobile Safari handles the pkpass MIME natively, and
# desktop downloads the file.
_BRIDGE_JS = (
    "if(window.webkit&&window.webkit.messageHandlers&&"
    "window.webkit.messageHandlers.addToWallet){"
    "window.webkit.messageHandlers.addToWallet.postMessage(this.href);"
    "return false;}"
)


@register.simple_tag
def wallet_add_button(
    url: str,
    css_class: str = "wallet-add-button",
    aria_label: str = "Add to Apple Wallet",
) -> str:
    """Render an "Add to Apple Wallet" anchor with the JS bridge.

    Args:
        url:        the .pkpass URL to install (will be served as the
                    button's ``href``).
        css_class:  outer ``<a>`` class. Defaults to
                    ``"wallet-add-button"`` so consumers can target it
                    in their stylesheet. Pass ``""`` to omit the class
                    attribute entirely.
        aria_label: accessible label. Defaults to "Add to Apple Wallet".

    The button is an ``<a href="...">`` with an ``onclick`` that
    short-circuits to the WKScriptMessageHandler bridge when running
    inside a djust-mobile-toga iOS app, and falls through to a normal
    link otherwise. Mobile Safari handles the pkpass MIME natively, so
    "fallthrough" still triggers Add-to-Wallet there.

    Renders the Apple mark + "Add to / Apple Wallet" two-line text
    matching Apple's marketing-button guidelines. CSS is the consumer's
    responsibility — see the docstring on the module for the standard
    treatment.
    """
    safe_url = escape(url)
    safe_class = escape(css_class)
    safe_aria = escape(aria_label)
    class_attr = f' class="{safe_class}"' if css_class else ""
    html = (
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
    return mark_safe(html)
