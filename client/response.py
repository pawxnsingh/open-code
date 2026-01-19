from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

# this gonna contain the schema 
# of what gonna be returned from the model(llm) can be
class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta" # like the way, message chunks are getting streamed
    MESSAGE_COMPLETE = "message_complete"
    
    ERROR = "error"
 
@dataclass
class TextDelta:
    content: str
    
    # This defines how the object is converted to a string.
    def __str__(self):
        return self.content
    
@dataclass
class TokenUsage:
    prompt_token: int = 0 # the system prompt also comes under this
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    
    def __add__(self, other: TokenUsage):
        return TokenUsage(
            prompt_token= self.prompt_token + other.prompt_token,
            completion_tokens= self.completion_tokens + other.completion_tokens,
            total_tokens= self.total_tokens + other.total_tokens,
            cached_tokens= self.cached_tokens + other.cached_tokens
        )

@dataclass
class StreamEvent:
    type: StreamEventType
    text_delta: TextDelta | None = None # this can be null, why if there is a tool call or something
    error: str | None = None # probably its going to be str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    
    
    