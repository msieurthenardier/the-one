"""End-to-end flow tests: Studio's Knowledge inventory (Mission 24 Flight 6
Leg 1 — replaces the F5 stub with the real global knowledge-base
inventory).

Covers: AC-1 (real inventory, stub gone), AC-2 (create + DD-16's advisory
name-length hint + client-side empty-name refusal), AC-3 (delete behind
the project's confirm affordance), AC-4 (detail-view hash routing +
full-reload + back), AC-5/AC-9/AC-13 (status summary, folders, indexer
state, reindex-triggers-immediate-refresh, the 5-second poll observing a
real indexing pass with no operator action), AC-6 (folder-registration
refusal renders the route's own message — the data-directory overlap
case), AC-7 (item status/error + DD-9's standalone badge), AC-8 (chunks
open in seq order; /source is never fetched during item-list render),
AC-10/AC-12 (search renders hits with score, and a degrade line named
alongside the response's own indexer word), AC-13b (the poll stops on
both a same-area section change and a cross-area switch).

Fixture-file discipline (leg Edge Cases / mission recon): only
`.txt`/`.md` files become items via the real walker — anything else is
silently skipped by design and never counted. Real-indexing assertions
(status transitions, search) use generous timeouts because the local
embedding backend loads its model lazily on first use in the freshly
spawned subprocess.

Setup that isn't a supported operator affordance (a synthetic `failed`
item, a synthetic standalone file item) is seeded via a direct,
credentialed HTTP POST against the running app (mirrors `seeders.py`'s
API-based-seeding idiom) rather than invented UI controls — the UI itself
is only ever driven for what it actually exposes.

Mission 24 Flight 6 Leg 5 (HAT-found affordance gaps) additions — NOTE
this leg has its OWN AC-1..AC-13 numbering, distinct from Leg 1's above;
every Leg-5 reference below is spelled out as "Leg 5 AC-N" to avoid
confusion with the Leg-1 AC-N citations above. Covers: Leg 5 AC-1/AC-2/
AC-3 (a folder's two-step remove control — App.confirmDelete, a static
consequence caption rendered before any click, an immediate
`refreshStatusNow()` + items refresh on the success path rather than
waiting on the poll — and the knowledge base itself survives; restyled
onto the summary-line trash icon by Leg 6's AMENDED L6-D3, which keeps
the two-step), Leg 5 AC-4
(the create form's description field is persisted), Leg 5 AC-8 (the
detail view's edit form joins dirty-confirm), Leg 5 AC-9/AC-10 (the
per-row overflow menu carrying "View chunks"/"View source" is keyboard-
operable — opens from the keyboard, Escape closes and returns focus to
the trigger, arrows move between items).
"""

from __future__ import annotations

import re as _re
import time
from pathlib import Path

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _wait_studio_ready(page: Page) -> None:
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)


