"""The counter LiveView — the smallest meaningful djust view.

``count`` is a public attribute, so djust auto-exposes it to the template
context and ships only the changed value to the client on each event. No
manual ``get_context_data`` and no client-side JavaScript required.
"""

from djust import LiveView
from djust.decorators import event_handler


class CounterView(LiveView):
    template_name = "counter.html"
    # The counter is intentionally public (no user data) — acknowledge it so
    # djust's S005 "exposes state without authentication" check passes.
    login_required = False

    def mount(self, request, **kwargs):
        self.count = 0

    @event_handler()
    def increment(self, **kwargs):
        self.count += 1

    @event_handler()
    def decrement(self, **kwargs):
        self.count -= 1

    @event_handler()
    def reset(self, **kwargs):
        self.count = 0
