"""On-device voice — speech-to-text (dictation) and text-to-speech (read-aloud).

Unlike Apple's Foundation Models (Swift-only — see ``apple_intelligence.py``),
the speech frameworks are **Objective-C-API** ``NSObject`` classes, so
``rubicon-objc`` reaches them **directly** — no Swift shim, no pbxproj patch:

* **Speech-to-text** — ``SFSpeechRecognizer`` (Speech.framework, iOS 10+) fed by
  an ``AVAudioEngine`` input tap. On-device only
  (``requiresOnDeviceRecognition`` — audio never leaves the phone).
* **Text-to-speech** — ``AVSpeechSynthesizer`` (AVFoundation, iOS 7+). On-device.

Public API (all fail-soft — never raise; on-device speech is an "extra")::

    from djust_mobile_toga import voice

    voice.stt_available()                      # -> bool  (iOS + on-device STT)
    voice.start_dictation(on_partial=cb, on_final=cb)
    voice.stop_dictation()
    voice.tts_available()                      # -> bool
    voice.speak("Your Part B premium is …")
    voice.stop_speaking()

On desktop / Android / older iOS the availability checks return ``False`` and
the start/speak calls are logged no-ops, so consumers degrade to a text box /
on-screen answer. Permissions (``NSMicrophoneUsageDescription`` +
``NSSpeechRecognitionUsageDescription``) are added by the consuming app's
Briefcase ``iOS.info`` table. See the spike:
``docs/specs/2026-06-08-voice-bridge-spike.md`` (in the max-companion repo).
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Callable, Optional

LOG = logging.getLogger("djust_mobile_toga.voice")

_IS_IOS = sys.platform == "ios"
# Locale for recognition + synthesis. Kept simple for the PoC (US English);
# a future version can read the beneficiary's language preference.
_LOCALE = "en-US"

_STT_READY = False  # SFSpeechRecognizer + AVAudioEngine classes resolved
_TTS_READY = False  # AVSpeechSynthesizer resolved
_ios: dict[str, Any] = {}
# Long-lived references for the active dictation session. The recognizer,
# request, task, audio engine, and every rubicon Block MUST outlive the call
# that starts them — iOS invokes the tap + result handlers asynchronously, and
# a GC'd Block/ctypes-callback crashes on callback (the lifetime gotcha, same
# as notifications._ios_keepalive / the AI bridge).
_session: dict[str, Any] = {}
_keepalive: list = []
# The synthesizer is retained for the process lifetime once created.
_synth: Any = None

if _IS_IOS:
    try:
        import ctypes

        from rubicon.objc import Block, ObjCClass, ObjCInstance
        from rubicon.objc.runtime import load_library, objc_id

        # Speech + AVFoundation aren't auto-linked into a Toga app; load them so
        # the ObjC runtime can resolve their classes (same as passkit.py dlopen
        # of PassKit, and toga's own av_foundation.py).
        load_library("Speech")
        load_library("AVFoundation")

        _ios["SFSpeechRecognizer"] = ObjCClass("SFSpeechRecognizer")
        _ios["SFSpeechAudioBufferRecognitionRequest"] = ObjCClass(
            "SFSpeechAudioBufferRecognitionRequest"
        )
        _ios["AVAudioEngine"] = ObjCClass("AVAudioEngine")
        _ios["AVAudioSession"] = ObjCClass("AVAudioSession")
        _ios["NSLocale"] = ObjCClass("NSLocale")
        _ios["Block"] = Block
        _ios["ObjCInstance"] = ObjCInstance
        _ios["objc_id"] = objc_id
        _ios["ctypes"] = ctypes
        _STT_READY = True
    except Exception as exc:  # noqa: BLE001 — not on iOS, or framework missing
        LOG.info("voice STT unavailable: %s", exc)

    try:
        from rubicon.objc import ObjCClass as _OC

        _ios["AVSpeechSynthesizer"] = _OC("AVSpeechSynthesizer")
        _ios["AVSpeechUtterance"] = _OC("AVSpeechUtterance")
        _ios["AVSpeechSynthesisVoice"] = _OC("AVSpeechSynthesisVoice")
        _TTS_READY = True
    except Exception as exc:  # noqa: BLE001
        LOG.info("voice TTS unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Speech-to-text (dictation)
# ---------------------------------------------------------------------------


def stt_available() -> bool:
    """True only on iOS where on-device speech recognition is usable.

    Checks the classes resolved AND that the recognizer supports on-device
    recognition for the locale (so audio stays on the phone). Never raises.
    """
    if not _STT_READY:
        return False
    try:
        recognizer = _make_recognizer()
        if recognizer is None:
            return False
        # supportsOnDeviceRecognition (iOS 13+) — gate before forcing on-device.
        return bool(recognizer.supportsOnDeviceRecognition())
    except Exception:  # noqa: BLE001 — must never crash the app
        LOG.exception("voice stt_available() check raised")
        return False


def _make_recognizer():
    locale = _ios["NSLocale"].localeWithLocaleIdentifier_(_LOCALE)
    return _ios["SFSpeechRecognizer"].alloc().initWithLocale_(locale)


def request_permission() -> None:
    """Ask iOS for speech-recognition + microphone permission (the one-time OS
    prompts). Call ONCE at app startup — without it, the prompt never fires and
    ``start_dictation`` returns auth-denied on a fresh install. No-op off-iOS;
    fail-soft (never raises). Requires ``NSSpeechRecognitionUsageDescription`` +
    ``NSMicrophoneUsageDescription`` in the app's Info.plist (or iOS hard-crashes
    at the request)."""
    if not _STT_READY:
        return
    try:
        # SFSpeechRecognizer.requestAuthorization(handler) — handler gets an
        # SFSpeechRecognizerAuthorizationStatus (NSInteger). Retain the Block
        # across the async callback (the GC-crash lifetime rule).
        def _on_speech_auth(status):
            LOG.info("speech recognition authorization status=%s", int(status))

        speech_block = _ios["Block"](_on_speech_auth, None, _ios["ctypes"].c_long)
        _keepalive.append(speech_block)
        _ios["SFSpeechRecognizer"].requestAuthorization_(speech_block)

        # AVAudioSession.requestRecordPermission(handler) — handler gets a BOOL.
        def _on_mic_auth(granted):
            LOG.info("microphone permission granted=%s", bool(granted))

        mic_block = _ios["Block"](_on_mic_auth, None, _ios["ctypes"].c_bool)
        _keepalive.append(mic_block)
        _ios["AVAudioSession"].sharedInstance().requestRecordPermission_(mic_block)
    except Exception:  # noqa: BLE001 — must never crash the app
        LOG.exception("voice request_permission failed")


def start_dictation(
    on_partial: Optional[Callable[[str], None]] = None,
    on_final: Optional[Callable[[str], None]] = None,
) -> bool:
    """Begin on-device dictation. ``on_partial(text)`` fires repeatedly with the
    in-progress transcript; ``on_final(text)`` fires once with the settled
    transcript. Returns True if capture started, False otherwise (and on any
    platform without STT). Never raises.

    Only one session at a time — a second call stops the first.
    """
    if not _STT_READY:
        LOG.info("start_dictation: no STT backend on this platform")
        return False
    try:
        stop_dictation()  # ensure single session

        recognizer = _make_recognizer()
        if recognizer is None or not recognizer.supportsOnDeviceRecognition():
            LOG.info("start_dictation: on-device recognition unsupported")
            return False

        session = _ios["AVAudioSession"].sharedInstance()
        # .playAndRecord so dictation and read-aloud can share the session.
        session.setCategory_error_("AVAudioSessionCategoryPlayAndRecord", None)
        session.setActive_error_(True, None)

        request = _ios["SFSpeechAudioBufferRecognitionRequest"].alloc().init()
        request.shouldReportPartialResults = True
        # Keep audio on the device — the loopback-contract-honoring path.
        request.requiresOnDeviceRecognition = True

        engine = _ios["AVAudioEngine"].alloc().init()
        input_node = engine.inputNode
        fmt = input_node.outputFormatForBus_(0)

        def _tap(buf, when):  # realtime audio thread — keep cheap
            try:
                request.appendAudioPCMBuffer_(_ios["ObjCInstance"](buf))
            except Exception:  # noqa: BLE001
                pass

        tap_block = _ios["Block"](_tap, None, _ios["objc_id"], _ios["objc_id"])
        input_node.installTapOnBus_bufferSize_format_block_(0, 1024, fmt, tap_block)

        def _result(result_ptr, error_ptr):  # speech callback thread
            try:
                if error_ptr:
                    return
                if not result_ptr:
                    return
                result = _ios["ObjCInstance"](result_ptr)
                text = str(result.bestTranscription.formattedString)
                if result.isFinal():
                    if on_final:
                        on_final(text)
                elif on_partial:
                    on_partial(text)
            except Exception:  # noqa: BLE001
                LOG.exception("dictation result handler raised")

        result_block = _ios["Block"](_result, None, _ios["objc_id"], _ios["objc_id"])

        engine.prepare()
        engine.startAndReturnError_(None)
        task = recognizer.recognitionTaskWithRequest_resultHandler_(
            request, result_block
        )

        # Retain EVERYTHING for the session lifetime (the GC-crash gotcha).
        _session.update(
            recognizer=recognizer, request=request, task=task, engine=engine
        )
        _keepalive.extend([tap_block, result_block, _result, _tap])
        LOG.info("dictation started (on-device)")
        return True
    except Exception:  # noqa: BLE001 — must never crash the app
        LOG.exception("start_dictation failed")
        stop_dictation()
        return False


def stop_dictation() -> None:
    """End the active dictation session (idempotent, fail-soft)."""
    try:
        engine = _session.get("engine")
        if engine is not None:
            try:
                engine.stop()
                engine.inputNode.removeTapOnBus_(0)
            except Exception:  # noqa: BLE001
                pass
        request = _session.get("request")
        if request is not None:
            try:
                request.endAudio()
            except Exception:  # noqa: BLE001
                pass
        task = _session.get("task")
        if task is not None:
            try:
                task.cancel()
            except Exception:  # noqa: BLE001
                pass
    finally:
        _session.clear()
        _keepalive.clear()


# ---------------------------------------------------------------------------
# Text-to-speech (read-aloud) — used by the read-aloud task (#3); shipped here
# so the bridge is one module. speak() is a no-op until then on the UI side.
# ---------------------------------------------------------------------------


def tts_available() -> bool:
    """True on iOS where AVSpeechSynthesizer resolved. Never raises."""
    return bool(_TTS_READY)


def speak(text: str) -> bool:
    """Speak ``text`` aloud on-device. Returns True if handed to the synthesizer,
    False otherwise (and on any platform without TTS). Never raises."""
    global _synth
    if not _TTS_READY or not text:
        return False
    try:
        if _synth is None:
            _synth = _ios["AVSpeechSynthesizer"].alloc().init()
        utterance = _ios["AVSpeechUtterance"].alloc().initWithString_(text)
        voice = _ios["AVSpeechSynthesisVoice"].voiceWithLanguage_(_LOCALE)
        if voice:
            utterance.voice = voice
        _synth.speakUtterance_(utterance)
        return True
    except Exception:  # noqa: BLE001 — must never crash the app
        LOG.exception("speak() failed")
        return False


def stop_speaking() -> None:
    """Stop any in-progress speech (idempotent, fail-soft)."""
    try:
        if _synth is not None:
            # AVSpeechBoundaryImmediate = 0
            _synth.stopSpeakingAtBoundary_(0)
    except Exception:  # noqa: BLE001
        LOG.exception("stop_speaking() failed")
