from __future__ import annotations

from pathlib import Path
from typing import Any

from the_one.platform import canonicalize
from the_one.tools.base import Tool


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "offset": {"type": "integer", "description": "Line number to start from (0-based)."},
            "limit": {"type": "integer", "description": "Max number of lines to read."},
        },
        "required": ["path"],
    }

    async def execute(
        self, path: str, offset: int = 0,
        limit: int | None = None, **kwargs: Any,
    ) -> str:
        try:
            p = canonicalize(path)
            text = p.read_text(errors="replace")
            lines = text.splitlines()
            if offset or limit:
                end = (offset + limit) if limit else None
                lines = lines[offset:end]
            return "\n".join(f"{i + offset + 1:>5} | {line}" for i, line in enumerate(lines))
        except Exception as e:
            return f"[error] {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file, creating directories as needed."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "content": {"type": "string", "description": "Content to write."},
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        try:
            p = canonicalize(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Wrote {len(content)} bytes to {p}"
        except Exception as e:
            return f"[error] {e}"


class ListDirTool(Tool):
    name = "list_dir"
    description = "List files and directories at a given path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: current dir)."},
            "recursive": {"type": "boolean", "description": "List recursively.", "default": False},
        },
        "required": [],
    }

    async def execute(self, path: str = ".", recursive: bool = False, **kwargs: Any) -> str:
        try:
            p = canonicalize(path)
            if recursive:
                entries = sorted(p.rglob("*"))
            else:
                entries = sorted(p.iterdir())
            lines = []
            for e in entries[:500]:  # cap output
                prefix = "d " if e.is_dir() else "f "
                lines.append(f"{prefix}{e.relative_to(p)}")
            result = "\n".join(lines)
            if len(entries) > 500:
                result += f"\n... and {len(entries) - 500} more"
            return result or "(empty directory)"
        except Exception as e:
            return f"[error] {e}"
