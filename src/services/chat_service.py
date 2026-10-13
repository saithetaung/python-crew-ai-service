
import logging
import re

from fastapi import status

from src.providers.bedrock_rag_client import (
    BedrockRagError,
    extract_citations,
)
from src.providers.bedrock_tool_client import (
    BedrockToolError,
)
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

        # Certificate expiry questions, regardless of word order.
        if asks_certificate and asks_expiry:
            return "get_expiring_certifications"

        # Other vessel crew certificate status questions.
        if asks_certificate and asks_vessel and asks_status:
            return "get_vessel_crew_certificate_status"

        return None

    async def run(self, payload) -> ChatResponse:
        if len(payload.message) > self.settings.max_message_chars:
            raise ChatServiceError(
                "Message is too long",
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        key = self.store.base_key(
            payload.actor.tenant_id,
            payload.actor.user_id,
            payload.conversation_id,
        )

        print(
            f"[CHAT] Received request={payload.request_id}; "
            f"message={payload.message!r}",
            flush=True,
        )

        try:
            async with self.store.conversation_lock(key):
                citations = []
                selected_tool = self._select_business_tool(
                    payload.message
                )

                print(
                    f"[CHAT] Selected tool={selected_tool}",
                    flush=True,
                )

                if (
                    self.tool_client is not None
                    and selected_tool is not None
                ):
                    print(
                        f"[CHAT] Calling tool client: {selected_tool}",
                        flush=True,
                    )

                    result = await self.tool_client.ask(
                        question=payload.message,
                        user_id=payload.actor.user_id,
                        forced_tool_name=selected_tool,
                    )

                    answer = result.get("answer", "").strip()
                    if not answer:
                        answer = (
                            "The tool request completed, but no answer "
                            "was returned."
                        )

                    latency = result["latency"]

                    print(
                        f"[CHAT] Tool flow completed; "
                        f"tool_calls={result.get('toolCalls', [])}",
                        flush=True,
                    )

                else:
                    if selected_tool and self.tool_client is None:
                        print(
                            "[CHAT] WARNING: a business tool was selected "
                            "but tool_client is not configured.",
                            flush=True,
                        )

                    print("[CHAT] Using existing RAG client", flush=True)

                    session_id = (
                        await self.store.get_bedrock_session_id(key)
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
                str(exc),
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
