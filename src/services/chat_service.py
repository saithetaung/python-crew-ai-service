import logging
from fastapi import status

from src.providers.bedrock_rag_client import BedrockRagError, extract_citations
from src.schemas.chat_response import ChatResponse, Citation

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    def __init__(self, public_message: str, status_code: int = 503):
        self.public_message = public_message
        self.status_code = status_code
        super().__init__(public_message)


class ChatService:
    def __init__(self, settings, store, rag):
        self.settings = settings
        self.store = store
        self.rag = rag

    async def run(self, payload):
        if len(payload.message) > self.settings.max_message_chars:
            raise ChatServiceError("Message is too long", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        key = self.store.base_key(
            payload.actor.tenant_id,
            payload.actor.user_id,
            payload.conversation_id,
        )
        try:
            async with self.store.conversation_lock(key):
                session_id = await self.store.get_bedrock_session_id(key)
                result = await self.rag.ask(payload.message, session_id=session_id)
                raw = result["response"]
                answer = raw.get("output", {}).get("text", "").strip()
                if not answer:
                    answer = "I couldn't find enough information about that in the available documents."

                returned_session_id = raw.get("sessionId")
                if returned_session_id:
                    await self.store.set_bedrock_session_id(key, returned_session_id)

                # Store completed QA pairs for bounded application-side memory/diagnostics.
                # Bedrock RetrieveAndGenerate uses sessionId for its own context; the unchanged
                # prompt does not receive this transcript as a custom history variable.
                await self.store.save_completed_turn(key, payload.message, answer)

                citations_raw = extract_citations(raw)
                citations = [Citation(**item) for item in citations_raw]
                return ChatResponse(
                    requestId=payload.request_id,
                    conversationId=payload.conversation_id,
                    answer=answer,
                    citations=citations,
                    latencySeconds=round(result["latency"], 3),
                )
        except TimeoutError as exc:
            raise ChatServiceError("This conversation is busy; retry shortly.", 409) from exc
        except BedrockRagError as exc:
            logger.warning("Bedrock RAG request failed; request_id=%s", payload.request_id)
            raise ChatServiceError(str(exc), 503) from exc
        except ChatServiceError:
            raise
        except Exception as exc:
            logger.exception("Unexpected chat failure; request_id=%s", payload.request_id)
            raise ChatServiceError("The AI service encountered an unexpected error.", 500) from exc
