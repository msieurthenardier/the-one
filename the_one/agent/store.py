"""Agent configuration store protocol and filesystem implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from the_one.agent.config import AgentConfig


@runtime_checkable
class AgentConfigStore(Protocol):
    """Protocol for persisting and retrieving agent configurations (async)."""

    async def list_agents(self) -> list[str]: ...

    async def load(self, name: str) -> AgentConfig: ...

    async def save(self, config: AgentConfig) -> None: ...

    async def delete(self, name: str) -> list[str]:
        """Delete the agent and its chats; return the deleted chat ids."""
        ...

    async def exists(self, name: str) -> bool: ...

    async def rename(self, old_name: str, new_name: str) -> None: ...


class FilesystemConfigStore:
    """Stores agent configs as JSON files in a directory.

    Legacy synchronous store — kept for migration and tests.
    Does NOT satisfy the async AgentConfigStore protocol.
    """

    def __init__(self, agents_dir: Path) -> None:
        self.agents_dir = agents_dir

    def list_agents(self) -> list[str]:
        if not self.agents_dir.exists():
            return []
        return sorted(p.stem for p in self.agents_dir.glob("*.json"))

    def load(self, name: str) -> AgentConfig:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"Agent config not found: {name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig.model_validate(data)

    def save(self, config: AgentConfig) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(config.name)
        path.write_text(json.dumps(config.model_dump(), indent=2) + "\n", encoding="utf-8")

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"Agent config not found: {name}")
        path.unlink()

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def rename(self, old_name: str, new_name: str) -> None:
        """Rename an agent by moving its JSON file and rewriting the ``name``
        field inside the JSON content. KeyError if source missing; ValueError
        if target already exists (mirrors :class:`SQLiteAgentStore.rename`).
        """
        old_path = self._path(old_name)
        new_path = self._path(new_name)
        if not old_path.exists():
            raise KeyError(f"Agent config not found: {old_name}")
        if new_path.exists():
            raise ValueError(f"Agent config already exists: {new_name}")
        data = json.loads(old_path.read_text(encoding="utf-8"))
        data["name"] = new_name
        new_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        old_path.unlink()

    def _path(self, name: str) -> Path:
        return self.agents_dir / f"{name}.json"
