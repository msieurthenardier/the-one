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

Mission 24 Flight 6 Leg 6 HAT polish pass (2026-09-19) — look-and-feel
only, no behaviour change. Assertions were ADDED to existing tests rather
than given a test of their own (each needs a fixture the host test already
builds): the section order is now Folders -> Status -> Search -> Danger
Zone with the two re-index controls inside Status (they act on the whole
knowledge base, never one folder — the misreading the move fixes),
carrying their new "Re-index changed files"/"Re-index all files" labels
and a scope hint; both destructive controls render a real trash SVG (the
Danger Zone one alongside its surviving label, the folder one in place of
the old text glyph); and the folder one's arming click still does not
toggle its `<details>`, which only became breakable once the target was an
`<svg>` rather than the `<button>`.

Mission 25 Flight 3 Leg 4a: the tile grid and its inline create form are
retired. Knowledge bases are rows of the Library list (``knowledge-base-card``
on an ``<a href>``), the create form lives at ``#library/knowledge/~new`` (Add
-> "Knowledge base") and creating OPENS the new knowledge base (squawk 0101),
so ``_create_knowledge_base`` leaves the test on the new item's detail view.
The section root shows the Knowledge empty state beside the list.

Mission 24 Flight 6 Leg 6 HAT pass 2 (2026-09-19) — two browser-layer gaps
closed by strengthening the pipeline test rather than adding a parallel
suite (the unit layer already covers walking, chunking and seq ordering;
what was missing was specifically the RENDERING of either). The single
real-pipeline fixture now carries two SUBDIRECTORIES, so the flattening
L6-D2 chose on purpose (a subdirectory is not a registered item, so it
gets no panel of its own) is asserted instead of merely assumed, together
with the relative-path display that puts the subdirectory back on screen;
and one fixture file is sized deliberately against the chunker's 1000/150
defaults so the chunk viewer renders MORE THAN ONE row and its "in seq
order" claim is tested against a list longer than one.
"""

from __future__ import annotations

import os
import re as _re
import time
from pathlib import Path

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import seed_mcp_source
from playwright.sync_api import Page, expect

# Sized DELIBERATELY against the chunker's shipped defaults (1000 chars,
# 150 overlap — pinned by `tests/test_chunking.py::test_defaults_are_1000_and_150`)
# rather than guessed: 24 paragraphs of ~82 characters is 1966 characters,
# which `chunk_text` splits into exactly three chunks. Small enough that the
# extra embedding work is not measurable next to the model load this test
# already waits on; long enough that "renders in seq order" is finally an
# assertion about a list of more than one element.
_MULTI_CHUNK_PARAGRAPHS = 24
_MULTI_CHUNK_EXPECTED_CHUNKS = 3
_MULTI_CHUNK_BODY = "\n\n".join(
    f"Paragraph {i:02d}. The incident response runbook records what happened and who acted."
    for i in range(_MULTI_CHUNK_PARAGRAPHS)
)


def _wait_studio_ready(page: Page) -> None:
    expect(page.locator('[data-testid="library-list"] .ui-list-pane-caption').first).to_be_visible(
        timeout=8000
    )


def _goto_knowledge_grid(app_clean: str, page: Page) -> None:
    """The Knowledge section root: the Library list and the empty detail state.

    State-driven readiness (fetch activity quiet) rather than a fixed wait:
    under load the boot outlasted one once in the leg-1 lane run (same
    slow-boot class as the four fixed flakes)."""
    _nav.goto_settled(page, app_clean, "library/knowledge")
    _wait_studio_ready(page)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=5000)


def _wait_kb_open(page: Page, name: str) -> str:
    """Wait for a knowledge base's detail view at its item route; return its id."""
    page.wait_for_function(
        "p => location.hash.startsWith(p) && !location.hash.endsWith('/~new')",
        arg=_nav.href("library/knowledge") + "/",
        timeout=8000,
    )
    expect(page.locator(".studio-section-content .editor-title")).to_have_text(name, timeout=8000)
    return _nav.current_route(page).rsplit("/", 1)[1]


def _create_knowledge_base(page: Page, name: str) -> str:
    """Create through the UI (Add -> "Knowledge base"): the new knowledge base's
    detail view opens (squawk 0101). Returns its id."""
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill(name)
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    kb_id = _wait_kb_open(page, name)
    expect(_lists.list_row(page, "library/knowledge", name)).to_be_visible(timeout=5000)
    return kb_id


