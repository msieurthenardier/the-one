"""Agent configuration store protocol and filesystem implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from the_one.agent.config import AgentConfig


@runtime_checkable
class AgentConfigStore(Protocol):
    """Protocol for persisting and retrieving agent configurations."""

    def list_agents(self) -> list[str]:
        """Return names of all stored agent configs."""
        ...

    def load(self, name: str) -> AgentConfig:
        """Load an agent config by name. Raises KeyError if not found."""
        ...

    def save(self, config: AgentConfig) -> None:
        """Persist an agent config. Creates or overwrites."""
        ...

    def delete(self, name: str) -> None:
        """Delete an agent config by name. Raises KeyError if not found."""
        ...

    def exists(self, name: str) -> bool:
        """Check if a named agent config exists."""
        ...


class FilesystemConfigStore:
    """Stores agent configs as JSON files in a directory."""

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
        data = json.loads(path.read_text())
        return AgentConfig.model_validate(data)

    def save(self, config: AgentConfig) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(config.name)
        path.write_text(json.dumps(config.model_dump(), indent=2) + "\n")

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"Agent config not found: {name}")
        path.unlink()

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def _path(self, name: str) -> Path:
        return self.agents_dir / f"{name}.json"
