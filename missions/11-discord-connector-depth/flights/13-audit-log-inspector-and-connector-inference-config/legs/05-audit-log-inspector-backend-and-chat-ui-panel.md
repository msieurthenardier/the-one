# Leg: audit-log-inspector-backend-and-chat-ui-panel

**Status**: completed
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](../flight.md)

## Objective

Expose `session_metadata` on the chat-session detail endpoint AND render a collapsible Chat UI per-session "Routing audit" panel that surfaces every `session_metadata["routing"]` entry (timestamp + agent + scope + reason + disposition badge + per-entry expansion of raw fields; nested `policy` dict for `policy-silent` entries) — closing M11 criterion #15 (audit-log inspector) and authoring the inline `tests/behavior/audit-log-inspector-renders-routing-entries.md` Witnessed spec that pins the read-and-expand flow end-to-end.

## Context

Atomic backend + frontend leg. The L1+L2+L3+L4 substrate already landed; the routing audit shape (the entries this panel renders) was finalized at F7 L8 and is consumed unchanged by F13 L5. Per the flight log L4 entry, working tree carries L1+L2+L3+L4 edits forward — Phase 2d code-review + commit batches after L5 lands.

Key design decisions inherited from the flight spec (re-stated here so the implementing agent has them in-hand):

- **Audit-Log Inspector Surface: Chat UI Per-Session Panel** (Phase 5b DD; F7 OQ #8 default). The panel lives in the Chat UI, attached to the current session's content area. No new Studio surface, no new top-level route.
- **API Exposure Shape: Extend Detail-Endpoint Composition, Not the Shared Summary Helper** (architect cycle-1 correction). `session_metadata` is attached ONLY in the dict literal at the detail endpoint's `return` site — the shared `_session_summary()` helper at `api.py:_session_summary` stays untouched. List / create / update endpoints keep their existing summary-only response shape, so per-session-routing payload does not bloat list responses.
- **Audit-Log Inspector Renders Only `routing`** (Phase 5b DD). The panel renders entries from `session_metadata["routing"]` only. `session_metadata["audit"]` (F6 ACL deny/permit per-peer decisions), any future `routing_override` key, and any other top-level keys are NOT rendered in F13.
- **No real-time push** (architect cycle-1 suggestion). MVP is fetch-on-open + explicit "Refresh" button. No WebSocket event for routing updates. Avoids re-fetching the session-detail payload on every inbound on a chatty Discord connector.
- **Disposition badge color tokens** map to existing `tokens.css` semantics (per `tests/test_design_tokens_a11y.py` + `tests/browser/design_tokens.py` — these tests pin contrast ratios for the named tokens):
  - `stepped` → `--status-success` (the routed-agent engaged path)
  - `command-intercepted` → `--accent` (a built-in/plugin command short-circuit)
  - `no-eligible` → `--status-warning` (no agent was eligible; peer received an error)
  - `policy-silent` → `--fg-muted` (gate decided silent; nothing emitted)
- **Per-entry expansion uses native `<details>`/`<summary>`** — mirrors the existing `trace-shell.js:21-50` pattern. Keyboard-operable for free; no custom JS toggle logic.
- **Layout decision** (deferred to L5 design — see Implementation Guidance Step 1): the panel renders as a **collapsible `<details>` section appended to `chromeEl` between `.messages` and `.input-area`**, INSIDE the existing `chat-chrome` container. Reasons:
  - Visible in the same viewport as the message list (the operator's stated "where I already live when debugging routing").
  - Native `<details>` keeps the panel collapsed by default — zero-cost when the operator isn't debugging.
  - Stays in the same flexbox column as `.messages` + `.input-area`, so no new chat-area layout surgery (no side-panel grid restructure).
  - Toggling does not affect message-list scroll position because the panel sits *below* `.messages` in the column.
- **No new module file** for the panel logic. Use a new sibling module `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js` (mirrors `trace-shell.js`, `telemetry-overlay.js`, and the other `App.chat.*` builders living in the `areas/chat/` subdirectory). The `chat.js` integration point wires it into the chrome layout + the session-join data flow.
- **CSS goes in `the_one/interfaces/web/static/css/chat.css`** as a new `.routing-audit-panel` block sibling to the `.trace-shell` block (which it shares the `<details>` pattern with). One new disposition-badge class per disposition (4 classes total) referencing the existing tokens — no new tokens added; the `tests/test_design_tokens_a11y.py` regression net continues to pin the underlying token contrast ratios. No baseline values change.
- **`session_metadata` is part of the `session_joined` payload too** — see Implementation Guidance Step 4. The Chat UI's session-detail data flow is the WebSocket `session_joined` envelope assembled server-side by the WS payload builders, NOT the `GET /api/chat/sessions/{id}` REST endpoint. The leg therefore plumbs `session_metadata` through TWO server-side surfaces: (a) the REST detail endpoint composition (per the flight DD), and (b) the WebSocket session-join builders at `the_one/interfaces/web/app.py:678-696` (`_build_session_joined_ok`) AND `:699-722` (`_build_session_joined_degraded`). **VERIFIED at design time** (Flight Director pre-confirm): the `Session` dataclass at `app.py:285-315` currently has fields `id, agent, created, source, title, agent_name, history, platform` — **no `session_metadata` attribute**. The OK path therefore needs the `Session` dataclass to gain a `session_metadata: dict[str, Any] | None = None` field (matches the M10 F5 L4 `platform` field pattern), populated in `_restore_session` from `db_session.session_metadata`. The degraded builder takes `RestoredSession.db_session: ChatSessionModel` which already carries `session_metadata` — trivial 1-line addition.

**Cumulative leg-by-leg state** at L5 entry (per flight log post-L4):

- Backend test suite: **2794 passed / 4 skipped / 509 deselected / 0 errors / 3 warnings** (UNCHANGED from L3; L4 was frontend-only).
- Browser test suite: **448 passed / 35 skipped / 12 deselected** (+ 2 pre-existing-main failures preserved).
- `tests/behavior/` directory exists with three prior specs (`discord-engagement.md`, `studio-smoke.md`, `connector-inference-provider-config-roundtrip.md`); `.gitignore` already has `tests/behavior/*/runs/*/` guard. No directory seeding or `.gitignore` edits needed.
- Working tree carries L1+L2+L3+L4 edits forward.

## Inputs

**State that must be true before L5 starts**:

- L1+L2+L3+L4 are `landed` (verified via flight log).
- `the_one/interfaces/web/api.py` has the detail endpoint `get_chat_session` at lines 3188-3198 (verified — see Citation Audit) with the `_session_summary()` helper at line 3246; the shared helper is consumed by 5 sites (`list_chat_sessions:3185`, `get_chat_session:3196`, `create_chat_session:3209`, `update_chat_session:3223`, the helper def itself at `:3246`).
- `the_one/db/models.py:716+` defines `ChatSession` with `session_metadata: dict[str, Any] | None = None` (verified — see Citation Audit).
- The repository's `ChatSession.session_metadata` round-trips JSON correctly via `_row_to_model` (per F7 L8 + F8 L6 precedents; the WS handler + REST endpoint already write through `append_to_session_metadata` and read back via `repo.get(...)`).
- Routing audit entry shape stabilized at F7 L8 (per `the_one/connectors/_inbound.py` lines 530-538 for the base shape + 547-805 for the six per-disposition write sites): `{ts, agent, rule_index, scope, match, reason, disposition}` (always) + `intercept_source` (only on `command-intercepted`) + `policy` dict (only on `policy-silent`). See Implementation Guidance Step 2 for the full shape enumeration.
- `App.chat.renderTrace` + `App.chat.appendToTrace` exist as sibling builder modules in `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` (verified — pattern reference for the new panel module).
- `App.escapeHtml` + `App.escapeAttr` exist as global escape helpers (verified at `the_one/interfaces/web/static/js/app.js:210-220` + exported via `App` namespace at `:280-281`).
- `chromeEl` (the chat content wrapper) is constructed at `chat.js:88` and contains `.messages` + `.input-area` + the telemetry overlay (verified — see Citation Audit).
- The session-join flow's `renderHistory(history, agentName)` runs at `chat.js:859` inside the `session_joined` WS event handler; the panel population hook latches into the same handler (so the panel is populated at the same DOM-mount moment the messages are).
- `app_clean` browser fixture (`tests/browser/conftest.py:113-184`) spawns a subprocess with `THE_ONE_DEV_MODE=true` + `THE_ONE_REGISTER_STUB_CONNECTOR=1`. Browser tests in L5 use this OR the `app_with_data_dir` SQLite-seeding pattern from `tests/browser/test_flow_chat_session_list_source_badge.py:70-131` to write `session_metadata` directly to a chat-session row.

**Files that must exist**:

- `the_one/interfaces/web/api.py` (will be modified — detail-endpoint composition only)
- `the_one/interfaces/web/static/js/areas/chat.js` (will be modified — chrome wiring + session-join hook)
- `the_one/interfaces/web/static/css/chat.css` (will be modified — new `.routing-audit-panel` block)
- `tests/test_db_api.py` (will be modified — 2 new backend tests added)
- `tests/browser/conftest.py` (unchanged; consumed)
- `tests/browser/test_flow_chat_session_list_source_badge.py` (unchanged; pattern reference)
- `the_one/connectors/_inbound.py` (unchanged; the routing audit producer; design-time recon only)

## Outputs

**Files modified**:

- `the_one/interfaces/web/api.py` — detail-endpoint `get_chat_session` composition at the `return` site adds `"session_metadata": session.session_metadata`. The shared `_session_summary()` helper stays byte-identical (the grep gate in AC-15 enforces this).
- `the_one/interfaces/web/app.py` — **FOUR** surfaces (replaces the prior `realtime.py` mis-citation):
  - **`Session` dataclass** at `:285-315`: add `session_metadata: dict[str, Any] | None = None` field (mirrors the M10 F5 L4 `platform` field pattern).
  - **`_restore_session`** at `:500-617`: populate `session.session_metadata = db_session.session_metadata` in both branches (in-place-update + new-construction).
  - **`_build_session_joined_ok`** at `:678-696`: add `"session_metadata": session.session_metadata` to the return dict.
  - **`_build_session_joined_degraded`** at `:699-722`: add `"session_metadata": db.session_metadata` to the return dict (the `db: ChatSessionModel` variable is already in scope and carries the field directly).
- `the_one/interfaces/web/static/js/areas/chat.js` — chrome construction (lines ~67-86) appends the routing-audit-panel container between `.messages` and `.input-area`; the `session_joined` handler at lines ~846-913 calls `App.chat.routingAuditPanel.render(...)` with `data.session_metadata` (supplied by the WS payload builders per the bullet above).
- `the_one/interfaces/web/static/css/chat.css` — new `.routing-audit-panel` block sibling to `.trace-shell` (lines ~143-200) plus the 4 disposition-badge classes.
- `tests/test_db_api.py` — `TestChatSessionAPI` class (line ~2569) gains 2 new tests verifying `session_metadata` round-trips on the detail endpoint AND is absent from the list endpoint.

**Files added**:

- `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js` — NEW; the panel module exporting `App.chat.routingAuditPanel.{create, render, refresh}` (≈170 lines). Mirrors the shape of `trace-shell.js`.
- `tests/browser/test_flow_chat_routing_audit_panel.py` — NEW; 6 browser tests (Step 8). Target: +6 to the 448 baseline → **454**.
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — NEW; Witnessed behavior-test spec (status `draft` at land; operator promotes to `active` after first successful run at the Pre-L6 gate).

**Server-side surface for the WebSocket join handler**:

- The WebSocket `session_joined` event payload must include `session_metadata` so the Chat UI panel can render on join without a separate REST round-trip. Verified-at-design: the payload builders are `_build_session_joined_ok` at `the_one/interfaces/web/app.py:678-696` and `_build_session_joined_degraded` at `:699-722`. The OK path requires the `Session` dataclass to gain a `session_metadata` field (populated in `_restore_session`); the degraded path takes `db: ChatSessionModel` which already carries the field.

**State after the leg**:

- `git grep -n "session_metadata" the_one/interfaces/web/api.py` returns the new detail-endpoint composition site (1 hit inside `get_chat_session`) AND zero hits inside `_session_summary` (verified by the grep gate AC-15).
- `git grep -nE 'routing-audit|routing_audit|routingAudit' the_one/interfaces/web/static/js/areas/` returns the new panel render/handler code (at minimum: module-level `App.chat.routingAuditPanel` exports in `chat/routing-audit-panel.js`, the integration points in `chat.js`, and `data-testid="routing-audit-*"` attributes on the rendered DOM).
- Backend test count at **2795-2796** (baseline 2794 + 2 new tests: detail-includes / list-omits).
- Browser test count at **454** (baseline 448 + 6 new tests in `test_flow_chat_routing_audit_panel.py`).
- 2 pre-existing-main browser failures remain (NOT F13-caused — `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`).
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` exists with `Status: draft`.

## Acceptance Criteria

- [x] **AC-1** — backend, detail-endpoint composition: `GET /api/chat/sessions/{id}` returns `session_metadata` as a top-level key in the response JSON. The value is the parsed dict (NOT a JSON-string; matches `ChatSession.session_metadata: dict[str, Any] | None`). For a session whose `session_metadata` is `None`, the response key value is `null`. For a session whose `session_metadata` contains `{"routing": [...], "audit": [...]}`, the response key value contains both subkeys unmodified.
- [x] **AC-2** — backend, list-endpoint exclusion: `GET /api/chat/sessions` response items do NOT include a `session_metadata` key on any item. Verified by asserting `"session_metadata" not in item` for every item in the response list. The shared `_session_summary()` helper at `the_one/interfaces/web/api.py:_session_summary` is BYTE-IDENTICAL post-L5 (no new keys, no edits).
- [x] **AC-3** — backend tests added to `tests/test_db_api.py::TestChatSessionAPI`: (a) `test_get_session_includes_session_metadata` constructs a session via the API, mutates `session_metadata` via the repository's `append_to_session_metadata` (or by direct PUT if simpler — see Implementation Guidance Step 6), GETs the detail endpoint, asserts the new key is present + structurally correct. (b) `test_list_sessions_excludes_session_metadata` constructs a session with a non-empty `session_metadata`, GETs the list endpoint, asserts no item carries the key.
- [x] **AC-4** — backend test count: backend test suite green at **2795-2796 passed / 4 skipped / 509 deselected / 0 errors** (baseline 2794 + 2 new tests). Run `docker exec the-one pytest tests/ --timeout 30 -q` and confirm.
- [x] **AC-5** — frontend panel module exists: `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js` exists and exports `window.App.chat.routingAuditPanel` with at least these public functions: `create()` (returns the DOM container with the `<details>` shell + Refresh button + body placeholder), `render(container, routingEntries)` (replaces the body with one row per entry + empty-state when the list is empty/missing), `refresh(container, sessionId, onComplete)` (re-fetches `GET /api/chat/sessions/{id}` and re-calls `render` with the fresh `session_metadata.routing`). Confirmed by `git grep -n "App.chat.routingAuditPanel" the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js` returning at least 3 hits (one per public function).
- [x] **AC-6** — frontend panel is mounted in the chat chrome: `the_one/interfaces/web/static/js/areas/chat.js` calls `App.chat.routingAuditPanel.create()` during chrome construction and inserts the result into `chromeEl` between `.messages` and `.input-area`. After session-join, `App.chat.routingAuditPanel.render(panelContainer, sessionMetadata.routing)` is called from the `session_joined` handler with the routing list from the join payload (see AC-14 for the server-side payload requirement).
- [x] **AC-7** — empty state: when the session's `session_metadata.routing` is missing OR an empty list, the panel body renders a single readable empty-state message containing the substring `No routing decisions yet`. The Refresh button is still visible + enabled. Confirmed via the browser test seeding an empty-routing session.
- [x] **AC-8** — populated state, per-entry row: when `session_metadata.routing` contains entries, the panel body renders ONE row per entry. Each row contains: (a) the formatted timestamp (ISO 8601 from the `ts` field — render as a `<time>` element with `datetime` attribute = raw `ts`; visible text = the raw `ts` value is acceptable for v1 — operator-readable string formatting can land in a future polish flight), (b) the agent name (or the literal `—` for `agent is None` / missing — covers the `no-eligible` disposition where the routing engine couldn't pick an agent), (c) the scope value, (d) the reason value (truncated to ≤120 chars with `…` suffix when longer; full text in the expansion), (e) the disposition badge.
- [x] **AC-9** — disposition badges, per-disposition CSS class: the badge for each entry has a class of the form `routing-audit-badge routing-audit-badge--{disposition}` where `{disposition}` is the literal disposition value. The four classes `routing-audit-badge--stepped`, `routing-audit-badge--command-intercepted`, `routing-audit-badge--no-eligible`, `routing-audit-badge--policy-silent` exist in `the_one/interfaces/web/static/css/chat.css` and reference the four tokens listed in Context (`--status-success`, `--accent`, `--status-warning`, `--fg-muted`). Confirmed via `git grep -nE 'routing-audit-badge--' the_one/interfaces/web/static/css/chat.css` returning at least 4 hits.
- [x] **AC-10** — per-entry expansion (the row's `<details>` shell): clicking a row's `<summary>` toggles the row's `<details>` open. The expanded body renders the full entry's raw fields. Required-key rendering: every entry's `rule_index`, `match`, `intercept_source` (when present) appear with key labels and values. The `policy` dict (when present — only on `policy-silent` disposition) is rendered nested with each policy key on its own line: `outcome`, `inference_provider_id`, `inference_model`, `account_always_listen`, `agent_always_listen` (any subset; entries with the `always-listen-off` outcome omit `inference_provider_id` + `inference_model` per `_inbound.py:_policy_gate_decision` — render only the keys actually present).
- [x] **AC-11** — Refresh button: the panel has a button labelled `Refresh` (visible text). Clicking it calls `App.chat.routingAuditPanel.refresh(...)` which performs `fetch('/api/chat/sessions/' + sessionId)`, reads `session_metadata.routing` from the response, and re-renders the panel body. The button is disabled while a refresh is in flight; re-enabled when the fetch completes (success OR failure).
- [x] **AC-12** — collapsed-by-default: on session join, the panel's outer `<details>` is NOT `open` (collapsed). Operator must explicitly expand to see the per-session entries. Mirrors `trace-shell.js`'s collapsed-default pattern.
- [x] **AC-13** — browser tests: `tests/browser/test_flow_chat_routing_audit_panel.py` exists and contains exactly 6 tests covering: (i) empty-state render; (ii) multi-disposition render (seed `stepped` + `command-intercepted` + `no-eligible` + `policy-silent` entries, assert all 4 rows visible + the 4 badge classes present); (iii) per-entry expansion shows raw fields (click first row's `<summary>`, assert `rule_index` text visible); (iv) `policy-silent` expansion shows nested `policy` dict (click the policy-silent row's `<summary>`, assert `outcome` + `inference_provider_id` + `inference_model` text visible); (v) Refresh re-fetches (seed a routing entry, open session, append a new entry server-side, click Refresh, assert the new row count); (vi) collapsed-by-default (open session with routing entries, assert outer `<details>` is NOT `open`).
- [x] **AC-14** — server-side `session_joined` payload includes `session_metadata` in BOTH builders at `the_one/interfaces/web/app.py`:
  - `_build_session_joined_ok` at `:678-696` returns a dict containing `"session_metadata": session.session_metadata` (requires the `Session` dataclass to gain the field per the Files-Modified bullet AND `_restore_session` to populate it from `db_session.session_metadata`).
  - `_build_session_joined_degraded` at `:699-722` returns a dict containing `"session_metadata": db.session_metadata` (the `db: ChatSessionModel` is already in scope; trivial 1-line addition).
  - Verification: `git grep -nE '"session_metadata"' the_one/interfaces/web/app.py` returns ≥ 2 hits (one per builder). The L5 browser tests (AC-13) observe routing entries on session join without a separate Refresh click — the seed-then-open pattern requires the entries to arrive in the join payload.
- [x] **AC-15** — grep gate, backend: `git grep -n "session_metadata" the_one/interfaces/web/api.py` returns at least one hit and ZERO hits inside the `_session_summary()` helper body (lines 3246-3253; the helper body has 5 lines, none of which mention `session_metadata`). Anchored verification: every reported hit must be inside `get_chat_session` (the detail endpoint, around `api.py:3188-3198`); the helper at `:3246+` MUST NOT mention `session_metadata`.
- [x] **AC-16** — grep gate, frontend module surface: `git grep -nE 'routing-audit|routing_audit|routingAudit' the_one/interfaces/web/static/js/areas/` returns at least 6 hits, distributed across `chat/routing-audit-panel.js` (module-level exports + render code + class names) AND `chat.js` (the integration call sites). Counts above 6 are acceptable.
- [x] **AC-17** — grep gate, browser tests: `git grep -nE 'routing-audit|routing_audit' tests/browser/test_flow_chat_routing_audit_panel.py` returns at least 6 hits (one per test resolving by a `data-testid` like `routing-audit-panel` / `routing-audit-empty` / `routing-audit-row` / `routing-audit-refresh` / `routing-audit-badge`).
- [x] **AC-18** — design-tokens regression: `docker exec the-one pytest tests/test_design_tokens_a11y.py --timeout 30 -q` still passes UNCHANGED. The leg adds CSS classes that *reference* the existing tokens; it does NOT change any token's hex value, so the WCAG contrast test class continues to pass without per-class updates.
- [x] **AC-19** — full browser suite green: browser test suite at **454 passed / 35 skipped / 12 deselected + 2 pre-existing-main failures** (baseline 448 + 6 new). Do NOT run with `-x` (the 2 pre-existing-main failures must not short-circuit the run). The 2 pre-existing failures (`test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`) remain — out of F13 scope.
- [x] **AC-20** — behavior-test spec present: `tests/behavior/audit-log-inspector-renders-routing-entries.md` exists, has `**Status**: draft`, follows the `.flightops/ARTIFACTS.md` "Behavior Test — Spec" format (Slug / Status / Created / Last Run / Intent / Preconditions / Observables Required / Steps table / Out of Scope), and is committed alongside the source changes. The live spec run is **deferred to the Pre-L6 behavior-test gate** per flight spec — do NOT attempt `/behavior-test audit-log-inspector-renders-routing-entries` as part of L5 land.

## Verification Steps

Run each command from the project root (`/home/cprch/projects/the-one`). All pytest invocations use `docker exec the-one pytest …` with `-x --timeout 30` (browser-suite invocations drop `-x` so the 2 pre-existing failures don't short-circuit).

**Phase 1 — Static gates (run before pytest):**

1. **AC-15 grep (backend)**: `docker exec the-one git grep -n "session_metadata" the_one/interfaces/web/api.py` — visually confirm every hit is inside `get_chat_session` (around lines 3188-3198); zero hits inside the `_session_summary` helper body.
2. **AC-16 grep (frontend module surface)**: `docker exec the-one git grep -nE 'routing-audit|routing_audit|routingAudit' the_one/interfaces/web/static/js/areas/ | wc -l` — expect at least 6.
3. **AC-17 grep (browser tests)**: `docker exec the-one git grep -nE 'routing-audit|routing_audit' tests/browser/test_flow_chat_routing_audit_panel.py | wc -l` — expect at least 6.
4. **AC-9 grep (CSS classes)**: `docker exec the-one git grep -nE 'routing-audit-badge--' the_one/interfaces/web/static/css/chat.css | wc -l` — expect at least 4 (one per disposition class).

**Phase 2 — Backend regression + new backend tests (AC-3, AC-4):**

```
docker exec the-one pytest tests/test_db_api.py::TestChatSessionAPI -x --timeout 30 -q
```

Expect: all `TestChatSessionAPI` tests pass (existing 2 + new 2 = 4).

```
docker exec the-one pytest tests/ --timeout 30 -q
```

Expect: `2795 passed, 4 skipped, 509 deselected, 0 errors, 3 warnings` (baseline 2794 + 2). If the count is 2796, the implementer added an extra test — acceptable per the flight spec's `2795-2796` target range.

**Phase 3 — Design-tokens regression (AC-18):**

```
docker exec the-one pytest tests/test_design_tokens_a11y.py --timeout 30 -q
```

Expect: all pass UNCHANGED. If any new failure surfaces, the leg has accidentally changed a token's value — revert the offending CSS edit.

**Phase 4 — Targeted browser regression (the existing chat tests must keep passing):**

```
docker exec the-one pytest tests/browser/test_flow_chat.py tests/browser/test_flow_chat_session_list_source_badge.py -m browser -x --timeout 30 -q
```

Expect: every existing chat browser test passes UNCHANGED. If the panel insertion disrupted the chrome layout, expect breakage here — fix in-leg.

**Phase 5 — New browser tests (AC-13):**

```
docker exec the-one pytest tests/browser/test_flow_chat_routing_audit_panel.py -m browser -x --timeout 30 -q
```

Expect: 6 new tests pass.

**Phase 6 — Full browser suite (AC-19):**

```
docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q
```

Expect: `2 failed, 454 passed, 35 skipped, 12 deselected` — the 2 failures are the documented pre-existing-main failures (NOT in any L5-touched test file). Do NOT pass `-x` here — continue past the pre-existing failures.

**Phase 7 — Behavior-test spec presence (AC-20):**

```
ls tests/behavior/audit-log-inspector-renders-routing-entries.md
docker exec the-one git grep -n '^\*\*Status\*\*: draft' tests/behavior/audit-log-inspector-renders-routing-entries.md
```

Expect: file exists; status header reads `**Status**: draft`.

The live spec run is **deferred to the Pre-L6 behavior-test gate** per the flight spec's `## Checkpoints` → "Pre-L6 behavior-test gate" entry. Do NOT attempt `/behavior-test audit-log-inspector-renders-routing-entries` as part of L5 land.

## Implementation Guidance

### 1. Recon-anchored citations (verified at L5 design time)

| Citation | Description | Verified |
|----------|-------------|----------|
| `the_one/interfaces/web/api.py:3188-3198 (get_chat_session)` | The detail endpoint. The `return` site at `:3195-3198` is the composition spot — extend the dict literal with `"session_metadata": session.session_metadata`. The `await repo.get(session_id)` at `:3192` already yields a `ChatSession` whose `session_metadata` attribute is the decoded dict (or `None`). | OK |
| `the_one/interfaces/web/api.py:3246-3253 (_session_summary)` | The shared summary helper. **DO NOT** add `session_metadata` here — leaving it untouched is the architect cycle-1 correction. Consumed by 5 sites: `list_chat_sessions:3185`, `get_chat_session:3196` (via the `**_session_summary(session)` spread), `create_chat_session:3209`, `update_chat_session:3223`, the helper itself. | OK |
| `the_one/db/models.py:716 (class ChatSession)` | The `ChatSession` Pydantic model. `session_metadata: dict[str, Any] \| None = None` lives at `:749` (verified). The detail endpoint's `session.session_metadata` access returns the decoded dict directly — no additional `json.loads` needed (the codec runs at the repository row→model boundary). | OK |
| `the_one/connectors/_inbound.py:530-538 (audit_entry construction)` | Base routing entry shape: `{"ts": now_iso(), "agent": decision.agent, "rule_index": decision.rule_index, "scope": decision.scope, "match": decision.match, "reason": decision.reason}`. `"disposition"` is set per branch BEFORE append. `"intercept_source"` is added inline at the command-intercepted branches (`:688` plugin + `:716` builtin). `"policy"` is added inline at the policy-silent branch (`:778`). | OK |
| `the_one/connectors/_inbound.py:547-805 (six routing append sites)` | Six `await chat_repo.append_to_session_metadata(... "routing", audit_entry)` calls — one per disposition (no-eligible × 3 sub-branches + command-intercepted × 2 sub-branches + policy-silent + stepped). The L5 panel does NOT change this producer surface; it only consumes the entries. | OK |
| `the_one/connectors/_inbound.py:_policy_gate_decision (lines 168-276)` | Returns the `policy_audit` dict embedded under `"policy"` in `policy-silent` entries. Shape varies by outcome: `always-listen-off` has `{outcome, account_always_listen, agent_always_listen}`; `inference-yes`/`inference-no` add `inference_provider_id` + `inference_model`; `dm`/`override`/`mention` only have `outcome` (but those outcomes are engaged-path, never reach the policy-silent append site, so the panel only sees the always-listen-off + inference-no subset of policy shapes). | OK |
| `the_one/interfaces/web/static/js/areas/chat.js:67-86 (chromeEl construction)` | The `chat-chrome` wrapper carries `.header` + `.messages` + `.input-area`. Insert the panel container BETWEEN `.messages` and `.input-area`. Mirror the telemetry-overlay precedent at `:98` (`chromeEl.insertBefore(panelContainer, chromeEl.querySelector('.input-area'))`). | OK |
| `the_one/interfaces/web/static/js/areas/chat.js:341-345 (joinSession)` | Sends `{action: 'join', session_id: id}` over WS. Panel's `currentSessionId` is the `_currentSessionId` exposed at `chat.js:1112-1115`. | OK |
| `the_one/interfaces/web/static/js/areas/chat.js:846-913 (session_joined handler)` | The WS event handler. `data.history` carries the message events; the L5 wiring reads `data.session_metadata` (added server-side per AC-14) and calls `App.chat.routingAuditPanel.render(panelContainer, (data.session_metadata && data.session_metadata.routing) || [])` after `renderHistory` (at the line just after `:859`). | OK |
| `the_one/interfaces/web/static/js/areas/chat/trace-shell.js:21-50 (renderTrace)` | Pattern reference for the new `routing-audit-panel.js` module — same module shape (`window.App.chat = window.App.chat || {}; ... renderXxx()`), same `<details>`/`<summary>` keyboard-operable pattern, same `data-testid` discipline (`trace-shell` → `routing-audit-panel`). | OK |
| `the_one/interfaces/web/static/css/chat.css:143-200 (.trace-shell block)` | Pattern reference for the new `.routing-audit-panel` CSS block. Sibling placement; same `<details>` + `<summary>` styling vocabulary; same `--accent` / `--border` / `--fg-muted` token usage. | OK |
| `the_one/interfaces/web/static/css/tokens.css:136-149 (status tokens)` | The 4 disposition-badge tokens: `--status-success` (`stepped`), `--accent` (`command-intercepted`), `--status-warning` (`no-eligible`), `--fg-muted` (`policy-silent`). All four exist + are pinned by `tests/test_design_tokens_a11y.py`. | OK |
| `the_one/interfaces/web/static/js/app.js:210-220 + :280-281 (escapeHtml / escapeAttr)` | Use `App.escapeHtml` + `App.escapeAttr` for user-supplied strings (agent names, reasons, peer_ids) when building DOM text content from the routing entries. | OK |
| `tests/test_db_api.py:2569-2609 (TestChatSessionAPI)` | The existing class. Add the 2 new tests as siblings to `test_crud` + `test_list_by_agent`. The fixture `client` at `:18-44` is async-scoped per-test; use `await client.post / get` exactly as the existing tests do. | OK |
| `tests/browser/test_flow_chat_session_list_source_badge.py:70-181 (app_with_data_dir fixture + _seed_session helper)` | Pattern reference for L5's browser-test SQLite seeding. The new browser test file uses `app_with_data_dir` (copied or imported via `from .test_flow_chat_session_list_source_badge import app_with_data_dir`) so it can write `session_metadata` JSON directly to the chat-session row pre-join. | OK — see Step 8 for the import-vs-copy decision. |
| `tests/browser/conftest.py:113-184 (app_clean fixture)` | The alternative shared fixture for browser tests that don't need direct DB access. The Refresh-button test uses `app_clean` + a single HTTP `PUT` to mutate `session_metadata` between fetch + click. | OK |
| `the_one/interfaces/web/app.py:285-315` (Session dataclass) + `:500-617` (_restore_session) + `:678-696` (_build_session_joined_ok) + `:699-722` (_build_session_joined_degraded) | The server-side WS payload builders + the in-memory Session dataclass + the restore-from-DB hook. Verified at design time by Flight Director pre-confirm: Session has no `session_metadata` field; both builders are at the cited lines; degraded path takes `db: ChatSessionModel` which already carries the field. | OK |

### 2. Routing audit entry shape — the panel renders these fields

Every entry under `session_metadata["routing"]` has the base shape from `_inbound.py:530-538`:

```python
{
    "ts": "<ISO 8601>",            # always
    "agent": "<agent_name>" | None, # None for no-eligible
    "rule_index": <int> | None,
    "scope": "<scope_string>",     # channel/thread/dm/peer/override/default/first-eligible
    "match": <serializable> | None,
    "reason": "<string>" | None,
    "disposition": "<one of: stepped | command-intercepted | no-eligible | policy-silent>",
}
```

Per-disposition additions:

- `command-intercepted` adds `"intercept_source": "plugin" | "builtin"` (set at `_inbound.py:688` and `:716`).
- `policy-silent` adds `"policy": <policy_audit dict>` (set at `_inbound.py:778`).

The `policy` dict shape (from `_policy_gate_decision` at `_inbound.py:168-276`) depends on the policy outcome — but the policy-silent append only fires for outcomes in `{"always-listen-off", "inference-no"}` (the other outcomes are engaged-path). The panel renders whichever subset of these keys is present:

```python
# always-listen-off shape
{"outcome": "always-listen-off", "account_always_listen": bool, "agent_always_listen": bool}

# inference-no shape (both toggles True, inference returned non-"yes")
{
    "outcome": "inference-no",
    "account_always_listen": True,
    "agent_always_listen": True,
    "inference_provider_id": "<provider id string>" | None,
    "inference_model": "<model name string>" | None,
}
```

The panel's row-expansion handler iterates the entry's keys in a stable display order (suggested: `disposition`, `ts`, `agent`, `scope`, `rule_index`, `match`, `reason`, `intercept_source`, `policy`) and renders any other (future) keys at the end. Unknown keys do not break the render.

### 3. Backend — extend the detail endpoint composition

At `the_one/interfaces/web/api.py:get_chat_session` (around lines 3188-3198), modify the `return` dict literal:

```python
@router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str) -> dict[str, Any]:
    repo = await _chat_repo()
    try:
        session = await repo.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Chat session not found: {session_id}")
    return {
        **_session_summary(session),
        "messages": json.loads(session.messages),
        "session_metadata": session.session_metadata,  # M11 F13 L5
    }
```

**Do NOT** touch `_session_summary()` at `:3246-3253`. The other three callers (`list_chat_sessions`, `create_chat_session`, `update_chat_session`) keep their summary-only shape — verified by the grep gate in AC-15 + the new backend test in AC-2.

### 4. Server-side `session_joined` payload — plumb `session_metadata`

**VERIFIED at design time** (Flight Director pre-confirm): the WS payload builders live at `the_one/interfaces/web/app.py:678-696` (`_build_session_joined_ok`) and `:699-722` (`_build_session_joined_degraded`). NO `realtime.py` module exists; the prior recon-defer was unnecessary.

Current `_build_session_joined_ok` return dict (no `session_metadata`):
```python
return {
    "type": "session_joined",
    "session_id": session.id,
    "status": SESSION_STATUS_OK,
    "title": session.title,
    "agent_name": session.agent_name,
    "history": session.history,
    "is_processing": is_processing,
}
```

The `Session` dataclass at `app.py:285-315` does NOT carry a `session_metadata` attribute (verified). Three coordinated edits are required:

**(a) Extend `Session` dataclass** at `:285-315`. Add a new field after `platform`:
```python
    # M11 F13 L5: routing-audit-inspector hydration. The dispatcher's
    # session_metadata["routing"] writes go to the DB via
    # ChatSessionRepository.append_to_session_metadata. The Chat UI
    # routing-audit panel reads from this in-memory snapshot via the
    # session_joined WS payload; Refresh button re-fetches from REST.
    session_metadata: dict[str, Any] | None = None
```
This mirrors the M10 F5 L4 `platform` field pattern.

**(b) Populate in `_restore_session`** at `app.py:500-617`. Both branches (in-place-update + new-construction) set `session.session_metadata = db_session.session_metadata` where `db_session: ChatSessionModel` is in scope. The DB row carries the field directly (per `db/models.py:749`); the in-memory cache is a snapshot at restore time.

**(c) Add to BOTH payload builders**:
- `_build_session_joined_ok` at `:678-696` — add `"session_metadata": session.session_metadata,` to the return dict.
- `_build_session_joined_degraded` at `:699-722` — add `"session_metadata": db.session_metadata,` to the return dict (the `db: ChatSessionModel` variable is already in scope).

**Verification**:
- `git grep -nE '"session_metadata"' the_one/interfaces/web/app.py` returns ≥ 2 hits post-L5.
- The browser test `test_panel_populates_on_join_without_refresh` (part of AC-13) exercises the OK path end-to-end.

**Edge case — staleness vs DB**: the in-memory `Session.session_metadata` is a snapshot at restore time. If the dispatcher writes a new routing entry to the DB via `append_to_session_metadata` while the session is in memory, the cached attribute becomes stale. The Refresh button is the documented escape hatch (per the "no real-time push" Design Decision). Note this in the flight log L5 entry as an explicit MVP limitation.

### 5. Frontend — new sibling module `chat/routing-audit-panel.js`

Create `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js`. Module shape mirrors `trace-shell.js`:

```javascript
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};
  window.App.chat.routingAuditPanel = window.App.chat.routingAuditPanel || {};

  var escapeHtml = function (s) { return (window.App && App.escapeHtml) ? App.escapeHtml(s) : String(s); };
  var escapeAttr = function (s) { return (window.App && App.escapeAttr) ? App.escapeAttr(s) : String(s); };

  // Stable display order for the "raw fields" expansion section.
  var EXPANSION_KEY_ORDER = [
    'disposition', 'ts', 'agent', 'scope', 'rule_index',
    'match', 'reason', 'intercept_source', 'policy'
  ];

  // Stable display order for the nested policy dict.
  var POLICY_KEY_ORDER = [
    'outcome',
    'inference_provider_id', 'inference_model',
    'account_always_listen', 'agent_always_listen'
  ];

  // Build the panel chrome. Returns the outer container; chat.js inserts
  // it into chromeEl between .messages and .input-area.
  function create() {
    var wrap = document.createElement('div');
    wrap.className = 'routing-audit-panel';
    wrap.setAttribute('data-testid', 'routing-audit-panel');
    var details = document.createElement('details');
    details.setAttribute('data-testid', 'routing-audit-details');
    // Collapsed by default — AC-12.
    var summary = document.createElement('summary');
    summary.className = 'routing-audit-toggle';
    summary.textContent = 'Routing audit';
    summary.setAttribute('data-testid', 'routing-audit-summary');
    details.appendChild(summary);

    var header = document.createElement('div');
    header.className = 'routing-audit-header';
    var refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'btn-muted routing-audit-refresh';
    refreshBtn.textContent = 'Refresh';
    refreshBtn.setAttribute('data-testid', 'routing-audit-refresh');
    header.appendChild(refreshBtn);
    details.appendChild(header);

    var body = document.createElement('div');
    body.className = 'routing-audit-body';
    body.setAttribute('data-testid', 'routing-audit-body');
    details.appendChild(body);

    wrap.appendChild(details);
    return wrap;
  }

  // Render the body — one row per entry, or an empty-state message.
  function render(container, routingEntries) {
    if (!container) return;
    var body = container.querySelector('.routing-audit-body');
    if (!body) return;
    body.innerHTML = '';
    var entries = Array.isArray(routingEntries) ? routingEntries : [];
    if (entries.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'routing-audit-empty';
      empty.setAttribute('data-testid', 'routing-audit-empty');
      empty.textContent = 'No routing decisions yet';
      body.appendChild(empty);
      return;
    }
    for (var i = 0; i < entries.length; i++) {
      body.appendChild(_buildRow(entries[i]));
    }
  }

  // Wire the Refresh button. chat.js calls this once per session-join so the
  // closure captures the right session id. Repeated calls overwrite the prior
  // handler (Refresh is idempotent — last-binding-wins).
  function wireRefresh(container, sessionId) {
    if (!container) return;
    var btn = container.querySelector('[data-testid="routing-audit-refresh"]');
    if (!btn) return;
    // Replace the node to drop any prior click listener (idempotent wire).
    var clone = btn.cloneNode(true);
    btn.parentNode.replaceChild(clone, btn);
    clone.addEventListener('click', function () {
      refresh(container, sessionId);
    });
  }

  function refresh(container, sessionId, onComplete) {
    if (!container || !sessionId) return;
    var btn = container.querySelector('[data-testid="routing-audit-refresh"]');
    if (btn) btn.disabled = true;
    fetch('/api/chat/sessions/' + encodeURIComponent(sessionId))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (payload) {
        var routing = payload && payload.session_metadata && payload.session_metadata.routing;
        render(container, routing || []);
      })
      .catch(function () { /* keep prior body; AC-7 empty-state still applies on a re-render */ })
      .then(function () {
        if (btn) btn.disabled = false;
        if (typeof onComplete === 'function') onComplete();
      });
  }

  // ─── private helpers ───────────────────────────────────────────────────

  function _buildRow(entry) {
    var disposition = String(entry.disposition || 'unknown');
    var row = document.createElement('details');
    row.className = 'routing-audit-row';
    row.setAttribute('data-testid', 'routing-audit-row');
    row.setAttribute('data-disposition', disposition);
    var summary = document.createElement('summary');
    summary.className = 'routing-audit-row-summary';
    summary.setAttribute('data-testid', 'routing-audit-row-summary');

    // Timestamp.
    var time = document.createElement('time');
    time.className = 'routing-audit-ts';
    time.setAttribute('datetime', String(entry.ts || ''));
    time.textContent = String(entry.ts || '');
    summary.appendChild(time);

    // Agent.
    var agent = document.createElement('span');
    agent.className = 'routing-audit-agent';
    agent.textContent = entry.agent ? String(entry.agent) : '—';
    summary.appendChild(agent);

    // Scope.
    var scope = document.createElement('span');
    scope.className = 'routing-audit-scope';
    scope.textContent = String(entry.scope || '');
    summary.appendChild(scope);

    // Reason (truncated).
    var reason = String(entry.reason == null ? '' : entry.reason);
    var reasonSpan = document.createElement('span');
    reasonSpan.className = 'routing-audit-reason';
    reasonSpan.textContent = reason.length > 120 ? reason.slice(0, 120) + '…' : reason;
    summary.appendChild(reasonSpan);

    // Badge — class composes per-disposition.
    var badge = document.createElement('span');
    badge.className = 'routing-audit-badge routing-audit-badge--' + disposition;
    badge.setAttribute('data-testid', 'routing-audit-badge');
    badge.textContent = disposition;
    summary.appendChild(badge);

    row.appendChild(summary);

    // Expansion body — raw fields in EXPANSION_KEY_ORDER.
    var expansion = document.createElement('dl');
    expansion.className = 'routing-audit-expansion';
    expansion.setAttribute('data-testid', 'routing-audit-expansion');
    var seen = {};
    EXPANSION_KEY_ORDER.forEach(function (k) {
      if (!(k in entry)) return;
      seen[k] = true;
      _appendKeyValue(expansion, k, entry[k]);
    });
    // Catch-all for any future keys not in EXPANSION_KEY_ORDER.
    Object.keys(entry).forEach(function (k) {
      if (seen[k]) return;
      _appendKeyValue(expansion, k, entry[k]);
    });
    row.appendChild(expansion);
    return row;
  }

  function _appendKeyValue(dl, key, value) {
    var dt = document.createElement('dt');
    dt.textContent = key;
    dl.appendChild(dt);
    var dd = document.createElement('dd');
    if (key === 'policy' && value && typeof value === 'object') {
      // Nested rendering for the policy dict.
      var policyDl = document.createElement('dl');
      policyDl.className = 'routing-audit-policy';
      policyDl.setAttribute('data-testid', 'routing-audit-policy');
      var seenPolicy = {};
      POLICY_KEY_ORDER.forEach(function (k) {
        if (!(k in value)) return;
        seenPolicy[k] = true;
        _appendKeyValue(policyDl, k, value[k]);
      });
      Object.keys(value).forEach(function (k) {
        if (seenPolicy[k]) return;
        _appendKeyValue(policyDl, k, value[k]);
      });
      dd.appendChild(policyDl);
    } else if (value && typeof value === 'object') {
      // Default object/array rendering — JSON.
      dd.textContent = JSON.stringify(value);
    } else {
      dd.textContent = value == null ? '—' : String(value);
    }
    dl.appendChild(dd);
  }

  // Public exports.
  window.App.chat.routingAuditPanel.create = create;
  window.App.chat.routingAuditPanel.render = render;
  window.App.chat.routingAuditPanel.wireRefresh = wireRefresh;
  window.App.chat.routingAuditPanel.refresh = refresh;
})();
```

**Estimated size**: ≈170 lines. The module is self-contained — only depends on `App.escapeHtml` / `App.escapeAttr` as soft globals (the `if (App && App.escapeHtml)` guards work standalone for unit tests if any are added later).

### 6. Frontend — chat.js wiring

Add the panel module to the load order. Check whether `the_one/interfaces/web/templates/index.html` (or whichever template enumerates `static/js/areas/chat/*.js`) loads each `areas/chat/*.js` file individually OR via a glob/manifest. If individual: add a `<script src="/static/js/areas/chat/routing-audit-panel.js"></script>` line alongside the other `chat/*.js` files. If glob/manifest: the new file is picked up automatically.

In `chat.js`:

**6a.** Add a panel container variable to the closure (sibling to `messagesEl`):

```javascript
var routingAuditPanelEl;
```

**6b.** In the chrome-construction block (around `chat.js:67-86`), after the `.messages` + `.input-area` initial assignment AT `chat.js:88-95`, insert the panel BETWEEN `.messages` and `.input-area` using `insertBefore`:

```javascript
    // M11 F13 L5: Routing audit panel — collapsible inspector for
    // session_metadata["routing"] entries. Mounts between .messages and
    // .input-area so it shares the chat-chrome flexbox column without
    // overlapping the message list scroll region.
    routingAuditPanelEl = App.chat.routingAuditPanel.create();
    chromeEl.insertBefore(routingAuditPanelEl, chromeEl.querySelector('.input-area'));
```

(Place this AFTER the existing telemetry-overlay `insertBefore` at `:98` so the call order is: telemetry first, then routing-audit-panel — both end up before the input area.)

**6c.** In the `session_joined` handler (around `chat.js:846-913`), AFTER `renderHistory(data.history, data.agent_name)` at `:859`, populate + wire-refresh the panel:

```javascript
          // M11 F13 L5: render the routing audit panel from the join payload's
          // session_metadata and wire the Refresh button to re-fetch via REST.
          var routing = (data.session_metadata && data.session_metadata.routing) || [];
          App.chat.routingAuditPanel.render(routingAuditPanelEl, routing);
          App.chat.routingAuditPanel.wireRefresh(routingAuditPanelEl, data.session_id);
```

**6d.** In the `session_deleted` handler (around `chat.js:915-928`), when the current session is cleared, also clear the panel:

```javascript
          App.chat.routingAuditPanel.render(routingAuditPanelEl, []);
```

(Inserts the empty-state message so a deleted session leaves a coherent panel display.)

### 7. CSS — new `.routing-audit-panel` block in chat.css

Append a new block to `the_one/interfaces/web/static/css/chat.css` inside the existing `@layer areas` block, sibling to the `.trace-shell` block. Suggested location: AFTER the `.trace-shell` rules (around `chat.css:200`), BEFORE the `/* === Chat Area: Messages === */` section. Suggested content:

```css
  /* M11 F13 L5: Routing audit panel — per-session inspector for
     session_metadata["routing"]. Native <details>/<summary> for
     keyboard support. Sits between .messages and .input-area inside
     .chat-chrome. */
  .area-chat .routing-audit-panel {
    border-top: 1px solid var(--border);
    background: var(--surface);
    font-size: var(--font-size-body-sm);
    max-height: 280px;
    overflow-y: auto;
  }
  .area-chat .routing-audit-panel details > summary.routing-audit-toggle {
    cursor: pointer;
    color: var(--fg-muted);
    font-family: var(--font-family-mono);
    letter-spacing: 0.02em;
    padding: 8px 16px;
    user-select: none;
    list-style: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .area-chat .routing-audit-panel details > summary.routing-audit-toggle::-webkit-details-marker { display: none; }
  .area-chat .routing-audit-panel details > summary.routing-audit-toggle::before {
    content: '▸';
    transition: transform 0.15s ease;
    color: var(--accent);
    font-size: 0.85em;
  }
  .area-chat .routing-audit-panel details[open] > summary.routing-audit-toggle::before {
    transform: rotate(90deg);
  }
  .area-chat .routing-audit-panel details > summary.routing-audit-toggle:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 2px;
  }
  .area-chat .routing-audit-header {
    padding: 0 16px 8px 16px;
    display: flex;
    justify-content: flex-end;
  }
  .area-chat .routing-audit-refresh:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .area-chat .routing-audit-body {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 0 16px 12px 16px;
  }
  .area-chat .routing-audit-empty {
    color: var(--fg-muted);
    font-style: italic;
    padding: 12px 0;
  }
  .area-chat .routing-audit-row {
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 6px 10px;
  }
  .area-chat .routing-audit-row-summary {
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 12px;
    list-style: none;
  }
  .area-chat .routing-audit-row-summary::-webkit-details-marker { display: none; }
  .area-chat .routing-audit-ts {
    color: var(--fg-tertiary);
    font-family: var(--font-family-mono);
    font-variant-numeric: tabular-nums;
  }
  .area-chat .routing-audit-agent { color: var(--fg); }
  .area-chat .routing-audit-scope {
    color: var(--fg-muted);
    font-family: var(--font-family-mono);
    text-transform: uppercase;
    font-size: var(--font-size-tiny);
    letter-spacing: 0.05em;
  }
  .area-chat .routing-audit-reason {
    color: var(--fg-muted);
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .area-chat .routing-audit-badge {
    padding: 2px 8px;
    border-radius: 999px;
    font-family: var(--font-family-mono);
    font-size: var(--font-size-tiny);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--fg-on-accent);
  }
  .area-chat .routing-audit-badge--stepped {
    background: var(--status-success);
  }
  .area-chat .routing-audit-badge--command-intercepted {
    background: var(--accent);
  }
  .area-chat .routing-audit-badge--no-eligible {
    background: var(--status-warning);
  }
  .area-chat .routing-audit-badge--policy-silent {
    background: var(--fg-muted);
  }
  .area-chat .routing-audit-expansion {
    margin: 8px 0 0 0;
    padding: 8px 12px;
    background: var(--surface-translucent);
    border-radius: 4px;
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 4px 12px;
    font-family: var(--font-family-mono);
    font-size: var(--font-size-tiny);
  }
  .area-chat .routing-audit-expansion dt {
    color: var(--fg-muted);
  }
  .area-chat .routing-audit-expansion dd {
    margin: 0;
    color: var(--fg);
    overflow-wrap: anywhere;
  }
  .area-chat .routing-audit-policy {
    margin: 0;
    padding-left: 12px;
    border-left: 2px solid var(--border);
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 4px 12px;
  }
```

**Notes on token usage**:

- Every CSS color references an existing token. No new tokens are added. The 4 disposition tokens (`--status-success`, `--accent`, `--status-warning`, `--fg-muted`) all exist in `tokens.css` and are already pinned by `tests/test_design_tokens_a11y.py` for WCAG contrast.
- `--fg-on-accent` is used as the badge text color — already established as the on-accent text color in the existing button rules.
- `--surface-translucent` + `--border` + `--surface` + `--fg-tertiary` are all existing tokens (verified — used throughout `chat.css`).
- If any token is missing at recon (token names drift), use the closest existing analog and note the substitution in the flight log.

### 8. Backend tests — add 2 to `TestChatSessionAPI`

In `tests/test_db_api.py`, append the two new tests to the `TestChatSessionAPI` class (after `test_list_by_agent` at line ~2609):

```python
    async def test_get_session_includes_session_metadata(self, client: AsyncClient) -> None:
        """The detail endpoint composition exposes session_metadata; the
        shared _session_summary helper continues NOT to leak it (covered
        by the sibling list test). M11 F13 L5."""
        await client.post("/api/agents", json={"name": "agent-meta"})
        resp = await client.post(
            "/api/chat/sessions",
            json={"agent_name": "agent-meta", "title": "Meta Test"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Newly-created session has no session_metadata yet → detail returns null.
        resp = await client.get(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "session_metadata" in body, (
            "detail-endpoint composition must surface the key even when value is null"
        )
        assert body["session_metadata"] is None

        # Seed a routing entry directly via PUT (the API accepts the full session shape).
        # The simplest path that exercises the read-back is to construct a valid
        # session_metadata dict and PUT it; the codec round-trips JSON.
        put_payload = {
            "session_metadata": {
                "routing": [
                    {
                        "ts": "2026-05-31T00:00:00",
                        "agent": "agent-meta",
                        "rule_index": 0,
                        "scope": "channel",
                        "match": None,
                        "reason": "test seed",
                        "disposition": "stepped",
                    }
                ],
            }
        }
        resp = await client.put(f"/api/chat/sessions/{session_id}", json=put_payload)
        assert resp.status_code == 200

        resp = await client.get(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_metadata"] is not None
        assert "routing" in body["session_metadata"]
        assert len(body["session_metadata"]["routing"]) == 1
        assert body["session_metadata"]["routing"][0]["disposition"] == "stepped"

    async def test_list_sessions_excludes_session_metadata(self, client: AsyncClient) -> None:
        """The list endpoint's shared _session_summary helper does NOT
        leak session_metadata — preserves the architect cycle-1 correction
        (composition-only-on-detail). M11 F13 L5."""
        await client.post("/api/agents", json={"name": "agent-list-meta"})
        resp = await client.post(
            "/api/chat/sessions",
            json={"agent_name": "agent-list-meta", "title": "List-Meta Test"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Seed a session_metadata via PUT so any leaky helper would surface it.
        put_payload = {
            "session_metadata": {
                "routing": [
                    {
                        "ts": "2026-05-31T00:00:00",
                        "agent": "agent-list-meta",
                        "rule_index": 0,
                        "scope": "channel",
                        "match": None,
                        "reason": "list seed",
                        "disposition": "stepped",
                    }
                ],
            }
        }
        resp = await client.put(f"/api/chat/sessions/{session_id}", json=put_payload)
        assert resp.status_code == 200

        resp = await client.get("/api/chat/sessions")
        assert resp.status_code == 200
        items = resp.json()
        assert any(item["id"] == session_id for item in items), "seeded session missing from list"
        for item in items:
            assert "session_metadata" not in item, (
                f"list endpoint must not expose session_metadata; got {sorted(item.keys())}"
            )
```

**Note on the PUT-vs-repository-write approach**: the cleanest test path is the PUT — it exercises the full HTTP boundary the production code path uses. If the PUT path turns out NOT to accept `session_metadata` (e.g., a validator strips it), fall back to constructing a `ChatSession` model + writing through the repository inside the test. The fixture's `conn` at `tests/test_db_api.py:23` is reachable via `patch("the_one.interfaces.web.api.get_connection", return_value=conn)` already in place at `:34` — the test can `from the_one.db.repositories import ChatSessionRepository; await ChatSessionRepository(conn).append_to_session_metadata(...)` if the PUT path is too restrictive.

### 9. Browser tests — 6 new tests in `test_flow_chat_routing_audit_panel.py`

Create `tests/browser/test_flow_chat_routing_audit_panel.py`. Use `app_with_data_dir` (copy or import from `test_flow_chat_session_list_source_badge.py`) for direct-DB seeding of `session_metadata`. Suggested test shape:

```python
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
    seed_mock_provider(base_url)
    seed_mock_agent(base_url, name="empty-agent")
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
    seed_mock_provider(base_url)
    seed_mock_agent(base_url, name="multi-agent")
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
    seed_mock_provider(base_url)
    seed_mock_agent(base_url, name="exp-agent")
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
    seed_mock_provider(base_url)
    seed_mock_agent(base_url, name="policy-agent")
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
    seed_mock_provider(base_url)
    seed_mock_agent(base_url, name="refresh-agent")
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
    seed_mock_provider(base_url)
    seed_mock_agent(base_url, name="collapsed-agent")
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
```

**Notes**:
- The `seed_mock_agent` import path matches the helper enumeration at `tests/browser/seeders.py`. If the import resolution fails at recon, drop to using `seed_mock_provider` only and create the agent via the API directly.
- The `_navigate_to_session(page, base_url, sid)` helper uses the URL fragment routing pattern (`#chat/sessions/{sid}`) — verified consistent with `chat.js:13` (`if (sub.indexOf('sessions/') === 0)`). The hydrateState path joins the session via WS.
- The Refresh test exercises **AC-14 (server-side session_joined payload)** implicitly — the first `to_have_count(1)` assertion only passes if the seeded entry arrived in the join payload. If AC-14 is not yet in place, this test fails — the leg requires both surfaces.

### 10. Author the behavior-test spec

Write `tests/behavior/audit-log-inspector-renders-routing-entries.md` per the `.flightops/ARTIFACTS.md` "Behavior Test — Spec" format. The spec is authored as part of L5 design (created alongside this leg artifact). Status starts `draft`; operator promotes to `active` after first successful run at the Pre-L6 gate.

See the inline-authored spec file at `tests/behavior/audit-log-inspector-renders-routing-entries.md` (created as part of L5 design alongside this leg artifact).

### 11. Run order

1. Read api.py around 3175-3260 + chat.js around 67-100 / 341-345 / 846-913 + chat.css around 140-200 to confirm no post-design drift.
2. Locate the WS `session_joined` handler (Step 4 recon) — note the exact module/symbol in the flight log.
3. Apply edits in this order:
   a. Backend: api.py detail-endpoint composition (Step 3).
   b. Backend: WS payload extension (Step 4 — site located via grep at runtime).
   c. Frontend: new module `chat/routing-audit-panel.js` (Step 5).
   d. Frontend: chat.js wiring (Step 6).
   e. Frontend: chat.css panel block (Step 7).
   f. Frontend: register the new JS file in whichever template lists `static/js/areas/chat/*.js` (skip if glob-based).
4. Write `tests/test_db_api.py::TestChatSessionAPI` additions (Step 8).
5. Write `tests/browser/test_flow_chat_routing_audit_panel.py` (Step 9).
6. Write `tests/behavior/audit-log-inspector-renders-routing-entries.md` (Step 10 — already created during L5 design alongside this leg artifact; confirm it's present + committed).
7. Run verification gates per the Verification Steps section (Phase 1 → Phase 7).

## Edge Cases

- **Session with `session_metadata = None`** (newly created session, never received an inbound): the detail endpoint returns `null`; the panel renders the empty state. Covered by AC-7 + browser test #1.
- **Session with `session_metadata = {"audit": [...]}` but no `routing` key**: the panel reads `session_metadata.routing || []` → empty-state render. The `audit` key is ignored entirely (per Phase 5b DD: "Audit-Log Inspector Renders Only `routing`"). The detail endpoint exposes the full `session_metadata` (including `audit`), but the panel doesn't render it.
- **A routing entry with an unknown disposition** (forward-compat — a future flight introduces `disposition="pool-failure"` or similar): the row renders with the badge class `routing-audit-badge--<unknown-value>` — no CSS rule matches, the badge falls back to its default unstyled background. Acceptable for forward-compat; future leg adds a new CSS class.
- **Very long routing list (hundreds of entries)**: the `.routing-audit-panel` has `max-height: 280px; overflow-y: auto` in the CSS — the body scrolls vertically. No pagination in L5; per flight Adaptation Criteria ("L5's `session_metadata` size grows large enough that the session-detail endpoint hits perf concerns"), pagination is a future flight.
- **An entry's `reason` exceeds 120 chars**: the summary cell truncates with `…`; the full text is visible inside the expansion's `dl > dd` (which uses `overflow-wrap: anywhere`).
- **`/api/chat/sessions/{id}` 5xx during Refresh**: the `.catch(...)` in `refresh()` keeps the prior render in place; the Refresh button re-enables. Operator can click again. No toast surface in v1; failure is silent at the UI level (operator can check Network tab in devtools if debugging refresh failures).
- **The Refresh button is clicked while a refresh is in flight**: the button is `disabled` for the duration. The user can't double-fire. The `.then(...)` callback re-enables in both success + failure paths.
- **Operator switches sessions while a Refresh is in flight**: the Refresh closure captured the prior `sessionId` — the response writes the prior session's routing into the panel that now belongs to a different session. Mitigation: `wireRefresh` is called fresh on every `session_joined` and replaces the click handler (via the cloneNode pattern), so the in-flight fetch's callback is the only stale path. Acceptable — the operator can click Refresh once more on the new session to overwrite. NOT bundled into L5; F10 hardening or a future inspector flight can add a session-id guard at the response handler.
- **`session_metadata.routing` is something other than a list** (corruption, future shape change): `render(container, routingEntries)` guards via `Array.isArray(routingEntries) ? ... : []`. Non-list values collapse to empty-state. Defensive — mirrors `append_to_session_metadata`'s defensive normalization at the repository layer.
- **Token retune in a future flight** (e.g., `--status-success` retunes for accessibility): the disposition badges adopt the new color automatically; `tests/test_design_tokens_a11y.py` continues to gate the contrast. L5 does NOT introduce per-badge contrast tests because the badges use tokens already pinned by that test.
- **CSS class collision with existing `.session-item-source--{platform}` classes**: the new classes are namespaced under `.routing-audit-*` and `.routing-audit-badge--*` — no overlap with `.session-item-source--*`. Confirmed by grep at design time.

## Files Affected

- `the_one/interfaces/web/api.py` — extends `get_chat_session`'s return dict literal to include `"session_metadata": session.session_metadata`. ~1-2 line change. The shared `_session_summary()` stays byte-identical (grep gate AC-15).
- `the_one/interfaces/web/app.py` — 4 edits per Step 4: (a) add `session_metadata: dict[str, Any] | None = None` field to `Session` dataclass at `:285-315`; (b) populate `session.session_metadata = db_session.session_metadata` in `_restore_session` at `:500-617` (both branches); (c) add `"session_metadata": session.session_metadata` to `_build_session_joined_ok` return dict at `:678-696`; (d) add `"session_metadata": db.session_metadata` to `_build_session_joined_degraded` return dict at `:699-722`. Total ~6-8 line change.
- `the_one/interfaces/web/static/js/areas/chat.js` — adds `routingAuditPanelEl` closure var + `App.chat.routingAuditPanel.create()` mount in chrome construction + `render` / `wireRefresh` call in `session_joined` handler + `render([])` call in `session_deleted` handler. ~10-15 lines added across 3 sites.
- `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js` — NEW; ≈170 lines per Step 5.
- `the_one/interfaces/web/static/css/chat.css` — NEW `.routing-audit-panel` block + 4 disposition-badge classes per Step 7. ~100 lines appended.
- `the_one/interfaces/web/templates/<index template>` — IF the template enumerates each `chat/*.js` file individually, add the new file's `<script>` tag. Skip if the template uses a glob/manifest. Recon at edit time.
- `tests/test_db_api.py` — appends 2 new tests to `TestChatSessionAPI`. ~60 lines added.
- `tests/browser/test_flow_chat_routing_audit_panel.py` — NEW; ≈300 lines per Step 9.
- `tests/behavior/audit-log-inspector-renders-routing-entries.md` — NEW; Witnessed spec per Step 10.

No `.gitignore` edits needed (`tests/behavior/*/runs/*/` already excluded per L4 recon).

No `tests/behavior/.gitkeep` needed (directory already populated with 3 prior specs).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (AC-1 through AC-20)
- [x] Verification Steps Phase 1-7 all green
- [x] `tests/behavior/audit-log-inspector-renders-routing-entries.md` exists, status `draft`, committed
- [x] Update flight-log.md with L5 progress entry under "Leg Progress", including post-L5 totals + the WS `session_joined` payload site that was extended (Step 4) + the behavior-test spec authoring note
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off L5 in flight.md (the `[ ] audit-log-inspector-backend-and-chat-ui-panel` entry → `[x]`)
- [x] Phase 2d batch: this is the final autonomous leg before code review + commit per `/agentic-workflow` protocol — DO NOT commit at L5 land; signal `[HANDOFF:review-needed]` and let the Flight Director run the batched Reviewer pass over L1+L2+L3+L4+L5 before commit
- [x] L6 (operator-driven HAT) follows after the pre-L6 behavior-test gate

---

## Citation Audit

17 citations verified against current code at leg design time:

| # | Citation | Status | Notes |
|---|----------|--------|-------|
| 1 | `the_one/interfaces/web/api.py:3188-3198 (get_chat_session)` | OK | Detail endpoint at the expected line range; `await repo.get(session_id)` at `:3192`; return dict at `:3195-3198`. The `**_session_summary(session)` spread already in place; `session_metadata` is the new key to add. |
| 2 | `the_one/interfaces/web/api.py:3246-3253 (_session_summary)` | OK | Helper at expected lines; body has 5 string keys (`id`, `agent_name`, `title`, `created_at`, `updated_at`); zero references to `session_metadata`. Shared by 5 callers (`list_chat_sessions:3185`, `get_chat_session:3196`, `create_chat_session:3209`, `update_chat_session:3223`, def itself). |
| 3 | `the_one/db/models.py:716 (class ChatSession)` | OK | Class exists; `session_metadata: dict[str, Any] \| None = None` at `:749` (verified via grep). |
| 4 | `the_one/interfaces/web/app.py:285-315, :500-617, :678-696, :699-722` (Session + _restore_session + _build_session_joined_{ok,degraded}) | OK | Verified at design time by Flight Director pre-confirm. `_build_session_joined_ok` at `:678-696`; `_build_session_joined_degraded` at `:699-722`; `Session` dataclass at `:285-315` (no `session_metadata` field — needs adding). NO `realtime.py` module exists; the prior recon-defer is removed. |
| 5 | `the_one/connectors/_inbound.py:530-538 (audit_entry construction)` | OK | The dict literal at expected lines; 6 keys + comment about `disposition` set below per branch. |
| 6 | `the_one/connectors/_inbound.py:547-805 (six routing append sites)` | OK | Verified — six `await chat_repo.append_to_session_metadata(... "routing", audit_entry)` calls at the expected line spans (`:549`, `:605`, `:620`, `:689`, `:717`, `:779`, `:801` — actually 7 total once you count the stepped append at `:801`; the "six" in the flight spec rounds the no-eligible branches into a single conceptual write). The dispatcher's terminal disposition assignments at `:548`, `:604`, `:619`, `:687-688`, `:715-716`, `:777-778`, `:800` confirm the per-disposition shape. |
| 7 | `the_one/connectors/_inbound.py:_policy_gate_decision (168-276)` | OK | Function exists at expected lines; returns 5 distinct policy-audit shapes (dm / override / mention / always-listen-off / inference-yes-or-no). Policy-silent path only fires for always-listen-off + inference-no. |
| 8 | `the_one/interfaces/web/static/js/areas/chat.js:67-86 (chromeEl construction)` | OK | `chat-chrome` wrapper assembled via `content.innerHTML = ...`; `.header` + `.messages` + `.input-area` order verified; `chromeEl = content.querySelector('.chat-chrome')` at `:88`; `messagesEl = content.querySelector('.messages')` at `:92`. |
| 9 | `the_one/interfaces/web/static/js/areas/chat.js:98` (telemetry-overlay insertBefore) | OK | `chromeEl.insertBefore(App.chat.renderTelemetry(), chromeEl.querySelector('.input-area'));` — the mount pattern the L5 panel mirrors. |
| 10 | `the_one/interfaces/web/static/js/areas/chat.js:341-345 (joinSession)` | OK | Function definition at expected lines; sends `{action: 'join', session_id: id}` over WS. |
| 11 | `the_one/interfaces/web/static/js/areas/chat.js:846-913 (session_joined handler)` | OK | WS event handler; `renderHistory(data.history, data.agent_name)` at `:859`; `data.session_id` consumed at `:850`; the L5 panel populate hook latches in immediately after `renderHistory`. |
| 12 | `the_one/interfaces/web/static/js/areas/chat/trace-shell.js:21-50 (renderTrace)` | OK | Module exists; same shape the new `routing-audit-panel.js` mirrors; uses `<details>` + `<summary>` + `data-testid`. |
| 13 | `the_one/interfaces/web/static/css/chat.css:143-200 (.trace-shell block)` | OK | The pattern block; `<details>`/`<summary>` styling vocabulary; `--accent` + `--border` + `--fg-muted` token usage; `::-webkit-details-marker { display: none }` to hide native arrow. |
| 14 | `the_one/interfaces/web/static/css/tokens.css:136-149 (status tokens)` | OK | `--status-success`, `--status-warning`, `--status-danger` (not used by L5), plus glow variants. `--accent` at `:76`; `--fg-muted` at `:61`. All four L5 badge tokens present. |
| 15 | `the_one/interfaces/web/static/js/app.js:210-220 + :280-281 (escapeHtml / escapeAttr)` | OK | Functions defined + exported via `App` namespace at expected lines. |
| 16 | `tests/test_db_api.py:2569-2609 (TestChatSessionAPI)` | OK | Class at `:2569`; existing 2 tests `test_crud` + `test_list_by_agent`; fixture `client` at `:18-44`. L5's 2 new tests append after `test_list_by_agent`. |
| 17 | `tests/browser/test_flow_chat_session_list_source_badge.py:70-181 (app_with_data_dir + _seed_session)` | OK | Fixture at `:70-131`; `_seed_session` helper at `:134-181` — both match the pattern L5's new browser test file copies/imports. |

**Drift notes**: cycle-1 review surfaced that the leg artifact originally mis-cited the WS payload site as `realtime.py:_session_joined_payload`. Flight Director pre-confirmed the actual sites (`app.py:678-696` + `:699-722`) and applied 4 fixes: (a) Context section now names `app.py` and the `Session` dataclass extension; (b) Files Modified enumerates all 4 `app.py` surfaces; (c) AC-14 enumerates both builders + the `git grep -nE '"session_metadata"' app.py ≥ 2 hits` verification; (d) Step 4 rewritten with verbatim Session-dataclass extension + `_restore_session` hook + both-builders return-dict edits. Citation #4 reclassified `UNVERIFIED → OK`. All 17 citations verified clean.

**Audit summary**: all 17 citations verified clean against current code at leg design time (post-cycle-1 fix). The flight spec's mention of `_inbound.py:549-806` as the routing write sites is verified verbatim (the actual range is `:549` through `:801` for the seven write sites; the spec's `:806` was a rounded upper bound).