@pytest.mark.browser
def test_knowledge_grid_renders_real_inventory_no_stub(app_clean: str, page: Page) -> None:
    """AC-1 (M25 F3 L4a shape): the Knowledge bases group with its empty line,
    the always-visible Add, and the section root's empty state whose action
    opens the create form — the F5 stub sentence and testid are gone."""
    _goto_knowledge_grid(app_clean, page)

    library = page.locator('[data-testid="library-list"]')
    expect(library.locator(".ui-list-pane-group-empty").first).to_have_text(
        "No knowledge bases yet."
    )
    expect(page.locator('[data-testid="library-add-btn"]')).to_be_visible()
    expect(_lists.library_empty_state(page, "knowledge")).to_contain_text(
        "Folders of your documents that agents can search."
    )
    page.locator('[data-testid="library-empty-knowledge-add"]').click()
    _nav.expect_route(page, "library/knowledge/~new")
    expect(page.locator('[data-testid="kb-create-name-input"]')).to_be_focused()
    expect(page.get_by_text("in a future mission")).to_have_count(0)
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_have_count(0)


@pytest.mark.browser
def test_create_knowledge_base_hint_and_empty_name_refused(app_clean: str, page: Page) -> None:
    """AC-2: the name field's advisory hint appears past 43 code points
    (creation still succeeds); an empty name is refused client-side and
    no request is sent."""
    _goto_knowledge_grid(app_clean, page)
    _lists.library_add(page, "knowledge")

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
    _wait_kb_open(page, long_name)
    expect(_lists.list_row(page, "library/knowledge", long_name)).to_be_visible(timeout=5000)
    assert len(create_requests) == 1


@pytest.mark.browser
def test_delete_knowledge_base_via_confirm_affordance(app_clean: str, page: Page) -> None:
    """AC-3: delete behind the project's existing two-step confirm
    control; the knowledge base disappears from the list."""
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Delete Me")
    delete_btn = page.locator('[data-testid="delete-knowledge-base-btn"]')
    expect(delete_btn).to_be_visible(timeout=5000)

    # HAT polish pass (L06 follow-up): the Danger Zone delete carries a
    # real trash icon ALONGSIDE its label, not instead of it — the same
    # shape mcp-server-editor.js's own Danger Zone delete has. The icon
    # sits outside the `[data-confirm-title]` span, so the label alone is
    # what App.confirmDelete swaps on arm.
    expect(delete_btn.locator("svg")).to_have_count(1)
    expect(delete_btn).to_have_text("Delete Knowledge Base")

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
    # the detail-only Save button to disappear instead, which only happens
    # once onDeleteSuccess has actually run (M25 F3 L4b retired Back, the
    # marker this used to wait on).
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_have_count(0, timeout=5000)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible()
    _nav.expect_route(page, "library/knowledge")
    expect(page.locator('[data-testid="knowledge-base-card"]', has_text="Delete Me")).to_have_count(
        0
    )


@pytest.mark.browser
def test_detail_view_routing_full_reload_and_back(app_clean: str, page: Page) -> None:
    """AC-4: selecting opens `#library/knowledge/{kb_id}`; a full page
    load of that URL lands directly on it; the breadcrumb's "Knowledge bases"
    link returns to the section root (M25 F3 L4b retired Back)."""
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Routing KB")
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=5000)
    detail_route = _nav.current_route(page)
    assert detail_route.startswith("library/knowledge/")

    page.reload()
    _wait_studio_ready(page)
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=5000)
    _nav.expect_route(page, detail_route)
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_have_count(0)
    _nav.expect_route(page, "library/knowledge")


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

    _nav.goto_settled(page, base_url, f"library/knowledge/{_nav.seg(kb_id)}")
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
    # HAT pass 2: the "Other items" panel keeps ABSOLUTE paths. A file row
    # inside a folder panel renders relative to that folder's root, but
    # these items are parentless by definition — there is no root to
    # relativize against, and this one's path merely LIES INSIDE a
    # registered folder, which is the false parentage DD-9's badge exists
    # to refuse. Shortening it against that folder would assert exactly the
    # relationship the badge is denying.
    expect(standalone_row.locator(".kb-item-path")).to_have_text(
        str(fixture_folder / "standalone.txt")
    )


