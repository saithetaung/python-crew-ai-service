
import logging
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import get_settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def require_user_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Validate a local test JWT and extract trusted identity claims."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    secret_setting = settings.jwt_secret
    secret = (
        secret_setting.get_secret_value()
        if hasattr(secret_setting, "get_secret_value")
        else str(secret_setting or "")
    )
    issuer = settings.jwt_issuer
    audience = settings.jwt_audience

    if not secret or not issuer or not audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured",
        )

    token = credentials.credentials

    try:
        claims = jwt.decode(
            token,
            key=secret,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            options={
                "require": [
                    "sub", "name", "role", "iss", "aud", "iat", "exp"
                ]
            },
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = claims.get("sub")
    name = claims.get("name")
    role = claims.get("role")

    if not all(
        isinstance(value, str) and value.strip()
        for value in (user_id, name, role)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT is missing required identity claims",
        )

    # Keep the token in memory only. Never log or store it in Redis.
    return {
        "user_id": user_id,
        "name": name,
        "role": role,
        "access_token": token,
    }
