
import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from src.tools.registry import BEDROCK_TOOL_CONFIG, TOOL_NAMES

logger = logging.getLogger(__name__)


class BedrockToolError(Exception):
    """Raised when Bedrock tool execution fails."""


class BedrockToolClient:
    def __init__(
        self,
        client,
        model_id: str,
        java_api_base_url: str,
        timeout_seconds: float = 30.0,
    ):
        self.client = client
        self.model_id = model_id
        self.java_api_base_url = java_api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        parsed = urlparse(self.java_api_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("JAVA_API_BASE_URL is invalid")

    @staticmethod
    def _validate_days(arguments: dict[str, Any]) -> int:
        days = arguments.get("days")

        if (
            isinstance(days, bool)
            or not isinstance(days, int)
            or days < 1
        ):
            raise ValueError("days must be a positive integer")

        return days

    async def _call_java(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        user_jwt: str,
        request_id: str,
    ) -> Any:
        if tool_name == "get_expired_contracts":
            path = "/api/dashboard/expired-contracts"
            params = {"days": self._validate_days(arguments)}

        elif tool_name == "get_expiring_certificates":
            path = "/api/dashboard/expiring-certificates"
            params = {"days": self._validate_days(arguments)}

        elif tool_name == "list_vessels":
            path = "/api/vessels"
            params = None

        else:
            raise BedrockToolError("Unsupported business tool")

        if not user_jwt:
            raise BedrockToolError("User JWT is missing")

        headers = {
            "Authorization": f"Bearer {user_jwt}",
            "Accept": "application/json",
            "X-Request-ID": request_id,
        }

        url = f"{self.java_api_base_url}{path}"

        logger.info(
            "Calling Java API: tool=%s path=%s request_id=%s",
            tool_name,
            path,
            request_id,
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds
            ) as http:
                response = await http.get(
                    url,
                    params=params,
                    headers=headers,
                )

            logger.info(
                "Java API response: tool=%s status=%s request_id=%s",
                tool_name,
                response.status_code,
                request_id,
            )

            response.raise_for_status()

            try:
                return response.json()
            except ValueError as exc:
                raise BedrockToolError(
                    "Java API returned invalid JSON"
                ) from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Java API returned HTTP %s for tool=%s request_id=%s",
                exc.response.status_code,
                tool_name,
                request_id,
            )
            raise BedrockToolError(
                f"Java API returned HTTP {exc.response.status_code}"
            ) from exc

        except httpx.RequestError as exc:
            logger.warning(
                "Java API connection failed: tool=%s type=%s request_id=%s",
                tool_name,
                type(exc).__name__,
                request_id,
            )
            raise BedrockToolError(
                "Could not connect to Java API"
            ) from exc

    async def ask(
        self,
        question: str,
        user_id: str,
        forced_tool_name: str | None = None,
        auth_context: dict[str, Any] | None = None,
        request_id: str = "",
    ) -> dict[str, Any]:
        if not self.model_id:
            raise BedrockToolError("MODEL_ARN is not configured")

        if forced_tool_name and forced_tool_name not in TOOL_NAMES:
            raise BedrockToolError("Unknown requested tool")

        auth_context = auth_context or {}
        user_jwt = auth_context.get("access_token")

        if not isinstance(user_jwt, str) or not user_jwt:
            raise BedrockToolError(
                "Validated user JWT is unavailable"
            )

        messages = [
            {
                "role": "user",
                "content": [{"text": question}],
            }
        ]

        tool_calls = []
        start = time.perf_counter()
        tool_config = {"tools": BEDROCK_TOOL_CONFIG}

        if forced_tool_name:
            tool_config["toolChoice"] = {
                "tool": {"name": forced_tool_name}
            }

        logger.info(
            "Starting Bedrock tool request: tool=%s request_id=%s",
            forced_tool_name,
            request_id,
        )

        try:
            for step in range(5):
                response = await asyncio.to_thread(
                    self.client.converse,
                    modelId=self.model_id,
                    messages=messages,
                    toolConfig=tool_config,
                    inferenceConfig={
                        "maxTokens": 800,
                        "temperature": 0.1,
                    },
                )

                message = response["output"]["message"]
                messages.append(message)

                tool_uses = [
                    block["toolUse"]
                    for block in message.get("content", [])
                    if "toolUse" in block
                ]

                if not tool_uses:
                    answer = "\n".join(
                        block["text"]
                        for block in message.get("content", [])
                        if "text" in block
                    ).strip()

                    return {
                        "answer": (
                            answer or "The model returned no text answer."
                        ),
                        "toolCalls": tool_calls,
                        "latency": time.perf_counter() - start,
                    }

                tool_results = []

                for tool_use in tool_uses:
                    name = tool_use.get("name")
                    arguments = tool_use.get("input", {})
                    tool_use_id = tool_use.get("toolUseId")

                    if (
                        not isinstance(arguments, dict)
                        or name not in TOOL_NAMES
                        or not tool_use_id
                    ):
                        result = {"error": "Invalid or unsupported tool call."}
                    else:
                        try:
                            result = await self._call_java(
                                tool_name=name,
                                arguments=arguments,
                                user_jwt=user_jwt,
                                request_id=request_id,
                            )
                        except (BedrockToolError, ValueError, TypeError):
                            logger.warning(
                                "Business tool failed: tool=%s request_id=%s",
                                name,
                                request_id,
                            )
                            result = {
                                "error": (
                                    "Business data could not be retrieved. "
                                    "Please try again later."
                                )
                            }

                    tool_calls.append({
                        "name": name,
                        "arguments": arguments,
                    })

                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"json": result}],
                        }
                    })

                messages.append({
                    "role": "user",
                    "content": tool_results,
                })

                # After a forced initial tool call, allow Bedrock
                # to generate the final answer normally.
                if step == 0 and forced_tool_name:
                    tool_config = {"tools": BEDROCK_TOOL_CONFIG}

            raise BedrockToolError(
                "Tool calling exceeded the maximum number of steps"
            )

        except BedrockToolError:
            raise
        except Exception as exc:
            logger.exception(
                "Bedrock Converse tool request failed; request_id=%s",
                request_id,
            )
            raise BedrockToolError(
                "Bedrock tool calling failed"
            ) from exc
