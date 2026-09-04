"""Local development settings."""

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = "django-insecure-smartaudit-local-only"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": PROJECT_ROOT / "db.sqlite3",  # noqa: F405
    }
}
