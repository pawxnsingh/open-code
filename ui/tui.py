from pathlib import Path

from rich import box
from typing import Any
from config.config import Config
from rich.rule import Rule
from rich.text import Text
from rich.table import Table
from rich.theme import Theme
from rich.panel import Panel
from rich.syntax import Syntax
from rich.console import Console, Group
from utils.text import truncate_text
from utils.paths import display_path_rel_to_cwd


AGENT_THEME = Theme(
    {
        # General
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "dim": "dim",
        "muted": "grey50",
        "border": "grey35",
        "highlight": "bold cyan",
        # Roles
        "user": "bright_blue bold",
        "assistant": "bright_white",
        # Tools
        "tool": "bright_magenta bold",
        "tool.read": "cyan",
        "tool.write": "yellow",
        "tool.shell": "magenta",
        "tool.network": "bright_blue",
        "tool.memory": "green",
        "tool.mcp": "bright_cyan",
        # Code / blocks
        "code": "white",
    }
)

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME, highlight=False)

    return _console


class TUI:
    def __init__(
        self,
        console: Console | None,
        config: Config
    ) -> None:
        self.console = console and get_console()
        self._assistant_stream_open = False
        self.config = config
        self.cwd = self.config.cwd
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}

    def begin_assistant(self):
        self.console.print()
        self.console.print(Rule(Text("Assistant"), style="assistant"))
        self._assistant_stream_open = True

    def end_assistant(self):
        if self._assistant_stream_open:
            self.console.print()
        self._assistant_stream_open = False

    def stream_assistant_delta(self, content: str) -> None:
        self.console.print(content, end="", markup=False)

    def _guess_language(self, path: str | None) -> str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()

        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")

    def print_welcome(self, title: str, lines: list[str]):
        body = "\n".join(lines)
        panel = Panel(
            renderable=Text(body, style="code"),
            title=Text(title, style="highlight"),
            box=box.ROUNDED,
            border_style="border",
            title_align="left",
            padding=(1, 2),
        )

        self.console.print(panel)

    def _ordered_args(self, tool_name: str, args: dict[str, Any]) -> list[tuple]:
        _PREFERED_ORDER = {"read_file": ["path", "offset", "limit"]}

        prefered = _PREFERED_ORDER[tool_name]
        ordered: list[tuple[str, Any]] = []
        seen = set()

        for key in prefered:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)

        remaining_keys = set(args.keys() - seen)
        ordered.extend((key, args[key]) for key in remaining_keys)

        return ordered

    def _render_args_table(self, tool_name: str, args: dict[str, Any]) -> Table:
        table = Table.grid(padding=(0, 1))
        # first we added columns, and then we wrote the rows
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(style="code", overflow="fold")

        for key, value in self._ordered_args(tool_name, args):
            table.add_row(key, value)

        return table

    def tool_call_start(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        arguments: dict[str, Any],
    ):
        self._tool_args_by_call_id[call_id] = arguments
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"

        title = Text.assemble(
            ("⏺ ", "muted"),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id.split('_')[1]}", "muted"),
        )

        display_args = dict(arguments)
        for key in ("path", "cwd"):
            val = display_args.get(key)
            if isinstance(val, str):
                display_args[key] = str(display_path_rel_to_cwd(val, self.cwd))

        panel = Panel(
            self._render_args_table(name, display_args)
            if display_args
            else Text("(no args)", style="muted"),
            title=title,
            title_align="left",
            padding=(1, 2),
            border_style=border_style,
            box=box.ROUNDED,
            subtitle=Text("running", "muted"),
            subtitle_align="right",
        )

        self.console.print()
        self.console.print(panel)

    def _extract_read_file_code(self, text: str):
        return text

    def tool_call_complete(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        success: bool,
        output: str,
        error: str | None,
        metadata: dict[str, Any],
        truncated: bool,
    ):
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"

        primary_path = None
        blocks = []
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = metadata.get("path")

        title = Text.assemble(
            (f"{status_icon} ", status_style),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id.split('_')[1]}", "muted"),
        )

        if name == "read_file" and success:
            if primary_path:
                path = metadata.get("path", "")
                shown_start = metadata.get("shown_start")
                shown_end = metadata.get("shown_end")
                total_lines = metadata.get("total_lines")
                output = self._extract_read_file_code(text=output)
                lexer = self._guess_language(path)

                # block.append(Text())

                header_parts = [display_path_rel_to_cwd(path=path, cwd=self.cwd)]
                header_parts.append(" * ")

                if shown_start and shown_end and total_lines:
                    header_parts.append(
                        f"lines {shown_start}-{shown_end} of {total_lines}"
                    )

                header = "".join(header_parts)

                blocks.append(Text(text=header, style="muted"))
                blocks.append(Syntax(code=output, lexer=lexer, theme="monokai"))

            else:
                output_display = truncate_text(
                    text=output,
                    max_tokens=self._max_block_tokens,
                    model="",
                )
                blocks.append(
                    Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=False,
                    )
                )

        panel = Panel(
            renderable=Group(*blocks),
            title=title,
            title_align="left",
            padding=(1, 2),
            border_style=border_style,
            box=box.ROUNDED,
            subtitle=Text("success" if success else "failed", status_style),
            subtitle_align="right",
        )

        self.console.print()
        self.console.print(panel)
