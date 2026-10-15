
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

        logger.warning(
            "[INIT] ChatService initialized | tool_client_available=%s",
            self.tool_client is not None,
        )

    @staticmethod
    def _select_business_tool(message: str) -> str | None:
        text = message.casefold()

        asks_certificate = bool(
            re.search(r"\b(certificates?|certifications?)\b", text)
        )
        asks_vessel = bool(
            re.search(r"\b(vessels?|ships?)\b", text)
        )
        asks_contract = bool(
            re.search(
                r"\b(contracts?|employment agreements?)\b",
                text,
            )
        )
        asks_expiry = bool(
            re.search(
                r"\b(expir\w*|expiry|expiration|due|"
                r"expiring|renewal|renewals)\b",
                text,
            )
        )

        if asks_contract and asks_expiry:
            return "get_expired_contracts"

        if asks_certificate and asks_expiry:
            return "get_expiring_certificates"

        if asks_vessel and asks_certificate:
            return None

        if asks_vessel:
            return "list_vessels"

        return None

    async def run(self, payload, auth_context: dict) -> ChatResponse:
        if len(payload.message) > self.settings.max_message_chars:
            raise ChatServiceError(
                "Message is too long",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        user_id = auth_context["user_id"]

        key = self.store.base_key(
            user_id,
            payload.conversation_id,
        )

        logger.warning(
            "[FLOW 1] Chat request received | request_id=%s "
            "conversation_id=%s user_id=%s",
            payload.request_id,
            payload.conversation_id,
            user_id,
        )

        try:
            async with self.store.conversation_lock(key):
                citations = []

                selected_tool = self._select_business_tool(
                    payload.message
                )

                logger.warning(
                    "[FLOW 2] Routing decision | request_id=%s "
                    "selected_tool=%s tool_client_available=%s",
                    payload.request_id,
                    selected_tool or "RAG",
                    self.tool_client is not None,
                )

                if (
                    self.tool_client is not None
                    and selected_tool is not None
                ):
                    logger.warning(
                        "[FLOW 3] Starting business-tool workflow | "
                        "request_id=%s tool=%s",
                        payload.request_id,
                        selected_tool,
                    )

                    result = await self.tool_client.ask(
                        question=payload.message,
                        user_id=user_id,
                        forced_tool_name=selected_tool,
                        auth_context=auth_context,
                        request_id=payload.request_id,
                    )

                    answer = result.get("answer", "").strip()

                    if not answer:
                        answer = (
                            "The tool request completed, but no answer "
                            "was returned."
                        )

                    latency = result["latency"]

                    logger.warning(
                        "[FLOW 9] Business-tool workflow completed | "
                        "request_id=%s answer_chars=%s",
                        payload.request_id,
                        len(answer),
                    )

                else:
                    if selected_tool and self.tool_client is None:
                        logger.error(
                            "[ROUTING ERROR] A business tool was selected, "
                            "but tool_client is not configured | request_id=%s",
                            payload.request_id,
                        )

                    logger.warning(
                        "[FLOW 3] Starting RAG workflow | request_id=%s",
                        payload.request_id,
                    )

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

                    logger.warning(
                        "[FLOW 9] RAG workflow completed | request_id=%s "
                        "answer_chars=%s citation_count=%s",
                        payload.request_id,
                        len(answer),
                        len(citations),
                    )

                logger.warning(
                    "[FLOW 10] Saving completed conversation to Redis | "
                    "request_id=%s",
                    payload.request_id,
                )

                await self.store.save_completed_turn(
                    key,
                    payload.message,
                    answer,
                )

                logger.warning(
                    "[FLOW 11] Preparing ChatResponse | request_id=%s",
                    payload.request_id,
                )

                return ChatResponse(
                    requestId=payload.request_id,
                    conversationId=payload.conversation_id,
                    answer=answer,
                    citations=citations,
                    latencySeconds=round(latency, 3),
                )

        except TimeoutError as exc:
            logger.warning(
                "Conversation lock timed out | request_id=%s",
                payload.request_id,
            )
            raise ChatServiceError(
                "This conversation is busy; retry shortly.",
                409,
            ) from exc

        except BedrockToolError as exc:
            logger.exception(
                "Bedrock tool request failed | request_id=%s",
                payload.request_id,
            )
            raise ChatServiceError(
                "The AI service could not complete the tool request.",
                503,
            ) from exc

        except BedrockRagError as exc:
            logger.exception(
                "Bedrock RAG request failed | request_id=%s",
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
                "Unexpected chat failure | request_id=%s",
                payload.request_id,
            )
            raise ChatServiceError(
                "The AI service encountered an unexpected error.",
                500,
            ) from exc
