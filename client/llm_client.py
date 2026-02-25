from openai import AsyncAzureOpenAI, RateLimitError, APIConnectionError, APIError
from typing import Any, Literal, AsyncGenerator
from client.response import parse_arguments_response
from pydantic import BaseModel
import asyncio
import os

from client.response import (
    StreamEvent,
    TextDelta,
    TokenUsage,
    StreamEventType,
    ToolCallDelta,
    ToolCall,
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class LLMCLient:
    def __init__(self) -> None:
        self._client: AsyncAzureOpenAI | None = None
        self._max_retries: int = 3

    def get_client(self) -> AsyncAzureOpenAI:
        if self._client is None:
            self._client = AsyncAzureOpenAI(
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "parameters": tool.get(
                        "parameters",
                        {
                            "type": "object",
                            "properties": {},
                        },
                    ),
                },
            }
            for tool in tools
        ]

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_client()
        kwargs = {
            "messages": messages,
            "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME"),
            "stream": stream,
        }

        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event

                return
            except RateLimitError as e:
                if attempt < self._max_retries:
                    # attempt = failed
                    # 1 attempt -> 1sec, 2 sec, 4 sec
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Rate Limit exceeded: {e}",
                    )
                    return

            except APIConnectionError as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Api Connection error: {e}",
                    )
                    return

            except APIError as e:
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    error=f"Rate Limit exceeded: {e}",
                )
                return

    async def _non_stream_response(
        self, client: AsyncAzureOpenAI, kwargs: dict[str, Any]
    ) -> StreamEvent:
        response = await client.chat.completions.create(**kwargs)
        tool_calls: list[ToolCall] = []
        choice = response.choices[0]
        message = choice.message

        text_delta = None
        if message.content:
            text_delta = TextDelta(
                content=message.content,
            )

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=tc.id,
                        name=tc.function.name,
                        arguments=parse_arguments_response(tc.function.arguments),
                    )
                )

        # token usage
        token_usage = None
        if response.usage:
            token_usage = TokenUsage(
                prompt_token=response.usage.prompt_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            finish_reason=choice.finish_reason,
            usage=token_usage,
        )

    async def _stream_response(
        self, client: AsyncAzureOpenAI, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
        response = await client.chat.completions.create(**kwargs)

        usage: TokenUsage | None = None
        finish_reason: str | None = None
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    prompt_token=chunk.usage.prompt_tokens,
                    cached_tokens=chunk.usage.prompt_tokens_details.cached_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    finish_reason=finish_reason,
                    usage=usage,
                    text_delta=TextDelta(content=delta.content),
                )

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    idx = tool_call_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tool_call_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }

                    if tool_call_delta.function:
                        if tool_call_delta.function.name:
                            tool_calls[idx]["name"] = tool_call_delta.function.name
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tool_calls[idx]["name"],
                                ),
                            )

                        if tool_call_delta.function.arguments:
                            tool_calls[idx]["arguments"] = (
                                tool_calls[idx]["arguments"]
                                + tool_call_delta.function.arguments
                            )
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_DELTA,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tool_calls[idx]["name"],
                                    arguments_delta=tool_call_delta.function.arguments,
                                ),
                            )

        for idx, tc in tool_calls.items():
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETED,
                tool_call=ToolCall(
                    call_id=tc["id"],
                    name=tc["name"],
                    arguments=parse_arguments_response(tc["arguments"]),
                ),
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage,
        )
