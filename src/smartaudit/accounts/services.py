"""Authentication and JWT token services."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model


class InvalidToken(ValueError):
    """A JWT is invalid, expired or has an unexpected purpose."""


def authenticate_user(request, email: str, password: str):
    return authenticate(request, username=email, password=password)


def _encode_token(user, token_type: str, lifetime_seconds: int) -> str:
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.pk),
        "type": token_type,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=lifetime_seconds),
        "jti": uuid4().hex,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(
        payload,
        settings.JWT_SIGNING_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def issue_token_pair(user) -> dict[str, str]:
    return {
        "access": issue_access_token(user),
        "refresh": _encode_token(
            user,
            "refresh",
            settings.JWT_REFRESH_TTL_SECONDS,
        ),
    }


def issue_access_token(user) -> str:
    return _encode_token(
        user,
        "access",
        settings.JWT_ACCESS_TTL_SECONDS,
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SIGNING_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken("Token inválido ou expirado.") from exc

    if payload.get("type") != expected_type:
        raise InvalidToken("Tipo de token inválido para esta operação.")
    return payload


def get_active_user_from_token(token: str, expected_type: str):
    payload = decode_token(token, expected_type)
    user = get_user_model().objects.filter(pk=payload["sub"], is_active=True).first()
    if user is None:
        raise InvalidToken("Usuário do token não está ativo.")
    return user
