from __future__ import annotations
from typing import AsyncGenerator
from config.config import Config
from agent.event import AgentEvent
from agent.session import Session
from client.response import StreamEventType, ToolCall, ToolResultMessage


class Agent:
    def __init__(self, config: Config):
        self.config = config
        self.session: Session | None = Session(
            config=config,
        )

    async def run(self, message: str):
        final_content = None
        yield AgentEvent.agent_start(message)
        self.session.context_manager.add_user_message(content=message)

        async for event in self._agent_loop():
            yield event

            if event.type == StreamEventType.MESSAGE_COMPLETE:
                final_content = event.data.get("content")

        yield AgentEvent.agent_end(final_content)

    # this _agent_loop, will be the multi turn conversations
    async def _agent_loop(self) -> AsyncGenerator[AgentEvent, None]:
        max_turns = self.config.max_turns

        for turn_number in range(max_turns):
            response_text = ""
            tool_schemas = self.session.tool_registry.get_schemas()
            tool_calls: list[ToolCall] = []
            
            self.session.increment_turn()

            messages = self.session.context_manager.get_message()
            async for event in self.session.client.chat_completion(
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
                stream=True,
            ):
                if event.type == StreamEventType.TEXT_DELTA:
                    if event.type:
                        content = event.text_delta.content
                        response_text += content
                        yield AgentEvent.text_delta(content)

                elif event.type == StreamEventType.TOOL_CALL_COMPLETED:
                    if event.tool_call:
                        tool_calls.append(event.tool_call)

                elif event.type == StreamEventType.ERROR:
                    yield AgentEvent.agent_error(
                        event.error or "Unknown error",
                    )

            self.session.context_manager.add_assistant_message(
                content=response_text,
                tool_calls=[
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": str(tc.arguments),
                        },
                    }
                    for tc in tool_calls
                ]
                if tool_calls
                else None,
            )
            if response_text:
                yield AgentEvent.text_complete(
                    content=response_text,
                )

            if not tool_calls:
                return

            tool_call_results: list[ToolResultMessage] = []

            for tool_call in tool_calls:
                yield AgentEvent.tool_call_start(
                    call_id=tool_call.call_id,
                    name=tool_call.name,
                    arguments=tool_call.arguments,
                )

                result = await self.session.tool_registry.invoke(
                    name=tool_call.name, params=tool_call.arguments, cwd=self.config.cwd
                )

                yield AgentEvent.tool_call_complete(
                    call_id=tool_call.call_id, name=tool_call.name, result=result
                )

                tool_call_results.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.call_id,
                        content=result.to_model_output(),
                        is_error=not result.success,
                    )
                )

            for tool_result in tool_call_results:
                self.session.context_manager.add_tool_result(
                    tool_call_id=tool_result.tool_call_id,
                    content=tool_result.content,
                )

    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ) -> None:
        if self.session.client and self.session:
            await self.session.client.close()
            self.session = None