def _goto_knowledge_grid(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/knowledge")
    _wait_studio_ready(page)
    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible(timeout=5000)


def _create_knowledge_base(page: Page, name: str) -> None:
    page.locator('[data-testid="new-knowledge-base-btn"]').click()
    page.locator('[data-testid="kb-create-name-input"]').fill(name)
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    expect(page.locator('[data-testid="knowledge-base-card"]', has_text=name)).to_be_visible(
        timeout=5000
    )


@pytest.mark.browser
def test_knowledge_grid_renders_real_inventory_no_stub(app_clean: str, page: Page) -> None:
    """AC-1: a page header, an always-visible create CTA, and an empty
    state — the F5 stub sentence and testid are gone."""
    _goto_knowledge_grid(app_clean, page)

    expect(page.locator(".area-studio .page-title")).to_have_text("Knowledge")
    expect(page.locator('[data-testid="new-knowledge-base-btn"]')).to_be_visible()
    expect(page.get_by_text("in a future mission")).to_have_count(0)
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_have_count(0)


@pytest.mark.browser
def test_create_knowledge_base_hint_and_empty_name_refused(app_clean: str, page: Page) -> None:
    """AC-2: the name field's advisory hint appears past 43 code points
    (creation still succeeds); an empty name is refused client-side and
    no request is sent."""
    _goto_knowledge_grid(app_clean, page)
    page.locator('[data-testid="new-knowledge-base-btn"]').click()

    name_input = page.locator('[data-testid="kb-create-name-input"]')
    hint = page.locator('[data-testid="kb-create-name-hint"]')
    expect(hint).to_be_hidden()

    create_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if request.method == "POST" and request.url.endswith("/api/knowledge-bases"):
            create_requests.append(request.url)

    page.on("request", _on_request)

    # Empty name: refused client-side, no request sent.
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    expect(page.locator('[data-testid="kb-create-error"]')).to_have_text("Name is required.")
    assert create_requests == []

    # Over-length name: advisory hint shows, creation still succeeds.
    long_name = "n" * 50
    name_input.fill(long_name)
    expect(hint).to_be_visible()
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    expect(page.locator('[data-testid="knowledge-base-card"]', has_text=long_name)).to_be_visible(
        timeout=5000
    )
    assert len(create_requests) == 1


@pytest.mark.browser
def test_delete_knowledge_base_via_confirm_affordance(app_clean: str, page: Page) -> None:
    """AC-3: delete behind the project's existing two-step confirm
    control; the knowledge base disappears from the list."""
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Delete Me")

    page.locator('[data-testid="knowledge-base-card"]', has_text="Delete Me").click()
    delete_btn = page.locator('[data-testid="delete-knowledge-base-btn"]')
    expect(delete_btn).to_be_visible(timeout=5000)

    delete_btn.click()  # arm
    # Wait for the armed state before the second click — App.confirmDelete
    # is a two-step in-place control (confirm.js), and the existing
    # MCP-source precedent (test_flow_studio_mcp_editor.py) asserts this
    # transition explicitly before committing, rather than firing both
    # clicks back-to-back.
    expect(delete_btn).to_have_class(_re.compile(r"\bconfirm-delete\b"))
    delete_btn.click()  # confirm

    # The detail view's root ALSO carries the shared inventory testid
    # (L1-D5) — that locator alone can't prove we left the detail view, it
    # is already satisfied before the delete round-trip resolves. Wait for
    # the detail-only Back button to disappear instead, which only happens
    # once onDeleteSuccess has actually run.
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_have_count(0, timeout=5000)
    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible()
    assert page.evaluate("location.hash") == "#studio/knowledge"
    expect(page.locator('[data-testid="knowledge-base-card"]', has_text="Delete Me")).to_have_count(
        0
    )


@pytest.mark.browser
def test_detail_view_routing_full_reload_and_back(app_clean: str, page: Page) -> None:
    """AC-4: selecting opens `#studio/knowledge/{kb_id}`; a full page
    load of that URL lands directly on it; Back returns to the grid."""
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Routing KB")

    page.locator('[data-testid="knowledge-base-card"]', has_text="Routing KB").click()
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible(timeout=5000)
    detail_hash = page.evaluate("location.hash")
    assert detail_hash.startswith("#studio/knowledge/")

    page.reload()
    _wait_studio_ready(page)
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == detail_hash

    page.locator('[data-testid="back-knowledge-btn"]').click()
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_have_count(0)
    assert page.evaluate("location.hash") == "#studio/knowledge"


@pytest.mark.browser
def test_folder_registration_data_dir_refusal_renders_message(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """AC-6/DD-10: the deterministic refusal case — registering the
    instance's own scratch data directory — renders the route's `detail`
    message (naming the application data directory), never a bare status
    code. Never `$HOME`: the guard only refuses overlap with
    `settings.data_dir` (CLAUDE.md's stated reason)."""
    base_url, data_dir = app_with_data_dir
    _goto_knowledge_grid(base_url, page)
    _create_knowledge_base(page, "Refusal KB")
    page.locator('[data-testid="knowledge-base-card"]', has_text="Refusal KB").click()
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(data_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()

    error_el = page.locator('[data-testid="kb-folder-add-error"]')
    expect(error_el).to_contain_text("application data directory", timeout=5000)
    # No folder panel was added for the refused registration.
    expect(page.locator('[data-testid="kb-folder-panel"]')).to_have_count(0)


@pytest.mark.browser
def test_item_row_failed_status_error_and_standalone_badge(
    app_with_data_dir: tuple[str, Path], page: Page, tmp_path: Path
) -> None:
    """AC-7: the item list renders each item's status; a `failed` item's
    error text is visible; a standalone file whose path lies inside a
    registered folder is badged, and a failed item OUTSIDE any registered
    folder is not. Seeded synthetically (direct API POSTs) since neither
    state is reachable through a UI control — a failed status comes from
    the real indexer, and a standalone item is, by definition, one the
    operator did not register through the folder form."""
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)

    fixture_folder = tmp_path / "kb-fixture-folder"
    fixture_folder.mkdir()
    outside_folder = tmp_path / "elsewhere"
    outside_folder.mkdir()

    kb_id = httpx.post(
        f"{base_url}/api/knowledge-bases", headers=headers, json={"name": "Items KB"}
    ).json()["id"]
    folder_item = httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={"type": "folder", "path_or_url": str(fixture_folder)},
    ).json()
    assert folder_item["type"] == "folder"

    # Failed item OUTSIDE the registered folder — status/error visible,
    # no standalone badge (not inside any registered folder's path).
    httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={
            "id": "failed-item-1",
            "type": "file",
            "path_or_url": str(outside_folder / "bad.txt"),
            "status": "failed",
            "error": "simulated extraction failure",
        },
    )
    # Standalone: path lies inside the registered folder, parent_id unset.
    httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={
            "id": "standalone-item-1",
            "type": "file",
            "path_or_url": str(fixture_folder / "standalone.txt"),
            "status": "indexed",
        },
    )

    page.goto(f"{base_url}#studio/knowledge/{kb_id}")
    _wait_studio_ready(page)
    # Leg 6 (restyle): neither item has a real `parent_id`, so both land in
    # the trailing "Other items" panel (L6-D2 chosen option (a)) rather
    # than a flat items list — a native `<details>`, collapsed by default,
    # so it must be expanded before asserting visibility on its rows.
    other_items_panel = page.locator('[data-testid="kb-other-items-panel"]')
    expect(other_items_panel).to_be_visible(timeout=5000)
    other_items_panel.locator("summary").click()

    failed_row = page.locator('[data-testid="kb-item-row"][data-item-id="failed-item-1"]')
    expect(failed_row).to_be_visible()
    expect(failed_row.locator('[data-testid="kb-item-status"]')).to_have_text("failed")
    expect(failed_row.locator('[data-testid="kb-item-error"]')).to_have_text(
        "simulated extraction failure"
    )
    expect(failed_row.locator('[data-testid="kb-item-standalone-badge"]')).to_have_count(0)

    standalone_row = page.locator('[data-testid="kb-item-row"][data-item-id="standalone-item-1"]')
    expect(standalone_row.locator('[data-testid="kb-item-standalone-badge"]')).to_be_visible()


