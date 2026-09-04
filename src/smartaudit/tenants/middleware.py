"""Resolve the active tenant selected by authenticated browser sessions."""

from smartaudit.tenants.services import (
    ACTIVE_TENANT_SESSION_KEY,
    TenantAccessDenied,
    TenantContextMissing,
    resolve_tenant_from_session,
)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        request.membership = None

        if request.user.is_authenticated:
            try:
                membership = resolve_tenant_from_session(request)
            except TenantContextMissing:
                pass
            except TenantAccessDenied:
                request.session.pop(ACTIVE_TENANT_SESSION_KEY, None)
            else:
                request.membership = membership
                request.tenant = membership.tenant

        return self.get_response(request)
