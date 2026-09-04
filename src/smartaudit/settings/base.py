"""Settings shared by every SmartAudit environment."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEBUG = False
SECRET_KEY = ""
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "smartaudit.core.apps.CoreConfig",
    "smartaudit.accounts.apps.AccountsConfig",
    "smartaudit.tenants.apps.TenantsConfig",
    "smartaudit.documents.apps.DocumentsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "smartaudit.tenants.middleware.TenantContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "smartaudit.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PROJECT_ROOT / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "smartaudit.wsgi.application"
ASGI_APPLICATION = "smartaudit.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["smartaudit.accounts.backends.EmailBackend"]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = PROJECT_ROOT / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = PROJECT_ROOT / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEST_RUNNER = "smartaudit.testing.SmartAuditTestRunner"

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "smartaudit"
JWT_AUDIENCE = "smartaudit-api"
JWT_ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900"))
JWT_REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", "604800"))

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://smartaudit:smartaudit-local@localhost:5672//",
)
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/0",
)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

DOCUMENT_UPLOAD_MAX_BYTES = int(
    os.getenv("DOCUMENT_UPLOAD_MAX_BYTES", str(5 * 1024 * 1024))
)

LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

MAILERS = {
    "default": {
        "BACKEND": os.getenv(
            "DJANGO_MAILER_BACKEND",
            "django.core.mail.backends.console.EmailBackend",
        )
    }
}
