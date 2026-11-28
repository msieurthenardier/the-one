"""The chat's Sign in flow owns its outcome (sortie 22, leg 2, DD3 / DD5).

``POST /api/oauth/start`` reports ``auth_resolved`` and resumes the paused turn exactly once,
only after the new tokens are saved; on failure it sends the only ``auth_failed``. The OAuth
callback only resolves the code. These tests run the real ``OAuthASStub``, ``shared_app()`` and
template databases (no mock libraries); the unit-level cases use a stand-in client for the
flow's HTTP call, as ``test_oauth_start_endpoint.py`` does.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

import httpx
import pytest
from conftest import FakeLLM
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from tests.fixtures.oauth import OAuthASStub
from the_one.agent.core import Agent
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import Encryptor
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web import mcp_oauth_flow
from the_one.interfaces.web.app import Session, _process_and_broadcast
from the_one.llm.base import Message, ToolCall
from the_one.mcp import _pool
from the_one.mcp.errors import MCPAuthRequired
from the_one.mcp.oauth import _state
from the_one.mcp.oauth.storage import MCPSourceTokenStorage
from the_one.tools.base import Tool, ToolRegistry

SRC = "src-chat-signin"
CSID = "cs-chat-signin"
DCR = {
    "client_id": "stub-client-1",
    "redirect_uris": ["http://127.0.0.1:8484/api/oauth/callback"],
    "token_endpoint_auth_method": "none",
}


@pytest.fixture(autouse=True)
async def _clean():
    _state._pending.clear()
    mcp_oauth_flow._flows.clear()
    mcp_oauth_flow._resolved_count.clear()
    mcp_oauth_flow._resuming.clear()
    await _pool._clear_for_test()
    yield
    _state._pending.clear()
    mcp_oauth_flow._flows.clear()
    mcp_oauth_flow._resolved_count.clear()
    mcp_oauth_flow._resuming.clear()
    web_app._sessions.pop(CSID, None)
    await _pool._clear_for_test()


@pytest.fixture
async def api_and_repo(tmp_path):
    conn = await connect_template_db(tmp_path / "chat-signin.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=shared_app()),
            base_url="http://test",
            headers=auth_headers(),
        ) as client:
            yield client, repo
    await conn.close()


class _RepoTokenTool(Tool):
    """Auth-gated tool: succeeds only once the stored token is the stub's valid one."""

    name = "mcp__x__echo"
    description = "auth-gated"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}  # noqa: RUF012

    def __init__(self, repo: MCPSourceRepository) -> None:
        self._repo = repo

    async def execute(self, **kwargs: Any) -> str:
        source = await self._repo.get(SRC)
        if source.secrets.get("access_token") != "stub-access-token":
            raise MCPAuthRequired(source_id=SRC, resource_metadata_url=None)
        return "signed-in ok"


