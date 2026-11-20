"""API-based seeders for browser test fixtures.

These helpers POST to the real HTTP endpoints exposed by an `app_clean`
subprocess. Using HTTP (rather than direct DB writes) exercises the real
code path — including the leg-02 schema migration v6, the dev-mode gating
on the mock provider, and the API request validation.

The fixtures that consume these helpers (`app_with_provider`,
`app_with_agent`) are defined in conftest.py.

Mission 20 / Flight 1 / Leg 3 (``harness-credential-plumbing``, DD10):
each function below sends the ``Authorization`` header for the app at the
``base_url`` it already receives, resolved via ``_credential_registry``
(populated by ``conftest.py``'s ``_spawn_app`` at spawn time). The 252
existing call sites that pass a plain ``base_url`` positional/keyword
argument are unchanged — no signature here widened, per the leg's binding
acceptance criterion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from browser._credential_registry import auth_headers_for


@dataclass
class SeededApp:
    """Bundles a running app's base_url with the seeded entity references.

    `agent_name` is None for `app_with_provider` (no agent was seeded);
    populated for `app_with_agent`.
    """

    base_url: str
    provider_id: str
    agent_name: str | None = None


def seed_mock_provider(
    base_url: str,
    name: str = "mock",
    config: dict | None = None,
) -> str:
    """POST a mock provider via /api/providers and return its id.

    Requires the target app to have THE_ONE_DEV_MODE=true (else the API
    rejects mock-typed creates with HTTP 400 — see leg 02 gating).

    `base_url=""` is sent because `LLMProviderConfig.base_url: str` has
    no default and Pydantic 422s if the field is omitted; the mock
    provider never connects anywhere, so the empty string is meaningless
    but valid.
    """
    payload = {
        "name": name,
        "type": "mock",
        "base_url": "",
        "config": config or {},
    }
    r = httpx.post(
        f"{base_url}/api/providers", json=payload, headers=auth_headers_for(base_url), timeout=5.0
    )
    assert r.status_code == 201, f"seed_mock_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


def seed_mock_agent(
    base_url: str,
    provider_id: str,
    name: str = "test-agent",
    model: str = "mock-default",
    system_prompt: str = "You are a test agent.",
    max_iterations: int | None = None,
) -> str:
    """POST an agent via /api/agents and return its name.

    `provider_id` should be the id from a prior seed_mock_provider call.
    Default `model` matches the mock provider's default model.

    Optional AgentConfig fields (description, enabled_tools, kb_ids,
    mcp_source_ids, max_iterations) are omitted by default; their
    defaults from `agent/config.py` apply. `extra: "ignore"` on AgentConfig
    means the API silently drops any unknown fields.

    ``max_iterations`` (M16 F10 L05): when set, bounds the agent loop. A
    static mock that returns the same tool_call every turn would otherwise
    loop to the default ceiling (20); ``max_iterations=1`` gives a turn with
    exactly one assistant message (thinking + tool_call) + one tool result.
    """
    payload = {
        "name": name,
        "provider_config_id": provider_id,
        "llm_model": model,
        "system_prompt": system_prompt,
    }
    if max_iterations is not None:
        payload["max_iterations"] = max_iterations
    r = httpx.post(
        f"{base_url}/api/agents", json=payload, headers=auth_headers_for(base_url), timeout=5.0
    )
    assert r.status_code == 201, f"seed_mock_agent failed: {r.status_code} {r.text}"
    return r.json()["name"]


def seed_mock_agents(
    base_url: str,
    provider_id: str,
    n: int,
    prefix: str = "agent",
    model: str | None = None,
) -> list[str]:
    """POST *n* agents named ``f"{prefix} {i:02d}"`` (i = 1..n) and return the names.

    M25 F3 L3: the scale and filter tests seed 10-60 agents, so this reuses one
    ``httpx.Client`` instead of one connection per agent (``seed_mock_agent``).
    ``model`` (default ``"mock-default"``) is each agent's ``llm_model``; pass a
    distinctive one to exercise the filter's model match. The provider TYPE the
    filter matches comes from ``provider_id``'s provider.
    """
    names = [f"{prefix} {i:02d}" for i in range(1, n + 1)]
    with httpx.Client(base_url=base_url, headers=auth_headers_for(base_url), timeout=10.0) as c:
        for name in names:
            r = c.post(
                "/api/agents",
                json={
                    "name": name,
                    "provider_config_id": provider_id,
                    "llm_model": model or "mock-default",
                    "system_prompt": "You are a test agent.",
                },
            )
            assert r.status_code == 201, f"seed_mock_agents failed: {r.status_code} {r.text}"
    return names


def seed_tool_config(
    base_url: str,
    name: str,
    *,
    enabled: bool | None = None,
    config: dict | None = None,
) -> None:
    """PUT a tool_configs row via the L1 endpoint.

    Either or both of ``enabled`` / ``config`` can be set; omitted keys
    preserve existing state per the L1 PUT contract (see api.py
    ``upsert_tool_config``). One-shot ``httpx.put`` mirrors the
    ``seed_mock_provider`` / ``seed_mock_agent`` POST pattern — no
    persistent client.

    F6 L7 callers use this to set up operator state (disable web_search,
    narrow timeout_seconds_max, seed a denylist for NarrowSuperset
    coverage) before navigating the page in tests.
    """
    body: dict = {}
    if enabled is not None:
        body["enabled"] = enabled
    if config is not None:
        body["config"] = config
    if not body:
        # Nothing to write — silent no-op so callers can pass conditionally
        # without sentinel handling at every site.
        return
    r = httpx.put(
        f"{base_url}/api/tools/configs/{name}",
        json=body,
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code == 200, f"seed_tool_config failed: {r.status_code} {r.text}"


# ── Library seeders (M25 F3 L4a) ─────────────────────────────────────────────


def seed_knowledge_base(base_url: str, name: str, description: str = "") -> str:
    """POST a knowledge base via /api/knowledge-bases and return its id."""
    r = httpx.post(
        f"{base_url}/api/knowledge-bases",
        json={"name": name, "description": description},
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), f"seed_knowledge_base failed: {r.status_code} {r.text}"
    return r.json()["id"]


def seed_mcp_source(
    base_url: str,
    name: str,
    tools: list[str] | None = None,
    *,
    type: str = "stdio",  # noqa: A002
    url: str | None = None,
    last_check: dict | None = None,
    last_updated: float | None = None,
) -> str:
    """POST an MCP source via /api/mcp-sources and return its id.

    ``tools`` (names) seeds ``config._cache.tools`` -- POST keeps the config
    as sent (PUT strips ``_cache``), so the Library list shows a tool count
    without a live connect. Omitted: no cache ("Not connected").
    ``type="streamable-http"`` seeds a remote server at ``url`` (a create via
    this route never connects). ``last_check`` (``{"status": "ok"|"error"|
    "auth_required", "at": epoch-seconds}``) and ``last_updated`` seed the
    cache's connection-check record, so a row can read "Couldn't connect" or
    "Sign-in needed" with no live server and no OAuth storage.
    """
    if type == "stdio":
        config: dict = {"command": "x"}
    else:
        config = {"url": url or "http://127.0.0.1:9/mcp"}
    cache: dict = {}
    if tools is not None:
        cache["tools"] = [{"name": t, "description": ""} for t in tools]
    if last_check is not None:
        cache["last_check"] = last_check
    if last_updated is not None:
        cache["last_updated"] = last_updated
    if cache:
        config["_cache"] = cache
    r = httpx.post(
        f"{base_url}/api/mcp-sources",
        json={"name": name, "type": type, "config": config, "secrets": {}},
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), f"seed_mcp_source failed: {r.status_code} {r.text}"
    return r.json()["id"]


def seed_connector(
    base_url: str,
    name: str,
    default_agent: str | None = None,
    channel_map: dict[str, str] | None = None,
) -> str:
    """POST a DISABLED discord connector via /api/connectors and return its id.

    Disabled (``config.enabled: false``) so it never tries to reach Discord.
    """
    config: dict = {"enabled": False}
    if default_agent is not None:
        config["default_agent"] = default_agent
    if channel_map is not None:
        config["channel_map"] = channel_map
    r = httpx.post(
        f"{base_url}/api/connectors",
        json={"name": name, "type": "discord", "config": config, "secrets": {}},
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), f"seed_connector failed: {r.status_code} {r.text}"
    return r.json()["id"]


def seed_secret(
    base_url: str,
    name: str,
    values: list[tuple[str, str]] | None = None,
    allowed_tools: list[str] | None = None,
    description: str = "",
) -> str:
    """POST a Library secret via /api/secrets and return its id (sortie 10)."""
    r = httpx.post(
        f"{base_url}/api/secrets",
        json={
            "name": name,
            "description": description,
            "values": [
                {"key": k, "value": v}
                for k, v in (
                    values
                    or [("k_" + "".join(c if c.isalnum() else "_" for c in name.lower()), "v")]
                )
            ],
            "allowed_tools": allowed_tools or ["shell"],
        },
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), f"seed_secret failed: {r.status_code} {r.text}"
    return r.json()["id"]


@dataclass
class StubConnectorApp:
    """A running app with a mock agent and an enabled ``stub`` connector."""

    base_url: str
    agent_name: str
    connector_id: str
    peer_id: str = "peer-1"
    peer_name: str = "Alice"
    # A second allowlisted peer (a second connector chat).
    peer2_id: str = "peer-2"
    peer2_name: str = "Bob"
    provider_id: str = ""


def seed_stub_connector(
    base_url: str,
    default_agent: str,
    peer_id: str = "peer-1",
    name: str = "Stub Connector",
    extra_peers: list[str] | None = None,
) -> str:
    """POST an ENABLED ``stub`` connector and return its id.

    The app must run with ``THE_ONE_DEV_MODE=true`` and
    ``THE_ONE_STUB_TEST_ENDPOINT=1`` (the ``app_with_stub_connector`` fixture).
    ``default_agent`` answers its DMs; ``peer_id`` is allow-listed so its DMs
    are admitted without pairing, as is every id in ``extra_peers``.
    """
    r = httpx.post(
        f"{base_url}/api/connectors",
        json={
            "name": name,
            "type": "stub",
            "config": {
                "enabled": True,
                "default_agent": default_agent,
                "allowlist": {"peers": [peer_id, *(extra_peers or [])], "channels": []},
            },
            "secrets": {"token": "stub-token"},
        },
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code in (200, 201), f"seed_stub_connector failed: {r.status_code} {r.text}"
    return r.json()["id"]


def stub_inbound(
    base_url: str,
    connector_id: str,
    text: str,
    peer_id: str = "peer-1",
    peer_name: str = "Alice",
    timeout: float = 15.0,
    channel_id: str | None = None,
) -> None:
    """Push one DM through ``POST /api/_test/stub/inbound`` and wait for the turn.

    The POST blocks for the whole connector turn. A 409 means the stub account
    is not connected yet; retry (bounded by *timeout*) until it is. Chats are
    keyed by ``channel_id`` (default empty): pass a distinct one per peer to get a
    separate chat.
    """
    import time

    deadline = time.monotonic() + timeout
    while True:
        r = httpx.post(
            f"{base_url}/api/_test/stub/inbound",
            json={
                "connector_id": connector_id,
                "peer_id": peer_id,
                "peer_name": peer_name,
                "text": text,
                "is_dm": True,
                **({"channel_id": channel_id} if channel_id else {}),
            },
            headers=auth_headers_for(base_url),
            timeout=30.0,
        )
        if r.status_code == 409 and time.monotonic() < deadline:
            time.sleep(0.25)
            continue
        assert r.status_code == 200, f"stub_inbound failed: {r.status_code} {r.text}"
        return


def seed_agent_with_attachments(
    base_url: str,
    provider_id: str,
    name: str,
    kb_ids: list[str] | None = None,
    mcp_source_ids: list[str] | None = None,
) -> str:
    """POST an agent with knowledge bases and MCP sources attached; return its name."""
    r = httpx.post(
        f"{base_url}/api/agents",
        json={
            "name": name,
            "provider_config_id": provider_id,
            "llm_model": "mock-default",
            "system_prompt": "You are a test agent.",
            "kb_ids": kb_ids or [],
            "mcp_source_ids": mcp_source_ids or [],
        },
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code == 201, f"seed_agent_with_attachments failed: {r.status_code} {r.text}"
    return r.json()["name"]


# ── Chat seeders (M25 F4 L3a) ────────────────────────────────────────────────


def _iso(value: str | datetime) -> str:
    """*value* as the app stores timestamps (``now_iso``: UTC ``isoformat``).

    A naive ``datetime`` is taken as UTC; a string is sent as-is.
    """
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def seed_session(
    base_url: str,
    agent_name: str | None,
    title: str,
    updated_at: str | datetime,
    created_at: str | datetime | None = None,
    platform: str | None = None,
    messages: list | str | None = None,
    session_metadata: dict | None = None,
) -> str:
    """POST a chat session via /api/chat/sessions and return its id.

    The route accepts a whole ``ChatSession``, so a test can place a session in
    the past (``updated_at``; ``created_at`` defaults to the same instant, so a
    session is never created after its last update) and mark it as a connector
    session (``platform``, e.g. ``"discord"``; None is a web session).
    ``messages`` is the stored history: a list (JSON-encoded here) or an
    already-encoded string, as ``the_one.db.codec.encode_messages`` returns;
    omitted, the session is empty. ``session_metadata`` is stored as given (a routine
    chat's ``{"routine": {...}}``). The server allocates the id.
    """
    body: dict = {
        "agent_name": agent_name,
        "title": title,
        "updated_at": _iso(updated_at),
        "created_at": _iso(created_at if created_at is not None else updated_at),
        "platform": platform,
    }
    if messages is not None:
        body["messages"] = messages if isinstance(messages, str) else json.dumps(messages)
    if session_metadata is not None:
        body["session_metadata"] = session_metadata
    r = httpx.post(
        f"{base_url}/api/chat/sessions",
        json=body,
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code == 201, f"seed_session failed: {r.status_code} {r.text}"
    return r.json()["id"]


def enable_notes(base_url: str, agent_name: str, enabled: bool = True) -> None:
    """Flip an agent's notes switch through ``PUT /api/agents/{name}/notes/settings``."""
    r = httpx.put(
        f"{base_url}/api/agents/{agent_name}/notes/settings",
        json={"enabled": enabled},
        headers=auth_headers_for(base_url),
        timeout=5.0,
    )
    assert r.status_code == 200, f"enable_notes failed: {r.status_code} {r.text}"


def seed_note(
    data_dir,
    agent_name: str,
    text: str,
    *,
    untrusted: bool = False,
    sources: list[str] | None = None,
    origin_kind: str = "web",
    session_id: str | None = None,
    label: str | None = None,
    platform: str | None = None,
    peer_id: str | None = None,
    peer_name: str | None = None,
    updated_by: str = "agent",
    created_at: str = "2026-01-01T10:00:00+00:00",
    updated_at: str | None = None,
) -> str:
    """INSERT one ``agent_notes`` row by sync sqlite3 against the instance's database.

    Notes can only be written by the agent (there is no operator create route),
    so a browser test that needs a note with a chosen origin, taint or age seeds
    it directly, the way the self-configuration history tests seed revisions.
    The number is the agent's ``notes_next_number`` counter, bumped here. Pass
    the instance's ``data_dir`` (the ``app_with_data_dir`` fixture).
    """
    import sqlite3
    import uuid

    note_id = uuid.uuid4().hex
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        row = conn.execute(
            "SELECT notes_next_number FROM agents WHERE name = ?", (agent_name,)
        ).fetchone()
        assert row is not None, f"seed_note: no agent {agent_name!r}"
        number = row[0]
        conn.execute(
            "INSERT INTO agent_notes (id, agent_name, number, text, untrusted, untrusted_sources,"
            " origin_kind, origin_session_id, origin_label, origin_platform, origin_peer_id,"
            " origin_peer_name, created_at, updated_at, updated_by)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note_id,
                agent_name,
                number,
                text,
                1 if untrusted else 0,
                json.dumps(sources or []),
                origin_kind,
                session_id,
                label,
                platform,
                peer_id,
                peer_name,
                created_at,
                updated_at or created_at,
                updated_by,
            ),
        )
        conn.execute(
            "UPDATE agents SET notes_next_number = ? WHERE name = ?", (number + 1, agent_name)
        )
        conn.commit()
    finally:
        conn.close()
    return note_id


