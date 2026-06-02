# Leg: test-baseline-hygiene

**Status**: landed (autonomous portion complete; FD `/behavior-test` re-run pending)
**Flight**: [Live-Traffic HAT Capability](../flight.md)

## Objective

Restore a clean, re-runnable test baseline before the live-traffic HAT legs: formally retire the already-fixed "2 pre-existing browser failures" fold-in (recon-confirmed `already-satisfied`), and make the `audit-log-inspector-renders-routing-entries` behavior test cleanly re-runnable by adding a dev-mode-gated test-seam endpoint that seeds `session_metadata["routing"]` (replacing the broken `PUT`/manual-`aiosqlite` seed), updating the spec's preconditions, and re-running the test to PASS.

## Context

- **Recon re-scoped this leg (operator-confirmed).** Flight planning assumed two live fold-ins; reconnaissance during L2 design found:
  - **Browser fails — `already-satisfied`.** The two files cited by the F13/F14 debriefs (`tests/browser/test_flow_agent_tabs.py`, `tests/browser/test_flow_studio_navigation.py`) now pass entirely (verified at design time: **22 passed, 1 skipped**). The F14 debrief metrics row already states "Pre-existing browser fails — F14: 0 (L5 resolved both)". The debrief-cited function names had drifted (`test_tablist_renders_with_three_tabs` → `test_tablist_renders_with_five_tabs`; `..._preserves_agent_selection` → `test_studio_section_round_trip_returns_to_agent_listing` at `test_flow_studio_navigation.py:253`). No code fix is needed; this leg only documents the retirement with evidence.
  - **Audit-log-inspector — already passed, but seed path is broken.** The spec passed **7/7** at F13 (run `tests/behavior/audit-log-inspector-renders-routing-entries/runs/2026-05-31-23-56-31.md`); the earlier same-day FAIL was transient cache-stale CSS, not a product bug. The F14 *re-run* was deferred because seeding is awkward: the spec's precondition option-(a) `PUT /api/chat/sessions/{id}` silently DROPS `session_metadata` (confirmed: `ChatSessionRepository.update` at `repositories.py:936` UPDATEs only `title, messages, updated_at` by design, per its docstring), so the F13 run had to seed via manual `aiosqlite UPDATE`. This leg gives the test a one-curl seed so it's a sustainable regression gate.
- **Operational note (carry to Phase 2d + HAT legs):** `make rebuild` (run in L1) wipes the Playwright browser cache + system deps; browser tests then ERROR at launch (`libglib-2.0.so.0` missing). The remedy is the existing `make _ensure-playwright` target (runs `playwright install chromium` + `playwright install-deps chromium`), which `make test-browser` invokes automatically. ALWAYS run browser tests via `make test-browser`, never raw `docker exec the-one pytest -m browser`. (Restored at L2 design time.)
- **Why a dev-mode-gated HTTP endpoint** (not a pytest fixture): the behavior test runs against the LIVE container via Chrome MCP + out-of-band `curl`, not pytest — so the seed must be reachable over HTTP. A dev-mode-gated endpoint matches the existing test-seam precedent (`THE_ONE_REGISTER_STUB_CONNECTOR` + `settings.dev_mode` gate at `app.py:118`; the mock-provider dev-mode gate at `api.py:3360`,`3378`).

## Inputs