@pytest.mark.browser
def test_chunks_open_in_seq_order_and_source_not_prefetched(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """AC-8: chunks open on demand and render in seq order; /source is
    never requested while the item list renders — only on the explicit
    "View source" click (DD-8)."""
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)

    kb_id = httpx.post(
        f"{base_url}/api/knowledge-bases", headers=headers, json={"name": "Chunks KB"}
    ).json()["id"]
    item_id = httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={
            "type": "file",
            "path_or_url": "/tmp/does-not-need-to-exist.txt",
            "status": "indexed",
        },
    ).json()["id"]

    source_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if "/source" in request.url:
            source_requests.append(request.url)

    page.on("request", _on_request)

    page.goto(f"{base_url}#studio/knowledge/{kb_id}")
    _wait_studio_ready(page)
    # Leg 6 (restyle): no `parent_id` set, so the item lands in the
    # trailing "Other items" panel — expand it before interacting with the
    # row inside.
    other_items_panel = page.locator('[data-testid="kb-other-items-panel"]')
    expect(other_items_panel).to_be_visible(timeout=5000)
    other_items_panel.locator("summary").click()
    row = page.locator(f'[data-testid="kb-item-row"][data-item-id="{item_id}"]')
    expect(row).to_be_visible(timeout=5000)
    # Item-list render alone must not have fetched /source.
    assert source_requests == []

    # AC-9/L5-D4: "View chunks" is reachable from the per-row overflow
    # control, not a bare button on the row.
    row.locator('[data-testid="kb-item-menu-btn"]').click()
    menu = row.locator('[data-testid="kb-item-menu"]')
    expect(menu).to_be_visible()
    menu.locator('[data-testid="kb-item-chunks-btn"]').click()
    panel = page.locator('[data-testid="kb-chunks-panel"]')
    expect(panel).to_be_visible()
    expect(panel.locator('[data-testid="kb-chunk-row"]')).to_have_count(0)
    expect(panel.locator(".empty-state")).to_be_visible(timeout=5000)
    # Opening chunks must not have fetched /source either.
    assert source_requests == []


