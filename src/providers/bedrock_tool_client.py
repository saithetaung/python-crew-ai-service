
import asyncio
import logging
import time
from typing import Any

from src.tools.registry import (
    BEDROCK_TOOL_CONFIG,
    TOOL_NAMES,
    execute_mock_tool,
)

logger = logging.getLogger(__name__)


class BedrockToolError(Exception):
    pass


class BedrockToolClient:
    def __init__(self, client, model_id: str):
        self.client = client
        self.model_id = model_id

    async def ask(
        self,
        question: str,
        user_id: str,
        forced_tool_name: str | None = None,
    ) -> dict[str, Any]:
        if not self.model_id:
            raise BedrockToolError("MODEL_ARN is not configured.")

        if forced_tool_name and forced_tool_name not in TOOL_NAMES:
            raise BedrockToolError("Unknown requested tool.")

        messages = [
            {
                "role": "user",
                "content": [{"text": question}],
            }
        ]

        tool_calls = []
        start = time.perf_counter()

        tool_config = {"tools": BEDROCK_TOOL_CONFIG}

        # Force the expected tool for deterministic integration testing.
        if forced_tool_name:
            tool_config["toolChoice"] = {
                "tool": {"name": forced_tool_name}
            }

        print(
            f"[BEDROCK TOOL] Starting request; "
            f"model={self.model_id}, forced_tool={forced_tool_name}",
            flush=True,
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
                stop_reason = response.get("stopReason")

                print(
                    f"[BEDROCK TOOL] step={step + 1}, "
                    f"stopReason={stop_reason}",
                    flush=True,
                )
                print(
                    f"[BEDROCK TOOL] message={message}",
                    flush=True,
                )

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

                    if not answer:
                        answer = "The model returned no text answer."

                    print(
                        f"[BEDROCK TOOL] Final answer received; "
                        f"tool_calls={tool_calls}",
                        flush=True,
                    )

                    return {
                        "answer": answer,
                        "toolCalls": tool_calls,
                        "latency": time.perf_counter() - start,
                    }

                tool_results = []

                for tool_use in tool_uses:
                    name = tool_use.get("name")
                    arguments = tool_use.get("input", {})
                    tool_use_id = tool_use.get("toolUseId")

                    print(
                        f"[BEDROCK TOOL] Requested tool={name}; "
                        f"arguments={arguments}",
                        flush=True,
                    )

                    if name not in TOOL_NAMES:
                        result = {"error": "Unsupported tool."}
                    else:
                        try:
                            result = execute_mock_tool(
                                name=name,
                                arguments=arguments,
                                user_id=user_id,
                            )
                            print(
                                f"[BEDROCK TOOL] Mock handler succeeded: "
                                f"{name}",
                                flush=True,
                            )
                        except (ValueError, TypeError, KeyError):
                            logger.exception(
                                "Mock tool failed: %s", name
                            )
                            result = {
                                "error": (
                                    "Invalid arguments or mock "
                                    "tool execution failed."
                                )
                            }

                    tool_calls.append(
                        {
                            "name": name,
                            "arguments": arguments,
                        }
                    )

                    tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [{"json": result}],
                            }
                        }
                    )

                # Send tool results back to Bedrock.
                messages.append(
                    {
                        "role": "user",
                        "content": tool_results,
                    }
                )

                # After the initial forced tool call, let the model
                # generate the final answer without forcing another tool.
                if step == 0 and forced_tool_name:
                    tool_config = {"tools": BEDROCK_TOOL_CONFIG}

            raise BedrockToolError(
                "Tool calling exceeded the maximum number of steps."
            )

        except BedrockToolError:
            raise
        except Exception as exc:
            logger.exception("Bedrock Converse tool request failed")
            raise BedrockToolError(
                "Bedrock tool calling failed."
            ) from exc
