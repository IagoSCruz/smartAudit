"""Tenant authorization rules shared by HTTP entrypoints."""

from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth.models import AnonymousUser

from smartaudit.tenants.models import Membership

ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


class TenantContextMissing(ValueError):
    """The caller did not select a tenant."""


class TenantAccessDenied(PermissionError):
    """The user has no active access to the selected tenant."""


def resolve_membership(user, tenant_id: object) -> Membership:
    """Resolve an active membership without trusting the supplied tenant id."""
    if isinstance(user, AnonymousUser) or not getattr(
        user,
        "is_authenticated",
        False,
    ):
        raise TenantAccessDenied("Autenticação obrigatória.")
    if not tenant_id:
        raise TenantContextMissing("Informe o tenant no cabeçalho X-Tenant-ID.")
    try:
        normalized_tenant_id = int(str(tenant_id))
    except (TypeError, ValueError) as exc:
        raise TenantAccessDenied("O identificador do tenant é inválido.") from exc
    if normalized_tenant_id <= 0:
        raise TenantAccessDenied("O identificador do tenant é inválido.")

    membership = (
        Membership.objects.select_related("tenant", "user")
        .filter(
            tenant_id=normalized_tenant_id,
            user=user,
            is_active=True,
            tenant__is_active=True,
        )
        .first()
    )
    if membership is None:
        raise TenantAccessDenied("Você não possui acesso ativo a este tenant.")
    return membership


def resolve_tenant_from_header(request) -> Membership:
    return resolve_membership(request.user, request.headers.get("X-Tenant-ID"))


def resolve_tenant_from_session(request) -> Membership:
    tenant_id = request.session.get(ACTIVE_TENANT_SESSION_KEY)
    if not tenant_id:
        raise TenantContextMissing("Selecione um tenant para continuar.")
    return resolve_membership(request.user, tenant_id)


def activate_tenant_session(request, tenant_id: object) -> Membership:
    membership = resolve_membership(request.user, tenant_id)
    request.session[ACTIVE_TENANT_SESSION_KEY] = membership.tenant_id
    return membership


def ensure_membership_role(
    membership: Membership | None,
    allowed_roles: Iterable[str],
) -> None:
    allowed = frozenset(allowed_roles)
    if (
        membership is None
        or not membership.is_active
        or membership.role not in allowed
    ):
        raise TenantAccessDenied("Seu papel não permite executar esta ação.")
