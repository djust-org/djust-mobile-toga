"""Tests for the on-device voice bridge.

These run off-iOS (desktop CI), exercising the fail-soft guard paths: the module
must import cleanly, report unavailable, and never raise. The actual
SFSpeechRecognizer / AVSpeechSynthesizer paths can only be verified on an iOS
device with a microphone — hand-verified, not covered here.
"""

from djust_mobile_toga import voice


def test_import_does_not_raise():
    assert voice is not None


def test_stt_unavailable_off_ios():
    assert voice.stt_available() is False


def test_tts_unavailable_off_ios():
    assert voice.tts_available() is False


def test_start_dictation_returns_false_off_ios():
    # No backend → False, and it must not raise even with real callbacks passed.
    assert (
        voice.start_dictation(on_partial=lambda t: None, on_final=lambda t: None)
        is False
    )


def test_start_dictation_no_callbacks_off_ios():
    assert voice.start_dictation() is False


def test_stop_dictation_is_safe_noop():
    # Idempotent + safe even when nothing is running.
    voice.stop_dictation()
    voice.stop_dictation()


def test_speak_returns_false_off_ios():
    assert voice.speak("Your Part B premium is $185.00 a month.") is False


def test_speak_empty_is_false():
    assert voice.speak("") is False


def test_stop_speaking_is_safe_noop():
    voice.stop_speaking()


def test_request_permission_is_safe_noop_off_ios():
    # No backend → no-op, never raises.
    voice.request_permission()


def test_stt_available_handles_flaky_backend(monkeypatch):
    # Simulate "classes resolved but the on-device check raises" → degrade to
    # False, never propagate.
    monkeypatch.setattr(voice, "_STT_READY", True)

    def _boom():
        raise RuntimeError("objc blew up")

    monkeypatch.setattr(voice, "_make_recognizer", _boom)
    assert voice.stt_available() is False
