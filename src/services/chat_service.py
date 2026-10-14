
import logging
import re

from fastapi import status

from src.providers.bedrock_rag_client import (
    BedrockRagError,
    extract_citations,
)
from src.providers.bedrock_tool_client import BedrockToolError
from src.schemas.chat_response import ChatResponse, Citation

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    def __init__(self, public_message: str, status_code: int = 503):
        self.public_message = public_message
        self.status_code = status_code
        super().__init__(public_message)


class ChatService:
    def __init__(self, settings, store, rag, tool_client=None):
        self.settings = settings
        self.store = store
        self.rag = rag
        self.tool_client = tool_client

    @staticmethod
    def _select_business_tool(message: str) -> str | None:
        text = message.casefold()

        asks_certificate = bool(
            re.search(r"\b(certificates?|certifications?)\b", text)
        )
        asks_vessel = bool(re.search(r"\bvessel\b", text))
        asks_status = bool(
            re.search(r"\b(status|statuses|valid|expired)\b", text)
        )
        asks_crew = bool(re.search(r"\bcrew\b", text))
        asks_expiry = bool(
            re.search(r"\b(expir\w*|expiry|expiration|due)\b", text)
        )

        # Vessel certificate questions take priority.
        if asks_certificate and asks_vessel and (
            asks_status or asks_crew
        ):
            return "get_vessel_crew_certificate_status"

        # Current-vessel questions.
        if re.search(
            r"\b(current|my)\s+vessel\b|\bwhich vessel\b",
            text,
        ):
            return "get_current_vessel"

        # Certificate expiry questions.
        if asks_certificate and asks_expiry:
            return "get_expiring_certifications"

        # Other vessel crew certificate status questions.
        if asks_certificate and asks_vessel and asks_status:
            return "get_vessel_crew_certificate_status"

        return None

    async def run(self, payload, auth_context: dict) -> ChatResponse:
        """
        Process a chat request using identity from a validated JWT.

        auth_context is supplied by require_user_jwt, not by the
        request JSON body.
        """
        if len(payload.message) > self.settings.max_message_chars:
            raise ChatServiceError(
                "Message is too long",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        user_id = auth_context["user_id"]

        # No tenant or actor fields are used.
        # Update RedisConversationStore.base_key to accept these 2 arguments.
        key = self.store.base_key(
            user_id,
            payload.conversation_id,
        )

        logger.info(
            "Chat request received; request_id=%s conversation_id=%s",
            payload.request_id,
            payload.conversation_id,
        )

        try:
            async with self.store.conversation_lock(key):
                citations = []
                selected_tool = self._select_business_tool(
                    payload.message
                )

                logger.info(
                    "Chat routing selected; request_id=%s tool=%s",
                    payload.request_id,
                    selected_tool or "rag",
                )

                if self.tool_client is not None and selected_tool is not None:
                    # The authenticated identity comes from the validated JWT.
                    # The tool client must not accept identity from the LLM.
                    result = await self.tool_client.ask(
                        question=payload.message,
                        user_id=user_id,
                        forced_tool_name=selected_tool,
                        auth_context=auth_context,
                    )

                    answer = result.get("answer", "").strip()

                    if not answer:
                        answer = (
                            "The tool request completed, but no answer "
                            "was returned."
                        )

                    latency = result["latency"]

                    logger.info(
                        "Tool flow completed; request_id=%s",
                        payload.request_id,
                    )

                else:
                    if selected_tool and self.tool_client is None:
                        logger.warning(
                            "Business tool selected but tool client is "
                            "not configured; request_id=%s",
                            payload.request_id,
                        )

                    # Preserve the existing Bedrock RAG behavior.
                    session_id = await self.store.get_bedrock_session_id(
                        key
                    )

                    result = await self.rag.ask(
                        payload.message,
                        session_id=session_id,
                    )

                    raw = result["response"]

                    answer = (
                        raw.get("output", {}).get("text", "").strip()
                    )

                    if not answer:
                        answer = (
                            "I couldn't find enough information about "
                            "that in the available documents."
                        )

                    returned_session_id = raw.get("sessionId")

                    if returned_session_id:
                        await self.store.set_bedrock_session_id(
                            key,
                            returned_session_id,
                        )

                    citations = [
                        Citation(**item)
                        for item in extract_citations(raw)
                    ]

                    latency = result["latency"]

                # Save only the completed user/assistant turn.
                # Never save the JWT or auth_context in Redis.
                await self.store.save_completed_turn(
                    key,
                    payload.message,
                    answer,
                )

                return ChatResponse(
                    requestId=payload.request_id,
                    conversationId=payload.conversation_id,
                    answer=answer,
                    citations=citations,
                    latencySeconds=round(latency, 3),
                )

        except TimeoutError as exc:
            raise ChatServiceError(
                "This conversation is busy; retry shortly.",
                409,
            ) from exc

        except BedrockToolError as exc:
            logger.warning(
                "Bedrock tool request failed; request_id=%s",
                payload.request_id,
            )
            raise ChatServiceError(
                "The AI service could not complete the tool request.",
                503,
            ) from exc

        except BedrockRagError as exc:
            logger.warning(
                "Bedrock RAG request failed; request_id=%s",
                payload.request_id,
            )
            raise ChatServiceError(
                "The AI service could not retrieve an answer.",
                503,
            ) from exc

        except ChatServiceError:
            raise

        except Exception as exc:
            logger.exception(
                "Unexpected chat failure; request_id=%s",
                payload.request_id,
            )
            raise ChatServiceError(
                "The AI service encountered an unexpected error.",
                500,
            ) from exc
