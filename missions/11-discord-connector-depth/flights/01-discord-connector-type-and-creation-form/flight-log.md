# Flight Log: Discord Connector-Type Registration + Discord-Shaped Creation Form

**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](flight.md)

## Summary

In-flight. Reconnaissance + design review complete; legs being designed and executed one at a time under `/agentic-workflow` orchestration. Branch `flight/01-discord-connector-type-and-creation-form`.

---

## Flight Director Notes

### 2026-05-21 — Flight start

- Loaded `the_one/.flightops/agent-crews/leg-execution.md`; phase file structurally valid (Crew + Interaction Protocol + Prompts present, all fenced blocks).
- Mission status: `active` (M11). Flight status: `ready` → `in-flight`.
- Branch created from `flight/08-planning-discord` (mission folder previously untracked there): `flight/01-discord-connector-type-and-creation-form`.
- Plan: 6 autonomous legs (L1-L6) drive design-review-implement cycles per leg. L7 (UAT) is operator-driven and gated to operator's call after L6 lands. Single code-review + commit at the end per `/agentic-workflow` v2 protocol.
- Dependency ordering documented in `flight.md` Legs header: L1 first; L2 before L4; L3 before L4; L5 + L6 independent.

### 2026-05-21 — L1 design review cycle 1

- Designed L1 (`codify-m10-conventions`) — doc-only codification of six conventions in `the_one/agents.md`, restructured Project Conventions section into Project-wide + Mission-specific (M10) subsections.
- Spawned Developer for design review. Assessment: approve with changes. Four low-severity issues flagged:
  1. Math sanity on "14 + 5 new" — accepted as already internally consistent.
  2. Off-by-one line citation (Project Conventions section end ~118-120) — replaced with "the `---` separator that introduces Subsystem contracts" (durable, line-number-free).
  3. `_CONNECTOR_AUTO_RELAY_DIRECTIVE` line range "~69-86" → tightened to "~69-84" (constant ends at line 84).
  4. **Substantive**: Option A (demote every existing `###` to `####`) was wrong on the `git blame` claim — git has no semantic awareness of markdown heading shifts. Switched to Option C (minimum-diff: insert `### Project-wide` and `### Mission-specific (M10)` marker headings, leave existing `### \`name\`` entries untouched). Preserves blame on every existing convention body.
- Added concrete file:line for `cross-subsystem-pattern-premise-revalidation` sentinel-wrapper exemplar: `_pool.py:148` (`_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"`), `_pool.py:512-530` (`connector_acquire`), call sites at `tools/connector_send.py:194` and `_inbound.py:140`.
- Suggestions and questions noted; the categorization-explicitness softening for `lifespan-wiring-same-leg-as-installation` applied. Decision NOT to re-spawn a second design-review pass: all changes are direct incorporation of the reviewer's own recommendations (especially Option C, which was the reviewer's explicit suggested alternative). Re-review would confirm the rewrite matches the request without adding signal.
- L1 status: `ready`.

### 2026-05-21 — L2 design review cycles

- Designed L2 (`discord-config-schema-and-validation`) — adds `_validate_connector_account_config` API helper (mirrors `_validate_mcp_source_config:730`) with Discord-branch validation for `config["intents"]` / `["guilds"]` / `["presence"]`; refactors hardcoded intents at `_discord.py:619-622` to config-driven reads with byte-identical fallback; tests in `tests/test_connectors_discord.py` + new `tests/test_api_connector_account_config_validation.py`.
- **Cycle 1** Developer review: approve with changes. Two HIGH-severity issues: (a) presence-type canonical set was specified as "read from `_build_activity`" but the plugin has no enumerated set (it uses `getattr` with try/except); (b) `_make_account` test helper does NOT accept a `config` kwarg — uses discrete kwargs. Two MEDIUM: try/except wrapper at validator call site was spec'd, but MCP precedent (`create_mcp_source:900`) is a bare call; empty-intents-dict policy was buried in Edge Cases instead of promoted to a Design Decision. Plus low-severity verbatim-string-pinning, citation tightening.
- Applied fixes: promoted four load-bearing decisions to a new "Design Decisions (L2-internal)" subsection (empty-intents=422; pinned presence frozenset; WARNING-log deviation; verbatim detail strings). Step 6 rewritten with the pinned module-local frozenset and explicit verbatim 422 detail strings. Step 7 changed to bare validator call with `create_mcp_source:900` citation. Step 10 specifies discrete `intents:` kwarg extension to `_make_account` (mirroring `presence`); recommends keeping `test_intent_construction` name. Step 11 cites specific `test_db_api.py:544+` fixture site. Citation Audit expanded 7 → 11 clusters.
- **Cycle 2** Developer review: approve (clean). All cycle-1 issues resolved at design level; AC + Design Decisions + Implementation Guidance internally consistent; no new issues introduced.
- L2 status: `ready`.

### 2026-05-21 — L3 design review cycles

- Designed L3 (`connector-form-registry-substrate`) — frontend `App.studio.connectorFormRegistry` with `register`/`get`; consult sites in `connector-account-editor.js` at `renderConnectionFields`, `renderSecretsKvTable`, `collectConfigRows`, `collectFormData`; fallback path is the test seam (existing `'stub'`-type browser tests pass UNMODIFIED).
- **Cycle 1** Developer review: approve with changes. One HIGH (Step 4 fallback wrapper contract was ambiguous on whether the typed renderer or substrate emits the outer wrapper — could let L4 break the byte-identical contract). Two MEDIUM (`auto_relay_platform_replies` open question unresolved — would the implementing agent add it to `RESERVED_CONFIG_KEYS` and break fallback DOM?; `renderSecretsKvTable` create-mode behavior ambiguous). Two LOW (literal line-number AC; no registry-contract unit test).
- Applied fixes: pinned wrapper contract at substrate level (always emits outer `<div class="field-row admin-pf-row connector-account-config-wrap"><label>Config</label><div class="connector-account-config" data-testid="connector-account-config">...</div></div>`; only inner varies). Added Design Decisions subsection deferring `auto_relay_platform_replies` (status-quo bug preserved). Step 5 explicit on create-mode fallback. AC switched from line-number-literal to ordering-only ("IMMEDIATELY BEFORE"). Added new AC + Playwright probe spec for the registry's own contract (`page.evaluate` + `console.warn` capture). Plus two new pinned contracts: entries MUST NOT return reserved config keys; entry signature does NOT receive `types`. ES5 style pinned in Implementation Guidance §1.
- **Cycle 2** Developer review: approve (clean). Byte-identical-fallback guarantee load-bearing on wrapper contract; AC + Step 4 + Step 5 unambiguous; no new issues.
- L3 status: `ready`.

### 2026-05-21 — L4 design review cycles

- Designed L4 (`discord-shaped-form`) — registers `'discord'` entry in L3's registry with typed BOT_TOKEN + intents (3 checkboxes) + guilds (comma-separated) + presence (name + type select) + Advanced kv-table disclosure. Plus dirty-tracker extension via two new optional entry hooks (`snapshot`, `wireEvents`).
- **Cycle 1** Developer review: needs rework. Two HIGH-severity correctness issues: (a) `attachStaticListeners` delegation only fires on `.field-input`/`.field-select` inside `.editor-section` — bare typed inputs won't trigger `checkDirty`; (b) `renderConfigKvTable` is IIFE-local but the spec hedged on namespace exposure. Three MEDIUM: presence-cleared-when-pre-existing edge case missing; snapshot byte-stability AC for unregistered types missing; BOT_TOKEN snapshot should be raw value not derived flag.
- Applied fixes: pinned TWO optional entry hooks — `snapshot` AND `wireEvents(container, checkDirty)` — for dirty-tracker integration; `wireEvents` is the cleaner-than-class-on-input route, matches the symmetric optional-hook pattern. `renderConfigKvTable` exposure is now a REQUIRED L4 output (Design Decisions + AC + Step 6c). Snapshot byte-stability AC added (no `typedFields` key when entry has no snapshot). Presence-cleared edge case + AC added. BOT_TOKEN snapshot changed to raw `botTokenValue: <str>`. Step 5 + 6/6b/6c rewritten to spell out the implementation. Step 14 rewritten to require the `wireEvents` hook explicitly.
- **Cycle 2** Developer review: approve with changes — two stale references (Step 13 still said `botTokenChanged: <bool>`; Citation Audit `wireEditorEvents` bullet said "delegated event handling covers new typed inputs"). Both fixed inline; no third review cycle (text reconciliation to match agreed design).
- L4 status: `ready`.

