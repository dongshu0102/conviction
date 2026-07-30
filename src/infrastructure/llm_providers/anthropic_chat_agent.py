"""Anthropic (Claude) adapter for tool-calling chat.

This is the only module that knows Anthropic's specific tool-use wire
format (content blocks, tool_use/tool_result types) — same quarantine
principle as the FMP and research/brief adapters.
"""
from __future__ import annotations

import json
import logging
from typing import Iterator

import anthropic

from src.application.interfaces.chat_agent import (
    ChatAgent,
    ChatAgentError,
    ChatResult,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6  # safety cap — prevents a runaway tool-calling loop


class AnthropicChatAgent(ChatAgent):
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        self._settings = settings
        self._client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def run(self, system_prompt, messages, tools, dispatch):
        anthropic_messages: list[dict] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

        tool_calls_made = 0
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = self._client.messages.create(
                    model=self._settings.anthropic_model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=anthropic_messages,
                    tools=anthropic_tools,
                )
            except anthropic.APIError as exc:
                raise ChatAgentError(f"Anthropic API request failed: {exc}") from exc

            if response.stop_reason != "tool_use":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return ChatResult(reply="".join(text_blocks).strip(), tool_calls_made=tool_calls_made)

            # Model wants to use one or more tools — execute each via the
            # supplied dispatch function, then feed results back.
            # Same defensive filtering as stream() below — a thinking
            # block surfacing here and being echoed back verbatim would
            # hit the identical API validation error real usage found
            # in the streaming path.
            keep_types = {"text", "tool_use"}
            filtered_content = [b for b in response.content if b.type in keep_types]
            anthropic_messages.append({"role": "assistant", "content": filtered_content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_calls_made += 1
                try:
                    result = dispatch(block.name, block.input)
                    result_text = json.dumps(result, default=str)
                    is_error = False
                except Exception as exc:  # noqa: BLE001 — a tool failure becomes
                    # information fed back to the model, not a crash of the
                    # whole conversation.
                    logger.warning("Tool %s failed: %s", block.name, exc)
                    result_text = str(exc)
                    is_error = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )
            anthropic_messages.append({"role": "user", "content": tool_results})

        raise ChatAgentError(f"Exceeded {MAX_TOOL_ROUNDS} tool-use rounds without a final reply")

    def stream(self, system_prompt, messages, tools, dispatch) -> Iterator[str]:
        """Same tool-resolution logic as run(), but streams the final
        reply's text token-by-token using Anthropic's native streaming
        API, instead of returning it all at once.
        """
        anthropic_messages: list[dict] = [
            {"role": m.role, "content": m.content} for m in messages
        ]
        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                with self._client.messages.stream(
                    model=self._settings.anthropic_model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=anthropic_messages,
                    tools=anthropic_tools,
                ) as stream:
                    # Text deltas during a tool-resolution round are usually
                    # empty or minimal — yielding them unconditionally is
                    # harmless and avoids needing to know in advance
                    # whether a round is "the final one."
                    for text in stream.text_stream:
                        yield text
                    final_message = stream.get_final_message()
            except anthropic.APIError as exc:
                raise ChatAgentError(f"Anthropic API request failed: {exc}") from exc

            if final_message.stop_reason != "tool_use":
                return  # all text already streamed above — done

            # Only tool_use and text blocks need to round-trip into the
            # next request. A "thinking" block showed up in real usage
            # here (streaming mode, unrequested) and echoing it back
            # verbatim triggered a genuine 400 from the API — its
            # re-serialized shape didn't match what the API expects on
            # the way back in. We never asked for extended thinking and
            # don't need to preserve it, so it's filtered out rather
            # than chasing the exact shape the API wants.
            keep_types = {"text", "tool_use"}
            filtered_content = [b for b in final_message.content if b.type in keep_types]
            anthropic_messages.append({"role": "assistant", "content": filtered_content})
            tool_results = []
            for block in final_message.content:
                if block.type != "tool_use":
                    continue
                try:
                    result = dispatch(block.name, block.input)
                    result_text = json.dumps(result, default=str)
                    is_error = False
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Tool %s failed: %s", block.name, exc)
                    result_text = str(exc)
                    is_error = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )
            anthropic_messages.append({"role": "user", "content": tool_results})

        yield "\n\n(Reached the maximum number of steps for this request — try rephrasing or asking something narrower.)"
