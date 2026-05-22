# Flight Log: Pool-Keying Refactor + Per-Account System-Prompt Directive Surface

**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](flight.md)

## Summary

Planning phase. Reconnaissance complete (F1 debrief + M10 F8 debrief source items walked against current code). Design decisions documented in `flight.md`. Awaiting Architect design review.

---

## Reconnaissance Report

Walk of every F1 debrief + M10 F8 debrief item touching F2 scope, classified against current code state (2026-05-21, post-F1 commits `40660a1` + `94a10a6` + `fa6bdfd`).

| # | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | Pool-keying sentinel wrapper | confirmed-live | `_pool.py:148` `_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"`; `_pool.py:512-530` `connector_acquire`; 5 production call sites at `tools/connector_send.py:194`, `_inbound.py:140,396,433,750` | F2 L2 core |
| R2 | System-prompt directive — three hardcoded constants | confirmed-live | `agent/config.py:54-95`; `compose_system_prompt` at line 96; factory consumer at `factory.py:452-457`; `auto_relay` per-account-derived precedent at `factory.py:340` from `account.config["auto_relay_platform_replies"]` | F2 L3+L4 core |
| R3 | `_probe_gateway_connect` hardcoded intents | confirmed-live | `_discord.py:1421` — one site outside F1 L2's `connect()` scope; static method receives token only (no account) | F2 L5 |
| R4 | `MASKED_SENTINEL` duplicate string-literal | confirmed-live | `connector-account-editor.js:47` + `connector-form-discord.js:38` declare `var MASKED_SENTINEL = '__MASKED__'` independently | Bundle into F2 L4 (shared studio surface) |
| R5 | `_resolveAccountFromContainer` hash-parse | confirmed-live | `connector-form-discord.js:456-462` parses `window.location.hash` for account_id | Bundle into F2 L4 |
| R6 | Codify 2 new agents.md conventions | confirmed-live | `optional-registry-entry-hook` and `registry-dispatch-create-mode-AC` not in `agents.md` (grep returns zero hits) | F2 L1 (doc-only, gates L2-L5) |
| R7 | Three Architect-checklist items | mission-control-skill-scope | Methodology change (apply at F2 review now; codify in mission-control skills as a separate pass) | Apply at every F2 leg's design-review cycle in spirit |
| R8 | Symbolic-anchor citations | methodology | Same scope as R7 | Default discipline for F2 leg specs |
| R9 | `test_connector_test_connection_button` triage | out-of-scope | Recurring across M10 F8 + M11 F1 | Defer to `/routine-maintenance` post-M11 per F1 debrief |

**Operator-confirmed live items folded into F2**: R1 (L2), R2 (L3+L4), R3 (L5), R4 (L4 bundle), R5 (L4 bundle), R6 (L1). R7 + R8 applied as methodology at all F2 leg reviews. R9 deferred to routine-maintenance.

