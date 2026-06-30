"""Minimal Django settings for the djust-mobile-toga counter demo.

One LiveView, served over the on-device loopback server. The writable data
dir comes from ``DJUST_MOBILE_DATA_DIR`` (exported by ``BaseDjustApp`` before
Django imports); on desktop it falls back to this project dir so a plain
``uvicorn counter_demo.asgi:application`` / ``python -m counter_demo`` just
works without any environment setup.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# BaseDjustApp exports the writable sandbox dir here (iOS app-support dir /
# Android files dir). Fall back to BASE_DIR for desktop runs.
DATA_DIR = Path(os.environ.get("DJUST_MOBILE_DATA_DIR", BASE_DIR))

# On-device SECRET_KEY: generate a random key on first launch and persist it in
# the writable data dir, so it's unique per install and stable across launches.
# This is the right pattern for a shipped app — a hardcoded key in a public repo
# lets anyone forge session cookies.
_key_file = DATA_DIR / "secret_key.txt"
if _key_file.exists():
    SECRET_KEY = _key_file.read_text().strip()
else:
    from django.core.management.utils import get_random_secret_key

    SECRET_KEY = get_random_secret_key()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _key_file.write_text(SECRET_KEY)

# The on-device server is loopback-only, so DEBUG can stay off (mirrors the
# device build). Flip to True for desktop development if you want tracebacks.
DEBUG = False

# The loopback server answers on 127.0.0.1; ``testserver`` covers Django's
# test client.
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "channels",
    "djust",
    "counter_demo",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "counter_demo.urls"
ASGI_APPLICATION = "counter_demo.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

# In-memory channel layer — a single-process on-device server needs nothing more.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DATA_DIR / "db.sqlite3"),
    }
}

STATIC_URL = "/static/"
STATIC_ROOT = str(DATA_DIR / "staticfiles")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
