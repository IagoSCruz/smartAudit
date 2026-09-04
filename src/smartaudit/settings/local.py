"""Local development settings."""

import os

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-smartaudit-local-only",
)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

JWT_SIGNING_KEY = os.getenv("JWT_SIGNING_KEY", SECRET_KEY)

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ["POSTGRES_USER"],
            "PASSWORD": os.environ["POSTGRES_PASSWORD"],
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    # Bootstrap rápido e testes podem rodar sem a infraestrutura do Compose.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": PROJECT_ROOT / "db.sqlite3",  # noqa: F405
        }
    }