---

## Reconnaissance Report

Walk of every M11 mission item that names F1 scope or sources F1 work, classified against current code state.

| # | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | Connector-type checklist layer 1: `ConnectorAccount.type: Literal["discord", "stub"]` | already-satisfied | `the_one/db/models.py:135` + module-load assert at `:447-448` | Mark complete in scope; no F1 work |
| R2 | Layer 2: `CONNECTOR_TYPES = ("discord", "stub")` | already-satisfied | `the_one/db/_connector_types.py:55` | Mark complete in scope |
| R3 | Layer 3: `register("discord", DiscordPlugin)` | already-satisfied | `the_one/connectors/registry.py:181-182` | Mark complete in scope |
| R4 | Layer 4: SQLite `CHECK (type IN ('discord','stub'))` (v19) | already-satisfied | `the_one/db/schema.py:745` (CHECK clause sourced from `_CONNECTOR_TYPES_SQL` at `:25`) | Mark complete in scope |
| R5 | Layer 5: API per-type config-shape validation | confirmed-live | `the_one/interfaces/web/api.py:2160-2163` comment explicitly defers to F8/F9 ("No per-type config-shape validation in this leg…"); MCP precedent at `_validate_mcp_source_config:730+` | F1 L2 work; open question on validation layer for architect |
| R6 | Layer 6a (frontend badge tokens) | already-satisfied | `the_one/interfaces/web/static/css/tokens.css:158` (`--badge-discord: #5865F2`); `static/css/studio.css:915` (`.admin-connector-badge--discord`) | Mark complete in scope |
| R7 | Layer 6b (frontend Discord-shaped creation form) | confirmed-live | `static/js/areas/studio/connector-account-editor.js:477-543` renders generic kv-table `renderConnectionFields` for every type | F1 L3 + L4 work |
| R8 | Layer 7: `_init_*` state hook on `DiscordPlugin` | already-satisfied as "not needed" | Plugin reads `account.config` at `connect()` time (`_discord.py:240,624`); no state outside base fields | Document as N/A in flight-log; architect's call |
| R9 | Layer 8: Tool-target validation | already-satisfied | `tools/connector_send.py` per `agents.md:318` | Mark complete in scope |
| R10 | Typed `BOT_TOKEN` field with masked-edit | confirmed-live | Currently in generic `renderSecretsKvTable` at `connector-account-editor.js:616-631` | F1 L4 work |
| R11 | Intents selector with safe defaults | confirmed-live | Discord plugin hardcodes intents at `_discord.py:619-622`; not config-driven | F1 L2 (config schema + plugin read) + L4 (UI selector) |
| R12 | Optional guild scoping | partially-satisfied | Plugin reads `account.config["guilds"]` at `_discord.py:240` already; UI exposes only via generic kv-table | F1 L4 work (typed UI) |
| R13 | Invite-URL helper | confirmed-live | Nothing in UI generates an invite URL today | F1 L5 work |
| R14 | Discord vocabulary substitution (username/server/channel/role) | partially-satisfied | Allowlist labels say "Peers / Channels / Guilds / Roles" generic for all types (`connector-account-editor.js:1482,1490,1497`); routing-rules editor uses generic vocab; no per-type substitution | F1 L6 work |
| R15 | M11 Known Issue #1: six M10-debrief conventions codified in `agents.md` | confirmed-live | None of `encryptor-parameter-receive-but-not-consume`, `cross-subsystem-pattern-premise-revalidation`, `prompt-discipline-needs-mechanical-fallback`, `mechanical-fallback-prompt-truth-pairing`, `lifespan-wiring-same-leg-as-installation`, `atomic-leg-pattern` appear in `the_one/agents.md` | Operator decision (2026-05-21): fold into F1 as L1; routine-maintenance deferred to a separate post-M11 pass |
| R16 | M10 post-mission action item: run `/routine-maintenance` | confirmed-live | Last maintenance report `maintenance/2026-05-15.md`; M10 landed 2026-05-20 | Out of F1 scope; operator (2026-05-21) decided to run it as a separate pass after M11 |

**Operator-confirmed retirements**: R1, R2, R3, R4, R6, R8, R9 are not F1 work (already-satisfied or N/A); appear as completed `[x]` entries in the Contributing-to-Criteria section of `flight.md` with the satisfying evidence inline.

**Operator-confirmed live items folded into F1**: R5 (L2), R7 (L3+L4), R10 (L4), R11 (L2+L4), R12 (L4), R13 (L5), R14 (L6), R15 (L1). R16 deferred to a post-M11 maintenance pass.

---

## Leg Progress

### L1 — `codify-m10-conventions`

- **Started**: 2026-05-21
- **Completed**: 2026-05-21 (landed; awaiting flight-end commit per agentic-workflow v2)
- **Changes Made**:
  - Restructured `## Project Conventions` in `the_one/agents.md` per Option C (minimum-diff): inserted `### Project-wide` marker before `### \`trust-the-runtime\`` and `### Mission-specific (M10)` marker after `### \`protocol-widening-for-required-capability\`` and before the `---` separator. No existing `### \`name\`` headings were demoted; every existing convention body is byte-identical, preserving `git blame`.
  - Appended five new project-wide conventions under `### Project-wide` (after `protocol-widening-for-required-capability`, before the M10 marker), in the order `cross-subsystem-pattern-premise-revalidation` → `prompt-discipline-needs-mechanical-fallback` → `mechanical-fallback-prompt-truth-pairing` → `lifespan-wiring-same-leg-as-installation` → `atomic-leg-pattern`. Each entry follows the shape definition + applicability boundary + exemplar citation + back-reference to the M10 mission-debrief recommendation.
  - Added `encryptor-parameter-receive-but-not-consume` under `### Mission-specific (M10)` with a brief subsection intro paragraph explaining the mission-specific-vs-project-wide promotion rule.
  - Diff: `the_one/agents.md` +68 lines, -0 lines (purely additive). No source code, test, migration, or static asset modified.
- **Notes**:
  - Citation audit (re-run at leg-end): every new convention's exemplar citation greps live against the current tree. No drift from the leg artifact's Citation Audit section (verified at design time 2026-05-21). Key spot-checks: `_discord.py:596` and `_discord.py:1077` carry the verbatim "encryptor parameter is received to satisfy the F1 Protocol" docstring; `_pool.py:148` defines `_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"`; `_pool.py:512-530` defines `connector_acquire`; `agent/config.py:54-67` and `:69-84` carry the directive constants; `agent/factory.py:168` defines `set_factory`; `interfaces/web/app.py:88` calls `_set_module_factory(_state["factory"])`; `db/_connector_types.py:22` carries the v17/v18 migration index entries; `connectors/_inbound.py:711` carries the auto-relay fallback.
  - Test outcome: `docker exec the-one pytest -x --timeout 30 -q` → 2404 passed, 4 skipped, 415 deselected (165s). M10 F8 baseline preserved; pre-existing aiosqlite event-loop-closed warning (test-shutdown noise) carried over unchanged.
  - No deviations or anomalies. Option C minimum-diff strategy was the architect's explicit Phase 5b cycle 1 recommendation; landed without alteration.

### L2 — `discord-config-schema-and-validation`

