"""Secrets through the agent loop (sortie 10, leg 2, AC5-AC14)."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import sys
from pathlib import Path

import pytest
from conftest import FakeLLM
from cryptography.fernet import Fernet

from tests._secret_env import COMPLEX, SIMPLE, Probe, call, make_env, tool_call_message
from the_one.agent._context import TurnContext, current_chat_session_id, current_turn
from the_one.agent.core import Agent
from the_one.db.codec import encode_messages
from the_one.llm.base import Message
from the_one.secret_store.runtime import UNAVAILABLE_MESSAGE, WITHHELD_MESSAGE, SecretResolver
from the_one.tools.base import ToolRegistry


@pytest.fixture
async def env(tmp_path, monkeypatch):
    e = await make_env(tmp_path, monkeypatch)
    yield e
    await e.conn.close()


async def _granted(env, *pairs, tools=("probe",), name="Home"):
    s = await env.secret(name, tools=tools, pairs=list(pairs) or None)
    await env.grant("alice", s.id)
    return s


def _echo(kw):
    return json.dumps(kw["text"]) if not isinstance(kw["text"], str) else kw["text"]


class TestSubstitution:
    async def test_value_reaches_the_tool_but_never_the_model_or_the_store(self, env) -> None:
        await _granted(env)
        probe = Probe("probe", lambda kw: "done")
        args = {"text": {"to": ["x", "{{secret:home_city}}"]}}
        agent = env.agent(
            probe,
            responses=[tool_call_message("probe", args), Message.assistant("finished")],
        )
        _ = [m async for m in agent.step("go")]
        assert probe.calls == [{"text": {"to": ["x", COMPLEX]}}]
        assistant = [m for m in agent.messages if m.tool_calls][0]
        assert assistant.tool_calls[0].arguments == args
        sent = repr(agent.llm.calls)
        assert COMPLEX not in sent and "{{secret:home_city}}" in sent
        assert COMPLEX not in encode_messages(agent.messages)
        assert COMPLEX not in repr(agent.messages)

    async def test_tool_call_arguments_are_never_mutated(self, env) -> None:
        await _granted(env)
        probe = Probe("probe")
        agent = env.agent(probe)
        tc = call("probe", {"text": ["{{secret:home_city}}", {"k": "{{secret:home_city}}"}]})
        before = copy.deepcopy(tc.arguments)
        await agent._execute_tool(tc)
        assert tc.arguments == before
        assert probe.calls[0]["text"][0] == COMPLEX

    async def test_an_agent_without_a_resolver_changes_nothing(self, env) -> None:
        await _granted(env)
        probe = Probe("probe")
        agent = env.agent(probe, secrets=False)
        await agent._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
        assert probe.calls == [{"text": "{{secret:home_city}}"}]


class TestMasking:
    async def _run(self, env, result, *, text="{{secret:home_city}}", pairs=None, **kw):
        if not await env.repo.list() or pairs:
            await _granted(env, *(pairs or [{"key": "home_city", "value": COMPLEX}]))
        probe = Probe("probe", result)
        agent = env.agent(probe)
        return await agent._execute_tool(call("probe", {"text": text})), probe

    async def test_str_dict_and_list_results(self, env) -> None:
        r, _ = await self._run(env, lambda kw: f"got {kw['text']}")
        assert r.content == "got [secret:home_city]" and not r.is_error
        # The governor (pre-existing) only accepts str, so a dict or list result becomes an
        # error result; the value must be absent from it either way. The container walk
        # itself is pinned in test_secret_runtime.TestMasker.
        for build in (lambda kw: {"a": [kw["text"]], "b": 1}, lambda kw: [kw["text"]]):
            r, _ = await self._run(env, build)
            assert COMPLEX not in r.content and r.is_error

    @pytest.mark.parametrize(
        "render",
        [
            lambda v: repr(v),
            lambda v: json.dumps(v),
            lambda v: json.dumps(v, ensure_ascii=False),
            lambda v: __import__("urllib.parse").parse.quote(v, safe=""),
            lambda v: __import__("urllib.parse").parse.quote_plus(v),
        ],
    )
    async def test_echoed_in_other_encodings(self, env, render) -> None:
        r, _ = await self._run(env, lambda kw: "out " + render(kw["text"]))
        assert COMPLEX not in r.content and "secret:home_city" in r.content
        assert "pa" not in r.content.replace("[secret:home_city]", "")

    async def test_ungranted_value_in_output_is_masked(self, env) -> None:
        await env.secret("Other", pairs=[{"key": "other_k", "value": "ungranted-val-77"}])
        r, _ = await self._run(env, lambda kw: "leak: ungranted-val-77", text="plain")
        assert r.content == "leak: [secret:other_k]"

    async def test_masked_before_the_governor_truncates(self, env, monkeypatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_FRACTION", "0.0001")
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_FLOOR", "256")
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_CEILING", "256")
        pairs = [{"key": "home_city", "value": SIMPLE}]
        # The value starts 3 bytes before the 256-byte cut.
        r, _ = await self._run(env, lambda kw: "x" * 253 + kw["text"] + "tail", pairs=pairs)
        assert "truncated" in r.content
        assert SIMPLE[:3] not in r.content.replace("truncated", "")
        assert "Zq9" not in r.content

    async def test_value_only_in_a_dict_key(self, env) -> None:
        r, _ = await self._run(env, lambda kw: {kw["text"]: 1})
        assert COMPLEX not in r.content  # key masking itself: test_secret_runtime.TestMasker

    async def test_bytes_result_errors_without_the_value(self, env) -> None:
        r, _ = await self._run(env, lambda kw: kw["text"].encode())
        assert r.is_error and COMPLEX not in r.content

    async def test_exception_message_is_masked(self, env) -> None:
        def boom(kw):
            raise RuntimeError(f"bad {kw['text']}")

        r, _ = await self._run(env, boom)
        assert r.is_error and COMPLEX not in r.content and "[secret:home_city]" in r.content

    async def test_timeout_is_masked_and_does_not_leak(self, env, monkeypatch) -> None:
        monkeypatch.setattr("the_one.agent.core._get_tool_call_timeout", lambda: 0.05)

        async def slow(**kw):
            await asyncio.sleep(5)

        await _granted(env)
        probe = Probe("probe")
        probe.execute = slow
        r = await env.agent(probe)._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
        assert r.is_error and "timed out" in r.content and COMPLEX not in r.content

    async def test_error_text_naming_a_value_in_a_timeout_message(self, env, monkeypatch) -> None:
        # The tool name is part of the timeout text; a value that equals it is masked.
        await env.secret("Odd", tools=("probe",), pairs=[{"key": "odd", "value": "probe"}])
        monkeypatch.setattr("the_one.agent.core._get_tool_call_timeout", lambda: 0.05)

        async def slow(**kw):
            await asyncio.sleep(5)

        probe = Probe("probe")
        probe.execute = slow
        r = await env.agent(probe)._execute_tool(call("probe", {}))
        assert "tool [secret:odd] timed out" in r.content

    async def test_masker_failure_withholds_the_output(self, env, monkeypatch) -> None:
        await _granted(env)
        monkeypatch.setattr(
            "the_one.secret_store.runtime.build_masker", lambda values: _boom_mask(values)
        )
        probe = Probe("probe", lambda kw: kw["text"])
        agent = env.agent(probe)
        r = await agent._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
        assert r.is_error and r.content == WITHHELD_MESSAGE and COMPLEX not in r.content

        def err(kw):
            raise RuntimeError(kw["text"])

        agent = env.agent(Probe("probe", err))
        r = await agent._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
        assert r.is_error and r.content == WITHHELD_MESSAGE

    async def test_metadata_of_an_auth_required_result_is_untouched(self, env) -> None:
        # Only content and the two error strings are masked; metadata is fixed fields.
        from the_one.mcp.errors import MCPAuthRequired

        await _granted(env)

        def need_auth(kw):
            raise MCPAuthRequired("s", source_name="n")

        r = await env.agent(Probe("probe", need_auth))._execute_tool(
            call("probe", {"text": "{{secret:home_city}}"})
        )
        assert r.content == "<auth required>" and r.metadata["is_auth_required"] is True


def _boom_mask(values):
    def mask(obj):
        raise RuntimeError("masker broke " + COMPLEX)

    return mask


class TestRefusals:
    async def test_not_granted_tool_not_run_and_value_absent(self, env) -> None:
        await env.secret(pairs=[{"key": "home_city", "value": COMPLEX}])
        probe = Probe("probe")
        r = await env.agent(probe)._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
        assert r.is_error and r.content == "Secret `home_city` is not granted to this agent."
        assert probe.calls == [] and COMPLEX not in r.content

    async def test_empty_library_token_refused_and_tool_not_called(self, env) -> None:
        probe = Probe("probe")
        r = await env.agent(probe)._execute_tool(call("probe", {"text": "{{secret:x}}"}))
        assert r.is_error and r.content == "Secret `x` is not granted to this agent."
        assert probe.calls == []

    async def test_agent_without_grants_and_the_default_agent(self, env) -> None:
        await env.secret()
        for name in ("alice", "default"):
            probe = Probe("probe")
            r = await env.agent(probe, name=name)._execute_tool(
                call("probe", {"text": "{{secret:home_city}}"})
            )
            assert r.content == "Secret `home_city` is not granted to this agent."
            assert probe.calls == []

    async def test_tool_not_allowed(self, env) -> None:
        await _granted(env)
        other = Probe("other")
        r = await env.agent(other)._execute_tool(call("other", {"text": "{{secret:home_city}}"}))
        assert r.content == "Secret `home_city` can't be used with the tool `other`."
        assert other.calls == []

    async def test_refused_set_tool_listed_in_a_stored_row(self, env) -> None:
        s = await _granted(env)
        await env.conn.execute(
            "UPDATE secrets SET allowed_tools = ? WHERE id = ?",
            (json.dumps(["save_note", "probe"]), s.id),
        )
        await env.conn.commit()
        note = Probe("save_note")
        r = await env.agent(note)._execute_tool(call("save_note", {"text": "{{secret:home_city}}"}))
        assert r.content == "Secret `home_city` can't be used with the tool `save_note`."
        assert note.calls == [] and COMPLEX not in r.content

    async def test_unavailable_when_secrets_cannot_load(self, env, monkeypatch) -> None:
        await _granted(env)

        async def boom(self):
            raise RuntimeError(COMPLEX)

        monkeypatch.setattr("the_one.db.repositories.SecretRepository.all_values", boom)
        probe = Probe("probe")
        r = await env.agent(probe)._execute_tool(call("probe", {"text": "no token"}))
        assert r.is_error and r.content == UNAVAILABLE_MESSAGE and probe.calls == []


class TestFreshness:
    async def test_update_rotation_and_grant_removal_on_one_agent(self, env) -> None:
        s = await _granted(env, {"key": "home_city", "value": "first-value-1"})
        probe = Probe("probe", lambda kw: "ok")
        agent = env.agent(probe)
        tc = {"text": "{{secret:home_city}}"}
        await agent._execute_tool(call("probe", tc))
        assert probe.calls[-1]["text"] == "first-value-1"

        pair = s.values[0]
        await env.repo.update(
            s.id, values=[{"id": pair.id, "key": "home_city", "value": "second-2"}]
        )
        await agent._execute_tool(call("probe", tc))
        assert probe.calls[-1]["text"] == "second-2"

        # Key rotation: re-encrypt every stored value, then install the new key.
        new_key = Fernet.generate_key()
        async with env.conn.execute("SELECT id, value FROM secret_values") as cur:
            rows = await cur.fetchall()
        newer = type(env.enc)(new_key)
        for vid, ct in rows:
            await env.conn.execute(
                "UPDATE secret_values SET value = ? WHERE id = ?",
                (newer.encrypt(env.enc.decrypt(ct)), vid),
            )
        await env.conn.commit()
        env.enc.install_key(new_key)
        await agent._execute_tool(call("probe", tc))
        assert probe.calls[-1]["text"] == "second-2"

        await env.grant("alice")  # removes the grant
        n = len(probe.calls)
        r = await agent._execute_tool(call("probe", tc))
        assert r.content == "Secret `home_city` is not granted to this agent."
        assert len(probe.calls) == n


class TestRenameAndContext:
    async def test_rename_follows_the_session_agent(self, env) -> None:
        s = await _granted(env)
        await env.session("sess-r", "alice")
        agent = env.agent(Probe("probe"), name="alice")  # built under the old name
        await env.store.rename("alice", "alicia")
        assert (await env.store.load("alicia")).secret_ids == [s.id]
        for setter, var in (
            (TurnContext(session_id="sess-r"), current_turn),
            ("sess-r", current_chat_session_id),
        ):
            token = var.set(setter)
            try:
                probe = agent.tools.get("probe")
                await agent._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
                assert probe.calls[-1]["text"] == COMPLEX
            finally:
                var.reset(token)


class TestResume:
    async def test_resume_after_auth_reprepares(self, env) -> None:
        # ``resume_after_auth`` re-dispatches through ``_dispatch_tool_calls``, which calls
        # ``_execute_tool`` for each real tool, so every resumed call is prepared again.
        import inspect

        src = inspect.getsource(Agent.resume_after_auth)
        assert "_dispatch_tool_calls" in src
        assert "await self._execute_tool(tc)" in inspect.getsource(Agent._dispatch_tool_calls)


_LOUD = ("httpx2", "httpcore2", "httpx", "httpcore", "mcp")


@pytest.fixture
def app_logging():
    """The app's logging setup (it quiets the HTTP and MCP client loggers), undone after."""
    from the_one.logging_config import configure_logging

    saved = {n: logging.getLogger(n).level for n in _LOUD}
    configure_logging()
    yield
    for n, level in saved.items():
        logging.getLogger(n).setLevel(level)


