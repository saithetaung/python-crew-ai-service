from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)
    user_id: str = Field(min_length=1, max_length=128, alias="userId")
    tenant_id: str = Field(min_length=1, max_length=128, alias="tenantId")


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)
    request_id: str = Field(min_length=8, max_length=128, alias="requestId")
    conversation_id: str = Field(min_length=8, max_length=128, alias="conversationId")
    message: str = Field(min_length=1, max_length=8000)
    actor: ActorContext

    @field_validator("message")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value.strip()
