"""Minimal Django settings for the djust-mobile-toga showcase.

One LiveView with a tab per native bridge, served over the on-device loopback
server. The writable data dir comes from ``DJUST_MOBILE_DATA_DIR`` (exported by
``BaseDjustApp`` before Django imports); on desktop it falls back to this
project dir so a plain ``uvicorn showcase.asgi:application`` just works.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.environ.get("DJUST_MOBILE_DATA_DIR", BASE_DIR))

# Generate + persist a random SECRET_KEY in the writable data dir on first
# launch, so it's unique per install and never a hardcoded repo value.
_key_file = DATA_DIR / "secret_key.txt"
if _key_file.exists():
    SECRET_KEY = _key_file.read_text().strip()
else:
    from django.core.management.utils import get_random_secret_key

    SECRET_KEY = get_random_secret_key()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _key_file.write_text(SECRET_KEY)

DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "channels",
    "djust",
    "showcase",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "showcase.urls"
ASGI_APPLICATION = "showcase.asgi.application"

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
