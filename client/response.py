from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from enum import Enum
import json


# this gonna contain the schema
# of what gonna be returned from the model(llm) can be
class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"  # like the way, message chunks are getting streamed
    MESSAGE_COMPLETE = "message_complete"
    ERROR = "error"

    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETED = "tool_call_complete"


@dataclass
class TextDelta:
    content: str

    # This defines how the object is converted to a string.
    def __str__(self):
        return self.content


@dataclass
class TokenUsage:
    prompt_token: int = 0  # the system prompt also comes under this
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: TokenUsage):
        return TokenUsage(
            prompt_token=self.prompt_token + other.prompt_token,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


@dataclass
class ToolCallDelta:
    call_id: str
    name: str | None = None
    arguments_delta: str = ""


@dataclass
class ToolCall:
    call_id: str
    name: str | None = None
    arguments: str = ""


@dataclass
class ToolResultMessage:
    tool_call_id: str
    content: str
    is_error: bool = False

    def to_open_schema(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "content": self.content,
        }


@dataclass
class StreamEvent:
    type: StreamEventType
    text_delta: TextDelta | None = (
        None  # this can be null, why if there is a tool call or something
    )
    error: str | None = None  # probably its going to be str
    finish_reason: str | None = None
    tool_call_delta: ToolCallDelta | None = None
    tool_call: ToolCall | None = None
    usage: TokenUsage | None = None


def parse_arguments_response(arguments_str: str) -> dict[str, Any]:
    if not arguments_str:
        return {}

    try:
        return json.loads(arguments_str)

    except json.JSONDecodeError:
        print("fcked up")
        return {"raw_arguments": arguments_str}
