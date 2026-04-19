"""Tests for FilesystemConfigStore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_one.agent.config import AgentConfig
from the_one.agent.store import FilesystemConfigStore


@pytest.fixture
def store(tmp_path: Path) -> FilesystemConfigStore:
    return FilesystemConfigStore(tmp_path / "agents")


def _minimal_config(name: str = "test-agent") -> AgentConfig:
    return AgentConfig(name=name)


class TestSaveAndLoad:
    def test_round_trip(self, store: FilesystemConfigStore) -> None:
        cfg = _minimal_config()
        store.save(cfg)
        loaded = store.load("test-agent")
        assert loaded.name == cfg.name
        assert loaded.llm_provider == cfg.llm_provider

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        store = FilesystemConfigStore(deep)
        store.save(_minimal_config())
        assert deep.exists()

    def test_save_overwrites_existing(self, store: FilesystemConfigStore) -> None:
        store.save(AgentConfig(name="x", description="old"))
        store.save(AgentConfig(name="x", description="new"))
        assert store.load("x").description == "new"


class TestListAgents:
    def test_empty_dir(self, store: FilesystemConfigStore) -> None:
        assert store.list_agents() == []

    def test_returns_sorted_names(self, store: FilesystemConfigStore) -> None:
        for name in ("charlie", "alpha", "bravo"):
            store.save(AgentConfig(name=name))
        assert store.list_agents() == ["alpha", "bravo", "charlie"]


class TestExists:
    def test_exists_true(self, store: FilesystemConfigStore) -> None:
        store.save(_minimal_config())
        assert store.exists("test-agent") is True

    def test_exists_false(self, store: FilesystemConfigStore) -> None:
        assert store.exists("nope") is False


class TestDelete:
    def test_delete_removes_file(self, store: FilesystemConfigStore) -> None:
        store.save(_minimal_config())
        store.delete("test-agent")
        assert store.exists("test-agent") is False

    def test_delete_nonexistent_raises_key_error(
        self, store: FilesystemConfigStore
    ) -> None:
        with pytest.raises(KeyError, match="Agent config not found"):
            store.delete("ghost")


class TestLoadErrors:
    def test_load_nonexistent_raises_key_error(
        self, store: FilesystemConfigStore
    ) -> None:
        with pytest.raises(KeyError, match="Agent config not found"):
            store.load("missing")

    def test_load_malformed_json(self, store: FilesystemConfigStore) -> None:
        store.agents_dir.mkdir(parents=True, exist_ok=True)
        (store.agents_dir / "bad.json").write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            store.load("bad")

    def test_load_wrong_shape_json(self, store: FilesystemConfigStore) -> None:
        """Valid JSON but fails Pydantic validation (missing required 'name')."""
        store.agents_dir.mkdir(parents=True, exist_ok=True)
        (store.agents_dir / "invalid.json").write_text('{"not_a_field": 123}')
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            store.load("invalid")
