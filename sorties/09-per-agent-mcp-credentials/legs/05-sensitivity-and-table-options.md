# Leg: sensitivity-and-table-options

**Status**: completed
**Flight**: [Per-agent MCP credentials](../flight.md)

## Objective
Build the two foundations the DD12 tile rewrite (leg 6) needs:
- on the server, a per-agent **sensitive flag** (`plain_names`) and a **targeted credentials route** that saves one source's overrides for one agent;
- in the control library, five generic `App.ui.keyValueTable` options: `readOnly`, `lockBy`, `onBeforeRemove`, `markerBy`/`markerLabel` and `removableBy`.

Each comes with tests and docs. The agent tile itself is unchanged in this leg.

## Context
- DD12 in `../flight.md` (with its "Mockup review changes") is the design, and the operator approved the rendered mockup on 2026-11-04 (flight log). Read DD12 first.
- The DD12 scoped design review is in the flight log ("DD12 scoped design review"); this leg follows its recommended server shape and factory options.
- Legs 1-3 and the H1 HAT fix are committed (`4b274ae4` … `53f441ef`). The behavior test passed on the leg 3 UI (`9bcc2fe4`); it is re-authored in leg 6.
- **Security-sensitive:** this leg adds a way for a per-agent credential value to be returned in clear (a non-sensitive value). Only names in `plain_names` are unmasked; `Authorization` and `bearer_token` never are. No value appears in any log line or error.
- **Control library rules** (CLAUDE.md "Control library"): every new option needs engine-parametrised contract tests (Chromium and WebKit) in `tests/browser/test_ui_key_value_table_contract.py`, the catalogue row in `docs/ui-control-inventory.md` updated (new owned classes listed), no HTML-string sinks, and disabled controls use the opaque `--btn-disabled-*` tokens, never `opacity`.

## Inputs
- Branch `sortie/09-per-agent-mcp-credentials` at `53f441ef` (plus uncommitted artifact edits: flight.md DD12, flight log, leg files).
- The HAT session instance on port 8486 and the mockup server on 8491 are running for the operator. Don't touch them.

## Acceptance Criteria

**Per-agent sensitivity (server)**
- [ ] AC1. `plain_names: list[str] | None = None` is declared on `StdioMCPOverride` and `StreamableHttpMCPOverride` (`the_one/mcp/_overrides.py`).
  - It is a plain field with no `Substitute` marker, so `MCP_OVERRIDE_CREDENTIAL_KEYS` still equals `{env, headers, bearer_token}` (a test asserts it).
  - `_tool_provider._apply_override` strips it along with `enabled_tools`/`disabled_tools` before the resolver, so a payload with only `plain_names` returns the source unchanged (test).
- [ ] AC2. Validation (`the_one/mcp/override_validation.py`, the DD2 helper and 422 shape):
  - `plain_names` must be a list of strings or `null`; otherwise 422 on `["mcp_overrides", <source>, "plain_names"]`.
  - A name equal to `Authorization` (any case, streamable-http) is refused: "An Authorization value is always sensitive."
  - Each check has a test.
- [ ] AC3. The merge (`api.py::_merge_preserved_mcp_credentials`) treats `plain_names` like the credential keys for the "nothing incoming" rule:
  - **omitted** from a present entry: keep the stored list;
  - `null`: clear it;
  - a list: replace it.

  After the `headers`/`env` merge, the result is **pruned** to names present in the merged `headers` (case-insensitive) or `env` (exact). Its order follows the merged dict.

  Tests:
  - a main-Save-shaped entry (tool filters only) keeps the stored `plain_names`;
  - a name whose value was removed drops out of `plain_names`;
  - `null` clears it.
- [ ] AC4. `_agent_response` returns the values of names in the stored `plain_names` in clear: for `headers` matched case-insensitively, for `env` exactly. Every other value is masked as today, and `bearer_token` is always masked. Tests:
  - a plain value is returned in clear;
  - a sensitive value is still masked;
  - `bearer_token` stays masked even with `Authorization` in a hand-written stored `plain_names`;
  - a plain value equal to a mask-shaped string is documented (test or comment) as dropped by the merge's `_looks_masked`, the Library's behaviour.