- `the_one/db/repositories.py:set_session_metadata_key` (`repositories.py:1067`) — `set_session_metadata_key(session_id, key, value)` OVERWRITE semantic; preserves other top-level keys; raises `KeyError` if the session is missing. This is the correct writer (it round-trips `session_metadata`, unlike `update`).
- `the_one/interfaces/web/api.py` — `router = APIRouter(prefix="/api")` (`api.py:49`); session handlers cluster at `api.py:3160-3232` (`get_chat_session` GET `/chat/sessions/{session_id}` at `3167` exposes `session_metadata`; `purge_chat_messages` POST `/chat/sessions/{session_id}/purge` at `3222` is the sibling session-scoped-POST pattern); dev-mode gate pattern at `api.py:3360`/`3378` (`if … and not settings.dev_mode:`).
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — the spec whose Preconditions (the "Operator seeds via the simplest path available" block) + Step 6 reference the broken PUT option-(a).
- How the repo is obtained inside a handler — the session handlers use the `_chat_repo()` helper (`api.py:93-95`), i.e. `repo = await _chat_repo()` (used at `api.py:3162/3169/3193/3202/3214/3224`). Use that, not an inline `get_connection()`.
- Unit-test home: `tests/test_db_api.py` (mounts `router` with its `/api` prefix via the module's `client` fixture, `test_db_api.py:18-44`). The dev-mode toggle pattern other gated-endpoint tests use is `with patch("the_one.interfaces.web.api.settings") as mock_settings: mock_settings.dev_mode = True/False` (see `tests/test_provider_api.py:1998+`).

## Outputs

- `the_one/interfaces/web/api.py` — NEW dev-mode-gated handler that sets `session_metadata["routing"]` for a session.
- `tests/test_*` — NEW unit tests for the endpoint (dev-mode happy path, 403 when not dev-mode, 404 when session missing, round-trip via the detail endpoint).
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — Preconditions + Step 6 updated to seed via the new endpoint (manual `aiosqlite` kept as a documented fallback).
- A fresh PASS run log under `tests/behavior/audit-log-inspector-renders-routing-entries/runs/` (produced by the FD-run re-run — see Acceptance Criteria).

## Acceptance Criteria

- [x] **(retirement, no code)** The two browser-test files pass: scoped run of `test_flow_agent_tabs.py` + `test_flow_studio_navigation.py` → **22 passed, 1 skipped** (chromium launched cleanly, no `_ensure-playwright` needed). Flight-log records the `already-satisfied` classification with the F14-L5 evidence. No code fix needed.
- [x] A dev-mode-gated endpoint exists: `POST /api/_test/chat/sessions/{session_id}/routing-audit` — accepts `{"routing": [...]}`, sets `session_metadata["routing"]` via `set_session_metadata_key` (NOT the dropping `update`), returns `{"count": N}`, **403** when not dev-mode, **404** on missing session, **400** on non-list body.
- [x] Unit tests cover all four cases (+ overwrite semantic + non-list 400): `TestRoutingAuditSeedEndpoint` in `tests/test_db_api.py`, **6 passed**. Round-trip asserted via `GET /api/chat/sessions/{id}`.
- [x] `tests/behavior/audit-log-inspector-renders-routing-entries.md` Preconditions + Step 6 updated: primary seed is the new endpoint via one `curl`; PUT removed as primary; `aiosqlite UPDATE` kept as documented fallback; `jq` length probe kept. Intent + Steps 1-5/7 untouched.
- [ ] **(FD-performed — PENDING)** `/behavior-test audit-log-inspector-renders-routing-entries` re-runs **PASS** (cache-cold: fresh tab + `ignoreCache=true`) using the new seed endpoint. NOT yet run — left for the FD's separate interactive re-run. The fresh run log lands under the spec's `runs/` dir.
- [x] Full backend suite green (`-m 'not browser and not live and not pixel and not requires_bwrap'`): **2829 passed, 4 skipped, 524 deselected**. The two browser-test files green (22 passed, 1 skipped).

## Verification Steps

- `grep -n "_test/chat/sessions" the_one/interfaces/web/api.py` — endpoint present; read it to confirm dev-mode gate + `set_session_metadata_key` use (NOT `update`).
- `docker exec the-one pytest tests/<new endpoint test file> -x --timeout 30 -q` — endpoint unit tests pass.
- Manual seed smoke (dev container is dev-mode): create or pick a session id `SID`, then
  `curl -sf -X POST http://localhost:8484/api/_test/chat/sessions/$SID/routing-audit -H 'Content-Type: application/json' -d '{"routing":[{"ts":"2026-06-02T00:00:00Z","agent":"x","rule_index":0,"scope":"channel","match":null,"reason":"matched","disposition":"stepped"}]}'`
  then `curl -s http://localhost:8484/api/chat/sessions/$SID | jq '.session_metadata.routing | length'` → `1`.
- `make test-browser` (runs `_ensure-playwright` first) — browser suite incl. the two files green.
- `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap' -x --timeout 30 -q` — backend green.
- FD runs `/behavior-test audit-log-inspector-renders-routing-entries` → PASS; run log committed.

## Implementation Guidance

1. **Add the seed endpoint** (`the_one/interfaces/web/api.py`, near the session handlers `~3167-3232`)
   - Mirror `purge_chat_messages` (`api.py:3222`) for the session-scoped-POST shape; acquire the repo via `repo = await _chat_repo()` (`api.py:93-95`, the helper the neighboring handlers use).
   - Gate first: `if not settings.dev_mode: raise HTTPException(status_code=403, detail="test-seam endpoint requires THE_ONE_DEV_MODE=true")`. (Gate on `settings.dev_mode` following the mock-provider precedent at `api.py:3378`; use **403** — endpoint-level disablement — NOT the mock-provider's field-level **400**. Do not "mirror exactly"; the status differs intentionally.)
   - Parse the body (`data = await request.json()`), pull `routing = data.get("routing")`; validate it's a list (400 otherwise).
   - `try: await repo.set_session_metadata_key(session_id, "routing", routing)` / `except KeyError: raise HTTPException(404, …)`.
   - Return `{"count": len(routing)}`.
   - Keep it minimal and clearly commented as an M11 F15 L2 dev-mode test seam (cite the precedent).
2. **Unit tests** — add to `tests/test_db_api.py` (its `client` fixture mounts `router` with the `/api` prefix, `test_db_api.py:18-44`). Flip dev-mode via `with patch("the_one.interfaces.web.api.settings") as mock_settings: mock_settings.dev_mode = True/False` (the mock-provider gating tests' pattern — `tests/test_provider_api.py:1998+`; note those assert 400, but the *toggle mechanism* is what to copy). Cover the four AC cases. Assert round-trip through `GET /api/chat/sessions/{id}` (full `/api` prefix) — not just the writer — so the detail exposure is exercised.
3. **Update the behavior-test spec** — in `audit-log-inspector-renders-routing-entries.md`, replace the Preconditions "Operator seeds via the simplest path available" bullet's option-(a) PUT with: "POST the routing entries to the dev-mode test-seam endpoint: `curl -X POST http://localhost:8484/api/_test/chat/sessions/<sid>/routing-audit -H 'Content-Type: application/json' -d '{\"routing\": [...4 entries...]}'`". Keep the `jq` length probe. Update Step 6's mid-run "append a 5th entry" to re-POST the full 5-entry array to the same endpoint (overwrite semantic) instead of the PUT example. Retain a one-line "fallback: direct `aiosqlite UPDATE`" note. Do NOT change the spec's Steps 1-5/7 assertions or Intent.
4. **Retirement doc** — no code; record in the flight log that the browser-fails fold-in is `already-satisfied` (F14 L5 resolved both; 22 passed verified). Update the flight's "Contributing to Criteria" only if needed (it doesn't list browser-fails as a criterion — no change).

## Edge Cases

- **Do NOT route the seed through `ChatSessionRepository.update`** — it drops `session_metadata` by design (`repositories.py:936-942` docstring). Use `set_session_metadata_key` only.
- **Production safety:** the endpoint MUST 403 when `dev_mode` is False — it writes arbitrary routing JSON; it is a test seam, never a production surface. Gate on `settings.dev_mode` (precedent: `api.py:3378`), returning 403 for the whole-endpoint disablement (distinct from the mock-provider's field-level 400).
- **Body validation:** a non-list / missing `routing` → 400, not a 500. Each entry is opaque JSON (the panel renders whatever strings are present); the endpoint does not validate entry shape (the spec's seed supplies well-formed entries).
- **`set_session_metadata_key` overwrite semantic** means re-POSTing replaces the whole `routing` list — which is exactly what Step 6's "now 5 entries" needs (post the full 5). Document this in the spec so the operator posts the full array, not a delta.
- **Playwright deps:** if `make test-browser` errors at chromium launch, run `make _ensure-playwright` (or `docker exec the-one playwright install-deps chromium`) first — the L1 rebuild wiped them.
- **`/behavior-test` re-run is FD-performed, cache-cold** (fresh tab + `ignoreCache=true`) to avoid the F13 transient-cache false-FAIL.

## Files Affected

- `the_one/interfaces/web/api.py` — new dev-mode-gated seed endpoint.
- `tests/…` — new endpoint unit tests (in the existing chat-session API test module or a sibling).
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — Preconditions + Step 6 seed path updated.
- (FD) fresh PASS run log under the spec's `runs/`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (the FD-performed `/behavior-test` re-run may complete after the Developer's autonomous portion — coordinate with the FD)
- [ ] Tests passing (backend + the two browser files via `make test-browser`)
- [ ] Update flight-log.md with leg progress entry (incl. the browser-fails retirement evidence)
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Not the final leg — commit handled at flight-level Phase 2d (deferred-commit model); the `/behavior-test` re-run's run log may commit per-run

## Citation Audit

9 citations verified against current code at L2 design time: `repositories.py:1067` (`set_session_metadata_key`, overwrite semantic) OK; `repositories.py:936-942` (`update` drops session_metadata, docstring) OK; `repositories.py:1021` (`append_to_session_metadata`, sibling) OK; `api.py:49` (`router = APIRouter(prefix="/api")`) OK; `api.py:3167` (`get_chat_session` exposes session_metadata) OK; `api.py:3198` (`update_chat_session` PUT) OK; `api.py:3222` (`purge_chat_messages` sibling POST) OK; `api.py:3360`/`3378` (dev-mode gate pattern) OK; `app.py:118` (`THE_ONE_REGISTER_STUB_CONNECTOR` + dev_mode seam precedent) OK; `test_flow_studio_navigation.py:253` (`test_studio_section_round_trip_returns_to_agent_listing`) OK. All clean.