def seed_gleepglorp_note(
    data_dir,
    text: str,
    *,
    untrusted: bool = False,
    sources: list[str] | None = None,
    origin_kind: str = "other",
    session_id: str | None = None,
    label: str | None = None,
    created_at: str = "2026-01-01T10:00:00+00:00",
) -> str:
    """INSERT one ``gleepglorp_notes`` row by sync sqlite3 (M36 F1 L06).

    Only GleepGlorp's own tools write these, so a browser test seeds them directly. The
    number is the counter row's ``next_number``, bumped here.
    """
    import sqlite3
    import uuid

    note_id = uuid.uuid4().hex
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        (number,) = conn.execute("SELECT next_number FROM gleepglorp_notes_counter").fetchone()
        conn.execute(
            "INSERT INTO gleepglorp_notes (id, number, text, untrusted, untrusted_sources,"
            " origin_kind, origin_session_id, origin_label, created_at, updated_at, updated_by)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'agent')",
            (
                note_id,
                number,
                text,
                1 if untrusted else 0,
                json.dumps(sources or []),
                origin_kind,
                session_id,
                label,
                created_at,
                created_at,
            ),
        )
        conn.execute("UPDATE gleepglorp_notes_counter SET next_number = ?", (number + 1,))
        conn.commit()
    finally:
        conn.close()
    return note_id


