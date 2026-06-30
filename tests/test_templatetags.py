"""Tests for the ``{% wallet_add_button %}`` template tag.

The tag is a thin vanilla-Django shim over
``passkit.render_wallet_button_html``. We verify both that the tag function
produces the same HTML as the helper and that it renders through Django's real
template engine (a configured Django is provided by ``conftest.py``).
"""

from __future__ import annotations

from django.template import Context, Template
from django.utils.safestring import SafeString

from djust_mobile_toga.passkit import render_wallet_button_html
from djust_mobile_toga.templatetags.djust_mobile_toga import wallet_add_button


def test_tag_fn_matches_helper():
    # The tag delegates to the helper; output must be identical.
    url = "/card/wallet.pkpass"
    assert str(wallet_add_button(url)) == render_wallet_button_html(url)


def test_tag_fn_returns_safe_string():
    # mark_safe'd so Django won't re-escape the (already-escaped) HTML.
    out = wallet_add_button("/c.pkpass")
    assert isinstance(out, SafeString)


def test_tag_fn_forwards_kwargs():
    out = str(wallet_add_button("/c.pkpass", css_class="my-btn", aria_label="Add card"))
    assert 'class="my-btn"' in out
    assert 'aria-label="Add card"' in out


def _render(template_str: str, context: dict | None = None) -> str:
    return Template(template_str).render(Context(context or {}))


def test_tag_renders_through_template_engine():
    out = _render("{% load djust_mobile_toga %}{% wallet_add_button '/card/wallet.pkpass' %}")
    assert "/card/wallet.pkpass" in out
    assert out.strip().startswith("<a")
    assert "messageHandlers.addToWallet" in out


def test_tag_render_escapes_url_from_context():
    # A url with HTML-significant chars passed via context is escaped on output.
    out = _render(
        "{% load djust_mobile_toga %}{% wallet_add_button bad %}",
        {"bad": '/x"><script>alert(1)</script>'},
    )
    assert '"><script>' not in out
    assert "<script>alert(1)" not in out


def test_tag_render_output_not_double_escaped():
    # mark_safe means Django outputs the helper's HTML verbatim (real anchor
    # markup), rather than escaping the whole thing into visible &lt;a&gt;.
    out = _render("{% load djust_mobile_toga %}{% wallet_add_button '/c.pkpass' %}")
    assert "&lt;a" not in out
    assert "<a" in out
