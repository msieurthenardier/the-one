"""API-based seeders for browser test fixtures.

These helpers POST to the real HTTP endpoints exposed by an `app_clean`
subprocess. Using HTTP (rather than direct DB writes) exercises the real
code path — including the leg-02 schema migration v6, the dev-mode gating
on the mock provider, and the API request validation.

The fixtures that consume these helpers (`app_with_provider`,
`app_with_agent`) are defined in conftest.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


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
    r = httpx.post(f"{base_url}/api/providers", json=payload, timeout=5.0)
    assert r.status_code == 201, f"seed_mock_provider failed: {r.status_code} {r.text}"
    return r.json()["id"]


def seed_mock_agent(
    base_url: str,
    provider_id: str,
    name: str = "test-agent",
    model: str = "mock-default",
    system_prompt: str = "You are a test agent.",
) -> str:
    """POST an agent via /api/agents and return its name.

    `provider_id` should be the id from a prior seed_mock_provider call.
    Default `model` matches the mock provider's default model.

    Optional AgentConfig fields (description, enabled_tools, kb_ids,
    mcp_source_ids, max_iterations) are omitted; their
    defaults from `agent/config.py` apply. `extra: "ignore"` on AgentConfig
    means the API silently drops any unknown fields.
    """
    payload = {
        "name": name,
        "provider_config_id": provider_id,
        "llm_model": model,
        "system_prompt": system_prompt,
    }
    r = httpx.post(f"{base_url}/api/agents", json=payload, timeout=5.0)
    assert r.status_code == 201, f"seed_mock_agent failed: {r.status_code} {r.text}"
    return r.json()["name"]


# M11 F12 L5 — flat-string fixture entries get this default guild_id
# (was ``None`` in L4); post-v25 the Pydantic validator rejects null
# guild_id. Browser tests that exercise guild_id matching pass the
# same constant in their envelope payloads so the entry's guild_id
# matches.
_DEFAULT_FIXTURE_GUILD_ID = "guild-fixture-default"


def _to_v24_allowlist(allowlist: dict) -> dict:
    """Translate a flat-shape allowlist (test-author convenience) to the
    structured-tuple shape required post-v24.

    M11 F12 L4 — browser-test fixtures continue using the flat shape
    (``peers: list[str]``, ``channels: list[str]``, ``roles: list[str]``)
    for readability; this helper does the mechanical translation at
    fixture-build time. Mirrors ``tests/test_connectors_acl.py``'s
    ``_to_v24_shape`` (backend-test sibling) so cross-suite drift is
    obvious.

    The translator is a no-op when the input is already structured.

    Renamings:
      - peers entry ``"alice"`` → ``{"id": "alice", "dm_allowed": True}``
      - channels entry ``"111"`` →
        ``{"guild_id": _DEFAULT_FIXTURE_GUILD_ID, "channel_id": "111"}``
      - roles entry ``"admin"`` →
        ``{"guild_id": _DEFAULT_FIXTURE_GUILD_ID, "role_id": "admin"}``
      - dm_admission ``"allowlisted-peers-only"`` → ``"admin-approved"``

    M11 F12 L5 — flat-string channel/role entries get a default
    guild_id (was ``None`` in L4); post-v25 the Pydantic validator
    rejects null guild_id. Browser tests that exercise guild_id
    matching pass the same constant in their envelope payloads.
    """
    result = dict(allowlist)
    if "peers" in result and isinstance(result["peers"], list):
        peers_new = []
        for entry in result["peers"]:
            if isinstance(entry, dict):
                peers_new.append(entry)
            else:
                peers_new.append({"id": str(entry), "dm_allowed": True})
        result["peers"] = peers_new
    if "channels" in result and isinstance(result["channels"], list):
        channels_new = []
        for entry in result["channels"]:
            if isinstance(entry, dict):
                channels_new.append(entry)
            else:
                channels_new.append(
                    {
                        "guild_id": _DEFAULT_FIXTURE_GUILD_ID,
                        "channel_id": str(entry),
                    }
                )
        result["channels"] = channels_new
    if "roles" in result and isinstance(result["roles"], list):
        roles_new = []
        for entry in result["roles"]:
            if isinstance(entry, dict):
                roles_new.append(entry)
            else:
                roles_new.append(
                    {
                        "guild_id": _DEFAULT_FIXTURE_GUILD_ID,
                        "role_id": str(entry),
                    }
                )
        result["roles"] = roles_new
    if result.get("dm_admission") == "allowlisted-peers-only":
        result["dm_admission"] = "admin-approved"
    return result


def _to_v24_agent_acl(agent_acl: dict | None) -> dict | None:
    """Same translator for the per-agent connector_acls inner dict.

    M11 F12 L4 — per-agent peers/channels/roles mirror the account-scope
    structured-tuple shape; ``admit_dms`` is passed through unchanged.
    ``None`` short-circuits.

    M11 F12 L5 — channels/roles entries from flat strings get
    ``_DEFAULT_FIXTURE_GUILD_ID`` (was ``None`` in L4)."""
    if agent_acl is None:
        return None
    result = dict(agent_acl)
    if isinstance(result.get("peers"), list):
        peers_new = []
        for entry in result["peers"]:
            if isinstance(entry, dict):
                peers_new.append(entry)
            else:
                peers_new.append({"id": str(entry), "dm_allowed": True})
        result["peers"] = peers_new
    if isinstance(result.get("channels"), list):
        channels_new = []
        for entry in result["channels"]:
            if isinstance(entry, dict):
                channels_new.append(entry)
            else:
                channels_new.append(
                    {
                        "guild_id": _DEFAULT_FIXTURE_GUILD_ID,
                        "channel_id": str(entry),
                    }
                )
        result["channels"] = channels_new
    if isinstance(result.get("roles"), list):
        roles_new = []
        for entry in result["roles"]:
            if isinstance(entry, dict):
                roles_new.append(entry)
            else:
                roles_new.append(
                    {
                        "guild_id": _DEFAULT_FIXTURE_GUILD_ID,
                        "role_id": str(entry),
                    }
                )
        result["roles"] = roles_new
    return result


def seed_connector(
    base_url: str,
    name: str = "Test Account",
    type: str = "stub",
    secrets: dict | None = None,
    config: dict | None = None,
    idle_timeout_seconds: int | None = None,
    session_continuation_seconds: int | None = None,
) -> str:
    """POST a connector account via /api/connectors and return its id.

    M10 F2 L6: mirrors ``seed_mock_provider``'s shape. Requires the
    target app subprocess to have registered the StubPlugin under the
    ``'stub'`` type — handled automatically by ``app_clean``'s
    ``THE_ONE_REGISTER_STUB_CONNECTOR=1`` env var (set in conftest.py).

    F5 L8 HAT: also accepts ``session_continuation_seconds`` so tests
    can seed a non-null continuation window and exercise the
    "Never (always continue)" dropdown selection round-trip.

    ``name`` is not unique-constrained server-side, so callers may seed
    duplicates intentionally for grid-rendering tests.

    M11 F12 L4 — auto-translates ``config['allowlist']`` to the post-v24
    structured-tuple shape if the test author passes the flat shape. The
    Pydantic validator REJECTS the flat shape post-L3, so this is the
    seeder-level back-compat shim. Already-structured entries pass
    through unchanged. Also renames the ``dm_admission`` Literal value
    ``"allowlisted-peers-only"`` → ``"admin-approved"`` (operator-
    vocabulary alignment per F12 L3).
    """
    config = config or {}
    if isinstance(config.get("allowlist"), dict):
        config = dict(config)
        config["allowlist"] = _to_v24_allowlist(config["allowlist"])
    payload: dict = {
        "name": name,
        "type": type,
        "config": config,
        "secrets": secrets or {},
    }
    if idle_timeout_seconds is not None:
        payload["idle_timeout_seconds"] = idle_timeout_seconds
    if session_continuation_seconds is not None:
        payload["session_continuation_seconds"] = session_continuation_seconds
    r = httpx.post(f"{base_url}/api/connectors", json=payload, timeout=5.0)
    assert r.status_code == 201, f"seed_connector failed: {r.status_code} {r.text}"
    return r.json()["id"]


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
    r = httpx.put(f"{base_url}/api/tools/configs/{name}", json=body, timeout=5.0)
    assert r.status_code == 200, f"seed_tool_config failed: {r.status_code} {r.text}"
