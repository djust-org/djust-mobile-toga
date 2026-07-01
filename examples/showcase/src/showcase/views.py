"""ShowcaseView — one tab per native bridge, all fail-soft.

Each tab calls a djust-mobile-toga bridge. Off their target platform (desktop,
CI, Android for the iOS-only ones) every bridge's availability check returns
False and its actions are logged no-ops — so this view renders and runs
everywhere; the *native behaviour* only fires on an iOS device/simulator.

The bridges are imported at module top on purpose: they guard their platform
imports internally (the fail-soft contract), so importing them on plain Linux
is safe.
"""

from djust import LiveView
from djust.decorators import event_handler

from djust_mobile_toga import apple_intelligence, notifications, voice
from djust_mobile_toga.passkit import render_wallet_button_html

TABS = ("voice", "ai", "wallet", "notifications", "bridge")


class ShowcaseView(LiveView):
    template_name = "showcase.html"
    # Public showcase, no user data — acknowledge unauthenticated access (S005).
    login_required = False

    # ---- lifecycle ---------------------------------------------------------
    def mount(self, request, **kwargs):
        self.tab = "voice"
        self._apply_tab()

        # Per-tab reactive state.
        self.voice_status = ""
        self.transcript = ""
        self._captured = ""  # raw STT result stashed by the native callback
        self.ai_prompt = ""
        self.ai_answer = ""
        self.ai_thinking = False
        self.notif_status = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Derived, constant-per-platform display data — computed here rather
        # than stored on self, so djust's change-tracker only follows the
        # mutable tab/status vars (and the static V008 check stays quiet).
        # Availability is False off each bridge's target platform (fail-soft).
        ctx.update(
            voice_stt=voice.stt_available(),
            voice_tts=voice.tts_available(),
            ai_available=apple_intelligence.is_available(),
            notif_available=notifications.is_available(),
            # Plain HTML — renders everywhere; installs a pass only on iOS.
            wallet_button=render_wallet_button_html(url="/passes/demo.pkpass"),
        )
        return ctx

    # ---- tabs --------------------------------------------------------------
    @event_handler()
    def show_tab(self, tab: str = "voice", **kwargs):
        if tab in TABS:
            self.tab = tab
            self._apply_tab()

    def _apply_tab(self):
        # Render every section always-present and toggle visibility via a
        # `display` value (never add/remove DOM — that breaks VDOM patching).
        for name in TABS:
            setattr(self, f"d_{name}", "block" if self.tab == name else "none")

    # ---- voice (SFSpeechRecognizer STT + AVSpeechSynthesizer TTS) ----------
    @event_handler()
    def speak_sample(self, **kwargs):
        text = "Hello from djust — this speech is synthesized on device."
        ok = voice.speak(text)
        self.voice_status = "Speaking…" if ok else "TTS unavailable on this platform."

    @event_handler()
    def start_dictation(self, **kwargs):
        self._captured = ""
        self.transcript = ""
        ok = voice.start_dictation(on_partial=None, on_final=self._on_transcript)
        self.voice_status = (
            "Listening… tap Stop when done." if ok else ("STT unavailable on this platform.")
        )

    @event_handler()
    def stop_dictation(self, **kwargs):
        voice.stop_dictation()
        # The on_final callback (fired on a native thread) stashed the result;
        # a view-initiated handler is the simplest way to surface it in the UI.
        self.transcript = self._captured or "(nothing captured)"
        self.voice_status = "Stopped."

    def _on_transcript(self, text: str):
        # Runs on a native thread — just stash; stop_dictation() reads it.
        self._captured = text

    # ---- Apple Intelligence (on-device Foundation Models) ------------------
    @event_handler()
    def ask_ai(self, value: str = "", **kwargs):
        self.ai_prompt = value.strip()
        if not self.ai_prompt:
            return
        self.ai_answer = ""
        self.ai_thinking = True  # flushed to the client immediately
        self.start_async(self._do_ask)  # the blocking ask() runs after the flush

    def _do_ask(self):
        answer = apple_intelligence.ask(self.ai_prompt, instructions="Answer briefly.")
        self.ai_answer = (
            answer
            if answer is not None
            else (
                "On-device AI is unavailable here — falling back to this message. "
                "On an Apple-Intelligence device the model answers your prompt."
            )
        )
        self.ai_thinking = False

    # ---- local notifications (iOS + Android) -------------------------------
    @event_handler()
    def schedule_reminder(self, **kwargs):
        ok = notifications.schedule_local(
            title="djust showcase",
            body="This local notification was scheduled from Python.",
            delay_seconds=5,
            identifier="showcase-demo",
        )
        self.notif_status = (
            "Scheduled — fires in 5s (leave the app to see it)."
            if ok
            else "Notifications unavailable on this platform (logged no-op)."
        )

    @event_handler()
    def cancel_reminder(self, **kwargs):
        notifications.cancel_local("showcase-demo")
        self.notif_status = "Cancelled."