@pytest.mark.browser
def test_detail_view_indexing_poll_reindex_and_search(
    app_with_data_dir: tuple[str, Path], page: Page, tmp_path
) -> None:
    """AC-5, AC-9, AC-10, AC-12, AC-13: the substantive real-pipeline
    walk — register a folder with one real file, watch the status poll
    reflect indexing with no operator action, trigger both reindex
    scopes, then search and see fused hits with a score."""
    base_url, _data_dir = app_with_data_dir

    fixture_dir = tmp_path / "kb-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("The quick brown fox jumps over the lazy dog.")

    _goto_knowledge_grid(base_url, page)
    _create_knowledge_base(page, "Pipeline KB")
    page.locator('[data-testid="knowledge-base-card"]', has_text="Pipeline KB").click()
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(fixture_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()

    folder_row = page.locator('[data-testid="kb-folder-panel"]')
    expect(folder_row).to_be_visible(timeout=5000)

    # AC-5: the folder panel's summary line carries path/status/watch,
    # rendered verbatim — the summary is always rendered regardless of the
    # panel's expand/collapse state, so no click is needed to assert on it.
    # a fresh registration reaches "starting" or "watching" (never "off"
    # or "unavailable", which need no manager / a real notifier failure
    # respectively — see this file's module docstring).
    expect(folder_row.locator(".kb-folder-path")).to_have_text(str(fixture_dir))
    expect(folder_row.locator(".kb-folder-watch")).to_have_text(
        _re.compile(r"watch: (starting|watching)"), timeout=10000
    )

    # AC-13: the detail view's status refreshes via the poll alone — no
    # further operator action — as the real indexer processes note.txt.
    # No button is clicked between registration and this assertion.
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 1", timeout=30000
    )

    # AC-9: reindex (both scopes) triggers one immediate status refresh
    # rather than waiting a full poll interval.
    page.locator('[data-testid="kb-reindex-changed-btn"]').click()
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 1", timeout=10000
    )
    page.locator('[data-testid="kb-reindex-all-btn"]').click()
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 1", timeout=15000
    )

    # AC-10/AC-12: search renders hits with score; a real query with no
    # matches is not degraded.
    page.locator('[data-testid="kb-search-input"]').fill("fox")
    page.locator('[data-testid="kb-search-btn"]').click()
    hit = page.locator('[data-testid="kb-search-hit"]')
    expect(hit).to_be_visible(timeout=10000)
    expect(hit.locator(".kb-search-hit-score")).to_contain_text("score:")
    expect(page.locator('[data-testid="kb-search-degraded"]')).to_be_hidden()


@pytest.mark.browser
def test_poll_stops_on_same_area_and_cross_area_navigation(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """AC-13b: with a detail view open and polling, navigating to another
    Studio section AND to another area entirely (Chat) each stop the
    poll — the two disjoint clear sites (L1-D2). Re-entering
    #studio/knowledge mounts the grid, not the previously-selected detail
    view."""
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)
    kb_id = httpx.post(
        f"{base_url}/api/knowledge-bases", headers=headers, json={"name": "Poll KB"}
    ).json()["id"]

    status_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if f"/api/knowledge-bases/{kb_id}/status" in request.url:
            status_requests.append(request.url)

    page.on("request", _on_request)

    page.goto(f"{base_url}#studio/knowledge/{kb_id}")
    _wait_studio_ready(page)
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible(timeout=5000)
    # The initial mount fetch.
    assert len(status_requests) >= 1

    # Same-area section change (Knowledge detail -> MCP Servers).
    page.locator('.section-nav-item[data-section="mcp-sources"]').click()
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    count_after_section_switch = len(status_requests)
    time.sleep(6)  # longer than one 5s poll interval
    assert len(status_requests) == count_after_section_switch, (
        "a same-area section change must stop the Knowledge poll"
    )

    # Re-enter Knowledge: mounts the grid, not the previously-selected detail.
    page.locator('.section-nav-item[data-section="knowledge"]').click()
    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible(timeout=5000)
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_have_count(0)

    # Re-open the detail view (in-app click, not a fresh page.goto — a
    # second goto to the exact hash already visited earlier in this test
    # would collide with app.js's own `currentSub` cache and no-op, a
    # separate, pre-existing router property this leg does not touch),
    # then cross-area switch (Knowledge -> Chat).
    page.locator('[data-testid="knowledge-base-card"]', has_text="Poll KB").click()
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible(timeout=5000)
    count_before_area_switch = len(status_requests)

    page.locator('[data-testid="nav-chat-btn"]').click()
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=8000)
    time.sleep(6)  # longer than one 5s poll interval
    assert len(status_requests) == count_before_area_switch, (
        "a cross-area switch must stop the Knowledge poll"
    )


