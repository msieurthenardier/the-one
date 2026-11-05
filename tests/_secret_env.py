"""Shared apparatus for the secrets-at-runtime tests (sortie 10, leg 2): a template
database, an encryptor, the seams the resolver reads through, and a probe tool."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

from conftest import StubTool
from cryptography.fernet import Fernet

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository, SecretRepository, SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.llm.base import Message, ToolCall
from the_one.secret_store.runtime import SecretResolver
from the_one.tools.base import ToolRegistry

# Quotes of both kinds, a backslash, a space, a non-ASCII letter and URL-special characters.
COMPLEX = "pa\"ss'wo\\rd é+&/x"
SIMPLE = "Zq9-straddle-VALUE"


class Probe(StubTool):
    """Records its arguments; ``result`` builds the return value from them."""

    def __init__(self, name: str, result: Callable[[dict[str, Any]], Any] | None = None) -> None:
        super().__init__(name)
        self.result = result
        self.parameters = {"type": "object", "properties": {"text": {}}, "required": []}

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.result is None:
            return "ok"
        return self.result(kwargs)


@dataclass
class Env:
    conn: Any
    enc: Encryptor
    repo: SecretRepository
    store: SQLiteAgentStore

    async def secret(self, name="Home", tools=("probe",), pairs=None):
        pairs = pairs or [{"key": "home_city", "value": COMPLEX}]
        return await self.repo.create(name, "d", list(tools), pairs)

    async def grant(self, agent: str, *secret_ids: str) -> None:
        await self.store.save(AgentConfig(name=agent, secret_ids=list(secret_ids)))

    async def session(self, session_id: str, agent: str) -> None:
        await ChatSessionRepository(self.conn).create(ChatSession(id=session_id, agent_name=agent))

    def agent(self, *tools: Any, name: str = "alice", responses=None, secrets=True) -> Agent:
        from conftest import FakeLLM

        reg = ToolRegistry()
        for t in tools:
            reg.register(t)
        return Agent(
            llm=FakeLLM(responses=responses or []),
            tools=reg,
            system_prompt="sys",
            secrets=SecretResolver(name) if secrets else None,
        )


async def make_env(tmp_path, monkeypatch) -> Env:
    conn = await connect_template_db(tmp_path / "t.db")
    enc = Encryptor(Fernet.generate_key())
    monkeypatch.setattr("the_one.db.connection.get_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr("the_one.encryption.get_encryptor", lambda _d: enc)
    return Env(conn, enc, SecretRepository(conn, enc), SQLiteAgentStore(conn, enc))


def call(name: str, arguments: dict[str, Any], cid: str = "c1") -> ToolCall:
    return ToolCall(id=cid, name=name, arguments=arguments)


def tool_call_message(name: str, arguments: dict[str, Any]) -> Message:
    return Message.assistant("", tool_calls=[call(name, arguments)])
