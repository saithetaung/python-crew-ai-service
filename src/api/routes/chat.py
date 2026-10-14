
from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_chat_service,
    require_internal_service,
)
from src.api.jwt_auth import require_user_jwt
from src.schemas.chat_request import ChatRequest
from src.schemas.chat_response import ChatResponse

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_internal_service)],
)
async def chat(
    payload: ChatRequest,
    auth_context: dict = Depends(require_user_jwt),
    service=Depends(get_chat_service),
) -> ChatResponse:
    return await service.run(
        payload,
        auth_context=auth_context,
    )