**Targeted credentials route (server)**
- [ ] AC5. New route `PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials`, behind the credential gate. Its body is `{"headers"|"env": {...} | null, "bearer_token": null?, "plain_names": [...] | null}` in the DD1 write shape (an unchanged sensitive name is `__MASKED__`, a removed name is left out).
  - **Refusals:**
    - an unknown agent, or a `source_id` the agent does not have attached: 404 (a clear detail sentence);
    - a self-configuration row: 422;
    - a malformed body: 422;
    - a DD2 or AC2 refusal: 422 in the `mcp_override` shape, `loc` starting `["mcp_overrides", <source name>, ...]`.
  - **What it changes:** only that source's credential keys and `plain_names`, merged against the stored entry with the same rules as the agent PUT. The entry's `enabled_tools`/`disabled_tools`, every other source's entry and every other agent field are untouched (test: a stored tool filter and another source's credentials survive). It saves through `SQLiteAgentStore` (the encrypted column).
  - **After the save:** it evicts `(name, source_id)` and deletes the agent's cache row for that source when the credential view changed, the same as the agent PUT (test: a changed key reaches a warm pool entry; a sensitivity-only change does not evict).
  - **Response:** the updated agent through `_full_agent_response` (with `mcp_tool_cache` and `notices`).
  - The route is classified in `tests/test_api_name_rule.py`.
- [ ] AC6. No value appears in any response (other than a `plain_names` value on agent responses, by design), log record or error from the new route and the `plain_names` paths. A leak test covers a refused save, a successful save and a sensitivity-only change.

**`App.ui.keyValueTable` options (control library)**
- [ ] AC7. `readOnly: true` (construct-time):
  - every input is read-only;
  - no "+ Add row", no remove cells and no remove header;
  - a `secret` column renders as plain text (no eye button, no "Stored. Type a new value…" hint), showing the row's value as given, so a caller passes the mask string or the clear value;
  - keyboard focus can still reach the read-only inputs, and their accessible names are unchanged.
- [ ] AC8. `lockBy: '<row field>'`: a row whose field is `'key'` has a read-only key input; one whose field is `'row'` has every control of that row disabled (inputs read-only, toggle and remove disabled). Rows without the field behave as today.
- [ ] AC9. `onBeforeRemove(row, index)`: when it returns `false`, the default splice is cancelled; the caller may then `setRow` instead. Focus after a cancelled remove stays on (or returns to) that row's remove button.
- [ ] AC10. `markerBy: '<row field>'` with `markerLabel` (for example "overridden"):
  - a row whose field is truthy shows a small marker pill in its key cell, using an owned class such as `ui-kv-marker`;
  - the key input references the pill through `aria-describedby`, so a screen reader announces "overridden";
  - the pill is real text, not a pseudo-element.
- [ ] AC11. `removableBy: '<row field>'`: a row whose field is `false` has its remove button disabled, with the opaque `--btn-disabled-*` look. The existing `.ui-kv .ui-kv-remove` rule must not override it (the mockup found it does today). The disabled button keeps an accessible name and is not focusable, or reads as `aria-disabled`; state which in the catalogue.
- [ ] AC12. Every new option has engine-parametrised contract tests in `tests/browser/test_ui_key_value_table_contract.py` (Chromium and WebKit), and existing contract tests pass unchanged. The `keyValueTable` row in `docs/ui-control-inventory.md` lists the new options and owned classes. `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py` and `tests/test_ui_emitted_classes.py` pass. The Library MCP editor (`mcp-env-headers.js`) is unchanged and its tests pass.

**Docs and gate**
- [ ] AC13. `the_one/agents.md`'s sortie 09 block gains `plain_names` (merge, prune, masking, the `Authorization` rule) and the targeted route. `SECURITY-MODEL.md`'s "Per-agent MCP credentials" paragraph says a per-agent value marked non-sensitive is returned in clear to the operator UI, though still encrypted at rest, and that `Authorization` and `bearer_token` are always masked. The flight log has the leg's entry.
- [ ] AC14. Gates:
  - the full `THE_ONE_TEST_NETNS=1 make test-unit` (expected skips);
  - the `contracts-controls` lane with `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`;
  - the `mcp`, `agent-tabs` and `agents` lanes (one failure that passes isolated and is logged is acceptable);
  - the static guards;
  - ruff.

## Verification Steps
- AC1-AC6: the new unit tests, plus `tests/test_db_api.py`, `tests/test_mcp_agent_credentials.py`, `tests/test_agent_mcp_tool_cache.py`, `tests/test_api_name_rule.py` and `tests/test_mcp_overrides.py`.
- AC7-AC12: `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_ui_key_value_table_contract.py -m browser`, then the `contracts-controls` lane.
- AC13: read the docs diff.
- AC14: as stated, each long run in the background, one at a time.

