# Leg: browser-lanes-guards-docs

**Status**: completed
**Flight**: [Studio Re-skin](../flight.md)

## Objective

Introduce per-area browser test lanes (chat/studio/system/shared) in the test runner, fix the dirty-back confirm-dialog flake, and clear the markdown.js node-types doc drift. Test-infra + docs only — no product changes.

## Scope (flight DDs authoritative)

- **Per-area browser lanes** (F4 debrief decision, ripe at 13:08 wall): add a lane arg to `scripts/run-tests.sh` (path-glob) OR pytest markers — hand-rolled, NO new deps. Lanes: `chat` (`test_flow_chat_*`, `test_flow_markdown_chat`, `test_flow_new_chat`), `studio` (`test_flow_studio_*`, `test_studio_*`, `test_connector_*`), `system` (`test_flow_admin_*`, `test_flow_provider_*`), `shared` (`test_smoke`, `test_theme_cross_tab_sync`, `test_markdown`, `test_app_fixture`, `test_flow_keyboard`, `test_flow_hash_routing`, `test_oauth_modal_flow`). Document usage in CLAUDE.md (each lane runnable independently so no verification leg pays the full ~13min tax; the full suite still runs as today). Verify each lane selects the right files and together they cover the whole browser suite (no test dropped).
- **Dirty-back confirm-dialog flake fix** (F3 rec 6 → F5; F4 flagged): in `test_flow_dirty_confirm.py` (or wherever the dirty-back confirm test lives — grep for it), bump the 4s expect-timeout / add a wait-for-render sync point on the confirm dialog so it doesn't flake under full-suite load. Root-cause-aligned (the modal renders slower under load), not a blind timeout bump if a sync point is cleaner.
- **markdown.js node-types comment** (F4 debrief): the header comment says "18 node-type string constants" but `NodeType` freezes 19 — fix "18"→"19". One-line docs fix, no code change; keep test_markdown.py green (it's a comment).

## Acceptance Criteria

- [x] `run-tests.sh` (or markers) supports the 4 lanes; each lane runs independently green via PYTHON=.venv/bin/python; the union covers the full browser suite (no file orphaned) — verify with a count/diff
- [x] CLAUDE.md documents the lanes (how to run each; the rationale)
- [x] dirty-back confirm test no longer flakes (run it a few times under load / with the fix; document the fix)
- [x] markdown.js comment reads "19 node-type" ; test_markdown.py green
- [x] make test-unit green; ruff clean; no product-source changes (test-infra + docs + one comment only)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
