"""Sanity tests for the seeded fixture variants from conftest.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_session


@pytest.mark.browser
def test_app_with_provider_has_one_mock_provider(app_with_provider: SeededApp) -> None:
    """The app_with_provider fixture seeds exactly one mock provider via the API."""
    r = httpx.get(
        f"{app_with_provider.base_url}/api/providers",
        timeout=5.0,
        headers=auth_headers_for(app_with_provider.base_url),
    )
    assert r.status_code == 200
    providers = r.json()
    assert len(providers) == 1
    p = providers[0]
    assert p["type"] == "mock"
    assert p["id"] == app_with_provider.provider_id
    assert app_with_provider.agent_name is None


@pytest.mark.browser
def test_app_with_agent_has_one_provider_and_one_agent(
    app_with_agent: SeededApp,
) -> None:
    """The app_with_agent fixture seeds a mock provider + an agent referencing it."""
    providers = httpx.get(
        f"{app_with_agent.base_url}/api/providers",
        timeout=5.0,
        headers=auth_headers_for(app_with_agent.base_url),
    ).json()
    assert len(providers) == 1
    assert providers[0]["type"] == "mock"
    assert providers[0]["id"] == app_with_agent.provider_id

    agents = httpx.get(
        f"{app_with_agent.base_url}/api/agents",
        timeout=5.0,
        headers=auth_headers_for(app_with_agent.base_url),
    ).json()
    assert len(agents) == 1
    a = agents[0]
    assert a["name"] == app_with_agent.agent_name
    assert a["provider_config_id"] == app_with_agent.provider_id
    assert a["llm_model"] == "mock-default"


@pytest.mark.browser
def test_seed_session_round_trips_past_dates_and_platform(app_with_agent: SeededApp) -> None:
    """``seed_session`` (M25 F4 L3a) places a session in the past and marks its
    platform; ``GET /api/chat/sessions`` reads both back (``platform`` is on the
    summary since M25 F4 L1), and the detail returns the stored messages."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=3, hours=2)
    created = past - timedelta(days=1)
    old = seed_session(
        base,
        agent,
        "Old discord chat",
        past,
        created_at=created,
        platform="discord",
        messages=[{"role": "user", "content": "hi"}],
    )
    recent = seed_session(base, agent, "Recent chat", (now - timedelta(minutes=5)).isoformat())

    h = auth_headers_for(base)
    rows = {r["id"]: r for r in httpx.get(f"{base}/api/chat/sessions", headers=h, timeout=5).json()}
    assert set(rows) == {old, recent}
    assert rows[old] == {
        "id": old,
        "agent_name": agent,
        "title": "Old discord chat",
        "created_at": created.isoformat(),
        "updated_at": past.isoformat(),
        "platform": "discord",
    }
    # created_at defaults to updated_at; a web session has no platform.
    assert rows[recent]["created_at"] == rows[recent]["updated_at"]
    assert rows[recent]["platform"] is None
    detail = httpx.get(f"{base}/api/chat/sessions/{old}", headers=h, timeout=5).json()
    assert detail["messages"] == [{"role": "user", "content": "hi"}]
