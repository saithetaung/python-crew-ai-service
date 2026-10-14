
import base64
import logging

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from src.core.config import get_settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


async def require_user_jwt(
    credentials: HTTPAuthorizationCredentials | None = Security(
        bearer_scheme
    ),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    configured_secret = settings.jwt_secret.get_secret_value()

    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT verification is not configured",
        )

    # Java: Decoders.BASE64.decode(jwtSecret)
    # Python must decode the same Base64-encoded secret.
    try:
        signing_key = base64.b64decode(configured_secret)
    except (ValueError, TypeError):
        logger.error("Java JWT signing secret is not valid Base64")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT verification configuration is invalid",
        )

    token = credentials.credentials

    try:
        claims = jwt.decode(
            token,
            key=signing_key,
            algorithms=["HS384"],
            options={
                "require": ["sub", "id", "type", "iat", "exp"],
            },
        )

        # Match Java's parserBuilder().require("type", "ACCESS").
        if claims.get("type") != "ACCESS":
            raise jwt.InvalidTokenError("Not an access token")

        authorities = claims.get("authorities", [])
        if not isinstance(authorities, list):
            raise jwt.InvalidTokenError("Invalid authorities claim")

        roles = []
        for item in authorities:
            if not isinstance(item, dict):
                raise jwt.InvalidTokenError("Invalid authority entry")

            authority = item.get("authority")
            if not isinstance(authority, str):
                raise jwt.InvalidTokenError("Invalid authority value")

            roles.append(authority)

        return {
            "user_id": str(claims["id"]),
            "username": claims["sub"],
            "name": claims.get("fullName", ""),
            "email": claims.get("email", ""),
            "role": roles,
            "access_token": token,
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except jwt.InvalidTokenError as exc:
        logger.warning(
            "Java JWT validation failed: error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT",
            headers={"WWW-Authenticate": "Bearer"},
        )