@pytest.mark.browser
def test_items_list_catches_up_when_backend_changes_while_mounted(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """kb-studio-round-trip remediation FIX 1 (run 2026-09-18-13-14-52,
    FINDING 1): with the detail view mounted and never touched, a new
    item appearing in the knowledge base must repaint the items list
    within one 5-second poll interval — no reload, no navigation, no
    button click. Before the fix, the status poll refreshed only the
    count chips (`knowledgeDetailHandle.updateStatus`); the items list,
    painted once at mount, never caught up — chips read `indexed: 2`
    while the list beneath them still showed one row, indefinitely.

    The new item is seeded via a direct API POST (this file's existing
    synthetic-item idiom — see `test_item_row_failed_status_error_...`)
    rather than a real disk write picked up by the watcher, so this
    isolates the poll's items-invalidation logic from indexing/watcher
    timing, which the rest of this file already covers.

    Also proves the poll does NOT re-fetch `/items` on every tick when
    nothing has changed (L1-D2's actual intent — the whole reason the
    fix compares a change signal instead of polling items directly), and
    that a chunks panel opened before the change survives the rebuild.
    """
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)

    kb_id = httpx.post(
        f"{base_url}/api/knowledge-bases", headers=headers, json={"name": "Freshness KB"}
    ).json()["id"]
    first_path = "/tmp/kb-freshness-fixture-1.txt"
    httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={
            "id": "freshness-item-1",
            "type": "file",
            "path_or_url": first_path,
            "status": "indexed",
        },
    )

    items_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        url = request.url
        if f"/api/knowledge-bases/{kb_id}/items" in url and "/items/" not in url:
            items_requests.append(url)

    page.on("request", _on_request)

    page.goto(f"{base_url}#studio/knowledge/{kb_id}")
    _wait_studio_ready(page)
    # Leg 6 (restyle): no `parent_id` set, so the item lands in the
    # trailing "Other items" panel — expand it so its row is interactable.
    other_items_panel = page.locator('[data-testid="kb-other-items-panel"]')
    expect(other_items_panel).to_be_visible(timeout=5000)
    other_items_panel.locator("summary").click()
    rows = page.locator('[data-testid="kb-item-row"]')
    expect(rows).to_have_count(1, timeout=5000)
    assert len(items_requests) == 1, "the detail-view mount fetch"

    # Open the chunks panel on the existing row (via the overflow menu,
    # L5-D4) — it must survive the upcoming list rebuild (the panel lives
    # outside the folders section's item containers).
    rows.first.locator('[data-testid="kb-item-menu-btn"]').click()
    rows.first.locator('[data-testid="kb-item-menu"]').locator(
        '[data-testid="kb-item-chunks-btn"]'
    ).click()
    panel = page.locator('[data-testid="kb-chunks-panel"]')
    expect(panel).to_be_visible()
    expect(panel.locator('[data-testid="kb-panel-title"]')).to_have_text(first_path)

    # Nothing has changed yet — past one poll interval, /items must NOT
    # have been re-fetched (no needless polling of the items route).
    time.sleep(6)
    assert len(items_requests) == 1, (
        "the poll must not re-fetch /items when the counts have not changed"
    )

    # Change backend state while the view stays mounted — no reload, no
    # navigation, no click in the app at all.
    httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={
            "id": "freshness-item-2",
            "type": "file",
            "path_or_url": "/tmp/kb-freshness-fixture-2.txt",
            "status": "indexed",
        },
    )

    # Within one poll interval, the items list catches up on its own.
    expect(rows).to_have_count(2, timeout=8000)
    expect(
        page.locator('[data-testid="kb-item-row"][data-item-id="freshness-item-2"]')
    ).to_be_visible()
    assert len(items_requests) == 2, "exactly one invalidation-triggered re-fetch"

    # The chunks panel opened before the rebuild is still visible and
    # still correctly attributed to the item it was opened for.
    expect(panel).to_be_visible()
    expect(panel.locator('[data-testid="kb-panel-title"]')).to_have_text(first_path)


