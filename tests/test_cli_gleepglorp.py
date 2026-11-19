"""`the-one chat` chats with GleepGlorp; an unready GleepGlorp is one plain line (M36 F1 L03)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from rich.console import Console

from the_one.agent.factory import GleepGlorpUnavailableError
from the_one.interfaces import cli


class _Factory:
    created: list[tuple] = []
    error: Exception | None = None

    def __init__(self, store=None) -> None:
        pass

    async def create(self, *args):
        _Factory.created.append(args)
        if _Factory.error is not None:
            raise _Factory.error
        raise AssertionError("stop after the build")


@pytest.fixture
def cli_env(monkeypatch):
    console = Console(record=True, width=200)
    monkeypatch.setattr(cli, "console", console)
    monkeypatch.setattr(cli, "AgentFactory", _Factory)
    _Factory.created = []
    _Factory.error = None
    with (
        patch.object(cli, "init_db", AsyncMock()),
        patch.object(cli, "get_connection", AsyncMock()),
        patch.object(cli, "reconcile_pending_key", AsyncMock(return_value="absent")),
        patch.object(cli, "get_encryptor", lambda _d: None),
        patch.object(cli, "SQLiteAgentStore", lambda _c: None),
        patch("the_one.tools.execution.prune_box_scratch", lambda: None),
    ):
        yield console


@pytest.mark.parametrize("state", ["off", "needs_model", "provider_missing"])
async def test_an_unready_gleepglorp_prints_one_plain_line_and_exits_non_zero(
    cli_env, state
) -> None:
    _Factory.error = GleepGlorpUnavailableError(state)
    with pytest.raises(SystemExit) as info:
        await cli._run_cli()
    assert info.value.code == 1
    out = cli_env.export_text()
    assert "Settings > GleepGlorp" in out
    assert "Traceback" not in out
    assert str(GleepGlorpUnavailableError(state)) in out


async def test_chat_with_no_agent_builds_gleepglorp(cli_env) -> None:
    """The CLI names no agent: create() gets no argument, so it is the factory's GleepGlorp."""
    with pytest.raises(AssertionError, match="stop after the build"):
        await cli._run_cli()
    assert _Factory.created == [()]
