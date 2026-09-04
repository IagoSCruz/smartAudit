"""Test utilities for the repository's ``src`` package layout."""

from django.test.runner import DiscoverRunner


class SmartAuditTestRunner(DiscoverRunner):
    """Discover project tests when ``manage.py test`` has no explicit label."""

    def run_tests(self, test_labels, **kwargs):
        return super().run_tests(test_labels or ("smartaudit",), **kwargs)
