from typing import Any, Literal
from pydantic import BaseModel, Field


class Citation(BaseModel):
    model_config = {"populate_by_name": True}
    text: str = ""
    content: str = ""
    location: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_name: str = Field(default="Document", alias="sourceName")


class ChatResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    conversation_id: str = Field(alias="conversationId")
    status: Literal["completed"] = "completed"
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    latency_seconds: float = Field(alias="latencySeconds")
