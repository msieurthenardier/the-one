"""Sortie 09 leg 1: per-agent MCP credentials are validated, never blank, and overlay cleanly.

Covers DD2 (validation and its 422 shape), DD1 (case-insensitive overlay), DD8 (OAuth
Authorization skip), DD3 (blank drop, ``missing_values``, classification) and DD9 (no
value in any response or log).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import _looks_masked
from the_one.mcp._overrides import configured_names, has_oauth_state, missing_values
from the_one.mcp._tool_provider import _apply_override
from the_one.mcp.client import MCPClient
from the_one.mcp.errors import MCPAuthRequired, MCPCredentialsRejected
from the_one.mcp.override_validation import OAUTH_AUTHORIZATION_REFUSAL, validate_mcp_overrides
from the_one.mcp.transports.stdio import build_stdio_environ
from the_one.mcp.transports.streamable_http import build_request_headers

SECRET = "distinctive-secret-value-12345"


def _http(name="srv", *, config_headers=None, secrets=None) -> MCPSource:
    return MCPSource(
        id=f"id-{name}",
        name=name,
        type="streamable-http",
        config={"url": "http://localhost/mcp", "headers": dict(config_headers or {})},
        secrets=dict(secrets or {}),
    )


def _stdio(name="srv", *, config_env=None, secrets=None) -> MCPSource:
    return MCPSource(
        id=f"id-{name}",
        name=name,
        type="stdio",
        config={"command": "echo", "args": [], "env": dict(config_env or {})},
        secrets=dict(secrets or {}),
    )


def _validate(overrides, *sources):
    return validate_mcp_overrides(overrides, {s.name: s for s in sources}, _looks_masked)


def _locs(details):
    return [tuple(d["loc"]) for d in details]


# --- DD2: source-independent rules (orphan entries included) --------------------


@pytest.mark.parametrize(
    ("headers", "field_name"),
    [
        ({"Bad Name": "v"}, "Bad Name"),
        ({"X:Colon": "v"}, "X:Colon"),
        ({"Host": "evil"}, "Host"),
        ({"content-length": "1"}, "content-length"),
        ({"Transfer-Encoding": "x"}, "Transfer-Encoding"),
        ({"CONNECTION": "x"}, "CONNECTION"),
        ({"Content-Type": "x"}, "Content-Type"),
        ({"Accept": "x"}, "Accept"),
        ({"Mcp-Session-Id": "x"}, "Mcp-Session-Id"),
        ({"mcp-protocol-version": "x"}, "mcp-protocol-version"),
        ({"X-Key": ""}, "X-Key"),
        ({"X-Key": "   "}, "X-Key"),
        ({"X-Key": "a\x00b"}, "X-Key"),
        ({"X-Key": "a\r\nInjected: 1"}, "X-Key"),
        ({"X-Key": "café"}, "X-Key"),
        ({"X-Key": None}, "X-Key"),
        ({"X-Key": 5}, "X-Key"),
        ({"X-Key\n": "v"}, "X-Key\n"),
    ],
)
def test_source_independent_header_rules_apply_to_an_orphan_entry(headers, field_name):
    details = _validate({"nobody-has-this-name": {"headers": headers}})
    assert _locs(details) == [("mcp_overrides", "nobody-has-this-name", "headers", field_name)]
    assert details[0]["type"] == "mcp_override"
    assert isinstance(details[0]["msg"], str) and details[0]["msg"].endswith(".")


def test_refusals_say_whether_the_name_or_the_value_was_refused():
    """The additive ``part`` key (HAT H5): "name" for a name rule, "value" otherwise."""
    gh = _http("gh")
    local = _stdio("local")
    parts = lambda ov, *srcs: [d["part"] for d in _validate(ov, *srcs)]  # noqa: E731
    assert parts({"gh": {"headers": {"Bad Header": "x"}}}, gh) == ["name"]
    assert parts({"gh": {"headers": {"Host": "x"}}}, gh) == ["name"]
    assert parts({"gh": {"headers": {"X-Ok": "  "}}}, gh) == ["value"]
    assert parts({"gh": {"bearer_token": ""}}, gh) == ["value"]
    assert parts({"local": {"env": {"1BAD": "x"}}}, local) == ["name"]
    assert parts({"local": {"env": {"GOOD": ""}}}, local) == ["value"]


def test_two_header_names_differing_only_by_case_are_refused():
    details = _validate({"x": {"headers": {"X-Api-Key": "aaa", "x-api-key": "bbb"}}})
    assert _locs(details) == [("mcp_overrides", "x", "headers", "x-api-key")]


def test_case_duplicate_of_two_masked_names_is_left_alone():
    assert _validate({"x": {"headers": {"X-Api-Key": "__MASKED__", "x-api-key": "***"}}}) == []


@pytest.mark.parametrize(
    ("env", "ok"),
    [
        ({"GOOD_NAME": "v"}, True),
        ({"1BAD": "v"}, False),
        ({"BAD-NAME": "v"}, False),
        ({"A B": "v"}, False),
        ({"FOO\n": "v"}, False),
        ({"K": ""}, False),
        ({"K": "  \t"}, False),
        ({"K": "a\x00b"}, False),
        ({"K": None}, False),
        ({"K": 3}, False),
    ],
)
def test_env_rules_apply_to_an_orphan_entry(env, ok):
    details = _validate({"orphan": {"env": env}})
    assert (details == []) is ok
    if not ok:
        assert _locs(details)[0][:3] == ("mcp_overrides", "orphan", "env")


@pytest.mark.parametrize("token", ["", "  ", "a\x00b", "tok\nen", "café", 7])
def test_bearer_token_uses_the_value_grammar(token):
    details = _validate({"orphan": {"bearer_token": token}})
    assert _locs(details) == [("mcp_overrides", "orphan", "bearer_token")]


def test_valid_credentials_pass_and_tabs_and_spaces_are_allowed():
    assert (
        _validate(
            {
                "a": {"headers": {"X-Api-Key": "abc 123\tdef"}, "bearer_token": "tok.en-1"},
                "b": {"env": {"API_KEY": "v"}},
            },
            _http("a"),
            _stdio("b"),
        )
        == []
    )


def test_top_level_null_credentials_are_valid_clears():
    assert _validate({"a": {"headers": None, "env": None, "bearer_token": None}}, _http("a")) == []


def test_mask_shaped_values_are_not_checked():
    ov = {"a": {"headers": {"X-Api-Key": "__MASKED__", "X-B": "***...wxyz"}, "bearer_token": "***"}}
    assert _validate(ov, _http("a")) == []


def test_all_refusals_in_one_body_are_returned_together():
    details = _validate(
        {"a": {"headers": {"Host": "x", "X-Key": ""}, "env": {"1": "v"}}, "b": {"bearer_token": 1}},
    )
    assert len(details) == 4


# --- DD2: source-dependent rules -------------------------------------------------


def test_headers_on_a_stdio_source_and_env_on_an_http_source_are_refused():
    details = _validate(
        {"s": {"headers": {"X-K": "v"}}, "h": {"env": {"K": "v"}}}, _stdio("s"), _http("h")
    )
    assert _locs(details) == [("mcp_overrides", "s", "headers"), ("mcp_overrides", "h", "env")]


def test_the_same_shape_on_an_orphan_entry_is_not_refused():
    assert _validate({"s": {"headers": {"X-K": "v"}}, "h": {"env": {"K": "v"}}}) == []


def test_authorization_on_a_source_with_oauth_state_is_refused_with_the_exact_sentence():
    oauth = _http("o", secrets={"access_token": "t", "dcr_credentials": {"client_id": "c"}})
    details = _validate({"o": {"headers": {"authorization": "x", "X-Org": "ok"}}}, oauth)
    assert _locs(details) == [("mcp_overrides", "o", "headers", "authorization")]
    assert details[0]["msg"] == OAUTH_AUTHORIZATION_REFUSAL
    assert OAUTH_AUTHORIZATION_REFUSAL == (
        "This server signs in with OAuth, so its Authorization header can't be set per agent."
    )
    details = _validate({"o": {"bearer_token": "tok"}}, oauth)
    assert _locs(details) == [("mcp_overrides", "o", "bearer_token")]
    assert details[0]["msg"] == OAUTH_AUTHORIZATION_REFUSAL


def test_cached_oauth_posture_without_oauth_secrets_accepts_authorization():
    """The refusal keys off stored sign-in state, NOT the cached `auth_posture`."""
    src = _http("p")
    src = src.model_copy(
        update={"config": {**src.config, "_cache": {"auth_posture": "oauth"}}},
    )
    assert not has_oauth_state(src)
    assert (
        _validate({"p": {"headers": {"Authorization": "Bearer abc"}, "bearer_token": "t"}}, src)
        == []
    )


# --- API: the 422 shape, ordering and the unchanged paths ------------------------


@pytest.fixture
async def api(tmp_path):
    conn = await connect_template_db(tmp_path / "t.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "t.key")
    repo = MCPSourceRepository(conn, encryptor)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as c:
            yield c, repo, conn, encryptor
    await conn.close()


async def _stored(api, name):
    _, _, conn, encryptor = api
    return await SQLiteAgentStore(conn, encryptor).load(name)


async def test_a_refused_save_is_one_422_list_and_nothing_is_stored(api, caplog):
    c, repo, _, _ = api
    await repo.create(_http("gh"))
    await repo.create(_stdio("local"))
    caplog.set_level(logging.DEBUG)
    resp = await c.post(
        "/api/agents",
        json={
            "name": "bad",
            "mcp_overrides": {
                "gh": {"headers": {"Host": SECRET, "X-Key": SECRET + "\x00"}},
                "local": {"headers": {"X-K": SECRET}},
            },
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert [tuple(d["loc"]) for d in detail] == [
        ("mcp_overrides", "gh", "headers", "Host"),
        ("mcp_overrides", "gh", "headers", "X-Key"),
        ("mcp_overrides", "local", "headers"),
    ]
    assert all(d["type"] == "mcp_override" for d in detail)
    # AC14: the value is in no response body and no log record.
    assert SECRET not in resp.text
    assert SECRET not in caplog.text
    assert (await c.get("/api/agents/bad")).status_code == 404


async def test_put_refusal_leaves_the_stored_agent_untouched(api):
    c, repo, _, _ = api
    await repo.create(_http("gh"))
    ok = await c.post(
        "/api/agents",
        json={"name": "a", "mcp_overrides": {"gh": {"headers": {"X-Key": "first-value-1234"}}}},
    )
    assert ok.status_code == 201
    resp = await c.put(
        "/api/agents/a",
        json={"name": "a", "mcp_overrides": {"gh": {"headers": {"X-Key": None}}}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["mcp_overrides", "gh", "headers", "X-Key"]
    assert (await _stored(api, "a")).mcp_overrides["gh"]["headers"] == {"X-Key": "first-value-1234"}


async def test_a_valid_body_saves_and_a_null_clear_is_still_a_clear(api):
    c, repo, _, _ = api
    await repo.create(_http("gh"))
    await c.post(
        "/api/agents",
        json={"name": "a", "mcp_overrides": {"gh": {"headers": {"X-Key": "first-value-1234"}}}},
    )
    resp = await c.put(
        "/api/agents/a", json={"name": "a", "mcp_overrides": {"gh": {"headers": None}}}
    )
    assert resp.status_code == 200
    assert "headers" not in ((await _stored(api, "a")).mcp_overrides or {}).get("gh", {})


async def test_oauth_source_refuses_authorization_through_the_api(api):
    c, repo, _, _ = api
    await repo.create(_http("o", secrets={"access_token": "t", "dcr_credentials": {"c": 1}}))
    resp = await c.post(
        "/api/agents",
        json={"name": "a", "mcp_overrides": {"o": {"headers": {"Authorization": "Bearer x1"}}}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == OAUTH_AUTHORIZATION_REFUSAL
    # Other headers on that source are still allowed.
    resp = await c.post(
        "/api/agents",
        json={"name": "b", "mcp_overrides": {"o": {"headers": {"X-Org": "acme"}}}},
    )
    assert resp.status_code == 201


async def test_source_list_is_read_for_validation_only_when_the_body_carries_a_credential(api):
    c, _, _, _ = api
    reads = []
    real_list = MCPSourceRepository.list

    async def spy(self, *a, **k):
        reads.append(1)
        return await real_list(self, *a, **k)

    from the_one.interfaces.web import api as api_mod

    seen: list[bool] = []
    real_validate = api_mod.validate_mcp_overrides

    def watch(incoming, sources, masked):
        seen.append(True)
        return real_validate(incoming, sources, masked)

    with (
        patch.object(MCPSourceRepository, "list", spy),
        patch.object(api_mod, "validate_mcp_overrides", watch),
    ):
        await c.post(
            "/api/agents",
            json={"name": "plain", "mcp_overrides": {"gh": {"enabled_tools": ["x"]}}},
        )
        assert seen == []
        await c.post(
            "/api/agents",
            json={"name": "cred", "mcp_overrides": {"gh": {"headers": {"X-K": "value-1234"}}}},
        )
        assert seen == [True]
    assert reads  # the credential body read the source list


# --- DD1/DD8: the overlay ---------------------------------------------------------


def test_header_overlay_removes_library_names_case_insensitively_from_both_layers():
    src = _http(
        config_headers={"x-api-key": "lib-config", "X-Keep": "keep"},
        secrets={"X-API-KEY": "lib-secret", "X-Other": "o"},
    )
    out = _apply_override(src, {"headers": {"X-Api-Key": "agent-value"}})
    sent = build_request_headers(out)
    assert sent == {"X-Keep": "keep", "X-Other": "o", "X-Api-Key": "agent-value"}
    # the input is untouched
    assert src.secrets["X-API-KEY"] == "lib-secret"
    assert src.config["headers"]["x-api-key"] == "lib-config"


def test_bearer_token_replaces_a_library_authorization_in_any_case():
    src = _http(config_headers={"authorization": "Bearer lib"}, secrets={"AUTHORIZATION": "lib2"})
    out = _apply_override(src, {"bearer_token": "agent-tok"})
    assert build_request_headers(out) == {"Authorization": "Bearer agent-tok"}


def test_bearer_token_wins_over_an_authorization_header_in_the_same_entry():
    out = _apply_override(_http(), {"headers": {"authorization": "x"}, "bearer_token": "t"})
    assert build_request_headers(out) == {"Authorization": "Bearer t"}


def test_env_overlay_stays_case_sensitive():
    out = _apply_override(_stdio(secrets={"Key": "lib"}), {"env": {"KEY": "agent"}})
    assert out.secrets == {"Key": "lib", "KEY": "agent"}


def test_oauth_source_skips_per_agent_authorization_and_bearer_but_keeps_other_headers():
    src = _http("o", secrets={"access_token": "t", "dcr_credentials": {"c": 1}, "X-Lib": "l"})
    out = _apply_override(
        src, {"headers": {"authorization": "x", "X-Org": "acme"}, "bearer_token": "stored-before"}
    )
    assert build_request_headers(out) == {"X-Lib": "l", "X-Org": "acme"}
    # only a bearer_token: nothing to apply, the source comes back unchanged
    assert _apply_override(src, {"bearer_token": "x"}) is src
    # only an Authorization header: the skip empties the headers, source unchanged
    assert _apply_override(src, {"headers": {"Authorization": "x"}}) is src


def test_a_source_without_overrides_is_returned_unchanged():
    src = _http()
    assert _apply_override(src, None) is src
    assert _apply_override(src, {}) is src
    assert _apply_override(src, {"enabled_tools": ["a"]}) is src


# --- DD3: blank values -------------------------------------------------------------


def test_build_request_headers_drops_a_blank_final_value():
    src = _http(config_headers={"X-Blank": "  ", "X-Ok": "v"}, secrets={"X-Empty": ""})
    assert build_request_headers(src) == {"X-Ok": "v"}


def test_a_blank_secret_hides_a_config_value_of_the_same_name():
    src = _http(config_headers={"X-K": "v"}, secrets={"X-K": ""})
    assert build_request_headers(src) == {}


def test_build_stdio_environ_drops_blanks_and_lets_the_allowlist_value_through():
    src = _stdio(config_env={"HOME": "", "A": "1"}, secrets={"B": "  ", "C": "3"})
    env = build_stdio_environ(src, {"HOME": "/home/host", "PATH": "/bin"})
    assert env == {"HOME": "/home/host", "PATH": "/bin", "A": "1", "C": "3"}


def test_missing_values_lists_blank_names_with_case_insensitive_headers():
    lib = _http(config_headers={"X-Api-Key": "", "X-Ok": "v"}, secrets={"X-Token": " "})
    assert missing_values(lib, lib) == ["X-Api-Key", "X-Token"]
    eff = _apply_override(lib, {"headers": {"x-api-key": "agent"}})
    assert missing_values(lib, eff) == ["X-Token"]


def test_missing_values_for_stdio_is_case_sensitive_and_excludes_oauth_keys():
    lib = _stdio(config_env={"API_KEY": ""}, secrets={"Other": ""})
    assert missing_values(lib, lib) == ["API_KEY", "Other"]
    eff = _apply_override(lib, {"env": {"api_key": "x"}})
    assert missing_values(lib, eff) == ["API_KEY", "Other"]
    http = _http(secrets={"access_token": "", "X-K": ""})
    assert missing_values(http, http) == ["X-K"]
    assert configured_names(http) == ["X-K"]


# --- DD3: classification ---------------------------------------------------------


def test_credentials_rejected_message_is_unchanged_without_missing_names():
    plain = str(MCPCredentialsRejected("sid", "srv"))
    assert plain == (
        "srv rejected the configured credentials (401). Check the headers for this MCP "
        "server in Library › MCP servers, or the agent's Tools tab if it overrides them."
    )
    named = str(MCPCredentialsRejected("sid", "srv", missing=["X-Api-Key", "X-B"]))
    assert named.startswith(plain)
    assert "It needs a value for X-Api-Key, X-B, which agents set in their Tools tab." in named


def test_bare_401_on_a_source_with_only_blank_headers_is_credentials_rejected_with_names():
    src = _http(config_headers={"X-Api-Key": ""})
    signal = MCPClient(src)._signin_signal(None)
    assert isinstance(signal, MCPCredentialsRejected)
    assert "needs a value for X-Api-Key" in str(signal)


def test_a_401_with_resource_metadata_or_no_headers_stays_a_sign_in_prompt():
    blank = _http(config_headers={"X-Api-Key": ""})
    assert isinstance(MCPClient(blank)._signin_signal("https://x/prm"), MCPAuthRequired)
    assert isinstance(MCPClient(_http())._signin_signal(None), MCPAuthRequired)
    # an OAuth-managed key alone is not "configured headers"
    assert isinstance(
        MCPClient(_http(secrets={"access_token": "t"}))._signin_signal(None), MCPAuthRequired
    )


def test_a_rejection_with_all_values_present_carries_no_missing_sentence():
    src = _http(config_headers={"X-Api-Key": "v"})
    signal = MCPClient(src)._signin_signal(None)
    assert isinstance(signal, MCPCredentialsRejected)
    assert "needs a value" not in str(signal)
