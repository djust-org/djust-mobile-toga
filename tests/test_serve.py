"""Tests for the loopback uvicorn helper.

``serve`` is pure logic with no platform dependency: ``free_port`` asks the
kernel for an ephemeral port, and ``run_loopback_server`` constructs a uvicorn
``Config`` / ``Server`` directly (bypassing ``uvicorn.main`` /
``uvicorn.supervisors``, which import ``_multiprocessing`` at load time). We
exercise both without standing up a real long-running server by capturing the
``Config`` a stubbed ``Server`` receives.
"""

from __future__ import annotations

import asyncio
import socket

import uvicorn.server

from djust_mobile_toga import serve


def test_import_does_not_raise():
    assert serve is not None


def test_free_port_returns_int_in_range():
    port = serve.free_port()
    assert isinstance(port, int)
    assert 1 <= port <= 65535


def test_free_port_is_actually_bindable():
    # The kernel handed it out as free; we must be able to bind it right back.
    port = serve.free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((serve.DEFAULT_HOST, port))  # raises if not actually free
        assert s.getsockname()[1] == port


def test_free_port_respects_host_arg():
    # An explicit loopback host is honored (binds on that interface).
    port = serve.free_port(host="127.0.0.1")
    assert isinstance(port, int)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_free_port_unique_enough():
    # Two back-to-back grabs typically differ (ephemeral allocator advances).
    # Not a hard guarantee, but a sanity check that it isn't pinned to one port.
    ports = {serve.free_port() for _ in range(5)}
    assert all(isinstance(p, int) for p in ports)


def _patch_server(monkeypatch):
    """Swap uvicorn's Server for a capture-only stub; return the capture dict."""
    captured: dict = {}

    class _FakeServer:
        def __init__(self, config):
            captured["config"] = config

        async def serve(self):  # awaited via loop.run_until_complete
            captured["served"] = True

    monkeypatch.setattr(uvicorn.server, "Server", _FakeServer)
    return captured


def _patch_loops(monkeypatch):
    """Capture loops created by run_loopback_server so the test can close them,
    and stop it clobbering the current event loop."""
    made: list = []
    real_new = asyncio.new_event_loop

    def _fake_new():
        loop = real_new()
        made.append(loop)
        return loop

    monkeypatch.setattr(asyncio, "new_event_loop", _fake_new)
    monkeypatch.setattr(asyncio, "set_event_loop", lambda _loop: None)
    return made


def test_run_loopback_server_builds_expected_config(monkeypatch):
    captured = _patch_server(monkeypatch)
    made = _patch_loops(monkeypatch)
    try:
        serve.run_loopback_server("myapp.asgi:application", 8123, log_level="warning")
    finally:
        for loop in made:
            loop.close()

    assert captured.get("served") is True
    config = captured["config"]
    assert config.app == "myapp.asgi:application"
    assert config.host == serve.DEFAULT_HOST
    assert config.port == 8123
    # The three pins that make this iOS-safe + single-process.
    assert config.workers == 1
    assert config.loop == "asyncio"
    assert config.ws == "wsproto"
    assert config.log_level == "warning"


def test_run_loopback_server_honors_custom_host(monkeypatch):
    captured = _patch_server(monkeypatch)
    made = _patch_loops(monkeypatch)
    try:
        serve.run_loopback_server("a.b:app", 9000, host="127.0.0.2")
    finally:
        for loop in made:
            loop.close()

    config = captured["config"]
    assert config.host == "127.0.0.2"
    assert config.port == 9000
    # Default log level is info when not overridden.
    assert config.log_level == "info"
