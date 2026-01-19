from openai import AsyncOpenAI, RateLimitError, APIConnectionError, APIError
from typing import Any, Literal, AsyncGenerator
from pydantic import BaseModel
import asyncio

from client.response import StreamEvent, TextDelta, TokenUsage, StreamEventType 

class ChatMessage(BaseModel):
    role: Literal['user', 'assistant', 'system']
    content: str

class LLMCLient:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self._max_retries: int = 3
    
    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                # api_key="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",
                # base_url="https://openrouter.ai/api/v1",
                api_key="",
                base_url="https://bedrock-runtime.ap-south-1.amazonaws.com/openai/v1",
                
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
            
    async def chat_completion(self, messages: list[ChatMessage], stream: bool = True) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_client()
        kwargs = {
            "messages": messages,
            # "model": "mistralai/devstral-2512:free",
            "model": "minimax.minimax-m2",
            "stream": stream
        }
                
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
            
    async def _non_stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any]) -> StreamEvent:
        response = await client.chat.completions.create(**kwargs)  
        choice = response.choices[0]
        message = choice.message
        
        text_delta = None
        if message.content:
            text_delta = TextDelta(
                content=message.content,
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
        
    async def _stream_response(self, client: AsyncOpenAI, kwargs: dict[str, Any]) -> AsyncGenerator[StreamEvent, None]:
        response = await client.chat.completions.create(**kwargs)
    
        usage: TokenUsage | None = None
        finish_reason: str | None = None
            
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
                    text_delta=TextDelta(content=delta.content)
                )
                
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage
        )
    