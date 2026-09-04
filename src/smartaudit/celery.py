"""Celery application shared by SmartAudit workers."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartaudit.settings.production")

app = Celery("smartaudit")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
