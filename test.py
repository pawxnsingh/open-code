from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.builtin.list_dir import ListDirTool
from config.config import Config
import asyncio

from pathlib import Path

invocations = ToolInvocation(
    cwd=Path.cwd(),
    params={
        "path": f"{Path.cwd()}/",
    },
)


config = Config()

listdir = ListDirTool(config=config)
res = asyncio.run(listdir.execute(invocation=invocations))
print(res)