## Implementation Guidance
1. **Server first** (AC1-AC6):
   - In `mcp/_overrides.py`, `mcp/override_validation.py` and `mcp/_tool_provider.py`, add `plain_names`, its validation and the strip.
   - In `interfaces/web/api.py`, change the merge (plus the prune) and the masking in `_agent_response`, then add the new route. Reuse leg 1's per-source credential diff and eviction helper and leg 2's cache-row delete. Place the route beside the other `/api/agents/{name}/…` routes.
   - Check the order in `update_agent` (validation on the raw body ~404, the merge ~1445): `plain_names` refusals on the raw body are only the malformed-list and `Authorization` checks; the prune runs after the merge.
2. **Factory** (AC7-AC12) in `the_one/interfaces/web/static/js/ui/key-value-table.js`:
   - Read the whole factory and its contract test first.
   - Implement each option as a small, separable branch.
   - CSS goes in the control library's stylesheet (where the existing `ui-kv*` rules live), using tokens only.
   - Keep the Library's behaviour byte-identical when no new option is passed.
3. Docs, then gates. Run the long gates in the background and wait for their notifications.

## Edge Cases
- **`plain_names` on an entry with no `headers`/`env`:** pruned to empty, which becomes `null`.
- **Changing only the sensitivity** (same value, toggled off): the value must be re-sent in clear, because the stored value can't be sent as a mask while non-sensitive. The UI handles this in leg 6 (DD12: toggling a stored sensitive row off clears it, so the operator retypes it). The server just applies what it gets.
- **The targeted route on a source the agent does not attach:** 404. Attaching stays a main-Save action.
- **A concurrent main Save:** the main PUT sends no credential keys (leg 6), so the omitted-keeps rule preserves what the targeted route saved, including `plain_names` (AC3).
- **`readOnly` with `lockBy`/`removableBy`:** `readOnly` wins (nothing editable, no remove column).

## Files Affected
- `the_one/mcp/_overrides.py`, `the_one/mcp/override_validation.py`, `the_one/mcp/_tool_provider.py`, `the_one/interfaces/web/api.py`
- `the_one/interfaces/web/static/js/ui/key-value-table.js`, the `ui-kv*` stylesheet
- `tests/test_*.py` (new and updated), `tests/browser/test_ui_key_value_table_contract.py`, `tests/test_api_name_rule.py`
- `docs/ui-control-inventory.md`, `the_one/agents.md`, `SECURITY-MODEL.md`

## Citation Audit
From the DD12 scoped design review (flight log), read against the tree at `53f441ef`; re-check line numbers at implementation:
- `ui/key-value-table.js`: no read-only mode, column hiding, per-row key lock, marker or per-row remove override; `removeByKey` always splices; the stored-mask mode (`maskedBy`, `storedKey`, `clearOnUnmask`), the toggle column, `setRow` and `setError` exist - reported by review, unverified line numbers
- `api.py::_agent_response` (~263-276) masks each inner value; `_merge_preserved_mcp_credentials` takes non-credential keys from the body (~427) - verified in flight design
- `api.py::update_agent`: raw-body validation (~404) vs merge (~1445) order - flagged by review as to be confirmed
- `mcp-env-headers.js`: `.ui-kv .ui-kv-remove` overrides the disabled look (mockup finding) - reported, unverified

---

## Design review changes (binding; they override the AC text above where they differ)
From the Developer design review (2026-11-04), with the Flight Director's calls on its questions:

