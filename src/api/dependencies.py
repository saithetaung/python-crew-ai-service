
import secrets

from fastapi import Header, HTTPException, Request, status
from src.core.config import get_settings


async def require_internal_service(
    x_internal_service_token: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    configured = settings.internal_api_token

    expected = (
        configured.get_secret_value()
        if hasattr(configured, "get_secret_value")
        else str(configured or "")
    )

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service authentication is not configured",
        )

    if not x_internal_service_token or not secrets.compare_digest(
        expected, x_internal_service_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credentials",
        )


def get_chat_service(request: Request):
    service = request.app.state.resources.chat_service

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not ready",
        )

    return service
