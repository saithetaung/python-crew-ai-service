import secrets
from fastapi import Header, HTTPException, Request
from src.core.config import get_settings


async def require_internal_service(
    x_internal_service_token: str | None = Header(default=None),
):
    expected = get_settings().internal_api_token.get_secret_value()
    if not expected:
        raise HTTPException(503, "Internal service authentication is not configured")
    if not x_internal_service_token or not secrets.compare_digest(expected, x_internal_service_token):
        raise HTTPException(401, "Invalid service credentials")


def get_chat_service(request: Request):
    service = request.app.state.resources.chat_service
    if service is None:
        raise HTTPException(503, "AI service is not ready")
    return service
