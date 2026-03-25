from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.builtin.write_file import WriteFileTool
import asyncio

from pathlib import Path

invocations = ToolInvocation(
    cwd=Path.cwd(),
    params={
        "path": f"{Path.cwd()}/test/test/test.py",
        "content": "hellow wasdasdasdasdasd",
        "create_directories": True,
    },
)


write = WriteFileTool()
res = asyncio.run(write.execute(invocation=invocations))
print(res)
