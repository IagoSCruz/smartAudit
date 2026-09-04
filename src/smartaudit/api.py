"""HTTP API shell, authentication endpoints and tenant boundary."""

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from ninja import NinjaAPI, Schema, Status
from ninja.errors import AuthenticationError, HttpError
from ninja.security import HttpBearer

from smartaudit.accounts.services import (
    InvalidToken,
    authenticate_user,
    get_active_user_from_token,
    issue_access_token,
    issue_token_pair,
)
from smartaudit.tenants.services import (
    TenantAccessDenied,
    TenantContextMissing,
    resolve_tenant_from_header,
)
from smartaudit.documents.api import router as documents_router


class LoginInput(Schema):
    email: str
    password: str


class RefreshInput(Schema):
    refresh: str


class TokenPairOutput(Schema):
    access: str
    refresh: str
    token_type: str = "Bearer"


class AccessTokenOutput(Schema):
    access: str
    token_type: str = "Bearer"


class ErrorOutput(Schema):
    detail: str


class TenantContextOutput(Schema):
    tenant_id: int
    tenant_name: str
    role: str
    user_email: str


class TenantJWTAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            user = get_active_user_from_token(token, "access")
        except InvalidToken as exc:
            raise AuthenticationError(message=str(exc)) from exc

        request.user = user
        try:
            membership = resolve_tenant_from_header(request)
        except TenantContextMissing as exc:
            raise HttpError(400, str(exc)) from exc
        except TenantAccessDenied as exc:
            raise HttpError(403, str(exc)) from exc

        request.membership = membership
        request.tenant = membership.tenant
        return user


api = NinjaAPI(
    title="SmartAudit API",
    version="1.0.0",
    description="API multi-tenant para conciliação e auditoria de fretes.",
    auth=TenantJWTAuth(),
)


@api.exception_handler(AuthenticationError)
def authentication_error(request, exc):
    message = exc.message
    if message == "Unauthorized":
        message = "Autenticação obrigatória."
    return JsonResponse({"detail": message}, status=exc.status_code)


@api.exception_handler(PermissionDenied)
def permission_denied_error(request, exc):
    return JsonResponse({"detail": str(exc)}, status=403)


@api.get("/", auth=None)
def api_root(request):
    return {
        "name": "SmartAudit API",
        "version": api.version,
        "docs": "/api/docs",
    }


@api.post(
    "/auth/login",
    auth=None,
    response={200: TokenPairOutput, 401: ErrorOutput},
)
def login(request, payload: LoginInput):
    user = authenticate_user(request, payload.email, payload.password)
    if user is None:
        return Status(401, {"detail": "E-mail ou senha inválidos."})
    return issue_token_pair(user)


@api.post(
    "/auth/refresh",
    auth=None,
    response={200: AccessTokenOutput, 401: ErrorOutput},
)
def refresh(request, payload: RefreshInput):
    try:
        user = get_active_user_from_token(payload.refresh, "refresh")
    except InvalidToken as exc:
        return Status(401, {"detail": str(exc)})
    return {"access": issue_access_token(user)}


@api.get("/tenant", response=TenantContextOutput)
def tenant_context(request):
    return {
        "tenant_id": request.tenant.pk,
        "tenant_name": request.tenant.name,
        "role": request.membership.role,
        "user_email": request.user.email,
    }


api.add_router("/documents", documents_router)