@pytest.mark.browser
def test_chunks_open_in_seq_order_and_source_not_prefetched(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """AC-8: chunks open on demand and render in seq order; /source is
    never requested while the item list renders — only on the explicit
    "View source" click (DD-8).

    This test's item is seeded with a path that need not exist, so it has
    no chunks at all — what it pins is the on-demand/no-prefetch contract
    and the empty state. The multi-chunk *rendering* (three rows, `#0`
    `#1` `#2`) is asserted in
    `test_detail_view_indexing_poll_reindex_and_search`, which is the test
    that runs a real indexing pass and can therefore have real chunks.
    """
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

    _nav.goto_settled(page, base_url, f"library/knowledge/{_nav.seg(kb_id)}")
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

    # Two SUBDIRECTORIES on purpose (HAT pass 2): every other fixture in
    # this file is one flat directory, so nothing here had ever rendered a
    # folder with a tree inside it. `notes/incident.md` is the deliberately
    # multi-chunk file.
    fixture_dir = tmp_path / "kb-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("The quick brown fox jumps over the lazy dog.")
    (fixture_dir / "handbook").mkdir()
    (fixture_dir / "handbook" / "onboarding.md").write_text(
        "Onboarding handbook. Read this before your first on-call shift."
    )
    (fixture_dir / "notes").mkdir()
    (fixture_dir / "notes" / "incident.md").write_text(_MULTI_CHUNK_BODY)

    _goto_knowledge_grid(base_url, page)
    kb_id = _create_knowledge_base(page, "Pipeline KB")
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
        "indexed: 3", timeout=30000
    )

    # ── HAT pass 2, part 1: a folder with subdirectories renders FLAT,
    # with relative paths ─────────────────────────────────────────────────
    #
    # L6-D2 deliberately refuses to nest a subdirectory as its own panel: a
    # subdirectory is not a registered item, so a panel would assert a
    # parentage the data does not have. The cost is that a tree collapses
    # into one list, and the relative path is what restores the missing
    # information. Both halves are asserted here because both are choices a
    # future change could silently reverse.
    folder_row.locator("summary").click()
    file_rows = folder_row.locator('[data-testid="kb-item-row"]')
    expect(file_rows).to_have_count(3, timeout=15000)
    # No nested panel: the two subdirectories produce no `<details>` of
    # their own anywhere inside this folder's panel.
    expect(folder_row.locator('[data-testid="kb-folder-panel"]')).to_have_count(0)
    expect(page.locator('[data-testid="kb-folder-panel"]')).to_have_count(1)

    # Each file reads relative to the folder root it was discovered under —
    # `notes/incident.md`, not the absolute path with the folder's own path
    # repeated in front of it. `os.path.join` rather than a literal "/": the
    # renderer takes its separator from the folder path's own form, which is
    # OS-native.
    rel_note = "note.txt"
    rel_onboarding = os.path.join("handbook", "onboarding.md")
    rel_incident = os.path.join("notes", "incident.md")
    # Squawk 0087 / Flight 7 Leg 2, AC-14a: order is now a CONTRACT
    # (`KBItemRepository.list_children`'s `ORDER BY created_at,
    # path_or_url` tiebreak), so this compares an exact SEQUENCE rather
    # than a sorted set — a set comparison was the squawk 0087 workaround
    # for when order was unguaranteed SQLite tie behaviour, not a database
    # contract. The expected order is ascending ABSOLUTE path (the
    # tiebreak column), which is also the order `walk_folder` discovers
    # files in: "handbook/onboarding.md" < "note.txt" < "notes/incident.md"
    # (byte-for-byte, "note.txt"'s "." sorts before "notes"'s "s").
    assert folder_row.locator(".kb-item-path").all_text_contents() == [
        rel_onboarding,
        rel_note,
        rel_incident,
    ]
    # ...and the absolute path is never lost, only moved one hover away.
    expect(folder_row.locator(".kb-item-path", has_text=rel_incident)).to_have_attribute(
        "title", str(fixture_dir / "notes" / "incident.md")
    )

    # ── HAT pass 2, part 2: the chunk viewer renders MORE THAN ONE row ────
    #
    # Every fixture file in this suite used to be one short line, so the
    # chunk panel had only ever been asserted against a list of length one
    # (or zero). `notes/incident.md` is sized against the chunker's 1000/150
    # defaults to produce three, which is what makes "in seq order" mean
    # something.
    incident_row = file_rows.filter(has=page.locator(".kb-item-path", has_text=rel_incident))
    incident_row.locator('[data-testid="kb-item-menu-btn"]').click()
    incident_row.locator('[data-testid="kb-item-chunks-btn"]').click()
    chunks_panel = page.locator('[data-testid="kb-chunks-panel"]')
    expect(chunks_panel).to_be_visible()
    expect(chunks_panel.locator('[data-testid="kb-chunk-row"]')).to_have_count(
        _MULTI_CHUNK_EXPECTED_CHUNKS, timeout=10000
    )
    assert chunks_panel.locator(".kb-chunk-seq").all_text_contents() == [
        f"#{i}" for i in range(_MULTI_CHUNK_EXPECTED_CHUNKS)
    ]
    # The panel titles itself with the item's FULL path (FIX 4), so an
    # operator reading chunks still knows which file they belong to even
    # though the row that opened them showed a relative path.
    expect(chunks_panel.locator('[data-testid="kb-panel-title"]')).to_have_text(
        str(fixture_dir / "notes" / "incident.md")
    )

    # HAT polish pass (L06 follow-up): section order is Folders -> Status
    # -> Search -> Danger Zone. The header's fields sit in an
    # `.editor-section` carrying no `.section-title`, so it does not
    # appear here. This assertion is DELIBERATELY order-encoding: the
    # operator asked for Status (and its re-index pair) to sit BELOW
    # Folders, which is a change from the leg's original AC-6 order.
    # Direct-child `>` on purpose: `_panelTitle` gives an OPEN chunks or
    # source panel a `.section-title` of its own, nested one level deeper
    # inside the Folders section, which a descendant selector would splice
    # into this sequence.
    root = page.locator('[data-testid="studio-knowledge-inventory"]')
    assert root.locator(".editor-section > .section-title").all_text_contents() == [
        "Folders",
        "Status",
        "Search",
        "Danger Zone",
    ]

    # ...and both re-index controls now live INSIDE the Status section,
    # not among the per-folder panels, because each acts on the whole
    # knowledge base (POST /reindex requeues every folder) — the scoping
    # the labels and the hint now make legible.
    status_section = root.locator(".editor-section").filter(
        has=page.locator(".section-title", has_text="Status")
    )
    expect(status_section.locator('[data-testid="kb-reindex-changed-btn"]')).to_have_text(
        "Re-index changed files"
    )
    expect(status_section.locator('[data-testid="kb-reindex-all-btn"]')).to_have_text(
        "Re-index all files"
    )
    scope_hint = status_section.locator('[data-testid="kb-reindex-scope-hint"]')
    expect(scope_hint).to_be_visible()
    expect(scope_hint).to_contain_text("every folder registered in this knowledge base")
    expect(scope_hint).to_contain_text("there is no per-folder re-index")

    # AC-9: reindex (both scopes) triggers one immediate status refresh
    # rather than waiting a full poll interval.
    page.locator('[data-testid="kb-reindex-changed-btn"]').click()
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 3", timeout=10000
    )
    # Squawk 0115: "indexed: 3" is ALREADY showing, so waiting on it again
    # proves nothing and the search below could run mid-reindex. Wait on the
    # real signal instead: `content_freshness` (MAX file `indexed_at`, a
    # microsecond ISO stamp rewritten when `scope=all` re-indexes each file)
    # moves only when a file actually re-indexes. It moves on the FIRST file,
    # so also wait for nothing pending or indexing. Bounded; fails loudly.
    kb_status_url = f"{base_url}/api/knowledge-bases/{kb_id}/status"
    kb_headers = auth_headers_for(base_url)

    def _kb_status() -> dict:
        return httpx.get(kb_status_url, headers=kb_headers, timeout=5.0).json()

    def _kb_idle(body: dict) -> bool:
        items = body["items"]
        return items.get("pending", 0) == 0 and items.get("indexing", 0) == 0

    # Quiesce the "changed" re-index above, then record the freshness.
    settle_deadline = time.monotonic() + 15
    while not _kb_idle(_kb_status()):
        assert time.monotonic() < settle_deadline, "KB never went idle before Re-index all"
        time.sleep(0.1)
    freshness_before_all = _kb_status()["content_freshness"]
    assert freshness_before_all

    page.locator('[data-testid="kb-reindex-all-btn"]').click()

    reindex_deadline = time.monotonic() + 30
    while True:
        body = _kb_status()
        if body["content_freshness"] != freshness_before_all and _kb_idle(body):
            break
        assert time.monotonic() < reindex_deadline, (
            "Re-index all files did not finish (content_freshness unchanged or items "
            f"still pending/indexing): {body}"
        )
        time.sleep(0.1)
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 3", timeout=15000
    )

    # AC-10/AC-12: search renders hits with score; a real query with no
    # matches is not degraded.
    page.locator('[data-testid="kb-search-input"]').fill("fox")
    page.locator('[data-testid="kb-search-btn"]').click()
    # HAT pass 2: the fixture now holds three files (one of them chunked
    # three ways), so a semantic query returns SEVERAL hits where it used
    # to return exactly one — `.first` replaces a now strict-mode-violating
    # bare locator. Nothing is weakened: the score assertion still runs,
    # and the file that actually carries the keyword is asserted to be
    # among the hits, which the old single-hit form could only imply.
    hits = page.locator('[data-testid="kb-search-hit"]')
    expect(hits.first).to_be_visible(timeout=10000)
    expect(hits.first.locator(".kb-search-hit-score")).to_contain_text("score:")
    expect(hits.filter(has_text=str(fixture_dir / "note.txt"))).to_have_count(1)
    expect(page.locator('[data-testid="kb-search-degraded"]')).to_be_hidden()


