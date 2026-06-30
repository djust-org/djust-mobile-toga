"""Template tags for djust_mobile_toga.

Load in your templates with::

    {% load djust_mobile_toga %}

Then::

    {% wallet_add_button '/card/wallet.pkpass' %}

Note for djust consumers: djust's Rust template engine doesn't process
Django custom template tags. If your view template is rendered by
djust (the LiveView mixin), use the equivalent plain-Python helper
:func:`djust_mobile_toga.passkit.render_wallet_button_html` from your
view and pass the result as a context variable. The tag below is for
vanilla Django consumers that use Django's standard template engine.
"""

from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

from djust_mobile_toga.passkit import render_wallet_button_html

register = template.Library()


@register.simple_tag
def wallet_add_button(
    url: str,
    css_class: str = "wallet-add-button",
    aria_label: str = "Add to Apple Wallet",
) -> str:
    """Vanilla-Django shim — calls ``render_wallet_button_html``."""
    return mark_safe(render_wallet_button_html(url, css_class=css_class, aria_label=aria_label))
