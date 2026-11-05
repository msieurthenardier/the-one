"""SecretResolver and the masker (sortie 10, leg 2, AC1-AC4)."""

from __future__ import annotations

import copy
import json
import urllib.parse

import pytest

from tests._secret_env import COMPLEX, make_env
from the_one.agent._context import TurnContext, current_chat_session_id, current_turn
from the_one.secret_store.runtime import (
    UNAVAILABLE_MESSAGE,
    SecretResolver,
    build_masker,
)


@pytest.fixture
async def env(tmp_path, monkeypatch):
    e = await make_env(tmp_path, monkeypatch)
    yield e
    await e.conn.close()


class TestMasker:
    def test_every_encoding_of_a_value_is_masked(self) -> None:
        mask = build_masker([("k", COMPLEX)])
        for variant in (
            COMPLEX,
            repr(COMPLEX)[1:-1],
            json.dumps(COMPLEX, ensure_ascii=True)[1:-1],
            json.dumps(COMPLEX, ensure_ascii=False)[1:-1],
            urllib.parse.quote(COMPLEX, safe=""),
            urllib.parse.quote_plus(COMPLEX),
        ):
            assert mask(f"a {variant} b") == "a [secret:k] b", variant

    def test_repr_needle_is_needed(self) -> None:
        # ``repr`` escapes the quote and backslash, so only its own needle catches it.
        assert repr(COMPLEX)[1:-1] != COMPLEX
        assert "[secret:k]" in build_masker([("k", COMPLEX)])(repr(COMPLEX))

    def test_single_pass_does_not_rescan_a_replacement(self) -> None:
        # Sequential ``str.replace`` would turn the first mask's text into another mask.
        mask = build_masker([("first", "secret"), ("other", "first")])
        assert mask("secret first") == "[secret:first] [secret:other]"

    def test_longest_value_wins(self) -> None:
        mask = build_masker([("short", "abc"), ("long", "abcdef")])
        assert mask("xabcdefx abc") == "x[secret:long]x [secret:short]"

    def test_containers_keys_and_other_types(self) -> None:
        mask = build_masker([("k", "VALUE12")])
        out = mask({"VALUE12": ["a VALUE12", ("VALUE12",)], "n": 3, "none": None})
        assert out == {"[secret:k]": ["a [secret:k]", ["[secret:k]"]], "n": 3, "none": None}
        assert mask(b"VALUE12") == b"VALUE12"  # bytes are left alone (ToolResult rejects them)

    def test_regex_metacharacters_are_matched_literally(self) -> None:
        # Squawk 0331 (1): the value is escaped, so it masks only where it appears as is.
        value = "a.b*(c)[d]|e"
        mask = build_masker([("k", value)])
        assert mask(f"x {value} y") == "x [secret:k] y"
        # Strings the unescaped pattern would match (or error on) stay as they are.
        for lookalike in ("aXbbb(c)d|e", "a.b*(c)d", "abbbc", "e", "a b c"):
            assert mask(lookalike) == lookalike, lookalike

    def test_no_values_is_identity(self) -> None:
        obj = {"a": ["b"]}
        assert build_masker([])(obj) is obj
        assert build_masker([("k", "")])(obj) is obj