def seed_gleepglorp_proposal(
    data_dir,
    session_id: str,
    *,
    kind: str = "agent",
    action: str = "change",
    agent_name: str | None = None,
    changes: dict | None = None,
    base: dict | None = None,
    tool_call_id: str | None = "tc-1",
    status: str = "pending",
    result: dict | None = None,
    untrusted: bool = False,
    sources: list[str] | None = None,
    target_id: str | None = None,
    created_at: str = "2026-01-02T10:00:00+00:00",
    resolved_at: str | None = None,
) -> int:
    """INSERT one ``gleepglorp_proposals`` row by sync sqlite3 (M36 F2 L6).

    Only GleepGlorp's ``propose_change`` tool writes these (no route creates one), so a browser
    test that needs a pending, resolved, failed or stale proposal seeds it, as ``seed_note`` does.
    ``changes`` and ``base`` use the stored field names (ids, not names). Returns the id.
    """
    import sqlite3

    target_key = f"{kind}:{agent_name}:{target_id or 'new'}"
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        cur = conn.execute(
            "INSERT INTO gleepglorp_proposals (session_id, tool_call_id, kind, action, agent_name,"
            " target_id, target_key, changes, base, status, result, untrusted, untrusted_sources,"
            " created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                tool_call_id,
                kind,
                action,
                agent_name,
                target_id,
                target_key,
                json.dumps(changes or {}),
                json.dumps(base) if base is not None else None,
                status,
                json.dumps(result) if result is not None else None,
                1 if untrusted else 0,
                json.dumps(sources or []),
                created_at,
                resolved_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def canonical_schedule(
    time: str = "09:00",
    *,
    repeat: dict | None = "daily",  # type: ignore[assignment]
    date: str = "2026-01-01",
    ends: dict | None = None,
) -> dict:
    """A stored (canonical, DD1) routine schedule. ``repeat`` is ``"daily"`` (every day),
    ``"weekdays"`` (every week on Monday-Friday), a repeat dict, or ``None`` (a one-off)."""
    if repeat == "daily":
        repeat = {"every": 1, "unit": "day"}
    elif repeat == "weekdays":
        repeat = {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]}
    return {
        "start": {"date": date, "time": time},
        "repeat": repeat,
        "ends": ends or {"kind": "never"},
    }


