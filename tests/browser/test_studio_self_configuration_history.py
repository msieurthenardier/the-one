"""Browser tests for the Self-configuration tab revision-HISTORY view +
restore control (M21 F02 L03, AC8).

Mirrors ``test_studio_self_configuration_queue.py``'s direct-sqlite seeding:
seed an agent via httpx, INSERT ``agent_revisions`` rows via sync sqlite3,
drive the tab, and assert the history renders and a Restore updates the
field + appends a history entry.

Covers:
  1. The full revision history renders (all statuses), distinct from the
     pending queue; distinct value-nodes each get a Restore control.
  2. Clicking Restore applies the value (store updated) and, after the
     re-render, a new restore history entry appears.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_agent(base_url: str, name: str, description: str = "seed desc") -> dict:
    r = httpx.post(
        f"{base_url}/api/agents",
        json={"name": name, "description": description},
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code in (200, 201), f"seed agent failed: {r.status_code} {r.text}"
    return r.json()


def _seed_applied_revision(
    data_dir: Path,
    *,
    agent_name: str,
    field: str,
    proposed_value: str,
    base_value: str,
    created_at: str | None = None,
) -> str:
    """INSERT an applied agent_revisions row via sync sqlite3. Returns id.

    ``created_at`` defaults to ``datetime('now')`` (existing callers); pass
    an explicit ISO string to control ordering across multiple seeded rows
    (list_for_agent sorts ``created_at DESC, id DESC`` — see
    test_restore_controls_independent_per_field_with_shared_value, which
    needs a deterministic oldest-first walk order).
    """
    db_path = data_dir / "the-one.db"
    revision_id = uuid.uuid4().hex
    conn = sqlite3.connect(str(db_path))
    try:
        if created_at is None:
            conn.execute(
                "INSERT INTO agent_revisions ("
                " id, agent_name, field, proposed_value, base_value,"
                " status, source, restored_from, created_at, resolved_at"
                ") VALUES (?, ?, ?, ?, ?, 'applied', 'self', NULL,"
                " datetime('now'), datetime('now'))",
                (revision_id, agent_name, field, proposed_value, base_value),
            )
        else:
            conn.execute(
                "INSERT INTO agent_revisions ("
                " id, agent_name, field, proposed_value, base_value,"
                " status, source, restored_from, created_at, resolved_at"
                ") VALUES (?, ?, ?, ?, ?, 'applied', 'self', NULL, ?, ?)",
                (
                    revision_id,
                    agent_name,
                    field,
                    proposed_value,
                    base_value,
                    created_at,
                    created_at,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return revision_id


def _navigate_to_self_configuration_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}/self-configuration")
    expect(page.locator('[data-testid="tab-self-configuration"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_history_renders_all_statuses(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base_url, data_dir = app_with_data_dir
    # Current description is D1; there's an applied D0->D1 self-revision.
    _seed_agent(base_url, "history-render-agent", description="D1")
    _seed_applied_revision(
        data_dir,
        agent_name="history-render-agent",
        field="description",
        proposed_value="D1",
        base_value="D0",
    )
    _navigate_to_self_configuration_tab(page, base_url, "history-render-agent")

    # HAT UX pass (M21 F02 L04): the chronological log now lives inside a
    # collapsible `<details>` (item 10) — closed by default, summary shows
    # the count. Entries exist in the DOM (assertable via count) even while
    # collapsed; open it to also assert visibility.
    details = page.locator('[data-testid="revision-history-details"]')
    expect(details).to_be_visible(timeout=8000)
    summary = page.locator('[data-testid="revision-history-summary"]')
    expect(summary).to_have_text("History (1)")
    entries = page.locator('[data-testid="revision-history-entry"]')
    expect(entries).to_have_count(1)
    summary.click()
    expect(page.locator('[data-testid="revision-history"]')).to_be_visible(timeout=8000)
    expect(entries.first).to_be_visible()
    # Two distinct value-nodes (D0 via base, D1 via proposed) → two controls,
    # always visible (never collapsed) — grouped under a visible "Description"
    # subheading (items 2 + 8: the group heading IS the restore rows' visible
    # field label).
    expect(page.locator('[data-testid="revision-restore-btn"]')).to_have_count(2)
    expect(page.locator(".self-configuration-restore-group-label")).to_have_text("Description")

    # Item 3: the restore list and the chronological log each get their own
    # visible subheading instead of sharing one.
    expect(page.locator(".self-configuration-subheading")).to_have_text(
        "Restore to an earlier value"
    )

    # Item 4: the history entry shows a formatted relative-time timestamp
    # ("just now" / "N minutes ago" / …) instead of the raw stored
    # timestamp, with the exact instant preserved as a `title=` tooltip.
    meta_text = page.locator(".history-entry-meta-text").first
    expect(meta_text).to_be_visible()
    raw_text = meta_text.inner_text()
    assert re.search(r"(just now|\d+ (minute|hour|day)s? ago)", raw_text), (
        f"expected a relative-time formatted timestamp, got: {raw_text!r}"
    )
    title_attr = meta_text.get_attribute("title")
    assert title_attr, "expected the exact timestamp preserved as a title= tooltip"
    assert title_attr != raw_text, "title= should carry the raw timestamp, not the formatted text"


@pytest.mark.browser
def test_restore_updates_field_and_appends_entry(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base_url, data_dir = app_with_data_dir
    # Current description is D1 (set on the agent); applied D0->D1 revision.
    _seed_agent(base_url, "history-restore-agent", description="D1")
    _seed_applied_revision(
        data_dir,
        agent_name="history-restore-agent",
        field="description",
        proposed_value="D1",
        base_value="D0",
    )
    _navigate_to_self_configuration_tab(page, base_url, "history-restore-agent")

    expect(page.locator('[data-testid="revision-history-entry"]')).to_have_count(1, timeout=8000)
    # Restore the D0 value-node (the earliest base_value, side=base).
    node = page.locator('[data-testid="revision-restore-node"][data-side="base"]').first
    node.locator('[data-testid="revision-restore-btn"]').click()

    # After the re-render, a new restore entry exists (2 total) and the
    # store now holds D0.
    expect(page.locator('[data-testid="revision-history-entry"]')).to_have_count(2, timeout=8000)
    expect(
        page.locator('[data-testid="revision-history-entry"][data-source="restore"]')
    ).to_have_count(1)
    agent = httpx.get(
        f"{base_url}/api/agents/history-restore-agent",
        timeout=5.0,
        headers=auth_headers_for(base_url),
    ).json()
    assert agent["description"] == "D0"


@pytest.mark.browser
def test_restore_controls_independent_per_field_with_shared_value(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Flight-end code-review fix regression test.

    `description` and `system_prompt` are independent fields (DD1) that
    both default to the same value — empty string `""`. The distinct-
    value-node dedup for Restore controls must be scoped PER FIELD: a
    dedup keyed by the raw value alone would let whichever field's node is
    processed first (oldest-first walk) claim `""`, silently dropping the
    OTHER field's original-restore control (any cross-field value
    collision, not just `""` — this is just the natural DD1 case).

    Seeds one applied revision per field, each with base_value="" as its
    ORIGINAL, with `system_prompt`'s row created strictly after
    `description`'s (so description's "" node is `seen` first under the
    old, buggy raw-value dedup) — and asserts BOTH fields still expose
    their own original-restore node (side=base).
    """
    base_url, data_dir = app_with_data_dir
    _seed_agent(base_url, "dedup-cross-field-agent", description="D1")
    _seed_applied_revision(
        data_dir,
        agent_name="dedup-cross-field-agent",
        field="description",
        proposed_value="D1",
        base_value="",
        created_at="2026-01-01T00:00:00",
    )
    _seed_applied_revision(
        data_dir,
        agent_name="dedup-cross-field-agent",
        field="system_prompt",
        proposed_value="SP1",
        base_value="",
        created_at="2026-01-01T00:00:01",
    )
    _navigate_to_self_configuration_tab(page, base_url, "dedup-cross-field-agent")

    expect(page.locator('[data-testid="revision-history-entry"]')).to_have_count(2, timeout=8000)

    # Each field's ORIGINAL (side=base, value="") must have its own restore
    # node — not silently dropped because the other field already claimed
    # the shared "" value.
    desc_original = page.locator(
        '[data-testid="revision-restore-node"][data-field="description"][data-side="base"]'
    )
    sp_original = page.locator(
        '[data-testid="revision-restore-node"][data-field="system_prompt"][data-side="base"]'
    )
    expect(desc_original).to_have_count(1)
    expect(sp_original).to_have_count(1)

    # Total distinct value-nodes: description {"", "D1"} + system_prompt
    # {"", "SP1"} = 4 — none collapsed across fields.
    expect(page.locator('[data-testid="revision-restore-node"]')).to_have_count(4)
