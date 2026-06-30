"""URL routing — one LiveView at the root path."""

from django.urls import path

from .views import CounterView

urlpatterns = [
    path("", CounterView.as_view(), name="counter"),
]
