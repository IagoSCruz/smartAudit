"""SmartAudit Django project."""

from smartaudit.celery import app as celery_app

__all__ = ("celery_app",)


def main() -> None:
    """Expose a small package-level command for installation smoke tests."""
    print("SmartAudit: use `python manage.py --help` for Django commands.")
