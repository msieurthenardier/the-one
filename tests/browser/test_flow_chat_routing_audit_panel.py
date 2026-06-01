"""Browser tests for the Chat UI routing-audit panel (M11 F13 L5).

Verifies:

1. Empty state renders for a session with no routing entries.
2. Multi-disposition entries render with the correct badge classes.
3. Per-entry expansion reveals the raw fields (rule_index, match, intercept_source).
4. policy-silent entries expand to show the nested policy dict.
5. Refresh button re-fetches and re-renders.
6. Panel is collapsed by default (outer <details> is not [open]).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_ready(base_url: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"App subprocess exited with code {proc.returncode} during startup"
            )
        try:
            r = httpx.get(f"{base_url}/api/info", timeout=1.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_exc = exc
        time.sleep(0.1)
    raise TimeoutError(f"App at {base_url} not ready within {timeout}s (last: {last_exc})")


@pytest.fixture
def app_with_data_dir(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Spawn a fresh app subprocess and yield (base_url, data_dir).

    Mirrors the fixture in tests/browser/test_flow_chat_session_list_source_badge.py.
    Direct-DB access lets us seed session_metadata['routing'] before the
    Chat UI joins the session.
    """
    port = _free_port()
    data_dir = tmp_path / "the-one-data"
    data_dir.mkdir()
    env = os.environ.copy()
    env["THE_ONE_DATA_DIR"] = str(data_dir)
    env["THE_ONE_DEV_MODE"] = "true"
    env["THE_ONE_REGISTER_STUB_CONNECTOR"] = "1"
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "the_one.interfaces.web.app:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_ready(base_url, proc=proc, timeout=15.0)
    except (TimeoutError, RuntimeError):
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"App subprocess on port {port} did not become ready.\n"
            f"--- stdout ---\n{stdout.decode(errors='replace')}\n"
            f"--- stderr ---\n{stderr.decode(errors='replace')}"
        )
    try:
        yield base_url, data_dir
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _seed_session_with_metadata(
    data_dir: Path,
    *,
    session_id: str,
    agent_name: str,
    title: str,
    session_metadata: dict | None,
) -> None:
    """INSERT a chat_sessions row with optional session_metadata."""
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO chat_sessions ("
            " id, agent_name, title, messages, created_at, updated_at,"
            " platform, connector_id, channel_id, thread_id, peer_id,"
            " session_metadata, last_inbound_at"
            ") VALUES (?, ?, ?, ?, datetime('now'), datetime('now'),"
            " NULL, NULL, NULL, NULL, NULL, ?, NULL)",
            (
                session_id, agent_name, title, "[]",
                json.dumps(session_metadata) if session_metadata is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _append_routing_entry(data_dir: Path, *, session_id: str, entry: dict) -> None:
    """Read-modify-write append to session_metadata['routing']."""
    db_path = data_dir / "the-one.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT session_metadata FROM chat_sessions WHERE id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        meta = json.loads(row[0]) if row and row[0] else {}
        routing = meta.get("routing") or []
        routing.append(entry)
        meta["routing"] = routing
        conn.execute(
            "UPDATE chat_sessions SET session_metadata = ? WHERE id = ?",
            (json.dumps(meta), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def _navigate_to_session(page: Page, base_url: str, session_id: str) -> None:
    page.goto(f"{base_url}/#chat/sessions/{session_id}")
    # The panel container mounts during chrome construction — wait for it.
    expect(page.locator('[data-testid="routing-audit-panel"]')).to_be_visible(timeout=8000)


# ── Test 1: empty state ────────────────────────────────────────────────────


@pytest.mark.browser
def test_routing_audit_empty_state(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id, name="empty-agent")
    sid = "sess-empty-1"
    _seed_session_with_metadata(
        data_dir, session_id=sid, agent_name="empty-agent",
        title="Empty Routing", session_metadata=None,
    )
    _navigate_to_session(page, base_url, sid)
    # Expand the outer details to reveal the empty-state inside.
    page.locator('[data-testid="routing-audit-summary"]').click()
    empty = page.locator('[data-testid="routing-audit-empty"]')
    expect(empty).to_be_visible(timeout=4000)
    expect(empty).to_contain_text("No routing decisions yet")


# ── Test 2: multi-disposition render + badge classes ─────────────────────


@pytest.mark.browser
def test_routing_audit_renders_all_four_dispositions(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id, name="multi-agent")
    sid = "sess-multi-1"
    routing = [
        {"ts": "2026-05-31T00:00:01", "agent": "multi-agent", "rule_index": 0,
         "scope": "channel", "match": None, "reason": "test", "disposition": "stepped"},
        {"ts": "2026-05-31T00:00:02", "agent": "multi-agent", "rule_index": 0,
         "scope": "default", "match": None, "reason": "ping", "disposition": "command-intercepted",
         "intercept_source": "builtin"},
        {"ts": "2026-05-31T00:00:03", "agent": None, "rule_index": None,
         "scope": "default", "match": None, "reason": "no agents", "disposition": "no-eligible"},
        {"ts": "2026-05-31T00:00:04", "agent": "multi-agent", "rule_index": 0,
         "scope": "channel", "match": None, "reason": "gate silent", "disposition": "policy-silent",
         "policy": {"outcome": "inference-no", "account_always_listen": True,
                    "agent_always_listen": True, "inference_provider_id": "prov-x",
                    "inference_model": "qwen2.5:7b"}},
    ]
    _seed_session_with_metadata(
        data_dir, session_id=sid, agent_name="multi-agent",
        title="Multi Routing", session_metadata={"routing": routing},
    )
    _navigate_to_session(page, base_url, sid)
    page.locator('[data-testid="routing-audit-summary"]').click()
    rows = page.locator('[data-testid="routing-audit-row"]')
    expect(rows).to_have_count(4, timeout=4000)
    # Verify per-disposition badge classes.
    for disp in ("stepped", "command-intercepted", "no-eligible", "policy-silent"):
        badge = page.locator(f'.routing-audit-badge--{disp}')
        expect(badge).to_be_visible()


# ── Test 3: per-entry expansion shows raw fields ────────────────────────


@pytest.mark.browser
def test_routing_audit_expansion_shows_raw_fields(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id, name="exp-agent")
    sid = "sess-exp-1"
    routing = [
        {"ts": "2026-05-31T00:00:01", "agent": "exp-agent", "rule_index": 42,
         "scope": "channel", "match": "C-test", "reason": "matched channel rule 42",
         "disposition": "stepped"},
    ]
    _seed_session_with_metadata(
        data_dir, session_id=sid, agent_name="exp-agent",
        title="Expansion Test", session_metadata={"routing": routing},
    )
    _navigate_to_session(page, base_url, sid)
    page.locator('[data-testid="routing-audit-summary"]').click()
    row_summary = page.locator('[data-testid="routing-audit-row-summary"]').first
    row_summary.click()
    expansion = page.locator('[data-testid="routing-audit-expansion"]').first
    expect(expansion).to_be_visible(timeout=4000)
    expect(expansion).to_contain_text("rule_index")
    expect(expansion).to_contain_text("42")
    expect(expansion).to_contain_text("match")


# ── Test 4: policy-silent expansion shows nested policy dict ────────────


@pytest.mark.browser
def test_routing_audit_policy_silent_renders_nested_policy(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id, name="policy-agent")
    sid = "sess-policy-1"
    routing = [
        {"ts": "2026-05-31T00:00:01", "agent": "policy-agent", "rule_index": 0,
         "scope": "channel", "match": None, "reason": "gate silent",
         "disposition": "policy-silent",
         "policy": {"outcome": "inference-no", "account_always_listen": True,
                    "agent_always_listen": True, "inference_provider_id": "prov-policy",
                    "inference_model": "test-model-xyz"}},
    ]
    _seed_session_with_metadata(
        data_dir, session_id=sid, agent_name="policy-agent",
        title="Policy Test", session_metadata={"routing": routing},
    )
    _navigate_to_session(page, base_url, sid)
    page.locator('[data-testid="routing-audit-summary"]').click()
    page.locator('[data-testid="routing-audit-row-summary"]').first.click()
    policy = page.locator('[data-testid="routing-audit-policy"]')
    expect(policy).to_be_visible(timeout=4000)
    expect(policy).to_contain_text("outcome")
    expect(policy).to_contain_text("inference-no")
    expect(policy).to_contain_text("inference_provider_id")
    expect(policy).to_contain_text("prov-policy")
    expect(policy).to_contain_text("inference_model")
    expect(policy).to_contain_text("test-model-xyz")


# ── Test 5: Refresh button re-fetches ───────────────────────────────────


@pytest.mark.browser
def test_routing_audit_refresh_re_fetches(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id, name="refresh-agent")
    sid = "sess-refresh-1"
    initial = {
        "routing": [
            {"ts": "2026-05-31T00:00:01", "agent": "refresh-agent", "rule_index": 0,
             "scope": "channel", "match": None, "reason": "first",
             "disposition": "stepped"},
        ]
    }
    _seed_session_with_metadata(
        data_dir, session_id=sid, agent_name="refresh-agent",
        title="Refresh Test", session_metadata=initial,
    )
    _navigate_to_session(page, base_url, sid)
    page.locator('[data-testid="routing-audit-summary"]').click()
    rows = page.locator('[data-testid="routing-audit-row"]')
    expect(rows).to_have_count(1, timeout=4000)
    # Append a second routing entry directly in the DB.
    _append_routing_entry(
        data_dir, session_id=sid,
        entry={"ts": "2026-05-31T00:00:02", "agent": "refresh-agent", "rule_index": 0,
               "scope": "channel", "match": None, "reason": "second",
               "disposition": "stepped"},
    )
    # Click Refresh and assert the second row appears.
    page.locator('[data-testid="routing-audit-refresh"]').click()
    expect(rows).to_have_count(2, timeout=4000)


# ── Test 6: collapsed by default ────────────────────────────────────────


@pytest.mark.browser
def test_routing_audit_panel_is_collapsed_by_default(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    provider_id = seed_mock_provider(base_url)
    seed_mock_agent(base_url, provider_id, name="collapsed-agent")
    sid = "sess-collapsed-1"
    routing = [
        {"ts": "2026-05-31T00:00:01", "agent": "collapsed-agent", "rule_index": 0,
         "scope": "channel", "match": None, "reason": "test",
         "disposition": "stepped"},
    ]
    _seed_session_with_metadata(
        data_dir, session_id=sid, agent_name="collapsed-agent",
        title="Collapsed Test", session_metadata={"routing": routing},
    )
    _navigate_to_session(page, base_url, sid)
    # Outer <details> exists but is NOT open on first render.
    details = page.locator('[data-testid="routing-audit-details"]')
    expect(details).to_be_visible(timeout=4000)
    # Per AC-12: collapsed default. Evaluating the `open` attribute on the
    # <details> element gives the boolean state.
    is_open = details.evaluate("el => el.hasAttribute('open')")
    assert is_open is False, "panel must be collapsed by default per AC-12"
