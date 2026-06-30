"""Tests for the Apple Wallet (.pkpass) integration.

``render_wallet_button_html`` is a pure HTML generator with no platform
dependency — the bulk of the coverage here. ``enable_apple_wallet`` is an
iOS-only side-effecting call that must fail-soft (no-op, never raise) off-iOS;
the actual PassKit install path can only be verified on an iOS device and is
hand-verified, not covered here.
"""

from __future__ import annotations

from djust_mobile_toga import passkit


def test_import_does_not_raise():
    assert passkit is not None


def test_render_contains_url():
    html = passkit.render_wallet_button_html("/card/wallet.pkpass")
    assert "/card/wallet.pkpass" in html


def test_render_is_an_anchor_button():
    html = passkit.render_wallet_button_html("/card/wallet.pkpass")
    assert html.startswith("<a")
    assert html.rstrip().endswith("</a>")
    assert 'href="/card/wallet.pkpass"' in html


def test_render_includes_apple_logo_and_label():
    html = passkit.render_wallet_button_html("/c.pkpass")
    assert "<svg" in html
    assert "Apple Wallet" in html
    assert 'aria-label="Add to Apple Wallet"' in html


def test_render_includes_bridge_js_onclick():
    html = passkit.render_wallet_button_html("/c.pkpass")
    # The JS bridge routes through the WKScriptMessageHandler when present.
    assert "messageHandlers.addToWallet" in html
    assert "onclick=" in html


def test_render_escapes_url_xss():
    # A url carrying HTML-significant chars must be escaped on output — no raw
    # quote-break-out, no live <script>.
    html = passkit.render_wallet_button_html('/x?a=1&b=2"><script>alert(1)</script>')
    assert '"><script>' not in html
    assert "<script>alert(1)" not in html
    assert "&amp;" in html  # the & was escaped
    assert "&quot;" in html or "&#x27;" in html  # the quote was escaped


def test_render_escapes_aria_and_class():
    html = passkit.render_wallet_button_html("/c.pkpass", css_class='c"x', aria_label='a"y')
    assert 'class="c"x"' not in html  # the quote in css_class must be escaped
    assert "&quot;" in html


def test_render_omits_class_attr_when_empty():
    html = passkit.render_wallet_button_html("/c.pkpass", css_class="")
    # The OUTER anchor carries no class attr (inner SVG/spans still do).
    assert html.startswith("<a href=")


def test_render_custom_class_and_label():
    html = passkit.render_wallet_button_html("/c.pkpass", css_class="my-btn", aria_label="Add card")
    assert 'class="my-btn"' in html
    assert 'aria-label="Add card"' in html


def test_enable_apple_wallet_noop_off_ios():
    # Off-iOS: guarded no-op, never raises (and never touches app internals).
    class _FakeApp:
        pass

    passkit.enable_apple_wallet(_FakeApp())


def test_enable_apple_wallet_custom_handler_name_off_ios():
    passkit.enable_apple_wallet(object(), handler_name="customWallet")


def test_present_pass_from_url_handles_none():
    # The callback must fail-soft on an empty/None URL (never raises).
    passkit._present_pass_from_url(None, None)
    passkit._present_pass_from_url(None, "")