1. **AC2 gate.** `_validate_mcp_override_credentials` (`api.py:~393-406`) returns early unless `carries_credentials(incoming)` holds (`override_validation.py:~51-58`, which checks only `env`/`headers`/`bearer_token`). Widen the gate so an entry carrying `plain_names` is validated too. Make the merge's prune robust to a non-list or non-string `plain_names`, since the merge also runs when validation was skipped.
2. **AC3 details.** Only the merge branch for a present dict entry needs `plain_names` logic; the omitted and `null`-entry branches copy the stored entry as-is. The prune also runs when `plain_names` is omitted but `headers`/`env` changed (a main Save that clears a header drops its name). In `create_agent` (stored `None`) it prunes against the incoming values. It runs **before** the empty-entry check, so a leftover holding only `plain_names` doesn't keep an empty entry alive. Test: a header removed by a main Save is pruned from the stored `plain_names`.
3. **AC5, the targeted route.**
   - (a) Resolve `source_id` to the source **name** through `mcp_repo.get`, since `mcp_overrides` is keyed by name.
   - (b) Seed the incoming entry with the stored entry's non-credential keys (`{**stored_non_credential, **body}`, where non-credential means `enabled_tools`/`disabled_tools`), then merge, prune and `AgentConfig.model_validate`. Feeding the bare body to the merge would wipe the tool filters (`resolved_entry = dict(incoming_entry)`, `api.py:~560`).
   - (c) An empty resulting entry is dropped by the merge, and an empty map becomes `None`.
   - (d) **Flight Director call:** a 404 only for an unknown agent or an unknown source id. A source not (yet) in the agent's `mcp_source_ids` is accepted, so a newly switched-on server's tile can save before the main Save. An override for an unattached source is already tolerated (the merge keeps it; `_warn_orphan_overrides` is non-fatal). A self-configuration row (`is_surface_row`) is still 422.
   - (e) Reuse `_validate_mcp_override_credentials`, `_drop_surface_override`, `_evict_changed_mcp_credentials(agent_name, before=existing.mcp_overrides, after=cfg.mcp_overrides, mcp_repo)` (`api.py:~409-447`, which already deletes the cache row), `_full_agent_response`, `_agent_store()` and `_mcp_repo()`.
   - (f) Add the route to `tests/test_api_name_rule.py`'s `EXEMPT` with a reason ("sets credentials, no name"), and confirm `tests/test_credential_gate.py` and `tests/test_seam_routes_403_sweep.py` cover it.
   - (g) **Known narrow race:** a main PUT that loaded the agent before a targeted save completes can overwrite it, since both do a load-merge-save of the whole row. Accepted and documented; there is no per-agent lock in this leg.
4. **AC1 strip site.** Add `plain_names` to the tuple at `_tool_provider._apply_override` (~157-159); the resolver raises on unmarked fields. Test: an entry with only `plain_names` is not a credential override for `has_credential_override` and does not switch on `per_agent_tools`.
5. **AC4 / AC6, list route (Flight Director call).** `list_agents` goes through `_agent_response`, so it returns plain values in clear as well. That is deliberate and consistent; a test pins it and the docs say so. No other response path exposes a value (the review checked the projection, exports, rotate and `_validation_detail`).
6. **AC7 `readOnly`, guards.** With no remove column, `row.remove` is null: guard every dereference (`onInput` ~150, `renumber`, `newRow`) and skip the actions `<col>` and `<th>`. Force plain-text rendering of `secret` columns by making `isMasked()` return `false` under `readOnly` (so `rebuildSecret` and `setRow`'s `maskChanged` agree). Toggle cells are **disabled** (a checkbox can't be read-only): find the toggle factory's real disable API and use it.
7. **AC8 `lockBy: 'row'`:** inputs read-only, toggle disabled, remove disabled.
8. **New AC8b, live updates.** `setRow` patching a `lockBy`, `markerBy` or `removableBy` field re-evaluates that row's key lock, marker pill and remove state without rebuilding it, and keeps focus. Leg 6 calls `setRow({overridden: true})` after a tile Save. Contract test.
9. **AC9 focus and events.** The hook goes at the top of `removeByKey` (~395). After a cancelled remove, call `row.remove.focus()` explicitly (a click doesn't focus a button in WebKit). `onChange` does **not** fire on a cancelled remove.
10. **AC11, Flight Director call: native `disabled`** for a non-removable row's remove button (matching the existing `.btn-ghost:disabled` rules). It isn't focusable, so the row's "overridden" pill or its absence is the visible reason. CSS: add `.ui-kv .ui-kv-remove:disabled` and `:disabled:hover` rules after `components.css:~2624-2640`, with `--btn-disabled-fg` and `cursor: not-allowed`. Also add `if (rm.disabled) return;` to the delegated `onClick` (~214), since WebKit can deliver clicks on a disabled button's children.
11. **Catalogue.** Record that `markerLabel` is real DOM text linked by `aria-describedby` (a uid), and record the native-`disabled` choice.
12. **SECURITY-MODEL.md** also notes the `_looks_masked` limitation: a plain value shaped like a mask is dropped by the merge, as in the Library.