def seed_routine_proposal(
    data_dir,
    agent_name: str,
    action: str,
    payload: dict,
    *,
    routine_name: str,
    created_at: str,
    base: dict | None = None,
    status: str = "pending",
    untrusted: bool = False,
    sources: list[str] | None = None,
    routine_id: str | None = None,
    resolved_at: str | None = None,
) -> str:
    """INSERT one ``agent_routine_proposals`` row by sync sqlite3 (M33 F2 L5).

    No REST route creates a proposal (only the agent's tools do), so a browser test that needs
    a pending, stale or resolved one seeds it, the way ``seed_note`` seeds a note. ``payload``
    is the validated REST request shape (a canonical ``schedule`` plus ``anchor_at``, null for a
    wall-clock schedule); ``base`` the raw stored fields (``name``, ``prompt``, ``schedule``,
    ``anchor_at``, ``enabled``, ``finished_at``).
    Timestamps are fixed ISO strings the test passes. Returns the proposal id.
    """
    import sqlite3
    import uuid

    proposal_id = uuid.uuid4().hex
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        conn.execute(
            "INSERT INTO agent_routine_proposals (id, agent_name, routine_id, routine_name,"
            " action, payload, base, status, untrusted, untrusted_sources, session_id,"
            " created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                proposal_id,
                agent_name,
                routine_id,
                routine_name,
                action,
                json.dumps(payload, sort_keys=True),
                json.dumps(base, sort_keys=True) if base is not None else None,
                status,
                1 if untrusted else 0,
                json.dumps(sources) if sources else None,
                None,
                created_at,
                resolved_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return proposal_id


def seed_agent_routine(
    data_dir,
    agent_name: str,
    name: str,
    *,
    prompt: str = "Say hello.",
    schedule: dict | None = None,
    anchor_at: str | None = None,
    created_by: str = "agent",
    untrusted: bool = False,
    sources: list[str] | None = None,
    created_at: str = "2026-01-01T10:00:00+00:00",
    finished_at: str | None = None,
) -> str:
    """INSERT one ``agent_routines`` row by sync sqlite3 (M33 F2 L5).

    REST cannot set ``created_by='agent'``, the untrusted flag or a finished one-off, so a
    browser test that needs an agent-made, flagged or Done routine seeds it. The next run is
    far in the future (none for a finished one) so the scheduler never fires it. Returns the
    routine id.
    """
    import sqlite3
    import uuid

    routine_id = uuid.uuid4().hex
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        conn.execute(
            "INSERT INTO agent_routines (id, agent_name, name, prompt, schedule, enabled,"
            " next_run_at, anchor_at, created_by, created_at, updated_at,"
            " untrusted, untrusted_sources, finished_at)"
            " VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                routine_id,
                agent_name,
                name,
                prompt,
                json.dumps(schedule or canonical_schedule("09:00")),
                None if finished_at else "2099-01-01T09:00:00+00:00",
                anchor_at,
                created_by,
                created_at,
                created_at,
                1 if untrusted else 0,
                json.dumps(sources) if sources else None,
                finished_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return routine_id