class TestPrepare:
    async def _setup(self, env):
        s = await env.secret(pairs=[{"key": "home_city", "value": COMPLEX}])
        await env.grant("alice", s.id)
        return s

    async def test_fills_nested_leaves_in_a_copy_and_leaves_the_original(self, env) -> None:
        await self._setup(env)
        args = {
            "text": "City: {{secret:home_city}} / {{secret:HOME_CITY}}",
            "n": 3,
            "nested": {"list": ["x", {"deep": "{{secret:home_city}}"}], "{{secret:home_city}}": 1},
        }
        before = copy.deepcopy(args)
        p = await SecretResolver("alice").prepare("probe", args)
        assert p.refusal is None
        assert p.args["text"] == f"City: {COMPLEX} / {COMPLEX}"
        assert p.args["nested"]["list"][1]["deep"] == COMPLEX
        assert "{{secret:home_city}}" in p.args["nested"]  # keys are not substituted
        assert p.args["n"] == 3
        assert args == before
        assert p.args["nested"] is not args["nested"]
        assert p.args["nested"]["list"] is not args["nested"]["list"]

    async def test_malformed_tokens_are_plain_text(self, env) -> None:
        await self._setup(env)
        args = {"a": "{{ secret:home_city }}", "b": "{{secret:}}"}
        p = await SecretResolver("alice").prepare("probe", args)
        assert p.refusal is None and p.args == args

    async def test_not_granted_unknown_and_other_agent(self, env) -> None:
        await self._setup(env)
        other = await env.secret("Other", pairs=[{"key": "other_k", "value": "other-value-99"}])
        await env.grant("bob", other.id)
        r = SecretResolver("alice")
        for key in ("other_k", "Nope"):
            p = await r.prepare("probe", {"t": "{{secret:%s}}" % key})
            assert p.refusal == f"Secret `{key}` is not granted to this agent."
        p = await SecretResolver("ghost").prepare("probe", {"t": "{{secret:home_city}}"})
        assert p.refusal == "Secret `home_city` is not granted to this agent."

    async def test_tool_not_allowed_names_the_key_as_written(self, env) -> None:
        await self._setup(env)
        p = await SecretResolver("alice").prepare("shell", {"t": "{{secret:Home_City}}"})
        assert p.refusal == "Secret `Home_City` can't be used with the tool `shell`."
        assert COMPLEX not in p.refusal

    async def test_refused_set_applies_even_when_a_stored_row_lists_it(self, env) -> None:
        s = await self._setup(env)
        await env.conn.execute(
            "UPDATE secrets SET allowed_tools = ? WHERE id = ?",
            (json.dumps(["save_note", "send_to_platform_channel"]), s.id),
        )
        await env.conn.commit()
        for tool in ("save_note", "send_to_platform_channel"):
            p = await SecretResolver("alice").prepare(tool, {"t": "{{secret:home_city}}"})
            assert p.refusal == f"Secret `home_city` can't be used with the tool `{tool}`."

    async def test_no_secrets_and_no_tokens_is_identity(self, env) -> None:
        args = {"t": "no token"}
        p = await SecretResolver("alice").prepare("probe", args)
        assert p.refusal is None and p.args is args and p.mask("abc") == "abc"

    async def test_empty_library_with_a_token_is_refused(self, env) -> None:
        p = await SecretResolver("alice").prepare("probe", {"t": "{{secret:x}}"})
        assert p.refusal == "Secret `x` is not granted to this agent."

    async def test_fixed_number_of_queries(self, env) -> None:
        await self._setup(env)
        seen: list[str] = []
        await env.conn.set_trace_callback(seen.append)
        args = {"t": " ".join(["{{secret:home_city}}"] * 20)}
        await SecretResolver("alice").prepare("probe", args)
        selects = [q for q in seen if q.lstrip().upper().startswith("SELECT")]
        assert len(selects) <= 6, selects

    async def test_fails_closed_when_values_cannot_be_read(self, env, monkeypatch) -> None:
        await self._setup(env)

        async def boom(self):
            raise RuntimeError("db down: " + COMPLEX)

        monkeypatch.setattr("the_one.db.repositories.SecretRepository.all_values", boom)
        for args in ({"t": "{{secret:home_city}}"}, {"t": "no token"}):
            p = await SecretResolver("alice").prepare("probe", args)
            assert p.refusal == UNAVAILABLE_MESSAGE

    async def test_grants_follow_the_session_agent(self, env) -> None:
        s = await self._setup(env)
        await env.grant("renamed", s.id)
        await env.session("sess-1", "renamed")
        token = current_turn.set(TurnContext(session_id="sess-1"))
        try:
            p = await SecretResolver("alice").prepare("probe", {"t": "{{secret:home_city}}"})
            assert p.args["t"] == COMPLEX
        finally:
            current_turn.reset(token)
        token = current_chat_session_id.set("sess-1")
        try:
            p = await SecretResolver("alice").prepare("probe", {"t": "{{secret:home_city}}"})
            assert p.args["t"] == COMPLEX
        finally:
            current_chat_session_id.reset(token)

    async def test_missing_session_row_falls_back_to_constructor_name(self, env) -> None:
        await self._setup(env)
        token = current_turn.set(TurnContext(session_id="no-such-row"))
        try:
            p = await SecretResolver("alice").prepare("probe", {"t": "{{secret:home_city}}"})
            assert p.args["t"] == COMPLEX
        finally:
            current_turn.reset(token)
        token = current_turn.set(TurnContext())
        try:
            p = await SecretResolver("alice").prepare("probe", {"t": "{{secret:home_city}}"})
            assert p.args["t"] == COMPLEX
        finally:
            current_turn.reset(token)