class TestLogs:
    def test_client_loggers_that_print_message_bodies_are_quieted(self, app_logging, caplog):
        # ``mcp.client.streamable_http`` logs "Sending client message: {message}" at DEBUG.
        caplog.set_level(logging.DEBUG)
        for name in ("mcp.client.streamable_http", "mcp.client.sse", "httpx2", "httpcore2"):
            lg = logging.getLogger(name)
            assert not lg.isEnabledFor(logging.INFO), name
            lg.debug("Sending client message: %s", SIMPLE)
        assert SIMPLE not in caplog.text

    async def test_no_log_record_holds_a_value(self, env, caplog, app_logging) -> None:
        await _granted(env, {"key": "home_city", "value": SIMPLE})
        caplog.set_level(logging.DEBUG)
        probe = Probe("probe", lambda kw: kw["text"])
        r = await env.agent(probe)._execute_tool(call("probe", {"text": "{{secret:home_city}}"}))
        assert SIMPLE not in r.content
        assert SIMPLE not in caplog.text

    async def test_mcp_echo_tool_masks_and_logs_no_value(self, env, caplog, app_logging) -> None:
        await _granted(env, {"key": "home_city", "value": SIMPLE}, tools=("mcp__hello__echo",))
        caplog.set_level(logging.DEBUG)
        result = await _call_hello_echo(env, "say {{secret:home_city}}")
        assert result.content == "say [secret:home_city]"
        assert SIMPLE not in caplog.text


async def _call_hello_echo(env, message):
    """Run the hello MCP server's ``echo`` over stdio and call it through an Agent."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from the_one.tools.base import Tool

    server = Path(__file__).parent / "fixtures" / "mcp" / "hello_server.py"
    params = StdioServerParameters(command=sys.executable, args=[str(server), "--stdio"])

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        class McpEcho(Tool):
            name = "mcp__hello__echo"
            description = "echo"
            parameters = {"type": "object", "properties": {"message": {}}, "required": []}

            async def execute(self, **kw):
                res = await session.call_tool("echo", kw)
                return "".join(getattr(c, "text", "") for c in res.content)

        reg = ToolRegistry()
        reg.register(McpEcho())
        agent = Agent(
            llm=FakeLLM(responses=[]), tools=reg, system_prompt="s", secrets=SecretResolver("alice")
        )
        return await agent._execute_tool(call("mcp__hello__echo", {"message": message}))
