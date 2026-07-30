"""Contract for a tool-calling chat agent.

Deliberately generic — this interface knows nothing about watchlists or
portfolios. The tool definitions and the dispatch function (what actually
happens when a tool is called) are supplied by the caller, same
Dependency Inversion principle as everywhere else: the LLM-loop
mechanics live here, the business logic lives in the use case that
calls this.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Iterator


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict


@dataclass(frozen=True, slots=True)
class ChatResult:
    reply: str
    tool_calls_made: int


class ChatAgent(ABC):
    @abstractmethod
    def run(
        self,
        system_prompt: str,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        dispatch: Callable[[str, dict], Any],
    ) -> ChatResult:
        """Runs the conversation, including any tool-use rounds, until
        the model produces a final text-only reply. `dispatch` is called
        once per tool the model requests, with (tool_name, tool_input),
        and must return a JSON-serializable result.
        """

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        dispatch: Callable[[str, dict], Any],
    ) -> Iterator[str]:
        """Same tool-resolution behavior as run(), but yields text chunks
        as they're generated for the final reply, instead of returning
        the whole thing at once. Tool-resolution rounds happen the same
        way under the hood — only the last, no-more-tools-needed turn
        streams token-by-token to the caller.
        """


class ChatAgentError(Exception):
    pass