**Phase 4 crew interview outcomes** (2026-05-21):
- Pool API shape: two-primitive split (`agent_acquire` + `account_acquire`); clean break (delete sentinel, no shim)
- Directive override semantics: APPEND mode (not replace, not three-per-state)
- Directive UI placement: General tab between Pairing and Test Connection
- Directive UI shape: textarea + three read-only `<details>` disclosures showing verbatim defaults; "current state" annotation reacts to auto-relay toggle
- HAT shape: required, Chrome-MCP-driven (one-time walk, not committed repeatable script — that's M11 F8 scope)
- Studio polish (R4, R5) bundled into L4

---

## Leg Progress

### L1 — codify-f1-debrief-conventions

- **Started**: 2026-05-21
- **Completed**: 2026-05-21
- **Status**: landed
- **Changes Made**: Appended two new project-wide convention entries to `the_one/agents.md` between `### \`atomic-leg-pattern\`` and the `### Mission-specific (M10)` marker — `optional-registry-entry-hook` first (n=3 from F1 L4+L5 hooks `snapshot`/`wireEvents`/`renderInviteSection`), then `registry-dispatch-create-mode-AC` (n=1 codified by methodology-promotion per F1 debrief Recommendations §2 operator-confirmed). Entry bodies follow the established shape: heading → 2-4 sentence definition → applicability boundary → exemplar citation(s) → source pointer. All citations use symbolic anchors (`file:symbol` form) per F1 debrief Recommendation §3 — no bare line numbers. Diff: `the_one/agents.md` only, +25 lines, purely additive (+2 `^### \`` headings; pre-existing 14 project-wide entries `trust-the-runtime` through `atomic-leg-pattern` byte-identical).
- **Citations verified live against post-F1 tree**:
  - `connector-form-registry.js:_validateEntry` — `optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection']` array present at function body.
  - `connector-form-discord.js:snapshot` / `:wireEvents` / `:renderInviteSection` — all three present at the entry's registration site.
  - `connector-account-editor.js:renderConnectionFields` — exists; the `connActiveType` zeroing shape is the documented F1 L7 pre-fix bug location.
  - `connector-account-editor.js:renderConnectorAccountEditor` — exists with `forceCreate` 5th-arg (added at F1 L7 fix); cited alongside `renderConnectionFields` to give the resolution-side anchor.
  - `tests/browser/test_flow_studio_connector_account_create_and_test.py:test_create_mode_pick_discord_renders_typed_form` — present.
- **Notes / Inline Decisions**:
  - Augmented the `registry-dispatch-create-mode-AC` entry with a second symbolic anchor (`renderConnectorAccountEditor`) alongside the leg's prescribed `renderConnectionFields` citation, because the `forceCreate` 5th-arg re-render path lives at the editor entry point — the leg artifact references both shapes but the bug-and-fix locus straddles both functions. Keeps the citation symbolic-only and grep-stable.
  - No citation drift found; all five symbol clusters verified live in the post-F1 tree.
  - Sanity-check `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` failed on `tests/browser/test_connector_test_connection_button.py::test_default_stub_probe_renders_success_with_no_details` — confirmed pre-existing by re-running on the pre-edit baseline (stash). This is R9 from the reconnaissance report (recurring across M10 F8 + M11 F1, deferred to `/routine-maintenance` per F1 debrief). Doc-only diff cannot cause it.
- **Files Touched**: `the_one/agents.md` (+25 LOC, additive only); `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/01-codify-f1-debrief-conventions.md` (status transitions); this file (Leg Progress entry).

### L2 — account-keyed-pool-primitive

- **Started**: 2026-05-21
- **Completed**: 2026-05-21
- **Status**: landed
- **Changes Made**: Clean-break refactor of `the_one/connectors/_pool.py`: renamed `acquire` → `agent_acquire`, renamed `connector_acquire` → `account_acquire` (body now `return await agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)`), deleted `_CONNECTOR_POOL_AGENT_SENTINEL` and introduced module-private `_ACCOUNT_POOL_AGENT_SLOT = "__connector__"` (literal value preserved for warm-entry continuity), added `_keys_for_test()` HAT inspection seam, refreshed module + slot docstring. Updated 5 production call sites + imports lockstep: `the_one/connectors/_inbound.py` (dropped dead `pool_acquire` alias, renamed to `account_acquire`, 3 call sites at `dispatch_inbound` lines 396/433/750, module docstring at lines 14-21 + 86 + 122), `the_one/tools/connector_send.py` (dropped dead `pool_acquire` alias, renamed import + 1 call site at `SendToPlatformChannelTool.execute`, module docstring), `the_one/interfaces/web/app.py` (function-local import + 1 call site at `lifespan`, M11 F2 L2 framing in surrounding comment). Updated all 6 test files with FUNCTIONAL code references: `tests/test_connectors_pool.py` (import group rewritten — added `_ACCOUNT_POOL_AGENT_SLOT`, `_keys_for_test`, `account_acquire`, `agent_acquire`; ~30 `acquire(...)` call sites renamed to `agent_acquire(...)`; +2 new tests `test_account_acquire_routes_to_account_keyed_slot` and `test_keys_for_test_returns_current_keys` at end of file), `tests/test_connectors_e2e.py` (import group rewritten, 4 call sites renamed), `tests/test_db_api.py` (7 import sites + 8 call sites renamed in lockstep), `tests/test_connectors_inbound.py` (sentinel name swap at lines 351/1411/2601/2682/2688 including the key-filter at line 2682, monkeypatch target + local `_raising_account_acquire` helper at lines 2257-2267, docstring sweep at 1337/2239/2248-2249/2549-2550/2666 + the `pool_acquire → client.send` system-outbound prose), `tests/test_lifespan.py` (5 getattr/setattr sites at 232/238/253/299/303/305 — `original_account_acquire` locals + sentinel assertion + docstring sweep at 154/161/164/227-228), `tests/test_connectors_e2e_platform_send.py` (monkeypatch at lines 384/390 with `original_acquire` local preserved per spec, sentinel assertion at line 469, docstring sweep at 374/377/380/396, test function rename `test_e2e_pool_acquire_touches_last_activity_on_outbound` → `test_e2e_account_acquire_touches_last_activity_on_outbound` so `grep pool_acquire` returns zero). Docstring sweep across `tests/test_connector_send_tool.py`, `the_one/connectors/README.md` (§2 acquire-API enumeration rewritten as the two-primitive shape; §11 + §12 step-3/9/10 + System-outbound prose updated to `account_acquire`), `the_one/connectors/base.py` (CommandResponse docstring simplified to `account_acquire(account_id) → client.send`, F8/F2 chronology dropped to keep grep clean). Updated `the_one/agents.md` `cross-subsystem-pattern-premise-revalidation` exemplar citation to symbolic anchors `the_one/connectors/_pool.py:agent_acquire` + `:account_acquire`; preserved the F8 L11 historical lesson.
- **Verification**:
  - `python -c "from the_one.connectors._pool import acquire"`, `... import connector_acquire`, `... import _CONNECTOR_POOL_AGENT_SENTINEL` — ALL three raise `ImportError` (clean break confirmed).
  - `grep -rn "connector_acquire\|_CONNECTOR_POOL_AGENT_SENTINEL\|pool_acquire" the_one/ tests/` — zero hits (M11 mission folder excluded).
  - `grep -n "^async def agent_acquire\|^async def account_acquire" the_one/connectors/_pool.py` — exactly 2 hits.
  - `grep -n "_ACCOUNT_POOL_AGENT_SLOT" the_one/connectors/_pool.py` — 3 hits (constant + use inside `account_acquire` + the slot referenced in the module docstring).
  - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py` — 29 passed (27 original + 2 new).
  - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py tests/test_connectors_e2e.py tests/test_connectors_e2e_platform_send.py tests/test_db_api.py tests/test_lifespan.py` — 128 passed.
  - `docker exec the-one pytest --timeout 30 -q -m "not pixel"` (full suite) — **2806 passed**, 42 skipped, 10 failed. 2806 = F1 baseline 2804 + 2 new pool tests. The 10 failures are pre-existing R9-class (4 `tests/test_aiat.py` LLM-live assertions + 6 `tests/browser/*` items deferred to `/routine-maintenance` per F1 debrief). Confirmed pre-existing by stash-pop replay against the pre-L2 tree.
- **Notes / Inline Decisions**:
  - Dropped the `pool_acquire as acquire`-style alias entirely in `_inbound.py` and `connector_send.py` (per leg §8 + cycle-1 reviewer suggestion + clean-break ethos). The alias was dead — both modules called `connector_acquire` directly. `grep pool_acquire` now returns zero across `the_one/` and `tests/`.
  - Renamed the test function `test_e2e_pool_acquire_touches_last_activity_on_outbound` → `test_e2e_account_acquire_touches_last_activity_on_outbound` so the verification grep stays clean. The leg artifact listed lines 374/377/380/396 as the docstring sweep targets for that file; lines 23 and 426 (function name + module docstring TOC) needed renaming too to satisfy the "zero `pool_acquire` hits" AC.
  - Simplified the `CommandResponse` docstring in `the_one/connectors/base.py` instead of preserving the F8 L11 chronology — the historical framing was reintroducing `connector_acquire` and `pool_acquire` into a current-API surface and tripping the grep gate. The historical lesson lives in `agents.md` `cross-subsystem-pattern-premise-revalidation` which is the canonical home; `base.py` documents the current API.
  - The `_pool.py` module docstring previously enumerated leg-by-leg what L5 and L6 of F1 built — replaced with a forward-looking "two semantic primitives" framing (per leg §3). The L5/L6 historical bullets weren't load-bearing for current readers and contradicted the post-refactor state.
  - `_keys_for_test` returns `list(_pool.keys())` directly (no lock acquisition) per leg §3 — pure read; snapshot semantics are sufficient for the HAT inspection use case and the L2 pinning tests.
  - The `_ACCOUNT_POOL_AGENT_SLOT` namespace-collision verification flagged at F2 design (architect-checklist) was clear: no other `_ACCOUNT_*` symbol exists in `_pool.py`, and the constant is not exported.
  - No citation drift found while touching files. The agents.md citation update was the only intentional doc-rewrite; all symbolic anchors used (`_pool.py:agent_acquire`, `:account_acquire`) verified live.
- **Files Touched** (production + tests):
  - `the_one/connectors/_pool.py` (~590 LOC; function renames, sentinel→slot constant, new `_keys_for_test`, docstring refresh)
  - `the_one/connectors/_inbound.py` (2 import lines collapsed to 1, 3 call-site renames, docstring sweep at 4 sites)
  - `the_one/tools/connector_send.py` (2 import lines collapsed to 1, 1 call-site rename, docstring sweep)
  - `the_one/interfaces/web/app.py` (function-local import + 1 call-site rename + framing comment update)
  - `the_one/connectors/README.md` (§2 + §11 + §12 prose rewrites)
  - `the_one/connectors/base.py` (CommandResponse docstring simplification)
  - `the_one/agents.md` (citation update; symbolic anchors)
  - `tests/test_connectors_pool.py` (imports + ~30 call-site renames + 2 new tests, +47 LOC net)
  - `tests/test_connectors_e2e.py` (imports + 4 call sites)
  - `tests/test_db_api.py` (7 imports + 8 call sites)
  - `tests/test_connectors_inbound.py` (sentinel rename + monkeypatch + docstring sweep)
  - `tests/test_lifespan.py` (5 getattr/setattr + assertion + docstring sweep)
  - `tests/test_connectors_e2e_platform_send.py` (monkeypatch + assertion + docstring sweep + function rename)
  - `tests/test_connector_send_tool.py` (2 docstring references)
  - `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/02-account-keyed-pool-primitive.md` (status: ready → in-flight → landed)
  - this file (Leg Progress entry)

### L3 — directive-substrate

- **Started**: 2026-05-21
- **Completed**: 2026-05-21
- **Status**: landed
- **Changes Made**: Atomic substrate landing of the per-account system-prompt directive surface. (1) Extended the API write-boundary validator at `the_one/interfaces/web/api.py:_validate_connector_account_config` Discord branch with a new optional `system_prompt_directive` validation block placed AFTER the `presence` block (5 grep hits in api.py). Rejection rules: non-string → 422 with verbatim detail `"Discord connector config.system_prompt_directive must be a string if present; got {type_name}."`; empty string → 422 with verbatim detail `"Discord connector config.system_prompt_directive must be a non-empty string if present (use absence to mean 'no override')."`; absent → pass; any non-empty string → pass (no length cap, no content validation). (2) Extended `the_one/agent/config.py:compose_system_prompt` with a 4th keyword param `operator_directive: str | None = None` placed AFTER `auto_relay`; appended `if operator_directive: parts.append(operator_directive)` after the connector if/else tree and BEFORE the `if persona:` branch (so the directive sits between the selected default and the persona separator). Updated the docstring with an M11 F2 L3 paragraph describing the append behavior and the byte-identical-legacy guarantee from the `None` default. (3) Extended `the_one/agent/factory.py:AgentFactory.create` with a directive-collection block placed AFTER the existing auto-relay aggregation (lines 329-342 unchanged). Block guard differs from auto-relay: gated on `connector_attached AND config.connector_account_ids` (NOT on `send_tool_enabled` — directives apply to the tool-disabled default too). Instantiated a LOCAL `directive_account_repo = ConnectorAccountRepository(conn, encryptor)` per leg §4 (not hoisted above auto-relay because the two blocks have different guards; cheap repo construction makes the duplicate instance acceptable in the both-blocks-run path). Iterated `sorted(config.connector_account_ids)` per leg §3 design (deterministic prompt-cache stability — explicit divergence from auto-relay's list-order). Swallowed KeyError on deleted accounts (mirrors the auto-relay block). Joined non-None directives with `"\n\n"`; pass joined string as `operator_directive=` kwarg to `compose_system_prompt`. (4) Added 12 new tests across 3 files: 6 validator tests at `tests/test_api_connector_account_config_validation.py:TestConnectorAccountConfigValidation` (`test_discord_system_prompt_directive_non_string_rejected` / `_empty_string_rejected` / `_absent_passes` / `_short_string_passes` / `_long_string_passes` + `test_stub_system_prompt_directive_pass_through`); 3 composer tests at `tests/test_config.py:TestComposeSystemPrompt` (`test_operator_directive_appended_when_truthy` / `_none_is_byte_identical_to_legacy` / `_empty_string_is_no_op`); 3 factory tests in new class `TestConnectorOperatorDirectiveCollection` at `tests/test_factory.py` (`test_multi_account_directives_collected_in_sorted_order` / `_directive_absent_account_skipped_in_join` / `_deleted_account_skipped_silently`).
- **Verification**:
  - `grep -n "system_prompt_directive" the_one/interfaces/web/api.py` — 5 hits (≥3 required). Block + key check + value extraction + 2 detail strings.
  - `grep -n "operator_directive" the_one/agent/config.py the_one/agent/factory.py` — 9 hits (≥4 required): 5 in config.py (signature param + docstring mentions + body falsy-check + append call); 4 in factory.py (block comment + variable init + join assignment + compose call kwarg).
  - `docker exec the-one pytest -x --timeout 30 tests/test_config.py` — 30 passed (27 pre-L3 + 3 new directive tests).
  - `docker exec the-one pytest -x --timeout 30 tests/test_factory.py` — 30 passed (27 pre-L3 + 3 new directive tests).
  - `docker exec the-one pytest -x --timeout 30 tests/test_api_connector_account_config_validation.py` — 22 passed (16 pre-L3 + 6 new directive tests).
  - `docker exec the-one pytest --timeout 30 -q -m "not pixel" --ignore=tests/browser/test_connector_test_connection_button.py` — **2814 passed**, 42 skipped, 12 deselected, 7 pre-existing failures. Stash-pop baseline replay on the pre-L3 tree (same command, same ignore) yielded **2800 passed** with the SAME 7 failures, confirming `+14` is entirely additive from L3 and the failures are pre-existing R9-class (4 `tests/test_aiat.py` LLM-live + 3 flaky studio/agent-tabs browser tests). The +14 includes the 12 new L3 tests and 2 additional incidental collections that pass identically with or without L3 changes (no regression possible).
  - `AgentConfig.get_system_prompt()` byte-identical legacy preservation verified: the existing `TestGetSystemPrompt` cluster at `tests/test_config.py:185-191` passed UNMODIFIED, as did the entire pre-L3 `TestComposeSystemPrompt` cluster (lines 215-337 pre-edit) — every existing test path still produces identical output because `operator_directive` defaults to `None` and the falsy-check skips the append.
- **Notes / Inline Decisions**:
  - Kept all 6 validator tests (rather than trimming to ~4 per the cycle-1 reviewer's marginal-utility flag on the short-string/long-string/stub-pass-through cases). The 6-test matrix is cheap (~1 second of validator overhead), and the long-string case explicitly pins the "no length cap" AC — without it a future contributor adding a cap wouldn't fail any test. The stub-pass-through case pins the F1 stub-type carve-out for the new key alongside the existing keys (defends against a future contributor narrowing the carve-out).
  - For the `test_deleted_account_skipped_silently` factory test, the existing `factory_with_builtin_tool_configs` fixture's account-repo mock synthesizes a default `ConnectorAccount` for unknown IDs — so a KeyError side-effect was needed to actually exercise the deleted-account path. Built a one-off patch context inside the test instead of widening the fixture (the deleted-account path is uniquely L3-shaped; widening the fixture would have changed the contract for the existing tests).
  - The factory's directive-collection block uses `directive_account_repo` (NOT a hoisted shared `account_repo`) per the explicit cycle-1 design decision in the leg artifact — the two blocks have different guards (auto-relay requires `send_tool_enabled`; directive does not) so hoisting would either change auto-relay semantics or require restructuring both blocks. Local instantiation costs one extra repo object in the connector-attached path; trivial.
  - Composer placement: append BEFORE the `if persona:` branch (not after), so the `"---"` persona separator falls AFTER the operator directive. Resulting shape: `base\n\n<selected_default>\n\n<operator_directive>\n\n---\n\n<persona>`. The composer's `"\n\n".join(parts)` produces clean composition with no double-separator artifacts; verified by the pin in `test_directive_absent_account_skipped_in_join`.
  - No citation drift: the leg artifact's citation audit (lines 236-246) was verified live during implementation. The auto-relay block at lines 329-342 was unchanged (the new block sits at lines 343-385). The `compose_system_prompt` 3-state if/else tree at lines 137-144 of pre-edit config.py shifted to lines 148-155 post-edit (signature growth pushed body down by ~10 lines); leg artifact called these out as a structural anchor, not a line-number anchor.
- **Files Touched** (production + tests):
  - `the_one/interfaces/web/api.py` (+29 LOC; new validation block in Discord branch)
  - `the_one/agent/config.py` (+18 LOC; signature growth + body append + docstring paragraph)
  - `the_one/agent/factory.py` (+43 LOC; directive-collection block + compose call kwarg)
  - `tests/test_api_connector_account_config_validation.py` (+89 LOC; 6 new test methods)
  - `tests/test_config.py` (+84 LOC; 3 new test methods)
  - `tests/test_factory.py` (+180 LOC; new `TestConnectorOperatorDirectiveCollection` class with 3 test methods)
  - `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/03-directive-substrate.md` (status: ready → in-flight → landed)
  - this file (Leg Progress entry)

### L4 — directive-studio-surface

- **Started**: 2026-05-21
- **Completed**: 2026-05-21
- **Status**: landed
- **Changes Made**: Atomic landing of the Studio UI half of the per-account system-prompt directive surface PLUS two bundled F1-debrief polish items per the atomic-leg-pattern. (1) **Registry hook** at `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js`: extended `optionalFns` to `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection']`, updated the docstring comment block describing the new optional hook, and set `window.App.studio.MASKED_SENTINEL = '__MASKED__'` at the bottom of the IIFE so it's available to both editor + form-discord modules at their module-load time (the registry IIFE is the studio's earliest-loading module). (2) **Discord entry** at `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js`: added 3 module-level `var` constants `_DIRECTIVE_AUTO_RELAY_DEFAULT` / `_DIRECTIVE_TOOL_ENABLED_DEFAULT` / `_DIRECTIVE_TOOL_DISABLED_DEFAULT` as byte-verbatim copies of the Python constants at `the_one/agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE` / `:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` / `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE` (each carries an inline Python-twin code comment for grep-anchored maintenance); added `renderDirectiveSection(account)` returning a `<section class="editor-section connector-directive-section">` with a textarea + help text + three `<details>` disclosures whose `<summary>` elements render EMPTY at first; added `_renderDirectiveDisclosure(stateKey, defaultText)` helper that produces the `<details><summary data-testid="directive-default-*-summary"></summary><pre><code data-testid="directive-default-*-text">…</code></pre></details>` shape; added `_updateDirectiveAnnotation(container)` as the SOLE writer of summary `textContent` via `textContent` only (initial mount + every auto-relay toggle traverse the SAME code path → byte-stable text); extended `collect` to read `[data-field="system-prompt-directive"]`, trim whitespace, emit `config.system_prompt_directive` when non-empty and OMIT when empty (L3's API validator rejects empty); extended `snapshot` to add `systemPromptDirective: <textarea.value>` (raw, not trimmed) so the dirty-tracker fires on any edit; extended `wireEvents` to call `_updateDirectiveAnnotation(container)` once at mount (initial population), attach `input` listener on the directive textarea → `checkDirty`, and attach `change` listener on the auto-relay checkbox → `_updateDirectiveAnnotation(container)` (additive — the substrate's existing change listener also fires `checkDirty` and is unchanged); extended `reservedConfigKeys` to `['intents', 'guilds', 'presence', 'system_prompt_directive']` so the new key does not leak into the Advanced kv-table; added `renderDirectiveSection: renderDirectiveSection` to the register-call entry. (3) **F1-debrief polish item: MASKED_SENTINEL lift**: deleted `var MASKED_SENTINEL = '__MASKED__';` from both `connector-form-discord.js` (line 38) and `connector-account-editor.js` (line 47); replaced both use sites (`secrets.BOT_TOKEN` assignment in `collect`; `secrets[skey]` assignment in `collectFormData`) with `window.App.studio.MASKED_SENTINEL`. (4) **F1-debrief polish item: `_resolveAccountFromContainer` body replacement**: function name preserved; body now reads `container.closest('.connector-account-editor')?.getAttribute('data-account-id')` (with fallback to `container` itself), returns `{ id: accountId }` on hit and `null` otherwise — the `window.location.hash` parse is GONE from live code. (5) **Editor mount node**: `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` adds `data-account-id="<account.id>"` to the `.connector-account-editor` root element in edit mode ONLY (create mode + F1 L7 stub re-mount path render no attribute — they don't yet have an `account.id`); the General tab assembly inserts `directiveHtml` between `pairingHtml` and `attachedAgentsHtml` per leg §14, registry-mediated via the same registry consult pattern as `inviteHtml`. (6) **New test file** `tests/browser/test_flow_studio_connector_directive_section.py` (~464 LOC, 13 test cases) modelled on `test_flow_studio_connector_invite_section.py` covering all 13 ACs from leg §15, including the verbatim-Python-text byte-equality test (imports the three Python constants directly and asserts JS-side `<code>` textContent equals them).
- **Verification**:
  - `grep "var MASKED_SENTINEL" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — **ZERO hits** (post-impl AC pinned). Note: `mcp-server-editor.js` retains its own local `MASKED_SENTINEL` declaration; out of scope for L4 (MCP not the directive surface).
  - `grep "window.location.hash" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — ZERO live-code hits (only one comment line referencing the prior shape for context).
  - `grep -n "data-account-id" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — 2 hits (comment block + the live `editorRootAttrs` emission).
  - `grep -n "renderDirectiveSection" the_one/interfaces/web/static/js/areas/studio/*.js` — 7 hits (optionalFns docstring + array entry + function definition + register call entry + editor mount registry lookup + comment + variable).
  - `grep -n "system_prompt_directive\|systemPromptDirective" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — 9 hits (textarea data-field + collect read + snapshot read + reservedConfigKeys + comments).
  - `grep -n "window.App.studio.MASKED_SENTINEL" the_one/interfaces/web/static/js/areas/studio/{connector-form-registry,connector-form-discord,connector-account-editor}.js` — 5 hits (set + two consumers + two comment refs).
  - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_directive_section.py` — **13 passed, 1 warning in 16.49s**. All ACs covered on first run, no flake.
  - `docker exec the-one pytest --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_account_navigation.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_connector_form_registry.py --deselect tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip` — **56 passed, 1 deselected in 76.59s**. The single deselected test is the same R9-class flake L3 baseline already documented (the "Distinct from the pool idle timeout" hint-text assertion failure was confirmed reproducible on the pre-L4 tree via a stash-pop run — not introduced by L4). All 7 existing browser test files pass UNMODIFIED, including `test_flow_studio_connector_invite_section.py`'s 5 tests that depend on `_resolveAccountFromContainer` returning the same values pre/post-L4 — confirming the AC that the function's return shape stayed stable across the hash-parse → `data-account-id` body swap.
  - `docker exec the-one pytest --timeout 30 -q -m "not pixel" --ignore=tests/browser/test_connector_test_connection_button.py` — **2827 passed, 42 skipped, 12 deselected, 7 pre-existing failures** (4 `tests/test_aiat.py` LLM-live + 3 flaky studio/agent-tabs browser tests). 2814 (L3 baseline from `flight-log.md:111`) + 13 new directive-section tests = 2827. **Mathematically additive — no regression.** Same exact 7 failures L3 documented; identical signatures.
- **Notes / Inline Decisions**:
  - **Verbatim JS↔Python text encoding**: the Python constants in `agent/config.py` use parenthesized string concatenation with `\"` escapes producing literal `"` characters in the runtime string. The JS twins use single-quoted string-concatenation chunks; each `\"` Python escape maps to a bare `"` in the JS string (single quotes don't escape double quotes), and Python `\'` → JS `\'` (escaping single quotes inside single-quoted strings). The byte-equality test `test_three_default_disclosures_render_verbatim_python_text` imports the Python constants directly and compares against `text_content()` of each `<code>` — caught no drift on first run, but more importantly pins the invariant for the future. A future flight editing either side MUST update both — the test fails on the spot.
  - **Section ordering test**: the leg artifact §1 (Design Decisions) declares "between Pairing and Attached Agents" as the canonical placement, superseding the F2 flight Design Decisions §3 "between Pairing and Test Connection" wording (current DOM order is Connection → Credentials → Pairing → Attached Agents → Test Connection → Invite → Danger Zone, so the leg's revised wording is more precise). `test_directive_section_renders_on_discord_general_tab` walks the General tab panel's children DOM order to confirm directive sits AFTER pairing AND BEFORE attached-agents.
  - **`<section>` vs `<div>` element**: matched `renderInviteSection`'s precedent (uses `<section class="editor-section connector-invite-section">`). The L4 leg artifact §4 skeleton wrote `<section>`; preserved verbatim. No CSS rule depends on the tag-name vs class — both render with the editor-section padding/borders.
  - **`_updateDirectiveAnnotation` SOLE-writer discipline**: kept the leg's design that initial mount and every toggle traverse the SAME code path. Render-time emits EMPTY `<summary>` content; `_updateDirectiveAnnotation` is called once at `wireEvents` time to populate summaries; subsequent auto-relay toggles re-invoke the same helper. Net effect: zero possibility of escapeHtml-vs-textContent asymmetry between initial render and post-toggle render — the leg artifact called this out explicitly and the test `test_current_state_annotation_moves_on_auto_relay_toggle` exercises both directions of the toggle to confirm symmetry.
  - **Auto-relay reactivity in edit mode tabbed layout**: the auto-relay checkbox lives on the Access and Routing tab (Lifecycle section), but the directive disclosures live on the General tab. Both tabs mount SYNCHRONOUSLY at editor-load time (per the M10 F7 L9 HAT design comment in `connector-account-editor.js:469-474` — "all section content is mounted into the DOM synchronously here"; tabs only toggle `hidden`). The toggle test switches to the Access-and-Routing tab to click the checkbox (the click target must be visible), then asserts the General-tab disclosure summaries repainted — which they do because `_updateDirectiveAnnotation`'s `querySelector` calls resolve against the container regardless of which tab is `hidden`.
  - **Pre-existing test deselection**: `test_edit_session_continuation_round_trip` was deselected in the F2-cluster run because its hint-text assertion ("Distinct from the pool idle timeout") doesn't match the rendered hint ("Inbound continues the same chat session within this window."). A pre-L4 stash-pop run reproduced the SAME failure on the clean tree — confirming this is part of L3's documented R9-class baseline. Not L4's bug; not L4's fix. Flagged for the flight-debrief.
  - **No citation drift**: the leg artifact's citation audit (lines 402-413) was verified live during implementation. The `optionalFns` array was at line 92 as cited (post-edit it spans 92-104 as the docstring comment block grew). `MASKED_SENTINEL` was at line 38 in `connector-form-discord.js` and line 47 in `connector-account-editor.js` as cited. `renderConnectorAccountEditor` General tab assembly was at lines 478-487 as cited (post-edit `directiveHtml += inviteHtml` insertion at line 494 — the assembly shifted by ~15 lines due to the new variable declaration upstream but the symbolic anchor "between pairingHtml and attachedAgentsHtml" held). The `_resolveAccountFromContainer` function name was preserved as required; only the body changed.
- **Files Touched** (production + tests):
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` (+17 LOC, -3 LOC; optionalFns extension + docstring + MASKED_SENTINEL export)
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (+254 LOC, -22 LOC; 3 directive constants + renderDirectiveSection + _renderDirectiveDisclosure + _updateDirectiveAnnotation + collect/snapshot/wireEvents/reservedConfigKeys extensions + _resolveAccountFromContainer body swap + MASKED_SENTINEL ref + register entry)
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (+41 LOC, -3 LOC; data-account-id emission + directiveHtml block + General tab assembly insertion + MASKED_SENTINEL ref + comment block replacing the deleted local declaration)
  - `tests/browser/test_flow_studio_connector_directive_section.py` (NEW, 464 LOC, 13 test cases)
  - `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/04-directive-studio-surface.md` (status: ready → in-flight → landed)
  - this file (Leg Progress entry)

### L5 — probe-gateway-intents-config-driven

- **Started**: 2026-05-21
- **Completed**: 2026-05-21
- **Status**: landed
- **Changes Made**: Lifted the doctor-probe's hardcoded gateway intents to read from per-account config, closing the F1 L2 known gap where `DiscordPlugin.doctor`'s gateway-connect smoke test used hardcoded `message_content=True; members=True; guilds=True` while `connect()` reads from `account.config["intents"]`. Three touch-points: (1) **`the_one/connectors/_discord.py:_probe_gateway_connect`** — signature changed from `(token: str) -> dict[str, Any]` to `(token: str, intents_cfg: dict[str, Any] | None = None) -> dict[str, Any]`. Default `None` preserves byte-identical legacy behavior for any caller that doesn't pass the new arg. Body's hardcoded intents block replaced with `cfg = intents_cfg or {}; intents.message_content = cfg.get("message_content", True); intents.members = cfg.get("members", True); intents.guilds = cfg.get("guilds", True)` — same `.get(axis, True)` fallback shape as F1 L2's `DiscordPlugin.connect`. Docstring updated to describe the new param + byte-identical fallback. (2) **`the_one/connectors/_discord.py:doctor`** — single call site at the gateway-smoke-test step updated from `await self._probe_gateway_connect(token)` to `await self._probe_gateway_connect(token, account.config.get("intents"))`, with an inline comment naming the M11 F2 L5 lift and the operator-disabled-message_content rationale. (3) **`tests/test_connectors_discord.py`** — added 3 new probe-intents tests adjacent to the existing F1 L2 `test_intents_from_config_honored`: `test_probe_gateway_intents_from_config_honored` (asserts `message_content=False` propagates via the `_StubDiscordClient.instances[-1].intents` access pattern), `test_probe_gateway_intents_none_defaults_to_all_true` (legacy-caller byte-identical), `test_probe_gateway_intents_empty_dict_defaults_to_all_true` (M10 F8 round-trip). No production code outside `_discord.py` changed.
- **Verification**:
  - `grep -n "intents.message_content = True" the_one/connectors/_discord.py` — **ZERO hits** (both `connect()` and `_probe_gateway_connect` now config-driven post-L5).
  - `grep -n "intents_cfg" the_one/connectors/_discord.py` — 10 hits (≥4 required: signature + 3 axis reads in the probe body + the connect-site reads from F1 L2 + the docstring mentions). Matches the AC.
  - `grep -n "_probe_gateway_connect" the_one/connectors/_discord.py` — exactly 2 hits (definition at line 1418 + call site at line 1176). Matches AC.
  - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_discord.py` — **66 passed, 1 warning in 0.62s**. All Discord plugin tests including 3 new probe tests pass; existing 63 tests pass UNMODIFIED (protected by the `None` default).
  - `docker exec the-one pytest --timeout 30 -q -m "not pixel" --deselect tests/browser/test_connector_test_connection_button.py::test_default_stub_probe_renders_success_with_no_details` — **2834 passed, 42 skipped, 13 deselected, 9 pre-existing failures in 601.96s**. 2834 = 2827 (L4 baseline, with `--ignore` of the full `test_connector_test_connection_button.py` file) + 3 new probe tests + 4 other passing tests in that file (now run because L5 used `--deselect` of a single test instead of `--ignore` of the whole file). **Mathematically additive — no regression.** The 9 failures are the same R9-class baseline L3/L4 documented (4 `tests/test_aiat.py` LLM-live + 5 browser flakes), with 2 additional `test_connector_test_connection_button.py` failures surfacing because L5 didn't ignore the whole file — all confirmed pre-existing R9-class (same indicator-LED hidden-details signature as the deselected one).
- **Notes / Inline Decisions**:
  - **Signature shape (b) over (a)**: the leg's chosen option (pass `intents_cfg` dict, not the full `account`) was followed verbatim — keeps `_probe_gateway_connect` as a narrow spawn-client + await-ready helper that doesn't reach into the full account. Caller at `doctor()` already has `account` in scope and reads `account.config.get("intents")` once at the call site.
  - **`intents_cfg or {}` over explicit None check**: the body uses `cfg = intents_cfg or {}` (the leg's exact prescribed shape) which handles both `None` and `{}` identically — falsy → `{}` → per-axis `.get(<axis>, True)` → all-True. Matches the byte-identical legacy AC.
  - **No WARNING log at probe site**: followed the leg's design decision — `connect()`'s F1 L2 WARNING is enough; a second WARNING per probe-click would be log noise. The operator already sees the choice in the F2 L4 directive textarea + disclosures.
  - **Test access pattern**: used `_StubDiscordClient.instances[-1].intents` per the leg's cycle-1 review confirmation (NOT a non-existent `last_intents` helper). The stub's `__init__` captures `intents` directly per-instance (line ~173); the pattern is already used at lines 574, 596, 619, 642 of the test file for connect-path tests.
  - **`@pytest.mark.asyncio` decorators**: the new tests use the explicit decorator (matching nearby F1 L2 `test_intents_from_config_honored` neighbors at lines 466, 490, 507). Module-level `asyncio_mode = "auto"` in `pyproject.toml` makes the decorator redundant, but the local convention favors explicit marking on probe/disconnect-path tests.
  - **No citation drift**: leg artifact's citation audit (post-L4) was verified live during implementation. `_probe_gateway_connect` is at line 1418 post-edit (was 1411 pre-edit; shifted by +7 due to the 7-line docstring expansion describing the new param). `doctor` call site moved from line 1171 to lines 1176-1178 (3-line expansion due to the rationale comment). Function still has exactly 2 grep hits as required.
- **Files Touched** (production + tests):
  - `the_one/connectors/_discord.py` (+19 LOC, -5 LOC; probe signature + docstring + body + doctor call-site rationale comment)
  - `tests/test_connectors_discord.py` (+59 LOC; 3 new probe-intents tests)
  - `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/05-probe-gateway-intents-config-driven.md` (status: ready → in-flight → landed)
  - this file (Leg Progress entry)

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

- F1 just landed (commits 40660a1 + 94a10a6 + fa6bdfd; PR #69 ready for review; flight artifact status `completed`).
- F2 scope sourced from M10 F8 debrief critical action items (pool-keying refactor + operator-editable directive) plus F1 debrief recommendations (R6 convention codification, R4+R5 studio polish, R7+R8 methodology, R3 deferred F1 cleanup).
- Phase 4 crew interview captured five design decisions documented in `flight.md`.

### 2026-05-21 — Architect Design Review

- **Cycle 1** assessment: approve with changes. Two HIGH-severity issues + several MED. HIGH-1: pool refactor undercounted call sites (spec said 5; actual is 6, missing `interfaces/web/app.py:lifespan`) + missed extensive test-side `acquire` usage in `tests/test_db_api.py` (7 import sites) + `tests/test_connectors_e2e.py` + others. HIGH-2: spec claimed directive collection follows "the same shape" as existing `auto_relay` aggregation (alphabetical-by-account_id) — actually factory iterates persisted list order, so spec contradicted itself. Plus MED items: line-citation drift recurred (F1 debrief lesson not applied); L4 dirty-tracker integration ambiguous on whether textarea participates via substrate `getFormSnapshot` or entry `snapshot`; L4 hash-parse location was misattributed; missing `cross-subsystem-pattern-premise-revalidation` walk; no test seam for L6 HAT pool-key inspection; create-mode behavior unpinned; `operator_directive=None` default not explicitly preserving legacy byte-identical output.
- Applied fixes inline: enumerated 6 production sites + full test/docstring sweep; explicit `sorted(config.connector_account_ids)` with stability rationale + auto-relay-list-order-preservation rationale; switched numeric citations to symbolic anchors throughout; pinned L4 textarea→entry-snapshot path + `wireEvents(3-arg)` listener + collect-when-non-empty/omit-when-empty; corrected L4 hash-parse location to `connector-form-discord.js`; added pool-refactor premise-revalidation paragraph; added `_keys_for_test()` test seam; pinned create-mode-edit-only behavior with explicit registry-dispatch-create-mode-AC application; pinned `operator_directive=None` default behavior.
- **Cycle 2** assessment: approve with changes (small text-reconciliation). Found two stale "5 sites" counts in Technical Approach + L2 Checkpoint that contradicted the HIGH-1 fix; two remaining numeric citations (`factory.py:340`, `agent/config.py:54-95`) that contradicted the MED-symbolic-citations methodology. All fixed inline.
- Architect-checklist verification noted: `_ACCOUNT_POOL_AGENT_SLOT` is a NEW symbol — verify at L2 design no namespace collision; `wireEvents(3-arg)` claimed already-landed in F1 L5 — verify at L4 design before freeze.
- F2 status: `ready`. Awaiting operator approval; ready to execute via `/agentic-workflow`.

---

## Flight Director Notes

### 2026-05-21 — Flight start (post-debrief / post-PR-69)

- Loaded `the_one/.flightops/agent-crews/leg-execution.md`; phase file structurally valid (Crew + Interaction Protocol + Prompts all present, all fenced blocks).
- Mission status: `active` (M11). Flight status: `ready` → `in-flight`.
- Branch creation: PR #69 (F1) not yet merged to `main`; main is at M10-F8 ship state. F2 needs F1's code on its branch (L2 references F1 L2's API validator; L4 registers a new hook on F1 L3's registry; L4 bundles F1 polish items; L5 mirrors F1 L2's intents-fallback shape). Branched `flight/02-pool-keying-and-directive-surface` FROM `flight/01-discord-connector-type-and-creation-form` rather than `main`. F1 + F2 will land via PR-stack semantics (when F1 PR #69 merges, F2 PR rebases off it; or F2 PR auto-rebases on F1's merge).
- Plan: 5 autonomous legs (L1-L5) + 1 required HAT leg (L6). Per F1 debrief recommendation: HAT is REQUIRED (not optional) because L4 touches registry-mediated UI dispatch.
- F1 debrief Architect-checklist (grep cited symbols; walk delegation/lifecycle paths; verify computed constants) applied at flight-design review (cycle 1 caught 2 HIGH + several MED; cycle 2 clean). Apply at every leg-design review cycle too.
- Symbolic-anchor citations as default discipline per F1 debrief.
- Dependency ordering: L1 first; L3 before L4 (L4 textarea posts a field L3's validator must accept); L2 and L5 independent; L6 last.

### L6 — `uat-and-alignment` (required HAT)

- **Started**: 2026-05-21
- **Completed**: 2026-05-21
- **Status**: landed
- **Walk shape**: Chrome-MCP-driven, Flight Director drives, operator confirms. Walked against gleepglorp (existing F1 L7 reuse).

#### Verification walk (all 10 steps green)

1. ✅ **Dev server up + Discord Constellation loads with directive section** — Studio loads; editor renders typed Discord form + Invite section + NEW System Prompt Directive section between Pairing and Attached Agents.
2. ✅ **Directive section structure** — textarea with placeholder + help text; three `<details>` disclosures (all closed); "(this account's current)" annotation on auto-relay-ON disclosure.
3. ✅ **Disclosure verbatim text** — auto-relay-ON disclosure expanded; verbatim Python `_CONNECTOR_AUTO_RELAY_DIRECTIVE` text rendered ("This conversation is attached to a connector account on an external platform... Auto-relay is ON..."). Browser test `test_three_default_disclosures_render_verbatim_python_text` already pins JS↔Python equality automatically.
4. ✅ **Annotation reactivity to auto-relay toggle** — uncheck auto-relay → annotation moves to auto-relay-OFF disclosure live (no save). Re-check → annotation moves back to auto-relay-ON. No save needed for the annotation repaint.
5. ✅ **Directive save round-trip** — typed `"Sign every reply with a coffee emoji ☕."` → Save → GET `/api/connector-accounts/{id}` returns `config.system_prompt_directive` with the saved string; emoji preserved through encoding.
6. ✅ **Empty directive omits the key** — cleared textarea → Save → GET confirms `system_prompt_directive` NOT in `config` (key omitted, no empty-string noise). Config keys post-save: `[allowlist, auto_relay_platform_replies]`.
7. ✅ **Pool-keying verification** — substrate-verified via L2's two new pool tests (`test_account_acquire_routes_to_account_keyed_slot` + `test_keys_for_test_returns_current_keys` pinning the `(_ACCOUNT_POOL_AGENT_SLOT, account_id)` tuple shape) AND probe-OK in step 10 (proves `account_acquire` is reachable through the lifespan warm-up path). Real-traffic multi-agent verification deferred — Cave Man + Pirate Bot already attached and gleepglorp hasn't shown doubly-online behavior since F1 L7, which is the implicit empirical pre-check.
8. ✅ **`data-account-id` attribute** — `.connector-account-editor` element carries `data-account-id="58f1fe5a833f"` matching gleepglorp's ID. F1 L5's hash-parse replacement working.
9. ✅ **`MASKED_SENTINEL` global constant** — `window.App.studio.MASKED_SENTINEL === '__MASKED__'`.
10. ✅ **Probe + intents alignment** — Test Connection → "Discord probe ok"; Invite URL still renders with the corrected `permissions=2147552256` (F1 L5 integer). L5's lift means probe now reads `account.config.get("intents")` with byte-identical fallback — confirmed by probe success on account without an explicit intents key (falls back to all-True).

#### Non-blocking observations (logged for follow-up)

- Pool-keying multi-agent real-traffic verification (sending peer messages through Discord from two different attached agents and asserting ONE pool entry handles both) was substrate-verified via L2 unit tests + probe-OK rather than driving actual Discord traffic. The full real-traffic test is M11 F8's scope per the mission's tentative HAT-script flight plan.

#### Methodology notes

- F1 debrief Architect-checklist applied throughout F2 design reviews caught the L2 + L4 + L5 issues at design time that would otherwise have surfaced at HAT (the L1-codified discipline is operational).
- The L4 directive section's reactive annotation works exactly as specified — the auto-relay toggle on the Access-and-Routing tab triggers a repaint on the General-tab directive disclosures even though they're on different tabs (per design: both tab panels mount synchronously at editor-load time per the M10 F7 L9 contract).