@pytest.mark.browser
def test_poll_stops_on_same_area_and_cross_area_navigation(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """AC-13b: with a detail view open and polling, navigating to another
    Library section (an MCP server row) AND to another area entirely
    (Chat) each stop the poll — the two disjoint clear sites (L1-D2).
    Re-entering #library/knowledge mounts the section root, not the
    previously-selected detail view."""
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)
    kb_id = httpx.post(
        f"{base_url}/api/knowledge-bases", headers=headers, json={"name": "Poll KB"}
    ).json()["id"]
    seed_mcp_source(base_url, "poll-mcp")

    status_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if f"/api/knowledge-bases/{kb_id}/status" in request.url:
            status_requests.append(request.url)

    page.on("request", _on_request)

    _nav.goto_settled(page, base_url, f"library/knowledge/{_nav.seg(kb_id)}")
    _wait_studio_ready(page)
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=5000)
    # The initial mount fetch.
    assert len(status_requests) >= 1

    # Same-area section change (Knowledge detail -> an MCP server row).
    _lists.open_item(page, "library/mcp", "poll-mcp")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=5000)
    count_after_section_switch = len(status_requests)
    time.sleep(6)  # longer than one 5s poll interval
    assert len(status_requests) == count_after_section_switch, (
        "a same-area section change must stop the Knowledge poll"
    )

    # Re-enter Knowledge (the rail's Library link goes to its root): mounts the
    # section root, not the previously-selected detail.
    _nav.open_destination(page, "library")
    _nav.expect_route(page, "library/knowledge")
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=5000)
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_have_count(0)

    # Re-open the detail view (in-app click, not a fresh page.goto — a
    # second goto to the exact hash already visited earlier in this test
    # would collide with app.js's own `currentSub` cache and no-op, a
    # separate, pre-existing router property this leg does not touch),
    # then cross-area switch (Knowledge -> Chat).
    page.locator('[data-testid="knowledge-base-card"]', has_text="Poll KB").click()
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=5000)
    count_before_area_switch = len(status_requests)

    _nav.open_destination(page, "chats")
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

    _nav.goto_settled(page, base_url, f"library/knowledge/{_nav.seg(kb_id)}")
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
    # HAT polish pass (L06 follow-up): the summary-line trash is a real
    # SVG icon now, not a text glyph rendering at the summary's 12px —
    # which is what "too small" meant. Its size comes from
    # `.kv-remove-row-btn svg`'s existing 16px, not a rule of its own.
    expect(remove_btn.locator("svg")).to_have_count(1)
    assert folder_panel.evaluate("el => el.open") is False
    remove_btn.click()

    summary = folder_panel.locator(".kb-folder-summary")
    expect(summary).to_have_class(_re.compile(r"\bconfirm-delete\b"))
    # ...and arming did NOT toggle the panel. The summary's default
    # handler skips clicks whose TARGET is a form control, and Blink tests
    # the target node itself rather than its ancestors — so the new `<svg>`
    # child, a hit-test target of its own, would reach the summary and
    # expand the panel on every delete press without
    # `.kb-folder-delete-btn svg { pointer-events: none }`. With the text
    # glyph the target was the button and this could not happen, so the
    # invariant only became assertable-and-breakable with the icon.
    assert folder_panel.evaluate("el => el.open") is False
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
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible()
    expect(page.locator(".editor-title")).to_have_text("Remove Folder KB")
    _lists.close_item(page)
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
    the round trip (`GET /api/knowledge-bases/{id}` returns it) — shown in
    the new knowledge base's detail view, which creating opens (M25 F3 L4a)."""
    _goto_knowledge_grid(app_clean, page)
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill("Described KB")
    page.locator('[data-testid="kb-create-description-input"]').fill("A description for testing.")
    page.locator('[data-testid="kb-create-submit-btn"]').click()

    kb_id = _wait_kb_open(page, "Described KB")
    expect(page.locator('[data-testid="kb-description-input"]')).to_have_value(
        "A description for testing."
    )
    expect(_lists.list_row(page, "library/knowledge", "Described KB")).to_be_visible()
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
    seed_mcp_source(app_clean, "dirty-mcp")
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Dirty Confirm KB")
    expect(page.locator('[data-testid="kb-name-input"]')).to_be_visible(timeout=5000)

    # Clean: navigating away (an MCP server row) without touching the
    # always-live fields must NOT gate navigation.
    mcp_row = _lists.list_row(page, "library/mcp", "dirty-mcp")
    mcp_row.click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=5000)

    # Dirty: back to the same knowledge base (its row), edit the name, then
    # try to leave — the dialog gates it.
    _lists.open_item(page, "library/knowledge", "Dirty Confirm KB")
    page.locator('[data-testid="kb-name-input"]').fill("Dirty Confirm KB Edited")

    mcp_row.click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=8000)

    # Cancel: stays put, no navigation.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_value("Dirty Confirm KB Edited")

    # Confirm: discards and navigates.
    mcp_row.click()
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=5000)


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

    _nav.goto_settled(page, base_url, f"library/knowledge/{_nav.seg(kb_id)}")
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


