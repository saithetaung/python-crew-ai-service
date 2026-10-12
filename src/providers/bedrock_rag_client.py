import asyncio
import time
from typing import Any

from src.prompts.generation_prompt import GENERATION_PROMPT


class BedrockRagError(Exception):
    pass


class BedrockRagClient:
    """Uses the same RetrieveAndGenerate API and prompt as the tested Streamlit app."""

    def __init__(self, client, knowledge_base_id: str, model_arn: str):
        self.client = client
        self.knowledge_base_id = knowledge_base_id
        self.model_arn = model_arn

    async def ask(self, question: str, session_id: str | None = None) -> dict[str, Any]:
        if not self.knowledge_base_id or not self.model_arn:
            raise BedrockRagError("KNOWLEDGE_BASE_ID or MODEL_ARN is not configured")

        request = {
            "input": {"text": question},
            "retrieveAndGenerateConfiguration": {
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": self.knowledge_base_id,
                    "modelArn": self.model_arn,
                    "generationConfiguration": {
                        "promptTemplate": {
                            "textPromptTemplate": GENERATION_PROMPT
                        }
                    },
                },
            },
        }
        if session_id:
            request["sessionId"] = session_id

        start = time.perf_counter()
        try:
            # boto3 is synchronous; keep it off FastAPI's event loop.
            response = await asyncio.to_thread(self.client.retrieve_and_generate, **request)
        except Exception as exc:
            raise BedrockRagError("The AI service could not process the request.") from exc

        return {
            "response": response,
            "latency": time.perf_counter() - start,
        }


def extract_citations(response: dict[str, Any]) -> list[dict[str, Any]]:
    citations = []
    for citation in response.get("citations", []):
        generated = citation.get("generatedResponsePart", {})
        text_part = generated.get("textResponsePart", {})
        for reference in citation.get("retrievedReferences", []):
            citations.append({
                "text": text_part.get("text", ""),
                "content": reference.get("content", {}).get("text", ""),
                "location": reference.get("location", {}),
                "metadata": reference.get("metadata", {}),
                "source_name": get_source_name(reference),
            })
    return citations


def get_source_name(reference: dict[str, Any]) -> str:
    uri = reference.get("location", {}).get("s3Location", {}).get("uri")
    if uri:
        return uri.split("/")[-1]
    metadata = reference.get("metadata", {})
    for key in ("fileName", "filename", "source", "document_name", "documentName", "title"):
        if metadata.get(key):
            return str(metadata[key])
    return "Document"