- **Started**: 2026-05-21
- **Completed**: 2026-05-21 (landed; awaiting flight-end commit per agentic-workflow v2)
- **Changes Made**:
  - `the_one/interfaces/web/api.py`: added `_DISCORD_PRESENCE_TYPES` module-local frozenset and `_validate_connector_account_config(account: ConnectorAccount) -> None` helper grouped immediately after `_validate_mcp_source_config` (after the latter's defensive `else` raise at line 849, before the `/mcp-sources` GET handler). Helper dispatches on `account.type` with three branches: discord (validates intents/guilds/presence per the leg spec, verbatim 422 detail strings), stub (pass-through carve-out), else (defensive `HTTPException(500)` mirroring the MCP precedent). Wired as bare calls at `create_connector_account` (replacing the deferred-validation comment) and `update_connector_account` (after `model_validate(merged)`, before `repo.update(updated)`). Net delta: +160 lines (helper + presence-types constant + two call-site inserts; comment block removed).
  - `the_one/connectors/_discord.py`: replaced hardcoded `intents.message_content/members/guilds = True` block at original lines 619-622 with `intents_cfg = account.config.get("intents", {})` followed by three `intents.<axis> = intents_cfg.get("<axis>", True)` reads. Added a WARNING-log call gated on `intents.message_content is False`. Net delta: +25 lines (the WARNING-log block + an explanatory in-code comment).
  - `tests/test_connectors_discord.py`: extended `_make_account` with a discrete `intents: dict[str, bool] | None = None` kwarg (mirroring the existing `presence` shape) and the body `if intents is not None: config["intents"] = intents`. Added `test_intents_from_config_honored` immediately after the existing `test_intent_construction` (which keeps its name and body unchanged — the assertion still holds because the new code path falls back to the same True defaults). Net delta: +28 lines.
  - `tests/test_api_connector_account_config_validation.py` (NEW FILE, 290 lines): one test class `TestConnectorAccountConfigValidation` with 16 tests covering the rejection matrix (intents missing/extra/non-bool/empty/non-dict; guilds non-digit/non-string/non-list; presence non-dict/empty-name/unknown-type), three happy-path cases (all keys well-formed; all keys absent; empty guilds list), the stub-type carve-out, and a PUT-path malformed-config case covering the second validator call site. All 422 detail-string assertions are byte-for-byte (`assert resp.json()["detail"] == "..."`) per `verbatim-message-equality`. Fixture mirrors the shape established in `tests/test_db_api.py:18-44` (aiosqlite + Fernet + FastAPI test client + `get_connection` / `get_encryptor` patches).
- **Notes**:
  - **WARNING-log deviation note (per Design Decisions §3)**: the M10 F8 baseline emitted no log for disabled intents because the three intents were hardcoded True. L2 introduces a single WARNING-level call site at `_discord.py:643-650` that fires iff `intents.message_content is False`. The log message names the account ID and warns that the bot will silently receive no channel messages. This is the only new log emission this leg introduces.
  - **Inline decision — second `_probe_gateway_connect` intents site at `_discord.py:1421` left untouched**: `grep -n "intents.message_content = True"` returned a second hit (line 1421) inside `DiscordPlugin._probe_gateway_connect`, a static-method doctor probe that opens a short-lived test connection with hardcoded intents (the docstring at lines 1414-1418 spells out the same `message_content` + `members` + `guilds` shape for parity with `connect`). The leg artifact's "Implementation surface" section pins the refactor to lines 619-622 only and explicitly states "No other edits to the plugin file." The probe is a separate code path with no `account.config` access in its signature — refactoring it would require either passing config through or accepting that the doctor probe runs with the pre-L2 hardcoded shape regardless of account config. Left untouched per spec; flagged here for L4 / future-leg consideration if the doctor probe should mirror the config-driven shape.
  - **Citation drift discovered**: none. Every cited line range (`api.py:2148/2160-2163/2218-2221`, `_discord.py:619-622`, `tests/test_connectors_discord.py:356-377/416`, `tests/test_db_api.py:544+`) resolved verbatim. The `_DISCORD_PRESENCE_TYPES` frozenset's contents were derived from the Design Decisions §2 spec (not from `discord.ActivityType` at import time, per the explicit non-coupling decision).
  - **Test outcomes**:
    - `tests/test_connectors_discord.py` → 63 passed (was 62; +1 from `test_intents_from_config_honored`).
    - `tests/test_api_connector_account_config_validation.py` → 16 passed (new file).
    - `tests/test_connector_types_consistency.py` → 4 passed (unchanged baseline).
    - Full suite `docker exec the-one pytest -x --timeout 30 -q` → **2421 passed**, 4 skipped, 415 deselected (180s). +17 over the L1 baseline of 2404 (16 new API validation tests + 1 new Discord intent test); zero regressions. Pre-existing aiosqlite event-loop-closed warning carried over unchanged.
  - No further deviations or anomalies.

### L3 — `connector-form-registry-substrate`

- **Started**: 2026-05-21
- **Completed**: 2026-05-21 (landed; awaiting flight-end commit per agentic-workflow v2)
- **Changes Made**:
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` (NEW FILE, 99 lines): IIFE-wrapped ES5 module attaching `App.studio.connectorFormRegistry = { register, get }` to the global namespace. `register(type, entry)` validates: type is a non-empty string, `entry.type === type`, the three required functions (`renderConnectionFields`, `renderCredentialsFields`, `collect`) are functions, and `Array.isArray(entry.reservedConfigKeys)`. Missing or wrong-type fields raise `TypeError` whose message names the offending field. Double-register on the same type → `console.warn('App.studio.connectorFormRegistry: re-registering type ' + type)` + last-writer-wins. `get(type)` returns the entry or `undefined`; never throws.
  - `the_one/interfaces/web/static/index.html`: inserted `<script src="/static/js/areas/studio/connector-form-registry.js"></script>` at line 57, IMMEDIATELY BEFORE the `connector-account-editor.js` script tag (which shifts to line 58). +1 line.
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`: four consult sites added with the triple-guard (`var registry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;`):
    - `renderConnectionFields` (around line 534): outer wrapper `<div class="field-row admin-pf-row connector-account-config-wrap"><label>Config</label><div class="connector-account-config" data-testid="connector-account-config">...</div></div>` stays unconditional; inner content swaps between `entry.renderConnectionFields(account, isCreate)` (when entry exists) and `renderConfigKvTable(account)` (fallback). Active type computed as `isCreate ? '' : (account && account.type) || ''` so create-mode always falls through (matches pre-L3 behavior).
    - `renderSecretsKvTable` (around line 616): early-return with `entry.renderCredentialsFields(account)` when an entry exists; otherwise the existing kv-table body runs unchanged. Outer `.editor-section` / `.connector-account-secrets` wrappers continue to come from the caller (`renderConnectorAccountEditor:268-273`), preserving the byte-identical fallback DOM contract.
    - `collectConfigRows` (around line 555): effective reserved-keys composed as `RESERVED_CONFIG_KEYS ∪ (entry.reservedConfigKeys || [])` at call time. Substrate baseline constant `RESERVED_CONFIG_KEYS = { pairing: true, allowlist: true, routing: true }` UNCHANGED.
    - `collectFormData` (around line 1119): registry's `collect(container, account, isEdit) → {config, secrets}` hook runs FIRST when an entry exists; its returned config/secrets seed the payload. The substrate's pairing / allowlist / routing / `auto_relay_platform_replies` merge code below (unchanged) runs AFTER, overlaying the substrate-known reserved keys. When no entry → existing DOM-scan path runs unchanged.
    - `getFormSnapshot` (line 650+) — NOT MODIFIED per spec; L4 owns the dirty-tracker extension when typed inputs land.
  - `tests/browser/test_connector_form_registry.py` (NEW FILE, 159 lines): `TestConnectorFormRegistry` class with 5 Playwright probes via `page.evaluate`: round-trip (`register` → `get` returns same reference + reserved keys propagate), `get` on unregistered returns `undefined`, double-register emits `console.warn` containing "re-registering type" + last-writer-wins (captured via `page.on("console", ...)`), missing `renderConnectionFields` raises `TypeError` whose message names the missing field, `entry.type` mismatch raises `TypeError`.
- **Notes**:
  - **`auto_relay_platform_replies` deferred explicitly per Design Decisions §3**: did NOT add `auto_relay_platform_replies` to `RESERVED_CONFIG_KEYS`. Adding it would change the fallback DOM (the key would no longer appear as a row in the Advanced kv-table when set), violating the byte-identical contract. Status-quo bug (key rendered both by the Lifecycle checkbox AND by the kv iterator when set) preserved untouched. Flagged for a later flight as a clean substrate fix.
  - **Citation drift discovered**: none. All cited lines resolved against the live tree. `renderConnectionFields:477`, `renderSecretsKvTable:616`, `collectConfigRows:555`, `RESERVED_CONFIG_KEYS:553`, `collectFormData:1092` all verbatim. `index.html` script tags pre-L3 at lines 56 (connector-accounts-grid.js) and 57 (connector-account-editor.js) verbatim; new tag landed at line 57, shifting the editor to 58.
  - **Test outcomes**:
    - `tests/browser/test_flow_studio_connector_account_editor.py` → 17 passed, 1 pre-existing failure (`test_edit_session_continuation_round_trip` expects hint text "Distinct from the pool idle timeout" but production renders "Inbound continues the same chat session within this window." — confirmed identical failure on baseline pre-L3 via `git stash`; NOT a L3 regression). The 17 that pass include every fallback-DOM contract for the `'stub'` type — the regression gate held.
    - `tests/browser/test_flow_studio_connector_account_create_and_test.py` → 3 passed (UNMODIFIED, all green).
    - `tests/browser/test_flow_studio_connector_account_navigation.py` → 8 passed (UNMODIFIED, all green).
    - `tests/browser/test_connector_form_registry.py` → 5 passed (new file; covers the registry's own contract).
    - Full suite `docker exec the-one pytest --timeout 30 -q -m "not pixel"` → **2781 passed**, 10 failed: 5 pre-existing browser drifts confirmed unchanged on baseline via `git stash` (3× `test_connector_test_connection_button`; `test_flow_agent_tabs::test_tablist_renders_with_three_tabs` (4 tabs expected, 5 actual — codebase added a 5th tab without updating the test); `test_flow_studio_navigation::test_studio_section_round_trip_preserves_agent_selection`); 4 LLM-flaky `tests/test_aiat.py` cases; 1 continuation-hint drift above. The L3-touched paths show 0 regressions / +5 new tests passed. The 2781 vs 2421 L2-baseline delta is the first run executed under the `-m "not pixel"` marker (which includes browser-marked tests the L2 invocation excluded by default `-x` halting); the L3 contract held on every fallback regression test.
  - **Inline decisions**:
    - `renderSecretsKvTable` consult placement chose early-return over wrap-as-inner-content because the outer `.editor-section` / `.connector-account-secrets` wrapper is emitted by the CALLER (`renderConnectorAccountEditor:268-273`), not by `renderSecretsKvTable` itself. The function's return value is "the secrets inner content," so substituting it wholesale when an entry exists is the byte-identical-fallback-preserving move. This matches the leg's wrapper-contract clause ("the outer wrappers stay unconditional; only the inner content varies") at the architectural layer correct for this function.
    - In `collectFormData`, the registry's `collect` hook is consulted using `typeValue` (from the form's type input) rather than `account.type` because edit mode reads from `typeEl.value` (the readonly type input) and create mode also reads from the type-select. This consistent source matches what the substrate-known merges below (pairing / allowlist / routing / auto_relay) also use for their own type discrimination.
    - Playwright browsers were not pre-installed in the docker container — first invocation surfaced `Executable doesn't exist` from chrome-headless-shell. Ran `playwright install chromium` then `playwright install-deps chromium` to land the binary + glib/cairo/atk system libs. One-time container hygiene, not a code decision; flagged here so future invocations know the env was warmed.
  - **Files affected counts**: 1 new JS file (99 LOC), 1 modified JS file (+72 LOC net, no removals), 1 modified HTML file (+1 LOC), 1 new test file (159 LOC). Total: ~330 LOC across 4 files (excluding artifact updates).

### L4 — `discord-shaped-form`

- **Started**: 2026-05-21
- **Completed**: 2026-05-21 (landed; awaiting flight-end commit per agentic-workflow v2)
- **Changes Made**:
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js`: additive extension to `_validateEntry` accepting two new optional entry fields (`snapshot`, `wireEvents`). Both validated as "must be a function IF present, otherwise no error" via a small `optionalFns` loop right after the existing required-fields + `reservedConfigKeys` checks. The 4 required functions + `reservedConfigKeys` array stay REQUIRED — no public surface change beyond the new optional fields. +18 LOC.
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (NEW FILE, 263 LOC): IIFE-wrapped ES5 module. Module-load consults `window.App.studio.connectorFormRegistry` (throws clear Error if absent — surfaces script-ordering misconfiguration in `index.html` immediately) and registers the `'discord'` entry with `type: 'discord'`, `reservedConfigKeys: ['intents', 'guilds', 'presence']`, and six functions: `renderConnectionFields` (4 sections — Intents fieldset with 3 checkboxes per-axis default-on or `account.config.intents` per-axis override; Guilds single comma-separated `<input>` with help-text; Presence two-field editor — name `<input>` + type `<select>` with the 5 L2-pinned values + empty default; Advanced `<details>` wrapping `window.App.studio.renderConfigKvTable(account)`), `renderCredentialsFields` (typed BOT_TOKEN secret input with `data-original-masked` + show/hide eye-toggle, mirroring the generic secret-row pattern at editor.js:691-694), `collect` (reads typed-input DOM, emits "only on change or pre-existing" per Design Decisions §§2-4 — intents emitted iff (any != True) OR `account.config.intents` already present; guilds emitted iff non-empty list OR `account.config.guilds` already present; presence emitted iff (name non-empty) OR (type non-default) OR `account.config.presence` already present with cleared-when-pre-existing emitting `{}`; BOT_TOKEN always — `MASKED_SENTINEL` when input equals `_originalMasked`, else raw value), `snapshot` (RAW typed-input values under `{intents, guildsList, presenceName, presenceType, botTokenValue}` — substrate JSON-stringifies), `wireEvents` (attaches `change` to the 3 intent checkboxes + presence-type `<select>` + BOT_TOKEN eye-toggle; `input` to guilds-list + presence-name + BOT_TOKEN; each handler calls `checkDirty`; eye-toggle additionally flips type=password/text mirroring the generic secret-row eye at editor.js:870-887). All required `data-testid`s present (`discord-intent-message_content`, `discord-intent-members`, `discord-intent-guilds`, `discord-guilds-list`, `discord-presence-name`, `discord-presence-type`, `discord-bot-token`, `discord-advanced-kv-disclosure`).
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`: three additive extensions:
    - `getFormSnapshot` (line ~756): after building the existing `{static, config, secrets, allowlist, routing}` snapshot object, captured as a named local `snapshotObj`. New triple-guarded registry consult — reads active type from `container.querySelector('[data-field="type"]')` (works for both create-mode `<select>` and edit-mode readonly `<input>`); if entry exists AND `entry.snapshot` is a function, calls it and adds the result under `snapshotObj.typedFields` ONLY IF return is `!== undefined`. When no entry / no snapshot method / undefined return → no `typedFields` key at all (byte-identical to L3 baseline for `'stub'` and other unregistered types). +21 LOC.
    - `wireEditorEvents` (line ~837): immediately after `attachStaticListeners()` call, new triple-guarded registry consult; if entry exists AND `entry.wireEvents` is a function, calls `entry.wireEvents(container, checkDirty)`. Absent hook → no-op (existing behavior preserved). +13 LOC.
    - Namespace exposure (line ~2509): added `window.App.studio.renderConfigKvTable = renderConfigKvTable;` adjacent to the existing `renderConnectorAccountEditor` export. Function body UNCHANGED — only accessibility extends. +6 LOC (with explanatory comment).
  - `the_one/interfaces/web/static/index.html`: inserted `<script src="/static/js/areas/studio/connector-form-discord.js"></script>` between the existing `connector-form-registry.js` (loads first → defines registry) and `connector-account-editor.js` (loads last → exposes `renderConfigKvTable`). Three adjacent script tags. +1 line.
  - `tests/browser/test_flow_studio_connector_discord_form.py` (NEW FILE, 296 LOC): 11 Playwright tests using `app_clean` + existing `seed_connector_account(type='discord', ...)` — the seeder was already generic so no extension needed. Tests cover: edit-mode renders typed intents from persisted config; intent toggle re-enables Save (dirty-tracker hook); no-change save round-trips byte-identical when intents/guilds/presence were absent; all-True intents round-trip with the key preserved when pre-existing; intent-toggle save emits three-key dict with toggled axis; guilds-add save → 201 list round-trip; presence name+type save → 201 dict round-trip; Advanced disclosure hides reserved keys (intents/guilds/presence absent from kv-table; non-reserved `extra_key` appears); BOT_TOKEN masked-edit no-change save preserves stored value; BOT_TOKEN value-edit save updates stored value; `'stub'`-type snapshot is byte-identical to baseline (no Discord typed inputs render; Save stays disabled → snapshot stable across re-mount, confirming no spurious `typedFields` injection for unregistered types).
- **Notes**:
  - **Citation drift discovered**: minor — the leg artifact cited `getFormSnapshot:650`, `wireEditorEvents:716+`, and `window.App.studio.renderConnectorAccountEditor` at `~2416`. Post-L3 the live tree puts `getFormSnapshot` near line 730, `wireEditorEvents` near line 794, and the export at line 2501 (L3 added ~70 lines from its four consult-site extensions; L4's own additions shifted further). The architectural anchors are unchanged — `attachStaticListeners` still runs first, the snapshot still serializes the same five-key object, the export still lives at the IIFE end — so the leg's contract held verbatim. Lines drifted; symbols / contracts did not.
  - **Inline decisions**:
    - **Snapshot active-type source**: used `container.querySelector('[data-field="type"]')` (works for both create-mode `<select>` and edit-mode readonly `<input>` — both carry the same `data-field="type"` attribute per the editor at lines 516 / 528). This matches the `collectFormData` pattern at line 1179 which reads from the same selector, and keeps the snapshot/collect/wireEvents trio source-consistent.
    - **`data-testid` separator**: spec used hyphens (`discord-intent-message-content`); used underscores instead (`discord-intent-message_content`) to keep them in sync with the L2 validator's intent-dict keys (`message_content`, `members`, `guilds`). The `data-field` attributes (`intent-message_content` etc.) also use underscores for the same reason. The leg artifact's example string in the Implementation surface used hyphens but the underlying field name is `message_content`; underscores keep the convention uniform.
    - **`MASKED_SENTINEL` duplication**: re-declared `var MASKED_SENTINEL = '__MASKED__';` at the top of `connector-form-discord.js` rather than importing from `connector-account-editor.js`. Reason: the editor's constant lives inside its own IIFE so it's not externally visible; the value is a stable wire-format contract pinned at api.py (PUT-side accepts the literal string `__MASKED__` to mean "preserve stored secret"). Duplicating the string-literal locally is the same posture the editor itself takes (no central constants file in this layer). Flagged as a candidate centralization for a later flight.
    - **`'stub'`-type snapshot test approach**: the leg required asserting the `'stub'`-type snapshot is byte-identical to the L3 baseline. There's no public hook to read `getFormSnapshot`'s output (it's IIFE-closure-private). Used a proxy approach — assert that no Discord typed-input renders for `'stub'` accounts AND Save stays disabled on load (dirty=false → snapshot equality holds → no spurious key injection). This is the strongest assertion possible without exposing the snapshot function; if a `typedFields` key had leaked in, the `'stub'`-type round-trip would surface as a dirty-state false-positive on the very next edit, which the test would catch.
  - **Test outcomes**:
    - `tests/browser/test_connector_form_registry.py` → **5 passed** (UNMODIFIED, all green — registry's optional-field extension is backward-compatible).
    - `tests/browser/test_flow_studio_connector_account_editor.py` → **17 passed**, 1 pre-existing failure (`test_edit_session_continuation_round_trip` — same hint-text drift confirmed pre-existing in L3's flight-log; reconfirmed via `git stash` to fail on baseline).
    - `tests/browser/test_flow_studio_connector_account_create_and_test.py` → **3 passed** (UNMODIFIED, all green).
    - `tests/browser/test_flow_studio_connector_account_navigation.py` → **8 passed** (UNMODIFIED, all green).
    - `tests/browser/test_flow_studio_connector_discord_form.py` → **11 passed** (new file; ~15s).
    - Full suite `docker exec the-one pytest --timeout 60 -q -m "not pixel"` → **2792 passed**, 10 failed (the SAME 10 as the L3 baseline — 4 LLM-flaky `test_aiat.py`; 3 `test_connector_test_connection_button` drifts; `test_flow_agent_tabs::test_tablist_renders_with_three_tabs`; `test_flow_studio_navigation::test_studio_section_round_trip_preserves_agent_selection`; `test_edit_session_continuation_round_trip` hint-text drift). Confirmed pre-existing via `git stash` spot-check. **+11 over the L3 baseline of 2781 (all 11 from the new Discord-form test file; zero regressions).**
  - **Anomalies**: none. Playwright chromium was already installed from L3's container warmup; the `playwright install chromium --with-deps` invocation completed in seconds (no new packages).
  - **Files affected counts**: 1 new JS file (263 LOC), 1 modified JS registry file (+18 LOC), 1 modified JS editor file (+40 LOC across three sites — snapshot extension, wireEvents extension, namespace exposure), 1 modified HTML file (+1 LOC), 1 new test file (296 LOC). Total: ~620 LOC across 5 files (excluding artifact updates).

### L5 — `invite-url-section`

- **Started**: 2026-05-21
- **Completed**: 2026-05-21 (landed; awaiting flight-end commit per agentic-workflow v2)
- **Changes Made**:
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js`: extended `_validateEntry`'s optional-function loop to include `renderInviteSection` alongside `snapshot` and `wireEvents`. The 4 required functions + `reservedConfigKeys` array stay REQUIRED. +6 LOC (comment + array element).
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js`: ~175 LOC added across four sections — (a) module-level `_lastApplicationIdByAccount = {}` cache, (b) `_DISCORD_INVITE_PERMISSIONS` constant via `(1 << 11) + (1 << 16) + (1 << 10) + Math.pow(2, 31)` = **2147552256**, (c) `_computeInviteUrl(applicationId)` pure function returning the OAuth2 invite URL, (d) `renderInviteSection(account)` returning the section HTML per Design Decisions §"Section structure" with hint/url-wrap initial-state from cache, (e) `_updateInviteUrlDisplay(container, account)` DOM mutation helper toggling hidden + updating `<code>` textContent, (f) extended `wireEvents` to accept an OPTIONAL third `account` arg (falls back to `_resolveAccountFromContainer` which reads `window.location.hash` for the route's account id), wires intent-checkbox `change` to ALSO call `_updateInviteUrlDisplay`, and wires the Copy + Recompute buttons (Copy → `navigator.clipboard.writeText` + ephemeral "Copied" label swap for 1500ms; Recompute → `_updateInviteUrlDisplay`), (g) `window.App.studio.connectorFormDiscord = { setApplicationId(accountId, appId), _computeInviteUrl, _DISCORD_INVITE_PERMISSIONS }` namespace export, (h) Discord entry registration extended with `renderInviteSection`.
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`: three additive extensions — (a) edit-mode HTML assembly between `testConnectionHtml` and `dangerZoneHtml`: triple-guarded registry consult on `account.type`, `inviteHtml = entry.renderInviteSection(account)` when the entry provides the hook, falls back to empty string for unregistered types (preserves `'stub'`-type byte-identical DOM); (b) `renderTestConnectionBanner` signature changed from `(container, report)` to `(container, report, accountId)`, threaded through ALL 3 call sites (post-mount `_pendingProbeReport` consumer line 487 → `account.id`; `handleTestConnection` success path line 1411 → `accountId`; synthetic-error path line 1416 → `accountId`); after the existing banner-render code, when `report.details.application_id` AND `accountId` AND the Discord namespace are all present, calls `window.App.studio.connectorFormDiscord.setApplicationId(accountId, applicationId)` so the cache populates and the URL display re-renders; (c) `wireEditorEvents` extended to pass `account` as third arg to the entry's `wireEvents` (was 2-arg before, additive; L4 entries that ignore extra args stay backward-compatible). +33 LOC net across the three sites.
  - `tests/browser/test_flow_studio_connector_invite_section.py` (NEW FILE, 234 LOC): 5 Playwright tests with a function-scoped `clipboard_page` fixture (mirrors `test_markdown.py:127-151` precedent — new context with `permissions=["clipboard-read", "clipboard-write"]`). Tests: pre-probe hint visible / url-wrap hidden; post-probe URL visible with `client_id=...` + `permissions=2147552256` + `scope=bot+applications.commands`; intent-toggle stability (URL string equality before/after toggle + `permissions=2147552256` substring preserved); `'stub'`-type renders no `connector-invite-section` element; Copy button → `navigator.clipboard.readText()` returns the URL. `_fulfill_probe(page, account_id, application_id)` helper installs a `page.route` interceptor that returns `{"status":"ok", "details":{"application_id": application_id}}` mirroring the pattern at `test_connector_test_connection_button.py:85-94`.
- **Notes**:
  - **CRITICAL — permissions integer corrected to 2147552256**: the leg spec pinned `_DISCORD_INVITE_PERMISSIONS = (1 << 11) | (1 << 16) | (1 << 10) | (1 << 31)` and stated the total is `2147552768`. Both claims are arithmetically incorrect: (a) `(1 << 31)` in JavaScript produces the signed-32-bit value `-2147483648` because bitwise operators coerce operands to int32, so the OR expression yields `-2147415040` (a negative integer), which would emit `permissions=-2147415040` in the URL; (b) even with the unsigned interpretation, `2048 + 65536 + 1024 + 2147483648 = 2147552256`, not `2147552768` (off by 512 — the spec's claim is arithmetically wrong by 512). Used `(1 << 11) + (1 << 16) + (1 << 10) + Math.pow(2, 31) = 2147552256` to land the **mathematically correct** total. Verified against Discord's published permission integers: Send Messages `0x800` = 2048 (bit 11), Read Message History `0x10000` = 65536 (bit 16), View Channels `0x400` = 1024 (bit 10), Use Application Commands `0x80000000` = 2147483648 (bit 31). The constant in the code comment was updated from `2147552768` → `2147552256`; the test's literal substring assertion was updated to match. A future flight that revisits the constant should re-derive the sum from the bit positions rather than copying the spec's stated total.
  - **Inline decision — `wireEvents` third-arg (`account`)**: the L4 `wireEvents(container, checkDirty)` signature did not carry the account. L5 needs the `account.id` to key the cache for intent-toggle recompute. Extended the signature to `(container, checkDirty, account)` with `_resolveAccountFromContainer(container)` as a fallback that reads `window.location.hash` for the `#studio/connectors/{id}` route fragment. Substrate updated to pass `account` as the third arg. Backward-compatible (extra args are ignored by L4-era hook implementations).
  - **Inline decision — `_resolveAccountFromContainer` via hash**: the editor DOM has no `data-account-id` attribute today. The most authoritative source for the active account id inside `wireEvents` is the route's hash fragment. Used `window.location.hash.match(/#studio\/connectors\/([^/?#]+)/)` to extract the id, filtering out `'new'` (create mode). Documented as the same limitation noted in the leg spec's Edge Cases ("split-pane future").
  - **Inline decision — `setApplicationId` DOM re-render scope**: uses `document.querySelector('[data-testid="connector-invite-section"]')` (first-match). Acceptable per the leg spec's Edge Cases ("first-match limitation"); today the editor mounts one-at-a-time.
  - **Test outcomes**:
    - `tests/browser/test_connector_form_registry.py` → **5 passed** (UNMODIFIED, all green — registry's optional-field extension stays backward-compatible).
    - `tests/browser/test_flow_studio_connector_account_editor.py` → **17 passed**, 1 pre-existing failure (`test_edit_session_continuation_round_trip` hint-text drift — same baseline failure documented in L3 + L4 flight-logs, reconfirmed pre-existing).
    - `tests/browser/test_flow_studio_connector_account_create_and_test.py` → **3 passed** (UNMODIFIED, all green).
    - `tests/browser/test_flow_studio_connector_account_navigation.py` → **8 passed** (UNMODIFIED, all green).
    - `tests/browser/test_flow_studio_connector_discord_form.py` → **11 passed** (UNMODIFIED, all green — L4 tests carry over unmodified).
    - `tests/browser/test_flow_studio_connector_invite_section.py` → **5 passed** (new file; ~7.5s wall clock).
    - Targeted regression set (the 6 files above) → **49 passed, 1 failed** in 73.6s — the single failure is the pre-existing baseline `test_edit_session_continuation_round_trip`.
    - Full suite `docker exec the-one pytest --timeout 60 -q -m "not pixel"` → **2797 passed**, 10 failed (the SAME 10 as the L4 baseline — 4 LLM-flaky `test_aiat.py`; 3 `test_connector_test_connection_button` drifts; `test_flow_agent_tabs::test_tablist_renders_with_three_tabs`; `test_flow_studio_navigation::test_studio_section_round_trip_preserves_agent_selection`; `test_edit_session_continuation_round_trip`). **+5 over L4's 2792 baseline (all 5 from the new invite-section test file; zero regressions).** Runtime 574s.
  - **Anomalies**: none. Initial test run surfaced the `permissions=-2147415040` JavaScript int32 issue described above; fixed inline; rerun green.
  - **Files affected counts**: 1 modified JS registry file (+6 LOC), 1 modified JS Discord-entry file (+175 LOC), 1 modified JS editor file (+33 LOC net across three sites — invite HTML insertion, `renderTestConnectionBanner` signature + body extension, `wireEvents` account-arg pass-through), 1 new test file (234 LOC). Total: ~448 LOC across 4 files (excluding artifact updates). No backend, API, DB, HTML, or CSS file modified — purely additive frontend JS + new test.

### L6 — `discord-vocabulary-substitution`

- **Started**: 2026-05-21
- **Completed**: 2026-05-21 (landed; awaiting flight-end commit per agentic-workflow v2)
- **Changes Made**:
  - **NEW FILE** `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` (69 LOC, IIFE ES5): attaches `window.App.studio.connectorVocabulary = { get(type) }`. Module-private `_DEFAULT_VOCAB` (generic baseline: `{peer:'peer', peers:'peers', group:'guild', groups:'guilds', channel:'channel', channels:'channels', role:'role', roles:'roles', hintTone:'generic'}`) + `_ENTRIES.discord` (`{peer:'user', peers:'users', group:'server', groups:'servers', channel:'channel', channels:'channels', role:'role', roles:'roles', hintTone:'native'}`). `get(type)` always returns a populated entry — never undefined — so call sites never need to nullcheck.
  - `the_one/interfaces/web/static/index.html`: inserted `<script src="/static/js/areas/studio/connector-vocabulary.js"></script>` between `connector-form-discord.js` (line 58) and `connector-account-editor.js` (now line 60). Ordering relative to the editor is the contract — the module attaches to `App.studio` before the editor's IIFE evaluates so the consult sites resolve on first render.
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`: ~80 LOC net added across the IIFE-top helpers + four substitution sites:
    - **Top of IIFE**: added module-local `_DEFAULT_VOCAB_INLINE` constant (mirror of the vocabulary module's default; covers the edge case where the vocabulary script failed to load), `_capitalize(s)` helper (`s.charAt(0).toUpperCase() + s.slice(1)`; returns `''` for falsy input), and `_vocabForAccount(account)` triple-guarded lookup (`(window.App && window.App.studio && window.App.studio.connectorVocabulary) ? .get(type) : null; v || _DEFAULT_VOCAB_INLINE`).
    - **`renderAllowlistSection`** (line 1652+): the four `<label>` strings became `_capitalize(vocab.peers/channels/groups/roles)`. The four hint texts use the lower-case singular `vocab.peer/channel/group/role`; the Guilds + Roles hints conditionally append the "Discord-flavored" qualifier only when `vocab.hintTone !== 'native'`. Per leg spec exact form: roles hint reads `'Empty list = no ' + vocab.role + ' restriction. Any-of overlap.' + (nativeTone ? '' : ' Discord-flavored.')` — note the trailing period after "overlap" replaces the original semicolon split, per leg-spec literal direction.
    - **`renderAttachedAgentsList`** (line 2282+): signature extended to `(container, rows, account)`; vocab looked up via `_vocabForAccount(account)`. The two `<th>` cells "Peers" / "Channels" became `_capitalize(vocab.peers)` / `_capitalize(vocab.channels)`. Only the table-header path consumes the vocab; the per-row `_renderAxis` empty-list hint copy ("DMs only" / "none") remains shared across types since those are channel-class-specific semantics, not per-type vocabulary.
    - **`_renderRoutingScopeOptions`** (line 1818+): signature extended to `(currentScope, vocab)`; defaults to `_DEFAULT_VOCAB_INLINE` if not provided (backward-compat for any future caller that forgets to thread it). For each scope value `s` in `_VALID_ROUTING_SCOPES`, textContent is computed as `s === 'peer' ? vocab.peer : (s === 'channel' ? vocab.channel : s)`. The `<option value>` attribute STAYS at the literal scope value via `escapeAttr(s)` — substrate vocabulary preserved at the persistence layer. Capitalization NOT applied (per leg AC: pre-L6 dropdown text was lower-case; `vocab.peer === 'user'` is already lower-case on Discord).
    - **`_renderRoutingRow`** (line 1865+): signature extended to `(row, idx, vocab)`; threads `vocab` to `_renderRoutingScopeOptions`. Two callers updated:
      - `renderRoutingRulesSection` (line 1919+): looks up `var vocab = _vocabForAccount(account);` at the section head, passes through to `_renderRoutingRow(rows[i], i, vocab)` in the pre-rendered rows loop.
      - The add-rule handler inside `wireRoutingRulesEvents` (line 2152+): `var addVocab = _vocabForAccount(account);` (account is in the closure scope) and `_renderRoutingRow({...}, idx, addVocab)`.
    - **`fetchAttachedAgents`** (line 2353+): signature changed from `(container, accountId, ...)` to `(container, account, ...)` — accepts the full account object so the post-fetch `renderAttachedAgentsList` call can pass `account` for the vocabulary lookup. `accountId` is extracted via `account && account.id` inside the function; the single caller in `wireEditorEvents` (line 1106) updated to pass `account` instead of `account.id`.
  - **NEW FILE** `tests/browser/test_flow_studio_connector_discord_vocabulary.py` (366 LOC): 6 Playwright tests. Each test seeds via `seed_connector_account(type='discord', config={...}, secrets={'BOT_TOKEN': 'plaintext'})` (or `type='stub'` for the regression test). Assertions anchor to the `.connector-allowlist-section .connector-account-acl-fieldlabel` selector (not page-wide text matches) so the L4 Discord typed-form's own connection-side "Guilds" label (Discord-intent input at `connector-form-discord.js:137`) doesn't pollute the assertion. Tests:
    1. `test_discord_account_renders_substituted_allowlist_labels`: Discord allowlist `<label>` text reads `["Users", "Channels", "Servers", "Roles"]` (exact array equality).
    2. `test_discord_account_hints_drop_discord_flavored_qualifier`: Discord hints contain "no server restriction" / "no role restriction" and DO NOT contain "Discord-flavored" (`hintTone === 'native'` drops the qualifier). Page-wide assertion that "Discord-flavored; ignored by other platforms." does not appear anywhere.
    3. `test_discord_account_attached_agents_header_renders_substituted_labels`: uses `page.route(...)` to stub the `/api/connector-accounts/{id}/attached-agents` fetch with a non-empty row (so the table header renders); reads `[Agent, Users, Channels]` exact equality off `<th>` cells.
    4. `test_discord_routing_scope_dropdown_substitutes_peer_textcontent`: Seeds a Discord account with `routing.rules[0] = {scope:'peer', match:['alice'], agent:'general'}` + `routing.default = None` (L2 validator requires both `rules` and `default` keys). Reads `<option value="peer">` textContent off `[data-routing-scope]` selectors — asserts `'user'` textContent and `'peer'` value attribute (substrate vocabulary preserved at the wire layer). Also asserts `<option value="channel">` textContent is `'channel'`.
    5. `test_stub_account_preserves_baseline_allowlist_labels`: `'stub'`-type account allowlist labels are `["Peers", "Channels", "Guilds", "Roles"]`; guilds hint still contains "Discord-flavored" (generic-tone keeps the qualifier).
    6. `test_discord_account_save_roundtrip_preserves_substrate_field_names`: Seeds Discord account with full `config.allowlist = {peers, channels, guilds, roles}`. Direct GET confirms the seeded shape persisted. UI round-trip (rename + Save) → GET again → field names still `{peers, channels, guilds, roles}`, never `{users, servers}`. Wire-layer substrate preserved.
- **Notes**:
  - **Inline decision — Roles hint wording split**: the original baseline hint "Empty list = no role restriction. Any-of overlap; Discord-flavored." used a semicolon between "Any-of overlap" and "Discord-flavored." The leg spec Implementation Guidance §4 directs the substitution as `'Any-of overlap.' + (vocab.hintTone === 'native' ? '' : ' Discord-flavored.')`, which replaces the semicolon with a period. Adopted the leg-spec literal form: generic-tone renders "...Any-of overlap. Discord-flavored." (two sentences, period-separated); native-tone renders "...Any-of overlap." (period, no trailing qualifier). Documented as a deliberate minor wording shift from L4 baseline.
  - **Inline decision — `fetchAttachedAgents` signature change**: the existing function took `accountId: string`. To thread the vocabulary into the post-fetch render, I extended it to take the full `account` object (`account.id` drives the URL; `account.type` drives the vocab lookup). Single caller in this codebase, updated atomically. Alternative considered (closure-capture `account` inside the editor and pass `vocab` directly to render) was rejected — `fetchAttachedAgents` is exposed via the editor IIFE and already received plenty of state through its arg list, so passing one richer object is cleaner than threading vocab as a fifth positional.
  - **Inline decision — vocab default in `_renderRoutingScopeOptions`**: the function's signature defaults to `_DEFAULT_VOCAB_INLINE` when vocab is omitted, so any future caller that forgets to thread the vocab gets the generic baseline (byte-identical to pre-L6 output). Belt-and-suspenders against the triple-guard at the consult site.
  - **Inline decision — Anchor allowlist label assertions to the section selector**: page-wide `get_by_text("Guilds", exact=True).count() == 0` initially failed because the L4 Discord typed-form's own connection-side "Guilds" label (at `connector-form-discord.js:137`, an input for guild-ID list within the Discord intent fieldset) also matches. The L4 label is OUT OF L6 SCOPE — L6 owns the allowlist surface; L4 owns the typed Discord intent inputs. Switched the test to read labels via `.connector-allowlist-section .connector-account-acl-fieldlabel` and assert the exact 4-element array. This is the more correct test shape anyway: it pins the position of each label, not just its presence/absence.
  - **Inline decision — `<option value>` literal preservation**: per AC #7 — the routing-scope dropdown's `<option value="peer">` MUST keep `value="peer"` (substrate persistence vocabulary) while textContent reads `"user"` (display vocabulary). The test (`test_discord_routing_scope_dropdown_substitutes_peer_textcontent`) asserts BOTH conditions independently to lock this contract.
  - **Test outcomes**:
    - `tests/browser/test_connector_form_registry.py` → **5 passed** (UNMODIFIED, all green — vocabulary module is unrelated to the registry).
    - `tests/browser/test_flow_studio_connector_account_editor.py` → **17 passed**, 1 pre-existing failure (`test_edit_session_continuation_round_trip` hint-text drift — same baseline failure documented in L3/L4/L5 flight-logs).
    - `tests/browser/test_flow_studio_connector_account_create_and_test.py` → **3 passed** (UNMODIFIED).
    - `tests/browser/test_flow_studio_connector_account_navigation.py` → **8 passed** (UNMODIFIED).
    - `tests/browser/test_flow_studio_connector_discord_form.py` → **11 passed** (UNMODIFIED — L4 tests carry over byte-identical; the substitution targets the substrate's allowlist + routing-scope display surfaces, not the L4 Discord typed-form fields).
    - `tests/browser/test_flow_studio_connector_invite_section.py` → **5 passed** (UNMODIFIED — L5 invite section is unaffected).
    - `tests/browser/test_flow_studio_connector_discord_vocabulary.py` → **6 passed** (new file; ~8s wall clock).
    - Targeted regression set (the 7 files above) → **55 passed, 1 deselected** (the pre-existing baseline failure deselected by `--deselect` flag) in 77.7s.
    - Full suite `docker exec the-one pytest --timeout 60 -q -m "not pixel"` → **2803 passed**, 10 failed (the SAME 10 as the L5 baseline: 4 LLM-flaky `test_aiat.py`; 3 `test_connector_test_connection_button` drifts; `test_flow_agent_tabs::test_tablist_renders_with_three_tabs`; `test_flow_studio_navigation::test_studio_section_round_trip_preserves_agent_selection`; `test_edit_session_continuation_round_trip`). **+6 over L5's 2797 baseline (all 6 from the new vocabulary test file; zero regressions).** Runtime 605s.
  - **Substrate preservation verified**: pre-L6 grep `'"peer"'` over `db/models.py`, `connectors/_acl.py`, `connectors/_inbound.py`, `connectors/_routing.py`, `tools/connector_send.py` returned 4 hits (2 in `models.py` line 113 + neighboring; 2 in `_routing.py`). Post-L6 grep returns the SAME 4 hits. Single-quoted `"'peer'"` grep returns 0 hits pre- and post- (the codebase uses double-quoted Python strings consistently). The `_outbound.py` file referenced in the leg spec does not exist in this codebase (no such file); the connectors namespace uses `_inbound.py` + `_acl.py` + `_routing.py` instead. Confirmed via `ls the_one/connectors/`.
  - **Anomalies**:
    - Routing-rule seed initially failed with `422 config['routing'] is missing required keys: ['default']` — the L2 validator requires both `rules` and `default` keys when `routing` is present. Added `"default": None` to the seed payload; rerun green.
    - Initial test wrote page-wide `get_by_text("Guilds", exact=True).count() == 0` which collided with the L4 Discord form's connection-side "Guilds" label. Switched to section-scoped selector — see inline decision above.
  - **Files affected counts**: 1 new JS vocabulary module (69 LOC), 1 modified JS editor file (~80 LOC net across 4 consult sites + 3 helpers), 1 modified `index.html` (+1 line script tag), 1 new test file (366 LOC). Total: ~516 LOC across 4 files (excluding artifact updates). No backend, API, DB, or CSS file modified — purely additive frontend JS + new test. Substrate (Pydantic models, ACL field names, `_VALID_ROUTING_SCOPES` literals, audit-log keys) verified unchanged via grep parity.

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

## Session Notes

### 2026-05-21 — Planning Session

- Mission `11-discord-connector-depth` planning landed 2026-05-20; F1 planning starts 2026-05-21 the next day.
- M10 F8 substrate confirmed in place and unchanged since 2026-05-20 ship.
- Operator decision on M11 Known Issue #1 (codification dependency): fold into F1 as first leg; defer routine-maintenance to a separate post-M11 pass.
- Operator decision on UAT/alignment leg: include as optional final leg (Create + Test + Invite + Attach round-trip on real Discord).
- Phase 4 crew interview captured four design decisions:
  - **Form abstraction**: substrate-level per-type form registry (frontend) — load-bearing for future second connector
  - **Intents shape**: three checkboxes, all-defaulted-on, plugin reads from `account.config["intents"]`
  - **Invite URL**: always-visible Invite section on detail page (post-probe — pre-probe shows hint)
  - **Vocabulary**: frontend vocabulary map by connector type; substrate code stays neutral
  - **Advanced kv-table**: kept behind disclosure for Discord; reserved-key hiding extended to intents/guilds/presence
- One open question deferred to Architect review: validation-layer choice (API dispatch vs plugin Protocol method vs Pydantic validator). Recommended default in `flight.md`: API dispatch.
- One open question marked for architect's confirmation: `_init_*` state hook necessity. Recommended default: skip; document as N/A.

### 2026-05-21 — Architect Design Review (Phase 5b cycle 1)

Architect's assessment: **approve with changes**. Resolutions and fixes applied to `flight.md` in the same session.

- **Open question resolutions**:
    - **Validation-layer**: (a) API-layer per-type dispatch — promoted to Design Decisions. Rationale: precedent fit exact (`_validate_mcp_source_config`), M11 substrate-neutrality honored, `agents.md:315` already documents the layer as "API gating."
    - **`_init_*` state hook**: skip — confirmed N/A; documented in Design Decisions and verified against `_discord.py` read sites at 240, 624.

- **Medium-severity fixes applied**:
    - L2 renamed from `discord-intents-config-schema` to `discord-config-schema-and-validation`; checkpoint and ACs broadened to cover all three config keys (intents, guilds, presence) the validator gates.
    - Explicit dependency ordering added under the Legs header: L1 before all; L2 before L4; L3 before L4.
    - L6 description extended to substitute per-axis hint copy ("Discord-flavored" qualifier drops on Discord connectors); vocabulary map carries `hintTone` flag.
    - L5 wording tightened: section is always mounted; content varies by probe state (URL post-probe, hint pre-probe). Edit-mode only.
    - L7 description extended: HAT-discovered fixes land in flight-log Anomalies sections under the relevant leg; substrate-contract reversals pause the flight per Adaptation Criteria.
    - L1 description carries a methodological note acknowledging the looser-reading framing operator chose.

- **Low-severity / suggestions applied**:
    - Form-registry collect hook contract pinned: returns `{config, secrets}` and substrate stitches (the cleaner of the two integration options at design review).
    - Per-type reserved-config-keys made registry-declared (not extending the generic `RESERVED_CONFIG_KEYS` substrate constant); substrate baseline stays `{pairing, allowlist, routing}`.
    - L6: internal `_VALID_ROUTING_SCOPES` Literal values pinned as persistence vocabulary, NOT substituted — only display labels substitute.
    - L5: explicit "no debounce" choice documented.
    - Acknowledgment that `connector-form-registry` is a consciously richer abstraction than the `admin.js:177-189` `TYPE_DEFAULTS` precedent.

- **Verified codebase claims** at architect's review (all confirmed):
    - Doctor probe surfaces `application_id` at `_discord.py:1089, 1124, 1301` — invite-URL helper has the data source.
    - Zero test files in `tests/` or `static/tests/` grep-match on the literal display text "Peers" / "Guilds" — vocabulary substitution's test-update surface is near-zero.
    - M10 conventions confirmed not in `the_one/agents.md` (L1 is correctly net-new content).

- **Architect-checklist items satisfied**:
    - Precedent-grep: `_validate_mcp_source_config:730` enumerated and contract delivery (FastAPI `HTTPException(422)`) confirmed at api.py:2148+ insertion point.
    - Cross-subsystem premise validation: per-type form registry premise (second Discord-shaped connector form) is mission-bound, not speculative.
    - Protocol-signature-vs-actual-contract: N/A for chosen option (a) at validation layer.

No substantive structural issues to escalate. Spec ready for user walk-through.
