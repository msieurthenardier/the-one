from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from the_one.tools.base import Tool
from the_one.config import settings

MEMORY_DIR = settings.workspace_dir / ".memory"


class MemoryTool(Tool):
    name = "memory"
    description = (
        "Your persistent memory. Survives restarts and deploys.\n"
        "Actions:\n"
        "- save: Save a memory (provide key and content)\n"
        "- read: Read a memory by key\n"
        "- list: List all memories\n"
        "- search: Search memories for a term\n"
        "- delete: Delete a memory by key\n"
        "Use this to remember things across conversations — preferences, "
        "decisions, context, lessons learned, what you've tried before."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: save, read, list, search, delete",
            },
            "key": {
                "type": "string",
                "description": "Memory key (used as filename). Required for save, read, delete.",
            },
            "content": {
                "type": "string",
                "description": "Content to save. Required for save.",
            },
            "query": {
                "type": "string",
                "description": "Search term. Required for search.",
            },
        },
        "required": ["action"],
    }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        key = kwargs.get("key", "")
        content = kwargs.get("content", "")
        query = kwargs.get("query", "")

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        if action == "save":
            return self._save(key, content)
        elif action == "read":
            return self._read(key)
        elif action == "list":
            return self._list()
        elif action == "search":
            return self._search(query)
        elif action == "delete":
            return self._delete(key)
        else:
            return f"[error] Unknown action '{action}'. Use: save, read, list, search, delete"

    def _slugify(self, key: str) -> str:
        return re.sub(r'[^a-z0-9_-]', '-', key.lower().strip())[:80]

    def _save(self, key: str, content: str) -> str:
        if not key:
            return "[error] Provide a key for the memory."
        if not content:
            return "[error] Provide content to save."
        slug = self._slugify(key)
        path = MEMORY_DIR / f"{slug}.md"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        # Prepend metadata
        text = f"# {key}\n_saved: {timestamp}_\n\n{content}\n"
        path.write_text(text)
        return f"Saved memory '{key}' → {path.name}"

    def _read(self, key: str) -> str:
        if not key:
            return "[error] Provide a key to read."
        slug = self._slugify(key)
        path = MEMORY_DIR / f"{slug}.md"
        if not path.exists():
            # Try fuzzy match
            matches = [f for f in MEMORY_DIR.glob("*.md") if slug in f.stem]
            if matches:
                path = matches[0]
            else:
                return f"[error] No memory found for '{key}'. Use list to see all memories."
        return path.read_text()

    def _list(self) -> str:
        files = sorted(MEMORY_DIR.glob("*.md"))
        if not files:
            return "No memories saved yet."
        lines = []
        for f in files:
            # Read first line for title
            first_line = f.read_text().split("\n")[0].lstrip("# ").strip()
            lines.append(f"- {f.stem}: {first_line}")
        return f"{len(files)} memories:\n" + "\n".join(lines)

    def _search(self, query: str) -> str:
        if not query:
            return "[error] Provide a search query."
        query_lower = query.lower()
        results = []
        for f in sorted(MEMORY_DIR.glob("*.md")):
            text = f.read_text()
            if query_lower in text.lower():
                # Show matching context
                for i, line in enumerate(text.split("\n")):
                    if query_lower in line.lower():
                        results.append(f"**{f.stem}** (line {i+1}): {line.strip()}")
                        break
        if not results:
            return f"No memories matching '{query}'."
        return f"{len(results)} matches:\n" + "\n".join(results)

    def _delete(self, key: str) -> str:
        if not key:
            return "[error] Provide a key to delete."
        slug = self._slugify(key)
        path = MEMORY_DIR / f"{slug}.md"
        if not path.exists():
            return f"[error] No memory found for '{key}'."
        path.unlink()
        return f"Deleted memory '{key}'."