class Rig:
    """A paused real-agent chat session, with frames and resume calls recorded."""

    def __init__(self, monkeypatch, repo: MCPSourceRepository) -> None:
        self.frames: list[dict[str, Any]] = []
        self.resumes = 0
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
        monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))

        async def capture(session, payload, exclude=None):  # noqa: ARG001
            self.frames.append(payload)

        monkeypatch.setattr(web_app, "_send_to_session", capture)
        real_resume = web_app._resume_paused_session

        async def counting_resume(session):
            self.resumes += 1
            await real_resume(session)

        monkeypatch.setattr(web_app, "_resume_paused_session", counting_resume)

        registry = ToolRegistry()
        registry.register(_RepoTokenTool(repo))
        tc = ToolCall(id="tc-1", name="mcp__x__echo", arguments={})
        llm = FakeLLM([Message.assistant("", tool_calls=[tc]), Message.assistant("all done")])
        self.agent = Agent(llm=llm, tools=registry, system_prompt="t")
        self.session = Session(id=CSID, agent=self.agent, created="2026-11-28T00:00:00+00:00")  # type: ignore[arg-type]
        web_app._sessions[CSID] = self.session

    async def pause(self) -> None:
        await _process_and_broadcast(self.session, "go")
        assert self.agent._deferred_tool_calls is not None

    def types(self) -> list[str]:
        return [f.get("type", "?") for f in self.frames]

    def of(self, type_: str) -> list[dict[str, Any]]:
        return [f for f in self.frames if f.get("type") == type_]

    async def wait_for(self, type_: str, timeout: float = 15.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = self.of(type_)
            if found:
                return found[-1]
            await asyncio.sleep(0.02)
        raise AssertionError(f"no {type_!r} frame: {self.types()}")

    async def consent_url(self) -> str:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for f in self.of("auth_required"):
                if f.get("consent_url"):
                    return f["consent_url"]
            await asyncio.sleep(0.02)
        raise AssertionError(f"no consent_url frame: {self.types()}")


async def _seed(repo: MCPSourceRepository, base_url: str, secrets: dict | None = None) -> None:
    await repo.create(
        MCPSource(
            id=SRC,
            name="stub",
            type="streamable-http",
            config={"url": f"{base_url}/mcp"},
            secrets=dict(DCR_ONLY if secrets is None else secrets),
        )
    )


DCR_ONLY = {"dcr_credentials": DCR}


async def _start(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/oauth/start",
        json={"source_id": SRC, "chat_session_id": CSID, "tool_call_id": "tc-1"},
    )
    assert resp.status_code == 200, resp.text


async def _complete_consent(client: AsyncClient, rig: Rig) -> None:
    """Follow the flow's consent URL to the stub and hit the callback with its redirect."""
    consent = await rig.consent_url()
    async with httpx.AsyncClient() as plain:
        redirect = await plain.get(consent, follow_redirects=False)
    assert redirect.status_code == 302
    parts = urlsplit(redirect.headers["location"])
    resp = await client.get(f"{parts.path}?{parts.query}")
    assert resp.status_code == 200
    assert "Login successful" in resp.text


async def _settle() -> None:
    """Wait for every flow and resume the module scheduled."""
    for _ in range(500):
        if not mcp_oauth_flow._flows and not mcp_oauth_flow._resuming:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("flow or resume never ended")


# --- End to end -----------------------------------------------------------------------


async def test_resume_waits_for_the_token_save_then_happens_once(api_and_repo, monkeypatch):
    client, repo = api_and_repo
    with OAuthASStub(token_delay=1.0) as stub:
        await _seed(repo, stub.base_url)
        rig = Rig(monkeypatch, repo)
        await rig.pause()
        assert len(rig.of("auth_required")) == 1  # the pause itself

        await _start(client)
        await _complete_consent(client, rig)

        # The callback has answered; the token exchange is still held by the stub.
        await asyncio.sleep(0.4)
        assert rig.of("auth_resolved") == []
        assert rig.resumes == 0
        assert "access_token" not in (await repo.get(SRC)).secrets

        await rig.wait_for("done")
        await _settle()

        assert (await repo.get(SRC)).secrets["access_token"] == "stub-access-token"
        assert len(rig.of("auth_resolved")) == 1
        assert rig.resumes == 1
        assert len(rig.of("done")) == 1
        assert rig.types().index("auth_resolved") < rig.types().index("done")
        results = [f for f in rig.of("tool_result") if f.get("tool_call_id") == "tc-1"]
        assert results and "signed-in ok" in results[-1]["content"]
        # No second pause for this turn: the one auth_required carrying no consent URL is
        # the original pause, the other is the flow's consent broadcast.
        assert [bool(f.get("consent_url")) for f in rig.of("auth_required")] == [False, True]
        assert rig.of("auth_failed") == []


async def test_token_endpoint_refusal_reports_one_failure_and_never_resumes(
    api_and_repo, monkeypatch
):
    client, repo = api_and_repo
    with OAuthASStub(token_status=400) as stub:
        await _seed(repo, stub.base_url)
        rig = Rig(monkeypatch, repo)
        await rig.pause()

        await _start(client)
        await _complete_consent(client, rig)
        failed = await rig.wait_for("auth_failed")
        await _settle()

        assert len(rig.of("auth_failed")) == 1
        assert failed["error"] == "start_failed"
        assert failed["description"]
        assert rig.of("auth_resolved") == []
        assert rig.resumes == 0


async def test_idp_denial_reports_exactly_one_failure_with_the_idp_text(api_and_repo, monkeypatch):
    from mcp.client.auth.exceptions import OAuthFlowError

    client, repo = api_and_repo
    with OAuthASStub() as stub:
        await _seed(repo, stub.base_url)
        rig = Rig(monkeypatch, repo)
        await rig.pause()

        await _start(client)
        consent = await rig.consent_url()
        state = dict(p.split("=", 1) for p in urlsplit(consent).query.split("&"))["state"]
        resp = await client.get(
            "/api/oauth/callback",
            params={"state": state, "error": "access_denied", "error_description": "no thanks"},
        )
        assert "Login failed" in resp.text
        await rig.wait_for("auth_failed")
        await _settle()
        await asyncio.sleep(0.1)

        failed = rig.of("auth_failed")
        assert len(failed) == 1
        assert failed[0]["description"] == str(OAuthFlowError("no thanks")) == "no thanks"
        assert rig.of("auth_resolved") == [] and rig.resumes == 0


async def test_idp_denial_without_description_reports_the_error_code(api_and_repo, monkeypatch):
    client, repo = api_and_repo
    with OAuthASStub() as stub:
        await _seed(repo, stub.base_url)
        rig = Rig(monkeypatch, repo)
        await rig.pause()
        await _start(client)
        consent = await rig.consent_url()
        state = dict(p.split("=", 1) for p in urlsplit(consent).query.split("&"))["state"]
        await client.get("/api/oauth/callback", params={"state": state, "error": "access_denied"})
        failed = await rig.wait_for("auth_failed")
        await _settle()
        assert failed["description"] == "access_denied"
        assert len(rig.of("auth_failed")) == 1


async def test_a_valid_stored_token_resolves_and_resumes(api_and_repo, monkeypatch):
    client, repo = api_and_repo
    with OAuthASStub() as stub:
        await _seed(repo, stub.base_url)
        rig = Rig(monkeypatch, repo)
        await rig.pause()
        # A Library sign-in landed meanwhile; then Sign in is clicked in the chat.
        source = await repo.get(SRC)
        source.secrets = {
            **source.secrets,
            "access_token": "stub-access-token",
            "token_expires_at": time.time() + 3600,
        }
        await repo.update(source)
        await _start(client)
        await rig.wait_for("auth_resolved")
        await _settle()
        assert rig.resumes == 1
        assert stub.token_requests == []  # nothing to sign in to


async def test_known_limitation_a_method_only_401_resolves_then_repauses(api_and_repo, monkeypatch):
    """Known limitation (sortie 22 DD3): the flow replays ``initialize``. When only
    ``tools/call`` needs the token, ``initialize`` gets a 2xx with no save, the flow resolves,
    the resumed call refuses again and the turn re-pauses (a 403 step-up behaves alike)."""
    client, repo = api_and_repo
    with OAuthASStub(auth_required_methods={"tools/call"}) as stub:
        await _seed(repo, stub.base_url)
        rig = Rig(monkeypatch, repo)
        await rig.pause()
        assert len(rig.of("auth_required")) == 1

        await _start(client)
        await rig.wait_for("auth_resolved")
        await _settle()

        assert rig.resumes == 1
        assert stub.token_requests == []
        # Resolved, resumed, then paused again with a new pause (no consent URL, no done).
        assert len(rig.of("auth_required")) == 2
        assert rig.of("done") == []
        assert rig.agent._deferred_tool_calls is not None


# --- The flow module, with a stand-in HTTP client ---------------------------------------


class _Storage:
    def __init__(self, saved: bool = False) -> None:
        self.tokens_saved = saved


class _Provider:
    def __init__(self, saved: bool = False) -> None:
        async def redirect_handler(_url: str) -> None:
            self.redirects += 1

        self.redirects = 0
        self.context = SimpleNamespace(storage=_Storage(saved), redirect_handler=redirect_handler)


def _client_class(behaviour):
    class _C:
        def __init__(self, *_a: Any, **_k: Any) -> None: ...

        async def __aenter__(self) -> _C:
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

        async def post(self, url: str, **_k: Any) -> Any:
            return await behaviour()

    return _C


def _resp(status: int) -> Any:
    return type("Resp", (), {"status_code": status})()


class _Paused:
    """Stand-in session whose resume clears the pause after a short hold."""

    def __init__(self, sid: str) -> None:
        self.id = sid
        self.agent = type("A", (), {"_deferred_tool_calls": [object()]})()


@pytest.fixture
def flow_rig(monkeypatch):
    frames: list[dict[str, Any]] = []
    resumes: list[str] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        frames.append(payload)

    async def resume(session):
        resumes.append(session.id)
        await asyncio.sleep(0.2)
        frames.append({"type": "done"})
        session.agent._deferred_tool_calls = None

    monkeypatch.setattr(web_app, "_send_to_session", capture)
    monkeypatch.setattr(web_app, "_resume_paused_session", resume)
    sessions: dict[str, _Paused] = {}

    def add(sid: str) -> _Paused:
        sessions[sid] = _Paused(sid)
        web_app._sessions[sid] = sessions[sid]  # type: ignore[assignment]
        return sessions[sid]

    yield frames, resumes, add
    for sid in sessions:
        web_app._sessions.pop(sid, None)


def _start_flow(provider, *, sid="cs-u", source="s1"):
    mcp_oauth_flow.start_chat_sign_in(
        provider,
        server_url="https://x.example/mcp",
        chat_session_id=sid,
        source_id=source,
        tool_call_id="tc-u",
        headers_for=lambda _v: {},
    )


async def test_final_non_2xx_without_a_save_reports_the_pinned_failure(flow_rig):
    frames, resumes, add = flow_rig
    add("cs-u")

    async def answer():
        return _resp(404)

    with patch("the_one.interfaces.web.mcp_oauth_flow.httpx2.AsyncClient", _client_class(answer)):
        _start_flow(_Provider())
        await _settle()
    assert frames == [
        {
            "type": "auth_failed",
            "source_id": "s1",
            "error": "start_failed",
            "description": mcp_oauth_flow.START_FAILED_DESCRIPTION.format(status=404),
        }
    ]
    assert "404" in frames[0]["description"] and resumes == []


async def test_a_save_wins_over_a_failed_retry(flow_rig):
    frames, resumes, add = flow_rig
    add("cs-u")

    async def answer():
        raise RuntimeError("retry blew up after the save")

    with patch("the_one.interfaces.web.mcp_oauth_flow.httpx2.AsyncClient", _client_class(answer)):
        _start_flow(_Provider(saved=True))
        await _settle()
    assert [f["type"] for f in frames] == ["auth_resolved", "done"] and resumes == ["cs-u"]


async def test_a_missing_or_unusable_provider_reports_a_fixed_failure(flow_rig):
    frames, resumes, add = flow_rig
    add("cs-u")
    _start_flow(None)
    await _settle()
    assert [f["description"] for f in frames] == [mcp_oauth_flow.NO_PROVIDER_DESCRIPTION]
    assert resumes == []


async def test_the_redirect_wrapper_resets_the_save_flag_before_the_original_runs():
    provider = _Provider(saved=True)
    storage = provider.context.storage
    mcp_oauth_flow._wrap_redirect_handler(provider, storage)
    await provider.context.redirect_handler("https://as.example/authorize?state=s")
    assert storage.tokens_saved is False and provider.redirects == 1


async def test_a_session_that_closed_gets_nothing_and_no_resume(flow_rig):
    frames, resumes, _add = flow_rig  # no session registered

    async def answer():
        return _resp(200)

    with patch("the_one.interfaces.web.mcp_oauth_flow.httpx2.AsyncClient", _client_class(answer)):
        _start_flow(_Provider())
        await _settle()
    assert frames == [] and resumes == []


async def test_two_flows_for_one_session_resume_once(flow_rig):
    """Two tabs: two sources' flows for the same chat session finish back to back."""
    frames, resumes, add = flow_rig
    add("cs-u")

    async def answer():
        return _resp(200)

    with patch("the_one.interfaces.web.mcp_oauth_flow.httpx2.AsyncClient", _client_class(answer)):
        _start_flow(_Provider(), source="s1")
        _start_flow(_Provider(), source="s2")
        await _settle()
    assert resumes == ["cs-u"]
    assert [f["type"] for f in frames].count("done") == 1
    assert [f["type"] for f in frames].count("auth_resolved") == 2


async def test_a_superseded_flow_failing_later_sends_no_auth_failed(flow_rig):
    frames, _resumes, add = flow_rig
    add("cs-u")
    gates = [asyncio.Event(), asyncio.Event()]
    calls = iter(range(2))

    async def answer():
        gate = gates[next(calls)]
        await gate.wait()
        raise RuntimeError("TTL")

    with patch("the_one.interfaces.web.mcp_oauth_flow.httpx2.AsyncClient", _client_class(answer)):
        _start_flow(_Provider())
        await asyncio.sleep(0.05)
        _start_flow(_Provider())  # the operator clicked Sign in again
        await asyncio.sleep(0.05)
        gates[0].set()  # the older flow fails at its TTL
        await asyncio.sleep(0.1)
        assert frames == []
        gates[1].set()  # the latest flow's failure is reported
        await _settle()
    assert [f["type"] for f in frames] == ["auth_failed"]
    assert frames[0]["description"] == "TTL"


async def test_completing_the_older_flow_resumes_once_and_cancels_the_newer(flow_rig):
    frames, resumes, add = flow_rig
    add("cs-u")
    gate = asyncio.Event()
    calls = iter(range(2))

    async def answer():
        if next(calls) == 0:
            await gate.wait()
            return _resp(200)
        await asyncio.Event().wait()  # the newer flow never completes by itself

    with patch("the_one.interfaces.web.mcp_oauth_flow.httpx2.AsyncClient", _client_class(answer)):
        _start_flow(_Provider())
        await asyncio.sleep(0.05)
        _start_flow(_Provider())
        await asyncio.sleep(0.05)
        gate.set()
        await _settle()
    assert resumes == ["cs-u"]
    assert [f["type"] for f in frames] == ["auth_resolved", "done"]
    assert mcp_oauth_flow._flows == {}


async def test_storage_flag_stays_false_when_the_write_fails(repo_for_storage):
    repo, sid = repo_for_storage
    storage = MCPSourceTokenStorage(repo, sid)
    assert storage.tokens_saved is False
    from mcp.shared.auth import OAuthToken

    with patch.object(repo, "update", AsyncMock(side_effect=RuntimeError("disk"))):
        with pytest.raises(RuntimeError):
            await storage.set_tokens(OAuthToken(access_token="a", token_type="Bearer"))
    assert storage.tokens_saved is False
    await storage.set_tokens(OAuthToken(access_token="a", token_type="Bearer"))
    assert storage.tokens_saved is True


@pytest.fixture
async def repo_for_storage(tmp_path):
    conn = await connect_template_db(tmp_path / "storage.db")
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)
    await repo.create(
        MCPSource(id="s-st", name="st", type="streamable-http", config={"url": "https://x/mcp"})
    )
    yield repo, "s-st"
    await conn.close()