# ── Mission 24 Flight 6 Leg 5 (HAT-found affordance gaps) ───────────────────
# Leg 5's OWN AC-1..AC-13 numbering — see the module docstring's note.


@pytest.mark.browser
def test_folder_remove_two_step_confirm_cascade_hint_and_immediate_refresh(
    app_with_data_dir: tuple[str, Path], page: Page, tmp_path: Path
) -> None:
    """Leg 5 AC-1/AC-2/AC-3, restyled by Leg 6's AMENDED L6-D3: the
    section-level cascade hint under Folders states the consequence
    BEFORE any click (persistent, not per-row); the folder panel's trash
    icon keeps Leg 5's TWO-STEP confirm through App.confirmDelete — the
    first click only arms (the summary takes `.confirm-delete`, the path
    span swaps to "Confirm delete?", and NO DELETE request is issued),
    the second commits — and both the folder/status display AND the item
    list then reflect it via an IMMEDIATE refreshStatusNow() + items
    refresh, well inside one 5-second poll interval, not by waiting on
    it; the knowledge base itself survives with no other folders
    affected.

    The "no DELETE yet" half is asserted through a `page.on('request')`
    counter rather than a DOM-stability sleep: the request either fired
    or it did not, with no timing heuristic to go stale."""
    base_url, _data_dir = app_with_data_dir

    fixture_dir = tmp_path / "kb-remove-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("removable folder fixture content.")

    _goto_knowledge_grid(base_url, page)
    _create_knowledge_base(page, "Remove Folder KB")
    page.locator('[data-testid="knowledge-base-card"]', has_text="Remove Folder KB").click()
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    # AC-2: the cascade hint is present BEFORE any folder even exists —
    # section-level, not per-row (L6-D3).
    hint = page.locator('[data-testid="kb-folders-cascade-hint"]')
    expect(hint).to_be_visible()
    expect(hint).to_have_text(
        "Removing a folder removes every file indexed from it, "
        "along with their chunks and search entries."
    )

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(fixture_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()
    folder_panel = page.locator('[data-testid="kb-folder-panel"]')
    expect(folder_panel).to_be_visible(timeout=5000)

    # The real indexing pipeline picks up note.txt — wait for it to land
    # in the item list before exercising removal, so the removal's
    # cascade has something real to remove. `to_have_count` matches DOM
    # presence regardless of the (collapsed-by-default) panel's expand
    # state, so no click is needed here.
    expect(page.locator('[data-testid="kb-item-row"]')).to_have_count(1, timeout=30000)

    delete_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if request.method == "DELETE":
            delete_requests.append(request.url)

    page.on("request", _on_request)

    # L6-D3 (amended): FIRST click only arms the confirm.
    remove_btn = folder_panel.locator('[data-testid="kb-folder-delete-btn"]')
    expect(remove_btn).to_be_visible()
    remove_btn.click()

    summary = folder_panel.locator(".kb-folder-summary")
    expect(summary).to_have_class(_re.compile(r"\bconfirm-delete\b"))
    expect(folder_panel.locator(".kb-folder-path")).to_have_text("Confirm delete?")
    # The arming click issued no DELETE: the folder and its indexed file
    # are both still there, and no DELETE left the browser at all.
    assert delete_requests == [], f"arming click issued a DELETE: {delete_requests}"
    expect(page.locator('[data-testid="kb-folder-panel"]')).to_have_count(1)
    expect(page.locator('[data-testid="kb-item-row"]')).to_have_count(1)

    # SECOND click within App.confirmDelete's 3s revert window commits.
    # expect_response makes a silent re-arm (revert-window expiry under
    # load) fail loudly as a missing-DELETE timeout rather than as a
    # confusing downstream visibility failure — same idiom as
    # test_flow_agent_crud.py's Danger Zone delete.
    with page.expect_response(
        lambda r: "/items/" in r.url and r.request.method == "DELETE"
    ) as delete_resp:
        remove_btn.click()
    assert delete_resp.value.status in (200, 204), (
        f"DELETE failed: {delete_resp.value.status} {delete_resp.value.text()}"
    )

    # AC-1: an IMMEDIATE refresh — asserted with a timeout well under one
    # 5-second poll interval, so a pass here cannot be explained by the
    # poll instead of the success-path refresh this criterion requires.
    expect(page.locator('[data-testid="kb-folder-panel"]')).to_have_count(0, timeout=2000)
    expect(page.locator('[data-testid="kb-item-row"]')).to_have_count(0, timeout=2000)

    # AC-3: the knowledge base itself is NOT deleted — still on its detail
    # view, still addressable, with the folder gone and nothing else.
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible()
    expect(page.locator(".editor-title")).to_have_text("Remove Folder KB")
    page.locator('[data-testid="back-knowledge-btn"]').click()
    expect(
        page.locator('[data-testid="knowledge-base-card"]', has_text="Remove Folder KB")
    ).to_be_visible()


@pytest.mark.browser
def test_folder_panel_open_state_survives_poll_ticks(
    app_with_data_dir: tuple[str, Path], page: Page, tmp_path: Path
) -> None:
    """L6-D2/L6-D3 coupling: an operator-expanded folder panel stays
    expanded across the 5-second status poll. This is the whole point of
    `renderFolders`' keyed reconciliation (`appendChild` MOVES an
    already-attached `<details>` rather than re-creating it), and it is
    what makes an armed delete confirm survivable — a tick that recreated
    the panel would silently destroy the armed row inside
    App.confirmDelete's 3-second revert window.

    Two `/status` RESPONSES are awaited rather than a wall-clock sleep:
    `renderFolders` runs in the response handler, so by the time the
    second response lands the first tick has certainly been rendered.
    A probe attribute stamped on the DOM node proves the node itself
    survived — not merely that some panel with the same testid is
    present."""
    base_url, _data_dir = app_with_data_dir

    fixture_dir = tmp_path / "kb-open-state-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("open-state fixture content.")

    _goto_knowledge_grid(base_url, page)
    _create_knowledge_base(page, "Open State KB")
    page.locator('[data-testid="knowledge-base-card"]', has_text="Open State KB").click()
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(fixture_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()

    folder_panel = page.locator('[data-testid="kb-folder-panel"]')
    expect(folder_panel).to_be_visible(timeout=5000)

    # Expand via the path span — inside the <summary>, and well away from
    # the trash icon (whose clicks must NOT toggle the panel).
    folder_panel.locator(".kb-folder-path").click()
    assert folder_panel.get_attribute("open") is not None, "panel did not expand"

    # Stamp the live node so a recreated panel is distinguishable from a
    # moved one.
    folder_panel.evaluate("el => { el.dataset.pollProbe = 'original-node'; }")

    for _ in range(2):
        with page.expect_response(
            lambda r: (
                "/api/knowledge-bases/" in r.url
                and r.url.endswith("/status")
                and r.request.method == "GET"
            ),
            timeout=15000,
        ):
            pass

    assert folder_panel.get_attribute("open") is not None, (
        "a poll tick collapsed an operator-expanded folder panel"
    )
    assert folder_panel.get_attribute("data-poll-probe") == "original-node", (
        "a poll tick RE-CREATED the folder panel instead of moving it"
    )


@pytest.mark.browser
def test_create_form_description_persisted(app_clean: str, page: Page) -> None:
    """Leg 5 AC-4: the create form accepts a description, and it survives
    the round trip (`GET /api/knowledge-bases/{id}` returns it) — rendered
    on the grid tile without a page reload."""
    _goto_knowledge_grid(app_clean, page)
    page.locator('[data-testid="new-knowledge-base-btn"]').click()
    page.locator('[data-testid="kb-create-name-input"]').fill("Described KB")
    page.locator('[data-testid="kb-create-description-input"]').fill("A description for testing.")
    page.locator('[data-testid="kb-create-submit-btn"]').click()

    card = page.locator('[data-testid="knowledge-base-card"]', has_text="Described KB")
    expect(card).to_be_visible(timeout=5000)
    expect(card.locator(".entity-tile-meta")).to_have_text("A description for testing.")

    kb_id = card.get_attribute("data-id")
    assert kb_id is not None
    body = httpx.get(
        f"{app_clean}/api/knowledge-bases/{kb_id}", headers=auth_headers_for(app_clean), timeout=5.0
    ).json()
    assert body["description"] == "A description for testing."


@pytest.mark.browser
def test_always_live_fields_join_dirty_confirm(app_clean: str, page: Page) -> None:
    """Leg 5 AC-8, restyled by Leg 6 (L6-D1): the always-live Name/
    Description fields' unsaved changes gate cross-section navigation
    through App.confirmDialog (L5-D3, a reversal of Leg 3's stated
    non-goal for the single-field create/register forms) — clean
    navigation (fields untouched since mount) does not prompt, since there
    is no edit-form toggle left to open."""
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Dirty Confirm KB")
    page.locator('[data-testid="knowledge-base-card"]', has_text="Dirty Confirm KB").click()
    expect(page.locator('[data-testid="kb-name-input"]')).to_be_visible(timeout=5000)

    # Clean: navigating away without touching the always-live fields must
    # NOT gate navigation.
    mcp_nav = page.locator('.section-nav-item[data-section="mcp-sources"]')
    mcp_nav.click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)

    # Dirty: back to the same knowledge base, edit the name, then try to
    # leave — the dialog gates it. In-app click, not a fresh page.goto — a
    # second goto to the exact hash already visited earlier in this test
    # would collide with app.js's own `currentSub` cache and no-op (the
    # same pre-existing router property test_poll_stops_on_same_area_and_
    # cross_area_navigation works around above).
    page.locator('.section-nav-item[data-section="knowledge"]').click()
    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible(timeout=5000)
    page.locator('[data-testid="knowledge-base-card"]', has_text="Dirty Confirm KB").click()
    page.locator('[data-testid="kb-name-input"]').fill("Dirty Confirm KB Edited")

    mcp_nav.click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=8000)

    # Cancel: stays put, no navigation.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_value("Dirty Confirm KB Edited")

    # Confirm: discards and navigates.
    mcp_nav.click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)