@pytest.mark.browser
def test_content_only_edit_updates_item_freshness_with_no_reload(
    app_clean: str, page: Page, tmp_path: Path
) -> None:
    """Mission 24 Flight 7 Leg 2, DD-6, AC-6: the full round trip a
    content-only edit has to survive — real folder, real file, real
    indexer, real 5-second poll. Before this leg,
    `knowledgeItemsSignature` was counts-only, so this exact edit would
    have produced no `/items` re-fetch at all (the render half alone would
    have shipped an invisible staleness bug, DD-6's own reason both halves
    land together).

    Per leg Edge Cases, the edit changes the file's SIZE (not just its
    bytes) — `plan_reconcile` keys change-detection on `size_bytes`/
    `mtime`, not `content_hash`, so a same-size edit is not detected as
    changed at all and must not be used here.
    """
    fixture_dir = tmp_path / "freshness-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("short")

    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "Freshness KB")
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(fixture_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()

    folder_row = page.locator('[data-testid="kb-folder-panel"]')
    expect(folder_row).to_be_visible(timeout=5000)
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 1", timeout=30000
    )
    folder_row.locator("summary").click()

    item_row = page.locator('[data-testid="kb-item-row"]')
    expect(item_row).to_have_count(1)
    fresh_el = item_row.locator('[data-testid="kb-item-indexed-at"]')
    expect(fresh_el).to_be_visible()
    initial_text = fresh_el.text_content()
    assert initial_text and initial_text.startswith("Indexed: ")

    # A content-only edit, on disk, with no operator action in the app at
    # all — no button click, no navigation, no reload. Longer content
    # changes the size, which is what makes the walk's reconcile pass
    # actually notice (see the module docstring above).
    (fixture_dir / "note.txt").write_text(
        "This is a substantially longer replacement body, so the file's "
        "size changes along with its content — the case plan_reconcile "
        "actually detects."
    )

    # AC-6: the row's freshness signal changes on its own, within a few
    # poll intervals — proving the whole chain: the watcher/walk re-
    # indexes -> `indexed_at` advances -> `content_freshness` moves ->
    # `knowledgeItemsSignature` differs -> `/items` re-fetches -> the row
    # re-renders with a new `kb-item-indexed-at` text. Generous timeout:
    # the local embedding backend loads its model lazily on first use.
    expect(fresh_el).not_to_have_text(initial_text, timeout=45000)
    updated_text = fresh_el.text_content()
    assert updated_text and updated_text.startswith("Indexed: ") and updated_text != initial_text


