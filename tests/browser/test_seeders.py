"""Sanity tests for the seeded fixture variants from conftest.py."""

from __future__ import annotations

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp


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
