"""On-device Apple Intelligence (Foundation Models) bridge.

One API, two outcomes:

* **iOS 26+ with Apple Intelligence** — wraps Apple's on-device Foundation
  Models LLM. Apple's framework is **Swift-only** (no Objective-C interface),
  and ``rubicon-objc`` resolves classes through the Objective-C runtime, so it
  cannot reach the Swift types directly. The consuming app therefore compiles a
  tiny Swift ``@objc(MaxLLMBridge)`` shim (an ``NSObject`` subclass) into its
  Briefcase binary; this module resolves that shim by name and drives it. The
  shim keeps the Swift-only types (``LanguageModelSession``, the async
  ``respond``, the ``Availability`` enum) inside Swift and exposes only
  ObjC-representable surface: a ``BOOL available()`` and a completion-handler
  ``generate(...)`` returning an ``NSString``.

* **Everything else** (desktop, Android, iOS < 26, or the shim not compiled in)
  — :func:`is_available` returns ``False`` and :func:`ask` returns ``None``.
  Consumers fall back to their own non-AI path.

Public API::

    from djust_mobile_toga import apple_intelligence

    apple_intelligence.is_available()                  # -> bool
    apple_intelligence.ask(
        "What's my Part B premium?",
        context='{"premium": {"amount": "$185.00"}}',  # grounding JSON
        instructions="You are a calm Medicare helper. Answer only from context.",
    )                                                  # -> str | None

Every function is fail-soft: any backend-internal exception is caught and logged
but never propagates. On-device AI is an "extra" — it must never crash the app.

Background on why the Swift shim is required (and how the consuming app compiles
it into the Briefcase scaffold): see the max-companion spike
``docs/specs/2026-06-08-foundation-models-bridge-spike.md``.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

LOG = logging.getLogger("djust_mobile_toga.apple_intelligence")

_IS_IOS = sys.platform == "ios"

# The ObjC runtime name the Swift shim pins via ``@objc(MaxLLMBridge)``.
_SHIM_CLASS = "MaxLLMBridge"
# How long ask() waits for the async model callback before giving up (the model
# runs on-device; first-token latency can be a few seconds).
_ASK_TIMEOUT_SECONDS = 30.0

_IOS_AVAILABLE = False
_ios: dict[str, Any] = {}
# Keeps rubicon ``Block`` completion wrappers alive across the async callback —
# iOS invokes the handler long after ``generate(...)`` returns, so the wrapper
# must not be garbage-collected in the meantime (same pattern as
# ``notifications._ios_keepalive``).
_ios_keepalive: list = []

if _IS_IOS:
    try:
        from rubicon.objc import Block, ObjCClass, ObjCInstance
        from rubicon.objc.runtime import objc_id

        # Resolve the Swift @objc shim the consuming app compiled in. If the app
        # didn't ship it (or this isn't really iOS 26+), ObjCClass raises and we
        # stay unavailable — exactly the degrade-to-FAQ path.
        _ios["MaxLLMBridge"] = ObjCClass(_SHIM_CLASS)
        _ios["bridge"] = _ios["MaxLLMBridge"].alloc().init()
        _ios["Block"] = Block
        _ios["ObjCInstance"] = ObjCInstance
        _ios["objc_id"] = objc_id
        _IOS_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001 — not on iOS, or shim absent
        LOG.info("Apple Intelligence bridge unavailable: %s", exc)


def is_available() -> bool:
    """True only on iOS 26+ where the shim resolves AND Apple Intelligence
    reports the model ready.

    Returns False on desktop / Android / older iOS / when the shim isn't
    compiled in. Never raises — a flaky availability check degrades to False.
    """
    if not _IOS_AVAILABLE:
        return False
    try:
        # The shim's ``available()`` wraps SystemLanguageModel.default.availability
        # (device eligible + Apple Intelligence enabled + model downloaded).
        return bool(_ios["bridge"].available())
    except Exception:  # noqa: BLE001 — must never crash the app
        LOG.exception("Apple Intelligence availability check raised")
        return False


def _ios_ask(prompt: str, context: str, instructions: str) -> str | None:
    """Drive the shim's async ``generate(...)`` through a completion handler,
    blocking until it fires (the synchronous request/response shape the caller
    wants). Returns the model text, or None on error/timeout."""
    done = threading.Event()
    result: dict[str, Any] = {"text": None}

    def _on_done(text_ptr, error_ptr):  # runs on an iOS callback thread
        try:
            if error_ptr:
                # Log only the error's domain + code, NOT its description — the
                # model error wraps prompt+context input, and Apple's NSError
                # userInfo is framework-controlled; logging the whole object
                # risks persisting beneficiary data to on-device logs.
                err = _ios["ObjCInstance"](error_ptr)
                LOG.info(
                    "Apple Intelligence generate() returned error (domain=%s code=%s)",
                    getattr(err, "domain", "?"),
                    getattr(err, "code", "?"),
                )
            elif text_ptr:
                result["text"] = str(_ios["ObjCInstance"](text_ptr))
        finally:
            done.set()

    # void (^)(NSString *result, NSError *error)
    handler = _ios["Block"](_on_done, None, _ios["objc_id"], _ios["objc_id"])
    _ios_keepalive.append(handler)
    try:
        _ios["bridge"].generate(
            prompt, context=context, instructions=instructions, completion=handler
        )
        if not done.wait(timeout=_ASK_TIMEOUT_SECONDS):
            LOG.info(
                "Apple Intelligence ask() timed out after %ss", _ASK_TIMEOUT_SECONDS
            )
            return None
        return result["text"]
    finally:
        # The callback has fired (or we timed out); drop the keepalive ref.
        try:
            _ios_keepalive.remove(handler)
        except ValueError:
            pass


def ask(prompt: str, *, context: str = "", instructions: str = "") -> str | None:
    """One-shot grounded completion from the on-device model.

    ``context`` is opaque grounding text (e.g. a JSON snapshot of the user's
    data) the model must answer from; ``instructions`` is the system-prompt
    policy. Returns the model's text, or ``None`` when the model is unavailable
    or the call fails/ times out. Never raises — callers fall back to their own
    non-AI path on ``None``.
    """
    if not is_available():
        return None
    try:
        return _ios_ask(prompt, context, instructions)
    except Exception:  # noqa: BLE001 — must never crash the app
        LOG.exception("Apple Intelligence ask() raised")
        return None