@pytest.mark.browser
def test_item_overflow_menu_keyboard_operable(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Leg 5 AC-9/AC-10, L5-D4: the per-row overflow menu opens from the
    keyboard, Escape closes it and returns focus to the trigger, and arrow
    keys move between "View chunks"/"View source". A click outside also
    closes it."""
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)

    kb_id = httpx.post(
        f"{base_url}/api/knowledge-bases", headers=headers, json={"name": "Menu KB"}
    ).json()["id"]
    httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/items",
        headers=headers,
        json={
            "id": "menu-item-1",
            "type": "file",
            "path_or_url": "/tmp/kb-menu-fixture.txt",
            "status": "indexed",
        },
    )

    page.goto(f"{base_url}#studio/knowledge/{kb_id}")
    _wait_studio_ready(page)
    # Leg 6 (restyle): no `parent_id` set, so the item lands in the
    # trailing "Other items" panel — expand it before interacting.
    other_items_panel = page.locator('[data-testid="kb-other-items-panel"]')
    expect(other_items_panel).to_be_visible(timeout=5000)
    other_items_panel.locator("summary").click()
    row = page.locator('[data-testid="kb-item-row"][data-item-id="menu-item-1"]')
    expect(row).to_be_visible(timeout=5000)

    trigger = row.locator('[data-testid="kb-item-menu-btn"]')
    menu = row.locator('[data-testid="kb-item-menu"]')
    expect(trigger).to_have_attribute("aria-haspopup", "menu")
    expect(trigger).to_have_attribute("aria-expanded", "false")
    expect(menu).to_be_hidden()

    # Opens from the keyboard: focus the trigger, then ArrowDown opens the
    # menu and moves focus to the first item.
    trigger.focus()
    trigger.press("ArrowDown")
    expect(menu).to_be_visible()
    expect(trigger).to_have_attribute("aria-expanded", "true")
    expect(page.locator('[data-testid="kb-item-chunks-btn"]:focus')).to_have_count(1)

    # Arrow keys move between items.
    page.keyboard.press("ArrowDown")
    expect(page.locator('[data-testid="kb-item-source-btn"]:focus')).to_have_count(1)
    page.keyboard.press("ArrowUp")
    expect(page.locator('[data-testid="kb-item-chunks-btn"]:focus')).to_have_count(1)

    # Escape closes it and returns focus to the trigger.
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()
    expect(trigger).to_have_attribute("aria-expanded", "false")
    expect(trigger).to_be_focused()

    # A click outside closes it too (no focus-return assertion here — the
    # outside click itself moves focus, by design).
    trigger.click()
    expect(menu).to_be_visible()
    page.locator('[data-testid="kb-status-summary"]').click()
    expect(menu).to_be_hidden()
