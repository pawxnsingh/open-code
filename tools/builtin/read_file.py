from pydantic import BaseModel, Field
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import resolve_path, is_binary
from utils.text import count_tokens, truncate_text

class ReadFileParams(BaseModel):
    path: str = Field(
        ...,
        description="The file system path to the file to be read. Can be an absolute path or relative to the current working directory.",
    )
    # line number to start from
    offset: int = Field(
        1,
        ge=1,
        description="The line number to start reading from (1-indexed).",
    )
    # number of lines to read from that offset
    limit: int = Field(
        None,
        ge=1,
        description="The maximum number of lines to read from the offset. If None, reads until end of file.",
    )


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Reads the contents of a file from the specified path, with optional line offset and limit parameters. "
        "For larger files, use offsets and limits to read specific portions of the file instead of loading the entire content. "
        "Cannot read binary files such as images, executables, or compiled code. "
        "Useful for examining source code, configuration files, logs, and other text-based documents."
    )
    schema = ReadFileParams
    kind = ToolKind.READ

    MAX_FILE_SIZE = 1024 * 1024 * 10  # 10MB
    MAX_OUTPUT_TOKENS = 25000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(error=f"File Not Found: {path}")

        if not path.is_file():
            return ToolResult.error_result(error=f"Path is not a file: {path}")

        file_size = path.stat().st_size

        # check the file size, if larger than the threshold, then we need return the error
        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(
                error=f"File too Large {file_size / (1024 * 1024):.1f}MB",
                output=f"Max File Size is {self.MAX_FILE_SIZE:.0f}MB",
            )

        # check if the file is binary
        if is_binary(path=path):
            file_size_mb = file_size / (1024 * 1024)
            size_str = (
                f"{file_size_mb:.2f}MB" if file_size_mb >= 1 else f"{file_size} bytes"
            )

            return ToolResult.error_result(
                error=f"Cannot read binary file: {path.name} ({size_str})",
                output="This tool only reads text files",
            )

        # lets read that fileso and send that shit to the llm
        try:
            try:
                read_file = path.read_text("utf-8")
            except UnicodeEncodeError:
                read_file = path.read_text("latin-1")

            # print(read_file)

            # now i need to split the lines and use the offset and limit to get the stuff
            lines = read_file.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult.success_result(
                    output="File is Empty",
                    metadata={
                        lines: 0,
                    },
                )

            start_idx = max(0, params.offset - 1)

            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines

            selected_lines = lines[start_idx:end_idx]
            formatted_lines = []

            for i, line in enumerate(selected_lines, start=start_idx + 1):
                formatted_lines.append(f"{i:6}|{line}")

            output = "\n".join(formatted_lines)

            token_count = count_tokens(text=output)

            truncated = False
            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    text=output,
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    suffix=f"\n... [truncated {total_lines} total lines]",
                )
                truncated = True

            metadata_lines = []
            if start_idx > 0 or end_idx < total_lines:
                metadata_lines.append(
                    f"Showing lines {start_idx + 1}-{end_idx} of {total_lines}"
                )

            if metadata_lines:
                header = " | ".join(metadata_lines) + "\n\n"
                output = header + output

            return ToolResult.success_result(
                output=output,
                truncated=truncated,
                metadata={
                    "path": str(path),
                    "total_lines": total_lines,
                    "shown_start": start_idx + 1,
                    "shown_end": end_idx,
                },
            )

        except Exception as e:
            print(f"Error: {str(e)}")
            return ToolResult.error_result(
                f"Failed to read files: {e}",
            )