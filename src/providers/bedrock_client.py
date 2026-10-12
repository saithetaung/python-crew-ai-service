import asyncio
import logging
from src.tools.registry import BEDROCK_TOOL_CONFIG, TOOL_NAMES

logger = logging.getLogger(__name__)

class BedrockCallError(Exception):
    pass

class BedrockClient:
    def __init__(self, client, model_id: str, max_tool_rounds: int = 4):
        self.client, self.model_id, self.max_tool_rounds = client, model_id, max_tool_rounds

    async def converse(self, *, system_prompt: str, messages: list[dict], tool_executor):
        if not self.model_id:
            raise BedrockCallError("BEDROCK_MODEL_ID is not configured")
        request_messages = list(messages)
        used = []
        for _ in range(self.max_tool_rounds + 1):
            kwargs = {
                "modelId": self.model_id,
                "system": [{"text": system_prompt}],
                "messages": request_messages,
                "inferenceConfig": {"temperature": 0.1, "maxTokens": 1800},
            }
            if BEDROCK_TOOL_CONFIG:
                kwargs["toolConfig"] = {"tools": BEDROCK_TOOL_CONFIG}
            try:
                response = await asyncio.to_thread(self.client.converse, **kwargs)
            except Exception as exc:
                logger.exception("Bedrock Converse failed")
                raise BedrockCallError("The AI model is temporarily unavailable") from exc
            message = response.get("output", {}).get("message", {})
            content = message.get("content", [])
            tool_uses = [part["toolUse"] for part in content if "toolUse" in part]
            if not tool_uses:
                answer = "\n".join(part.get("text", "") for part in content if "text" in part).strip()
                if not answer:
                    raise BedrockCallError("The model returned an empty response")
                return answer, used
            request_messages.append(message)
            results = []
            for call in tool_uses:
                name, call_id = call.get("name", ""), call.get("toolUseId", "")
                if name not in TOOL_NAMES:
                    result = {"error": "Tool is not allowed"}
                else:
                    try:
                        result = await tool_executor(name, call.get("input", {}))
                        used.append(name)
                    except Exception:
                        logger.exception("Tool call failed: %s", name)
                        result = {"error": "Tool execution failed or data was unavailable"}
                results.append({"toolResult": {
                    "toolUseId": call_id,
                    "content": [{"json": result}],
                    "status": "error" if "error" in result else "success",
                }})
            request_messages.append({"role": "user", "content": results})
        raise BedrockCallError("The AI reached its maximum tool-call limit")
