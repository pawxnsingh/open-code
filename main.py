from agent.event import AgentEventType
from ui.tui import get_console, TUI
from agent.agent import Agent
from pathlib import Path
from config.config import Config
from dotenv import load_dotenv
from config.loader import load_config
import asyncio
import click
import sys

load_dotenv()

console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.config = config
        self.tui = TUI(console=console, config=self.config)

    async def run_single(self, message: str) -> str | None:
        # we will be using this later in other helper functions
        async with Agent(self.config) as agent:
            self.agent = agent
            response = await self._process_message(message)
            return response

    async def run_interactive(self) -> str | None:
        # we will be using this later in other helper functions
        self.tui.print_welcome(
            title="100xCLI agent (made by pawxnsingh while half asleep)",
            lines=[
                f"model: {self.config.model_name}",
                f"cwd: {self.config.cwd}",
                "commands: /models /help /config /approval /exit",
            ],
        )

        async with Agent(self.config) as agent:
            self.agent = agent

            while True:
                try:
                    input_message = console.input("\n[user]>[/user]").strip()

                    if input_message == "/exit":
                        break

                    await self._process_message(input_message)

                except KeyboardInterrupt:
                    console.print("\n[dim] use /exit to quit[/dim]")
                except EOFError:
                    break

        console.print("\n[dim]Goodbye!![/dim]")

    def _get_tool_kind(self, tool_name: str) -> str:
        tool = self.agent.session.tool_registry.get(tool_name)
        if not tool:
            return None

        return tool.kind.value

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None

        assistant_streaming = False
        final_response: str | None = None

        async for event in self.agent.run(message):
            if event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")
                if not assistant_streaming:
                    self.tui.begin_assistant()
                    assistant_streaming = True
                self.tui.stream_assistant_delta(content)

            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content", "")
                if assistant_streaming:
                    self.tui.end_assistant()
                    assistant_streaming = False

            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                console.print(f"\n[error] Error: {error}[/error]")

            elif event.type == AgentEventType.TOOL_CALL_START:
                call_id = event.data.get("call_id")
                tool_name = event.data.get("name", "unknown")
                arguments = event.data.get("arguments", {})

                tool_kind = self._get_tool_kind(tool_name=tool_name)

                self.tui.tool_call_start(
                    call_id=call_id,
                    name=tool_name,
                    tool_kind=tool_kind,
                    arguments=arguments,
                )

            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                call_id = event.data.get("call_id")
                tool_name = event.data.get("name", "unknown")
                arguments = event.data.get("arguments", {})
                output = event.data.get("output", "")
                truncated = event.data.get("truncated", False)
                diff = event.data.get("diff")
                metadata = event.data.get("metadata", {})
                exit_code = event.data.get("exit_code")

                tool_kind = self._get_tool_kind(tool_name=tool_name)

                self.tui.tool_call_complete(
                    call_id=call_id,
                    name=tool_name,
                    tool_kind=tool_kind,
                    success=True,
                    error=None,
                    output=output,
                    diff=diff,
                    metadata=metadata,
                    truncated=truncated,
                    exit_code=exit_code,
                )

        return final_response


@click.command()
@click.argument("prompt", required=False)
@click.option(
    "--cwd",
    "-c",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    help="Current Working Directory",
)
def main(
    prompt: str | None,
    cwd: Path | None,
):
    config = load_config(cwd=cwd)

    errors = config.validate()

    if errors:
        for error in errors:
            console.print(f"\n[error] Error: {error}[/error]")
            sys.exit(1)

    cli = CLI(config=config)

    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            sys.exit(1)
    else:
        asyncio.run(cli.run_interactive())


main()
