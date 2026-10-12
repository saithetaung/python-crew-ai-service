from fastapi import APIRouter, Depends, HTTPException
from src.api.dependencies import get_chat_service, require_internal_service
from src.schemas.chat_request import ChatRequest
from src.schemas.chat_response import ChatResponse
from src.services.chat_service import ChatServiceError

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_internal_service)])
async def chat(payload: ChatRequest, service=Depends(get_chat_service)):
    try:
        return await service.run(payload)
    except ChatServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
