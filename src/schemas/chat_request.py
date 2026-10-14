
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    request_id: str = Field(alias="requestId", min_length=1, max_length=128)
    conversation_id: str = Field(
        alias="conversationId",
        min_length=1,
        max_length=256,
    )
    message: str = Field(min_length=1)

    @field_validator("request_id", "conversation_id", "message")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Value must not be blank")

        return value
