"""Role guards for tenant-scoped views and API operations."""

from functools import wraps

from django.core.exceptions import PermissionDenied

from smartaudit.tenants.services import TenantAccessDenied, ensure_membership_role


def require_roles(*allowed_roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            try:
                ensure_membership_role(
                    getattr(request, "membership", None),
                    allowed_roles,
                )
            except TenantAccessDenied as exc:
                raise PermissionDenied(str(exc)) from exc
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
