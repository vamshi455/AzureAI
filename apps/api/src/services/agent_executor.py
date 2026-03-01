"""
Agent Executor - ReAct-style tool-calling loop for AI agents.
Sends messages to Azure OpenAI, processes tool_calls, executes tools, and loops.
"""

import json
import logging
from typing import Any, Callable, Awaitable

from services.ai_service import AIFoundryService

logger = logging.getLogger(__name__)

# Safety limit to prevent infinite tool-calling loops
MAX_ITERATIONS = 10


class AgentExecutor:
    """
    ReAct-style agent executor that runs a tool-calling loop.

    1. Send messages to the LLM with tool definitions
    2. If the LLM returns tool_calls, execute them
    3. Append tool results as tool messages
    4. Loop until the LLM returns a final text response (no tool_calls)
    """

    def __init__(
        self,
        ai_service: AIFoundryService,
        tool_handlers: dict[str, Callable[..., Awaitable[Any]]],
    ):
        self._ai_service = ai_service
        self._tool_handlers = tool_handlers

    async def run(
        self,
        deployment_name: str,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Execute the agent loop until a final response or max iterations.

        Returns:
            dict with 'content' (final text), 'usage' (token counts),
            'iterations' (number of loops), 'tool_calls_made' (list of tool names).
        """
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        tool_calls_made: list[str] = []

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"Agent iteration {iteration + 1}/{MAX_ITERATIONS}")

            result = await self._ai_service.chat_completion(
                deployment_name=deployment_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools if tools else None,
            )

            # Accumulate token usage
            usage = result.get("usage", {})
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)

            choice = result.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            # If no tool_calls, this is the final response
            if finish_reason != "tool_calls" and not message.get("tool_calls"):
                return {
                    "content": message.get("content", ""),
                    "usage": total_usage,
                    "iterations": iteration + 1,
                    "tool_calls_made": tool_calls_made,
                }

            # Process tool calls
            tool_calls = message.get("tool_calls", [])
            if not tool_calls:
                return {
                    "content": message.get("content", ""),
                    "usage": total_usage,
                    "iterations": iteration + 1,
                    "tool_calls_made": tool_calls_made,
                }

            # Append the assistant message with tool_calls
            messages.append(message)

            # Execute each tool call and append results
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                tool_calls_made.append(func_name)

                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    arguments = {}

                logger.info(f"Executing tool: {func_name}({arguments})")

                handler = self._tool_handlers.get(func_name)
                if handler:
                    try:
                        tool_result = await handler(**arguments)
                        result_str = json.dumps(tool_result, default=str)
                    except Exception as e:
                        logger.error(f"Tool '{func_name}' failed: {e}", exc_info=True)
                        result_str = json.dumps({"error": str(e)})
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {func_name}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })

        # Hit max iterations
        logger.warning(f"Agent hit max iterations ({MAX_ITERATIONS})")
        return {
            "content": "I was unable to complete the analysis within the allowed steps. Please try a more specific question.",
            "usage": total_usage,
            "iterations": MAX_ITERATIONS,
            "tool_calls_made": tool_calls_made,
        }