@pytest.mark.browser
def test_armed_folder_confirm_survives_items_signature_tick(
    app_with_data_dir: tuple[str, Path], page: Page, tmp_path: Path
) -> None:
    """Squawk 0088's third invariant, mechanically pinned (Mission 24
    Flight 7 leg confirm-lapse, AC-10/AC-10a). L6-D3 named three
    behaviours the folder-delete confirm depends on; only two had a test
    before this one:

    1. `renderFolders` reconciles by folder id and moves existing nodes
       rather than recreating them (tested).
    2. `updateFolderMeta` never rewrites the path span (tested).
    3. `renderAllItems` must not rebuild the `<summary>` either — it
       reaches a panel only through `renderFolderFiles`
       (`knowledge-section.js:1111`), which writes `panel.filesEl` (the
       panel BODY), never the summary. **This test.**

    AC-10a: a naive version of this test — arm, then wait on the real
    walk -> hash -> chunk -> embed -> 5-second-poll pipeline for a tick —
    would see the confirm auto-revert (3s) before a naturally-timed tick
    ever arrives, failing or passing for reasons that have nothing to do
    with the invariant (the very mechanism this leg is redesigning). Two
    techniques avoid that race:

    1. The signature-changing edit is driven and CONFIRMED directly —
       `httpx` against `POST .../reindex?scope=changed`, then a tight
       polling loop against `GET .../status` — never by sleeping on the
       real pipeline's own latency. By the time anything is armed, the
       change already sits in the database.
    2. The arm click is PHASE-LOCKED to the app's own 5-second status
       poll (observed live via `page.expect_response`), so the very next
       natural tick lands well inside the 3-second `revertMs` window
       instead of racing an arbitrary point in that 5-second cycle.
    """
    base_url, _data_dir = app_with_data_dir
    headers = auth_headers_for(base_url)

    fixture_dir = tmp_path / "lapse-invariant-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("short")

    _goto_knowledge_grid(base_url, page)
    kb_id = _create_knowledge_base(page, "Lapse Invariant KB")
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(fixture_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()

    folder_panel = page.locator('[data-testid="kb-folder-panel"]')
    expect(folder_panel).to_be_visible(timeout=5000)
    # Warm-up: the real indexing pipeline (including the embedding
    # backend's lazy model load) pays its one-time cost here, off the
    # timing-critical section below.
    expect(page.locator('[data-testid="kb-status-count"][data-status="indexed"]')).to_have_text(
        "indexed: 1", timeout=30000
    )

    status_url = f"{base_url}/api/knowledge-bases/{kb_id}/status"
    items_url = f"{base_url}/api/knowledge-bases/{kb_id}/items"
    initial_freshness = httpx.get(status_url, headers=headers, timeout=5.0).json()[
        "content_freshness"
    ]

    # Stamp the live summary node so a REBUILT node is distinguishable
    # from the SAME node surviving in place — the identity technique
    # `test_folder_panel_open_state_survives_poll_ticks` already uses.
    summary = folder_panel.locator(".kb-folder-summary")
    summary.evaluate("el => { el.dataset.lapseInvariantProbe = 'original-node'; }")

    items_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if request.url == items_url and request.method == "GET":
            items_requests.append(request.url)

    page.on("request", _on_request)

    # Phase-lock step 1: observe a natural poll tick land, establishing a
    # timing anchor (the poll has been running in the background since
    # mount, throughout the indexing warm-up above).
    with page.expect_response(
        lambda r: r.url == status_url and r.request.method == "GET", timeout=15000
    ):
        pass
    anchor = time.monotonic()

    # Drive the signature-changing edit directly — a content-only change
    # (longer body, so plan_reconcile's size/mtime-keyed change detection
    # actually fires; a same-size edit would not, per the freshness test
    # above) — and confirm it landed via our OWN tight polling loop
    # against the real API, never by sleeping on the pipeline or the
    # app's poll.
    (fixture_dir / "note.txt").write_text(
        "A substantially longer replacement body so the file's size "
        "changes along with its content, which is what plan_reconcile's "
        "change detection actually keys on."
    )
    reindex_resp = httpx.post(
        f"{base_url}/api/knowledge-bases/{kb_id}/reindex",
        headers=headers,
        params={"scope": "changed"},
        timeout=5.0,
    )
    assert reindex_resp.status_code == 202

    new_freshness = None
    deadline = anchor + 4.3  # stay well clear of the next ~5s tick
    while time.monotonic() < deadline:
        body = httpx.get(status_url, headers=headers, timeout=5.0).json()
        if body["content_freshness"] and body["content_freshness"] != initial_freshness:
            new_freshness = body["content_freshness"]
            break
        time.sleep(0.1)
    assert new_freshness is not None, (
        "content_freshness did not move within the phase-lock budget — the "
        "reindex/detection technique itself needs a longer budget, not the "
        "confirm/tick invariant below"
    )

    # Phase-lock step 2: arm just before the next natural tick is due
    # (~5s after the anchor), so that tick's re-render lands comfortably
    # inside the 3-second revertMs window instead of racing it.
    remaining = (anchor + 4.6) - time.monotonic()
    if remaining > 0:
        page.wait_for_timeout(remaining * 1000)

    remove_btn = folder_panel.locator('[data-testid="kb-folder-delete-btn"]')
    remove_btn.click()
    expect(summary).to_have_class(_re.compile(r"\bconfirm-delete\b"))
    expect(folder_panel.locator(".kb-folder-path")).to_have_text("Confirm delete?")

    # The next natural tick — carrying the already-landed signature
    # change — fires here, well inside revertMs per the phase lock.
    with page.expect_response(
        lambda r: r.url == status_url and r.request.method == "GET", timeout=3000
    ):
        pass
    # Give the chained /items re-fetch + renderAllItems pass a brief beat
    # to complete (a second network round trip after /status).
    page.wait_for_timeout(300)

    assert items_requests, (
        "no /items re-fetch followed the status tick — this exercised "
        "updateStatus only, not the renderAllItems path AC-10 pins"
    )

    # The invariant: still armed, and it is the SAME node — not a fresh
    # one recreated with the armed markers coincidentally reapplied.
    expect(summary).to_have_class(_re.compile(r"\bconfirm-delete\b"))
    expect(folder_panel.locator(".kb-folder-path")).to_have_text("Confirm delete?")
    assert summary.get_attribute("data-lapse-invariant-probe") == "original-node", (
        "an items-signature tick RECREATED the armed folder summary instead of leaving it in place"
    )


@pytest.mark.browser
def test_folder_delete_confirm_lapse_is_visually_distinct(
    app_with_data_dir: tuple[str, Path], page: Page, tmp_path: Path
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: a lapsed folder-delete
    confirm is distinguishable on screen from one that was never armed.
    `App.confirmDelete`'s timer-expiry-only `lapse()` marks
    `.confirm-lapsed` (confirm.js) before reverting; this asserts the
    call site actually receives it, waiting past the real 3s `revertMs`
    rather than a shortened test-only value (leg AC-6/guidance: the
    default is not touched)."""
    base_url, _data_dir = app_with_data_dir

    fixture_dir = tmp_path / "folder-lapse-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "note.txt").write_text("lapse fixture content.")

    _goto_knowledge_grid(base_url, page)
    _create_knowledge_base(page, "Folder Lapse KB")
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    page.locator('[data-testid="kb-folder-path-input"]').fill(str(fixture_dir))
    page.locator('[data-testid="kb-add-folder-btn"]').click()
    folder_panel = page.locator('[data-testid="kb-folder-panel"]')
    expect(folder_panel).to_be_visible(timeout=5000)

    summary = folder_panel.locator(".kb-folder-summary")
    remove_btn = folder_panel.locator('[data-testid="kb-folder-delete-btn"]')

    expect(summary).not_to_have_class(_re.compile(r"\bconfirm-lapsed\b"))
    remove_btn.click()
    expect(summary).to_have_class(_re.compile(r"\bconfirm-delete\b"))

    # Past the real 3-second revertMs, the control has reverted (AC-7:
    # the path text is restored, not left as the placeholder) AND carries
    # the lapse cue distinguishing it from never-armed.
    expect(summary).not_to_have_class(_re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(summary).to_have_class(_re.compile(r"\bconfirm-lapsed\b"))
    expect(folder_panel.locator(".kb-folder-path")).to_have_text(str(fixture_dir))

    # AC-7 (re-arm): the next click clears the lapse cue (per the
    # helper's "cleared on the next interaction" contract) and arms fresh
    # with the ORIGINAL title, never the stale "Confirm delete?" text a
    # capture-discipline regression would produce.
    remove_btn.click()
    expect(summary).not_to_have_class(_re.compile(r"\bconfirm-lapsed\b"))
    expect(summary).to_have_class(_re.compile(r"\bconfirm-delete\b"))
    expect(folder_panel.locator(".kb-folder-path")).to_have_text("Confirm delete?")


@pytest.mark.browser
def test_kb_delete_confirm_lapse_is_visually_distinct(app_clean: str, page: Page) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the Danger Zone
    knowledge-base delete confirm (a plain button, not a `<summary>`)
    gets the same lapse cue through the shared helper — no call site is
    special-cased (AC-5)."""
    _goto_knowledge_grid(app_clean, page)
    _create_knowledge_base(page, "KB Delete Lapse KB")
    expect(page.locator('[data-testid="kb-folder-path-input"]')).to_be_visible(timeout=5000)

    delete_btn = page.locator('[data-testid="delete-knowledge-base-btn"]')
    expect(delete_btn).not_to_have_class(_re.compile(r"\bconfirm-lapsed\b"))
    delete_btn.click()
    expect(delete_btn).to_have_class(_re.compile(r"\bconfirm-delete\b"))

    expect(delete_btn).not_to_have_class(_re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(delete_btn).to_have_class(_re.compile(r"\bconfirm-lapsed\b"))
    expect(delete_btn).to_have_text("Delete Knowledge Base")
