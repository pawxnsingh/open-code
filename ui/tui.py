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
    def __init__(self, console: Console | None, config: Config) -> None:
        self.console = console and get_console()
        self._assistant_stream_open = False
        self.config = config
        self.cwd = self.config.cwd
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self._max_block_tokens = 240

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
        _PREFERED_ORDER = {
            "read_file": ["path", "offset", "limit"],
            "write_file": ["path", "create_directories", "content"],
            "edit": ["path", "replace_all", "old_string", "new_string"],
            "shell": ["command", "timeout", "cwd"],
            "list_dir": ["path", "include_hidden"],
            "grep": ["pattern", "case_insensitive", "path"],
            "glob": ["pattern", "path"],
            "web_search": ["query", "max_results"],
            "web_fetch": ["url", "timeout"],
            "todos": ["id", "action", "content"],
            "memory": ["action", "key", "value"],
        }

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
            if key in {"content", "old_string", "new_string"}:
                line_count = len(value.splitlines()) or 0
                byte_count = len(value.encode("utf-8", errors="replace"))

                value = f"<{line_count} lines • {byte_count} bytes>"

            # rich.Table expects renderable values (strings, Text, etc.).
            # Convert non-string scalar values to string to avoid NotRenderableError.
            if not isinstance(value, (str, Text)):
                value = str(value)

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
        diff: str | None,
        truncated: bool,
        exit_code: int | None,
    ):
        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"

        args = self._tool_args_by_call_id.get(call_id, {})

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
                    model=self.config.model_name,
                )
                blocks.append(
                    Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=False,
                    )
                )

        elif name in {"write_file", "edit"} and success and diff:
            output_line = output.strip() if output.strip() else "Completed"
            blocks.append(Text(output_line, style="muted"))
            diff_text = diff

            diff_display = truncate_text(
                text=diff_text,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )

            blocks.append(
                Syntax(
                    diff_display,
                    "diff",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name in "shell":
            commands = args.get("commands")
            if isinstance(commands, str) and commands.strip():
                blocks.append(Text(f"$ {commands.strip()}", style="muted"))

            if exit_code is not None:
                blocks.append(Text(f"exit_code={str(exit_code)}", style="muted"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )

            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name == "list_dir" and success:
            entries = metadata.get("entries")
            path = metadata.get("path")
            summary = []
            if isinstance(path, str):
                summary.append(path)

            if isinstance(entries, int):
                summary.append(f"{entries} entries")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name == "grep" and success:
            matches = metadata.get("matches")
            files_searched = metadata.get("files_searched")
            summary = []
            if isinstance(matches, int):
                summary.append(f"{matches} matches")
            if isinstance(files_searched, int):
                summary.append(f"searched {files_searched} files")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "glob" and success:
            matches = metadata.get("matches")
            if isinstance(matches, int):
                blocks.append(Text(f"{matches} matches", style="muted"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "web_search" and success:
            results = metadata.get("results")
            query = args.get("query")
            summary = []
            if isinstance(query, str):
                summary.append(query)
            if isinstance(results, int):
                summary.append(f"{results} results")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "web_fetch" and success:
            status_code = metadata.get("status_code")
            content_length = metadata.get("content_length")
            url = args.get("url")
            summary = []
            if isinstance(status_code, int):
                summary.append(str(status_code))
            if isinstance(content_length, int):
                summary.append(f"{content_length} bytes")
            if isinstance(url, str):
                summary.append(url)

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "todos" and success:
            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )
        elif name == "memory" and success:
            action = args.get("action")
            key = args.get("key")
            found = metadata.get("found")
            summary = []
            if isinstance(action, str) and action:
                summary.append(action)
            if isinstance(key, str) and key:
                summary.append(key)
            if isinstance(found, bool):
                summary.append("found" if found else "missing")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))
            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        else:
            if error and not success:
                blocks.append(Text(error, style="error"))

            output_display = truncate_text(
                text=output,
                model=self.config.model_name,
                max_tokens=self._max_block_tokens,
            )
            if output_display.strip():
                blocks.append(
                    Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=True,
                    )
                )
            else:
                blocks.append(Text("(no output)", style="muted"))

        if truncated:
            blocks.append(Text("note: tool output was truncated", style="warning"))

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
