"""
AIAT — Automated Integration and Acceptance Tests

These tests run against the live the-one agent via /api/chat.
They validate that the agent can actually do what it's supposed to do,
end-to-end, with the real LLM, real tools, and real container.

Usage:
    pytest -m live tests/test_aiat.py
    THE_ONE_TEST_URL=http://localhost:8484 pytest -m live tests/test_aiat.py
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

TIMEOUT = 120  # some tool calls are slow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the live agent, from env var or default."""
    return os.environ.get("THE_ONE_TEST_URL", "http://localhost:8484")


@pytest.fixture
def session_id() -> str:
    """Unique session ID per test."""
    return f"aiat-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def chat(base_url: str, session_id: str, message: str) -> dict:
    """Send a message and return the full response."""
    r = httpx.post(
        f"{base_url}/api/chat",
        json={"message": message, "source": "aiat", "session_id": session_id},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def reset(base_url: str, session_id: str) -> None:
    """Reset agent context between tests."""
    httpx.post(
        f"{base_url}/api/chat/reset",
        json={"session_id": session_id},
        timeout=10,
        headers={"Content-Type": "application/json"},
    )
    time.sleep(0.5)


def assistant_text(resp: dict) -> str:
    """Extract concatenated assistant text from response."""
    return "\n".join(
        m.get("content", "") for m in resp.get("messages", []) if m.get("role") == "assistant"
    )


def has_tool_call(resp: dict, name: str | None = None) -> bool:
    """Check if response contains a tool call (optionally by name)."""
    for m in resp.get("messages", []):
        for tc in m.get("tool_calls", []):
            if name is None or tc.get("name") == name:
                return True
    return False


def has_tool_result(resp: dict, substring: str | None = None) -> bool:
    """Check if response contains a tool result (optionally containing substring)."""
    for m in resp.get("messages", []):
        if m.get("role") == "tool":
            if substring is None:
                return True
            if substring.lower() in m.get("content", "").lower():
                return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_health(base_url: str) -> None:
    """Service is up and responding."""
    r = httpx.get(f"{base_url}/api/info", timeout=10)
    r.raise_for_status()
    data = r.json()
    assert "version" in data, f"missing version in {data}"
    assert "base_prompt" in data, f"missing base_prompt in {data}"


@pytest.mark.live
def test_basic_chat(base_url: str, session_id: str) -> None:
    """Agent responds to a simple message."""
    resp = chat(base_url, session_id, "What is 2 + 2? Reply with just the number.")
    text = assistant_text(resp)
    assert "4" in text, f"expected '4' in response, got: {text[:200]}"


@pytest.mark.live
def test_tool_use_file_read(base_url: str, session_id: str) -> None:
    """Agent can read a file using a tool."""
    resp = chat(
        base_url,
        session_id,
        "Read the file /app/pyproject.toml and tell me the project name.",
    )
    text = assistant_text(resp)
    assert has_tool_result(resp), "expected a tool result in response"
    assert "gleepglorp" in text.lower() or "the_one" in text.lower(), (
        f"expected project name in response, got: {text[:200]}"
    )


@pytest.mark.live
def test_reset(base_url: str, session_id: str) -> None:
    """Context reset works — agent forgets previous conversation."""
    chat(base_url, session_id, "Remember this secret code: PINEAPPLE42")
    reset(base_url, session_id)
    resp = chat(base_url, session_id, "What was the secret code I told you?")
    text = assistant_text(resp)
    assert "PINEAPPLE42" not in text, f"agent remembered after reset: {text[:200]}"


@pytest.mark.live
def test_self_awareness(base_url: str, session_id: str) -> None:
    """Agent knows it's 'the-one' and can describe its own architecture."""
    resp = chat(
        base_url, session_id, "What is your name and what directory is your source code in?"
    )
    text = assistant_text(resp)
    assert "gleepglorp" in text.lower() or "the_one" in text.lower(), (
        f"agent doesn't know its name: {text[:200]}"
    )


@pytest.mark.live
def test_multi_step(base_url: str, session_id: str) -> None:
    """Agent can handle a task that requires multiple tool calls."""
    resp = chat(
        base_url,
        session_id,
        "List the files in /app/the_one/tools/ and tell me how many there are.",
    )
    text = assistant_text(resp)
    assert has_tool_result(resp), "expected tool usage for listing files"
    assert "shell" in text.lower() or "base" in text.lower() or len(text) > 20, (
        f"expected file listing response, got: {text[:200]}"
    )
