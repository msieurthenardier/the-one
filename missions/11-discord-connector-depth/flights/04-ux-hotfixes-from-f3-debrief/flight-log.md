# Flight Log: UX Hotfixes from F3 Debrief

**Flight**: [UX Hotfixes from F3 Debrief](flight.md)

## Summary

In-flight. Reconnaissance complete (F3 debrief's 3 hotfix items + 4 methodology codifications + criterion-coverage map seed all verified against current code). Design decisions documented in `flight.md`. /agentic-workflow orchestration started 2026-05-23.

---

## Reconnaissance Report

Walk of every F3-debrief-cited source item against current code state (2026-05-23, post-F3 ship at commits e53f9e1 + 4cc562f + 75639d4 + edf4383). Per the F3-debrief-recommended `cross-flight-ux-debt-reconciliation` discipline.

| # | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | A1 — Test Connection does NOT warm pool | confirmed-live | `api.py:2573-2638` `test_connector_connection` calls `plugin.doctor()` at L2621; zero `account_acquire` references in the function | F4 L2 — bundle with C1 |
| R2 | A2 — checkbox-mode renders raw IDs | confirmed-live | `connectors-tab.js:507` `nameSpan.textContent = item;` where `item` is raw snowflake; no label-cache lookup | F4 L3 — fetch L4 API; resolve labels |
| R3 | C1 — `test_edit_session_continuation_round_trip` text drift | confirmed-live | `tests/browser/test_flow_studio_connector_account_editor.py:417` asserts `"Distinct from the pool idle timeout"`; source at `connector-account-editor.js:368` says `"Inbound continues the same chat session within this window."` | F4 L2 — one-line test update; bundle with A1 |
| R4 | `pool-warming-entrypoints-are-finite-and-named` convention | confirmed-live | Not in `agents.md` (grep returns zero hits) | F4 L1 codification |
| R5 | `frozen-snapshot-for-cross-lock-read` convention | confirmed-live | Not in `agents.md` | F4 L1 codification |
| R6 | `slot-getter-bridge-for-dropdown-collect-path` convention | confirmed-live | Not in `agents.md` | F4 L1 codification |
| R7 | `two-concurrent-callers-reasoning` architect-checklist extension | confirmed-live | Not in `agents.md` | F4 L1 codification (separate subsection or text in L1 leg artifact) |
| R8 | `cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` (mission-control side) | partially-satisfied | F4 itself USES these disciplines (this recon table is `cross-flight-ux-debt-reconciliation`-shaped); project-side `agents.md` note codifies for the project; mission-control's `/flight` and `/leg` skill prompts remain un-touched per "no mission-control changes" stance from F3 | F4 L1 — project-side note only |
| R9 | M11 criterion-coverage living artifact (M10 debrief recommendation #5) | confirmed-live | `missions/11-discord-connector-depth/criterion-coverage.md` does not exist | F4 L1 — seed |
| R10 | `account_acquire` callable from `api.py` | confirmed-live | `the_one/connectors/_pool.py:830` exports `async def account_acquire(account_id: str) -> ConnectorClient`; existing `api.py` callsites import via function-local-import convention | A1's integration target |
| R11 | L4 GET endpoint `/api/connector-accounts/{id}/discoverable-entities` callable from `connectors-tab.js` fetch | confirmed-live | F3 L4 shipped + F3 L7 HAT verified the endpoint live | A2's integration target |

**Operator-confirmed live items folded into F4**: R1 (L2), R2 (L3), R3 (L2 bundle), R4-R7 (L1), R8 (L1 project-side note), R9 (L1 seed), R10 (A1 integration), R11 (A2 integration).

**Items DEFERRED out of F4 scope per operator selection**:
- F3 L7 step 8 (stale-entry indicator HAT verification) — operator-side Discord action required; deferred to F9 (Live-traffic HAT script).
- F3 debrief Routine-maintenance candidates (C3 AIAT cluster; C5a/b chronic UI tests; unify `_xxxValues` getter pattern; lift axis vocabulary constant; remove `_RegistryEntry.account_type=""` default; L4 `prior_cache` force-interleaving test) — slot for `/routine-maintenance` between F4 and F5 OR fold into F5+ as touched-surface debt.
- Mission-control skill prompt changes (`cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` skill updates; `two-concurrent-callers-reasoning` extension to `/leg`) — out of project scope; project-side notes in `agents.md` are the binding fallback.

**Phase 4 crew interview outcomes** (2026-05-23):
- Codifications first per L1-style; mirrors F3 L1 precedent.
- A1: `account_acquire` placement AFTER `plugin.doctor()` succeeds (not before; not in parallel). Adds `details.pool_warmed` field to response envelope.
- A2: per-tile fetch (not shared cache). Per-tile cost is one L4 cache hit; acceptable.
- C1: update test-side (not source-side) per L2 `match-tests-to-code-when-code-is-operator-friendly` precedent.
- L4 HAT scope: A1 + A2 only; stale-entry deferred to F9.
- Criterion-coverage map: seed with M11 19 criteria + initial status; format = plain markdown table; future flights maintain incrementally.

---

## Leg Progress

### L1 — codify-f3-debrief-conventions-and-criterion-coverage

**Status**: completed

**Changes made**:
- Inserted six new entries in `the_one/agents.md` `### Project-wide` subsection, between `### \`flight-spec-dom-order-audit\`` and `### Mission-specific (M10)`, in the F4-design-locked order: `pool-warming-entrypoints-are-finite-and-named` → `frozen-snapshot-for-cross-lock-read` → `slot-getter-bridge-for-dropdown-collect-path` → `two-concurrent-callers-reasoning` → `cross-flight-ux-debt-reconciliation` → `touched-surface-ux-debt-folding`. First four are project-wide conventions; last two are project-side fallbacks whose primary codification destination is mission-control's `/flight` skill prompt.
- Created `missions/11-discord-connector-depth/criterion-coverage.md` (33 lines): title + purpose + status vocabulary (`closed-by-Fn` / `partially-closed-by-Fn` / `structurally-complete-pending-HAT` / `open`) + maintenance contract paragraph + 19-row table (one row per M11 mission criterion in `mission.md` source order). Seed state captured as-of 2026-05-23: row 1 `closed-by-F1`; row 14 `closed-by-F2`; row 16 `closed-by-F2`; rows 3 + 4 `partially-closed-by-F3` (stale-entry indicator deferred to F9); all other rows `open`. F4 does NOT prefill its own contributions — those land at F4 debrief gate per the maintenance contract.

**Verification**:
- `grep -nE "^### \`(pool-warming|frozen-snapshot|slot-getter|two-concurrent|cross-flight-ux-debt|touched-surface-ux-debt)" the_one/agents.md` returns exactly six hits in expected order.
- `wc -l missions/11-discord-connector-depth/criterion-coverage.md` returns 33 (>= 30 threshold).
- `grep -c "^| [0-9]" missions/11-discord-connector-depth/criterion-coverage.md` returns 19.
- `git diff --stat` shows changes only in `the_one/agents.md`, the new `criterion-coverage.md`, and F4 sibling artifacts (`flight.md`, `flight-log.md`, this leg). No source files (`*.py`, `*.js`, `*.ts`, `*.tsx`, `*.json`, `*.sql`) touched.

**Notes**:
- Doc-only leg; pytest not required and not run.
- L1 lands codifications BEFORE source-touching L2-L4 per the F3 L1 precedent so subsequent legs can invoke the four new conventions by name.
- `stub-fixture-extension-via-plugin-connect` (F3 debrief §14) deliberately deferred — n=2 from F3 alone awaits a third citation per methodology-promotion threshold; deferral already recorded in Session Notes.

### L2 — test-connection-warms-pool-and-fix-session-continuation-test

**Status**: completed

**Changes made**:
- `the_one/interfaces/web/api.py:test_connector_connection`: added function-local import `from the_one.connectors._pool import account_acquire` (colocated with existing function-local imports). After the existing `plugin.doctor(...)` try/except (which remains byte-identical), inserted a new warmup block gated on `report.status == "ok"`. The block shallow-copies `report.details` (so the plugin's-owned dict is not mutated cross-call), calls `await account_acquire(account_id)` inside a `try / except Exception as exc:` (NOT `BaseException` — `CancelledError`/`SystemExit`/`KeyboardInterrupt` propagate per cooperative-cancellation discipline; `# noqa: BLE001` with one-line WHY comment), and records `pool_warmed` + `pool_warm_error` into the copied dict. The final return uses the copied `details` dict. On non-ok doctor verdict, the warmup is SKIPPED entirely — `pool_warmed=False`, `pool_warm_error=None` (uniform schema). On warmup failure, the doctor's `status='ok'` verdict is preserved (partial-success isolation contract per `two-concurrent-callers-reasoning`).
- `tests/test_db_api.py:TestConnectorAccountDoctor`: added three new tests after `test_doctor_probe_records_the_call`, before `class TestConnectorAccountPairingCodeAndAttached` — `test_doctor_probe_success_warms_pool` (asserts `(_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool` post-call via the existing test idiom), `test_doctor_probe_failed_skips_warmup` (asserts `pool_mod._pool == {}`), `test_doctor_probe_ok_warmup_failure_does_not_escalate` (monkeypatches `pool_mod.account_acquire` only — handler's function-local import resolves at call time, so source-module patch is in effect). Updated three existing tests in the same class to extend their asserted envelopes with `pool_warmed` + `pool_warm_error`: `test_doctor_probe_success` (`True` / `None`), `test_doctor_probe_configured_failure` (`False` / `None`), `test_doctor_probe_degraded_status` (`False` / `None`).
- `tests/browser/test_flow_studio_connector_account_editor.py:417`: assertion text updated from `"Distinct from the pool idle timeout"` to `"Inbound continues the same chat session within this window."` (full-stop included; matches `connector-account-editor.js:368`). Surrounding comment at line 414 updated to `# Helper text under the continuation input describes the session-continuation behavior.` to match the new assertion intent (C1 closure per `match-tests-to-code-when-code-is-operator-friendly`).
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md`: inserted one annotation line under the Status block (separate paragraph, blank-line separated from both Mission line and `## Contributing to Criteria`): `**Subsequent corrections**: L4's Test-Connection-warms-pool assumption corrected at F4 L2; see <leg path> (and F4 flight-debrief once landed).`. L4 body text at original line 55 NOT modified — verified via `git diff` showing only the header insertion.

**Verification**:
- `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountDoctor -x --timeout 30 -v` — 10 passed (7 existing + 3 new).
- `docker exec the-one pytest -m browser tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip -x --timeout 60` — 1 passed (C1 closure).
- `docker exec the-one pytest -m browser tests/browser/test_connector_test_connection_button.py -x --timeout 60` — 7 passed (page.route() mocks unaffected by new envelope shape; UI ignores the new fields at present).
- Broader sweep: `docker exec the-one pytest tests/test_db_api.py -x --timeout 60` — 66 passed; `docker exec the-one pytest -m browser tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py -x --timeout 60` — 25 passed.
- Grep checks: `grep -n "account_acquire" the_one/interfaces/web/api.py` returns the function-local import + call inside `test_connector_connection`; `grep -n "pool_warmed" the_one/interfaces/web/api.py` returns 3 hits in the handler; `grep -rn "Distinct from the pool idle timeout" tests/` returns zero hits; `grep -n "Inbound continues the same chat session within this window" tests/browser/test_flow_studio_connector_account_editor.py` returns one hit at line 417; `git diff` of F3 flight.md shows only the annotation insertion (no diff hunks elsewhere).

**Notes**:
- Browser marker filter is required to run browser tests (`pyproject.toml` `addopts` defaults to `-m 'not browser'`). Used `pytest -m browser` for the browser-test runs.
- The `noqa: BLE001` marker matches existing project convention (one prior site at `the_one/connectors/README.md:186`).
- No source files beyond `the_one/interfaces/web/api.py` were touched. JS source at `connector-account-editor.js:368` not modified (C1 chose test-side fix). Test files modified: `tests/test_db_api.py` (six tests touched: three new + three existing extended) and `tests/browser/test_flow_studio_connector_account_editor.py` (one line + one comment).

### L3 — per-agent-overlay-checkbox-label-resolver

**Status**: completed

**Changes made**:
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:_renderAccountTile`: inserted four closure-scoped helpers between the `var scopeChannels` declaration and the `var tile = document.createElement('div');` line. Helpers: `var _labelCache = null;` (populated with `{id → label}` map on first successful fetch, or `{}` on any failure mode), `var _labelCachePromise = null;` (single-flight gate), `function _ensureLabelCache()` (lazy fetch of `GET /api/connector-accounts/{id}/discoverable-entities`; on 200, flattens `body.entities.{peers,channels,groups,roles}` into a flat map skipping entries missing either `id` or `label`; on non-OK / network error, sets `_labelCache = {}` and logs to `console.error`), and `function _applyLabelsToCheckboxes(bodyEl)` (walks `.connector-acl-checkboxlist-row` children and updates each `.mcp-tool-toggle-name` span's `textContent` iff `_labelCache[cb.value]` is truthy; otherwise no-op preserves the raw-id render).
- `_buildAxisRow`'s `expandBtn` click handler: added ONE new clause AFTER the existing visibility-toggle code (preserved byte-identical), gated on `nextExpanded && scopeList && scopeList.length > 0` (checkbox-mode + opening, not collapsing), calling `_ensureLabelCache().then(function () { _applyLabelsToCheckboxes(body); });`. The single-flight promise means N axes on the same tile fire ONE GET; collapse-then-re-expand reuses the resolved cache.
- `_buildCheckboxList` function body and the chip-mode `else` branch in `_buildAxisRow` are byte-identical to before this leg — A2 mutates the rendered spans AFTER initial render, never at render time.
- Created `tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` (270 lines): module-level `_DISCOVERABLE_PAYLOAD` with channels axis populated for IDs `111` (`#general`) and `222` (`#random`); three route helpers (`_route_discoverable_ok`, `_route_discoverable_503`, `_route_discoverable_network_error` using `route.abort('failed')`); precedent-verbatim helpers `_attach_agent_to_account` and `_open_agent_connectors_tab` mirroring `test_flow_studio_per_agent_overlay_dropdown.py`. Three tests: `test_per_agent_overlay_checkbox_mode_resolves_discord_labels` (Discord account + 200 OK → spans show `#general` and `#random`), `test_per_agent_overlay_checkbox_mode_stub_shows_raw_ids` (stub account + 503 → spans show raw IDs `raw-id-A` / `raw-id-B`), `test_per_agent_overlay_checkbox_mode_network_error_shows_raw_ids` (Discord account + abort → span shows raw ID `111`). All three carry the `@pytest.mark.browser` marker.

**Verification**:
- `grep -n "_labelCache\|_ensureLabelCache\|_applyLabelsToCheckboxes" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns 16 hits (well above the AC threshold of 8).
- `grep -n "/discoverable-entities" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns exactly 1 hit (inside `_ensureLabelCache`).
- `grep -n "nameSpan.textContent = item;" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` returns exactly 1 hit (preserved — initial render still uses raw-id; A2 mutates AFTER render).
- `grep -nE "^(async )?def test_" tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py` returns exactly 3 hits matching the three test names.
- `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py -m browser -x --timeout 60 -v` — 3 passed.
- Regression contract `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_connector_test_connection_button.py -m browser -x --timeout 60` — 9 passed.
- Broader sweep `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_account_editor.py -m browser -x --timeout 60` — 30 passed.

**Notes**:
- The stub-type account + `config={"allowlist": ...}` seed shape went through the server's POST endpoint cleanly (opaque dict storage); no swap to Discord-type needed.
- The single-flight promise design means the network-error test asserting `#general`-style fallback also implicitly proves the fetch fired exactly once — `route.abort` would observe an N-times-aborted handler if N parallel GETs fired.
- The `_applyLabelsToCheckboxes` walk is idempotent — re-running it after the cache resolves only mutates spans whose ids have a resolved label; spans missing from the cache keep their raw-id text. This preserves the F9-deferred stale-entry-indicator UX as a separate concern.
- Browser marker filter (`-m browser`) required per pyproject.toml addopts (default deselects browser tests).

---

## Decisions

Runtime decisions not in original plan.

*(empty — to be populated during execution)*

---

## Deviations

Departures from planned approach.

*(empty)*

---

## Anomalies

Unexpected issues encountered.

*(empty)*

---

## Flight Director Notes

### 2026-05-23 — Orchestration start

- /agentic-workflow invoked with `flight 4, mission 11, the-one`.
- Loaded `leg-execution.md` phase file (validated: Crew / Interaction Protocol / Prompts all present; 5 fenced prompt blocks).
- Flight status `ready` → `in-flight`. Branch `flight/04-ux-hotfixes-from-f3-debrief` already created at planning commit `a8a41f2`.
- Execution plan: L1 (design → review → implement) → L2 (design → review → implement) → L3 (design → review → implement) → batch Reviewer + commit → L4 HAT (interactive, operator-driven). L1-L3 deferred to single review/commit per per-flight protocol; L4 commit follows HAT.

### 2026-05-23 — L1 design review (cycle 1, approve with changes)

- Spawned Developer for L1 design review.
- Outcome: approve with changes. 1 MED + 3 LOW + 5 non-blocking suggestions + 2 questions.
- MED: Outputs vs AC inconsistency on row 2 of criterion-coverage seed (compound `partially-closed-by-F1+F3` not in status vocabulary). Resolved: dropped the row 2 prefill (matches Outputs; aligns with F3 debrief's "Mission Criteria Advanced" enumeration).
- LOW: AC#51 ambiguity ("current line 214's entry") clarified.
- LOW: Pool-warming definition embedded code paths — moved to citation block per `optional-registry-entry-hook` precedent.
- LOW: Stray trailing-quote noise in 2 Source lines (#64 + #68) — fixed; #72, #76, #80 were already balanced (reviewer note was imprecise).
- Suggestions absorbed: flight-log.md breadcrumb fix; broader grep regex in verification step; date-pin for grep; live-as-of timestamp on seed; Citation Audit count restated as 5 code-locations + 1 line-range.
- Questions resolved by Flight Director without re-spawning architect: (1) no special visual marker for project-side fallbacks — citation block already explains; (2) deferred `stub-fixture-extension-via-plugin-connect` recorded in this Session Notes (n=2 from F3 alone awaits third citation per methodology-promotion threshold).
- L1 status → `ready`. Cycle 2 not needed — all fixes are wording/AC-level, no structural changes. Skipping per agentic-workflow guidance (max 2 cycles unless cycle 2 raises new HIGH issues).

### 2026-05-23 — Deferred convention tracking

- `stub-fixture-extension-via-plugin-connect` (F3 debrief §14, n=2 from L3 + L4) — NOT codified in F4 L1; awaits a third citation per the methodology-promotion threshold (matches the F3 L1 precedent that codified only n=1-by-methodology-promotion + n=3 conventions). Re-evaluate when a flight touches the stub fixture surface in a way that produces a third independent citation.

### 2026-05-23 — L2 design review (cycle 1, approve with changes)

- Spawned Developer for L2 design review.
- Outcome: approve with changes. 1 HIGH + 1 MED + 2 LOW + 4 suggestions + 2 questions.
- HIGH: Pool dict symbol was wrong — leg used `_entries` throughout (Outputs, ACs, test bodies, Edge Cases), actual module-level dict at `the_one/connectors/_pool.py:206` is `_pool`. Existing tests at `tests/test_db_api.py:647,656,686,695` use `pool_mod._pool` and `(_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool`. **Fixed**: replaced all `_entries` references with `_pool`; switched success-path assertion to the clean tuple-in idiom; imported `_ACCOUNT_POOL_AGENT_SLOT` (per existing precedent).
- MED: Monkeypatch strategy was correct in conclusion but muddled in explanation; dropped the defensive `monkeypatch.setattr("the_one.interfaces.web.api.account_acquire", …, raising=False)` (no module-level binding exists, so the call was a no-op); tightened the comment to one line explaining the function-local-import binding mechanism.
- LOW: AC#68's "may be empty or carry a failed entry" hedge — tightened to `pool_mod._pool == {}` since the monkeypatched `account_acquire` raises before touching the pool.
- LOW: Success-path test used substring-on-stringified-tuple — switched to `(_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool` matching existing test idiom.
- Suggestions absorbed: added one-line comment in `_failing_acquire` explaining `ConnectorClientError` choice (realistic production failure mode); added `agent_acquire` serialization citation in Edge Case #5.
- Questions resolved by Flight Director:
  - (1) Annotation lands AFTER one blank line — separate paragraph from Status/Mission block. Confirmed.
  - (2) Only third test monkeypatches — AC tightened to make this explicit.
- Forward-reference fix: F3 flight.md annotation now points at the F4 L2 leg artifact (exists today) with F4 flight-debrief as the once-landed follow-up reference.
- L2 status → `ready`. Cycle 2 not needed — all fixes are wording/AC/code-snippet-level corrections of a single symbol-name typo plus refinements; no structural rework.

### 2026-05-23 — L3 design review (cycle 1, approve with changes)

- Spawned Developer for L3 design review.
- Outcome: approve with changes. 0 HIGH/MED + 5 LOW + 3 suggestions + 2 questions. Design is sound; only cosmetic drift.
- LOW: Line-number drift on expandBtn handler (leg said 241, actual 243). Fixed across 5 references in the leg.
- LOW: Line-number drift on chip-mode `else` branch (leg said ~591, actual ~310; the file is ~529 lines so the original was structurally impossible). Fixed.
- LOW: Internal "three"/"four" wording inconsistency on helper count — AC opener said "three" but enumerated four. Fixed to "four".
- LOW: Verification-step grep "at least 8 hits" was under-counted (real count is ~16-18) but threshold still holds — left as-is.
- LOW: Stub-type seed with `config={"allowlist": ...}` — accepted by the server (opaque dict storage); precedent at `test_flow_studio_per_agent_overlay_dropdown.py:160-178` uses Discord-type with the same shape. Test author can swap to Discord+503-route if stub-side validation rejects.
- Suggestions absorbed inline: added "empty-cache walk is a no-op" clarification to the four-helpers AC.
- Questions resolved by Flight Director:
  - (1) Comment-block citation format `// A2 (M11 F4 L3) —` matches existing convention (`// L7 HAT —`, `// M11 F3 L6b —` precedents in the same file).
  - (2) `_labelCacheFetchOk = false` flag for F9 forward-design — REJECTED as overdesign. F9 stale-entry work can re-touch this surface and add the distinction then; YAGNI for L3.
- L3 status → `ready`. Cycle 2 not needed — all fixes are cosmetic.

---

## Session Notes

### 2026-05-23 — Architect Design Review

- **Cycle 1**: approve with changes. One MED + 2 LOW catches:
  - MED: L4 HAT step 3 "cold-test variant" was impractical — no test-only API to evict; idle TTL is 30 min. Restart is the cold-pool path; merged into step 1.
  - LOW: F3 flight.md correction site moved from L4-body to F3-header annotation per agentic-workflow `SKILL.md:47` guidance.
  - LOW: `two-concurrent-callers-reasoning` placement pinned as regular Project-wide convention.
  - Plus suggestions absorbed: A1 inner-try/except error-surface isolation (avoids regression where pool-warmup-fail looks like Test Connection FAIL); A2 lazy-on-tile-expand + tile-local closure cache; criterion-coverage row schema locked; maintenance contract pinned; HAT renumbered to 6 steps with envelope inspection; Known UX Gaps escalation location pinned to F4 flight-debrief subsection.
- **Cycle 2**: approve. All cycle-1 fixes landed cleanly. 3 LOW inline refinements flagged for leg-author absorption (not blocking):
  - Narrow `BaseException` → `Exception` in A1 (L2 leg author note); preserves cooperative-cancellation discipline.
  - Add self-describing maintenance contract line to criterion-coverage.md header (L1 leg author note); applies the `mechanical-fallback-prompt-truth-pairing` convention recursively.
  - Reconcile stale L4-cache-strategy phrasing in L2 leg description (applied inline).
- F4 status: `ready`. Awaiting operator approval / `/agentic-workflow` execution.

### 2026-05-23 — Planning Session

- F3 just completed (PR #71 open; flight artifact status `completed`; debrief at `flight-debrief.md`).
- F4 scope sourced from F3 debrief Action Items "Immediate (before F4)" + "Methodology (before F4 planning)" + cumulative-UX-debt enumeration. Operator selected the broadest scope option ("hotfixes + codifications + criterion-map + HAT smoke-verify").
- Phase 1b recon (this section) is the n=1 application of the new `cross-flight-ux-debt-reconciliation` discipline F3 debrief recommended. It verified all 11 source items against current code.
- Phase 4 crew interview resolved 6 design decisions documented in `flight.md`.
- L1's codifications close the F3 debrief's "before F4 planning" methodology Action Items. L2-L4 close the "Immediate (before F4)" Action Items + the HAT smoke-verify.
- F4's framing as "intervention to arrest UX-debt accumulation" is explicit in flight.md Objective. Adaptation Criteria mandate: if HAT surfaces new UX issues, fold into F4 OR escalate as Known UX Gap with near-term path — NOT F8/F10 deferral.
