"""Root URL configuration for SmartAudit."""

from django.contrib import admin
from django.urls import path

from smartaudit.core.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]
