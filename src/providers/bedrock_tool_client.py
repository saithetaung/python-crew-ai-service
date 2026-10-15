import asyncio
import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from src.tools.registry import BEDROCK_TOOL_CONFIG, TOOL_NAMES

logger = logging.getLogger(__name__)


class BedrockToolError(Exception):
    """Raised when Bedrock tool execution fails."""


class BedrockToolClient:
    MAX_TOOL_ROUNDS = 5

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

    def _log_java_response(
        self,
        *,
        tool_name: str,
        request_id: str,
        data: Any,
    ) -> None:
        """Log Java response metadata and optionally its raw JSON body."""
        if (
            os.getenv("LOG_JAVA_API_RESPONSE_BODY", "false").lower()
            == "true"
        ):
            logger.warning(
                "[FLOW 5] Java raw JSON response BEFORE Bedrock | "
                "request_id=%s tool=%s\n%s",
                request_id,
                tool_name,
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            )
        else:
            logger.info(
                "[FLOW 5] Java returned data | request_id=%s "
                "tool=%s response_type=%s",
                request_id,
                tool_name,
                type(data).__name__,
            )

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
        }

        if request_id:
            headers["X-Request-ID"] = request_id

        url = f"{self.java_api_base_url}{path}"

        logger.info(
            "[FLOW 4a] Calling Java API | tool=%s path=%s request_id=%s",
            tool_name,
            path,
            request_id,
        )

        started = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
            ) as http:
                response = await http.get(
                    url,
                    params=params,
                    headers=headers,
                )

            elapsed_ms = round(
                (time.perf_counter() - started) * 1000,
                2,
            )

            logger.info(
                "[FLOW 4b] Java API response received | tool=%s "
                "status=%s elapsed_ms=%s request_id=%s",
                tool_name,
                response.status_code,
                elapsed_ms,
                request_id,
            )

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as exc:
                raise BedrockToolError(
                    "Java API returned invalid JSON"
                ) from exc

            self._log_java_response(
                tool_name=tool_name,
                request_id=request_id,
                data=data,
            )

            logger.info(
                "[FLOW 6] Python received Java data | tool=%s request_id=%s",
                tool_name,
                request_id,
            )

            return data

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

        except httpx.TimeoutException as exc:
            logger.warning(
                "Java API timed out | tool=%s request_id=%s",
                tool_name,
                request_id,
            )
            raise BedrockToolError(
                "Java API request timed out"
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
        base_tool_config = {"tools": BEDROCK_TOOL_CONFIG}

        logger.info(
            "[FLOW 1] Starting Bedrock tool workflow | request_id=%s "
            "user_id=%s forced_tool=%s",
            request_id,
            user_id,
            forced_tool_name or "automatic",
        )

        try:
            for step in range(self.MAX_TOOL_ROUNDS):
                # Force the selected tool only for the first request.
                # Subsequent requests must be allowed to produce a final
                # answer instead of repeatedly invoking the same tool.
                tool_config = dict(base_tool_config)

                if forced_tool_name and step == 0:
                    tool_config["toolChoice"] = {
                        "tool": {"name": forced_tool_name}
                    }

                logger.info(
                    "[FLOW 2] Sending request to Bedrock Converse | "
                    "request_id=%s round=%s message_count=%s "
                    "tool_choice=%s",
                    request_id,
                    step + 1,
                    len(messages),
                    forced_tool_name if step == 0 else "automatic",
                )

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

                stop_reason = response.get("stopReason", "unknown")

                logger.info(
                    "[FLOW 3] Bedrock response received | "
                    "request_id=%s round=%s stop_reason=%s",
                    request_id,
                    step + 1,
                    stop_reason,
                )

                message = response.get("output", {}).get("message")

                if not isinstance(message, dict):
                    raise BedrockToolError(
                        "Bedrock returned an invalid assistant message"
                    )

                messages.append(message)

                tool_uses = [
                    block["toolUse"]
                    for block in message.get("content", [])
                    if isinstance(block, dict)
                    and "toolUse" in block
                ]

                logger.info(
                    "[FLOW 4] Bedrock tool requests | request_id=%s "
                    "round=%s tools=%s",
                    request_id,
                    step + 1,
                    [item.get("name") for item in tool_uses],
                )

                if not tool_uses:
                    answer = "\n".join(
                        block["text"]
                        for block in message.get("content", [])
                        if isinstance(block, dict)
                        and isinstance(block.get("text"), str)
                    ).strip()

                    if not answer:
                        answer = "The model returned no text answer."

                    latency = time.perf_counter() - start

                    logger.info(
                        "[FLOW 8] Bedrock final answer received | "
                        "request_id=%s answer_chars=%s latency_seconds=%.3f",
                        request_id,
                        len(answer),
                        latency,
                    )

                    return {
                        "answer": answer,
                        "toolCalls": tool_calls,
                        "latency": latency,
                    }

                tool_results = []

                for tool_use in tool_uses:
                    name = tool_use.get("name")
                    arguments = tool_use.get("input", {})
                    tool_use_id = tool_use.get("toolUseId")

                    logger.info(
                        "[FLOW 4c] Processing tool request | request_id=%s "
                        "tool=%s tool_use_id=%s",
                        request_id,
                        name,
                        tool_use_id,
                    )

                    if (
                        not isinstance(arguments, dict)
                        or name not in TOOL_NAMES
                        or not isinstance(tool_use_id, str)
                        or not tool_use_id
                    ):
                        result = {
                            "error": "Invalid or unsupported tool call."
                        }
                        result_status = "error"

                    else:
                        try:
                            result = await self._call_java(
                                tool_name=name,
                                arguments=arguments,
                                user_jwt=user_jwt,
                                request_id=request_id,
                            )
                            result_status = "success"

                        except (BedrockToolError, ValueError, TypeError) as exc:
                            logger.warning(
                                "Business tool failed | tool=%s "
                                "error_type=%s request_id=%s",
                                name,
                                type(exc).__name__,
                                request_id,
                            )

                            result = {
                                "error": (
                                    "Business data could not be retrieved. "
                                    "Explain the failure to the user. "
                                    "Do not repeat the same tool call."
                                )
                            }
                            result_status = "error"

                    tool_calls.append({
                        "name": name,
                        "arguments": arguments,
                    })

                    # Converse toolResult content must contain a list of
                    # content blocks. Preserve the matching toolUseId.
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [{"json": {"result": result}}],
                            "status": result_status,
                        }
                    })

                logger.info(
                    "[FLOW 7] Sending Java tool results to Bedrock | "
                    "request_id=%s result_count=%s",
                    request_id,
                    len(tool_results),
                )

                messages.append({
                    "role": "user",
                    "content": tool_results,
                })

            logger.error(
                "Bedrock exceeded maximum tool rounds | request_id=%s "
                "max_rounds=%s tool_calls=%s",
                request_id,
                self.MAX_TOOL_ROUNDS,
                [call["name"] for call in tool_calls],
            )

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
