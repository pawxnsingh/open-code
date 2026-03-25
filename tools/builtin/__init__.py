from tools.builtin.read_file import ReadFileTool
from tools.builtin.write_file import WriteFileTool
from tools.builtin.edit_file import EditFileTool
from tools.builtin.shell import ShellTool
from tools.builtin.list_dir import ListDirTool
from tools.base import Tool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EEditFileTool",
    "ShellTool",
    "ListDirTool",
]


def get_all_builtin_tools() -> list[Tool]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ShellTool,
        ListDirTool,
    ]
