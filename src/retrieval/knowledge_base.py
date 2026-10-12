import asyncio
import logging

logger = logging.getLogger(__name__)

class KnowledgeBaseError(Exception):
    pass

class KnowledgeBaseRetriever:
    def __init__(self, client, knowledge_base_id: str, number_of_results: int = 5):
        self.client, self.knowledge_base_id, self.number_of_results = client, knowledge_base_id, number_of_results

    async def retrieve(self, query: str) -> list[dict]:
        if not self.knowledge_base_id:
            raise KnowledgeBaseError("BEDROCK_KNOWLEDGE_BASE_ID is not configured")
        try:
            response = await asyncio.to_thread(
                self.client.retrieve,
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={"vectorSearchConfiguration": {
                    "numberOfResults": self.number_of_results
                }},
            )
        except Exception as exc:
            logger.exception("Knowledge Base retrieval failed")
            raise KnowledgeBaseError("Knowledge retrieval is temporarily unavailable") from exc
        output = []
        for item in response.get("retrievalResults", []):
            text = item.get("content", {}).get("text")
            if not text:
                continue
            location = item.get("location", {})
            s3 = location.get("s3Location", {})
            metadata = item.get("metadata", {})
            output.append({
                "text": text,
                "score": item.get("score"),
                "source_uri": s3.get("uri") or metadata.get("source_uri"),
                "title": metadata.get("title") or metadata.get("document_title"),
                "location": metadata.get("page") or metadata.get("section"),
            })
        return output
