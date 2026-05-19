# Leg: studio-connectors-account-surface

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

## Objective

Extend the existing Studio Connector account editor at `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` with three new sections: (i) **Pairing** — generate/copy/regenerate the pairing code; (ii) **Account-scope allowlist** — peers + channels list editors with add/remove; (iii) **Attached agents (read-only)** — summary of agents whose `connector_account_ids` includes this account, with per-agent ACL counts and deep-links to the Agent Editor's Connectors tab (leg 5). Adds an API endpoint or extension to `/api/agents` to enable the reverse lookup. Quality bar is F5 HAT-class — design tokens, accessibility, focus management, keyboard reachability.

## Context

- **Flight Design Decision — "Intra-Studio edit-surface split"** (flight.md): account-scope state (pairing code + account-scope allowlist) on the Studio Connectors detail page; per-agent ACL on the new Studio Agent Editor Connectors tab (leg 5). Plus a read-only summary of attached agents with ACL counts and deep-links on this detail page.
- **Empty-allowlist preservation** (leg 1b critical invariant): when the operator clicks "save" with no entries, the saved allowlist is `{"peers": [], "channels": []}` (lockdown), NOT absent. The UI must distinguish the empty-lockdown affordance from clearing-back-to-default. Provide a clear "no allowlist (default-permit everyone)" toggle separate from "lockdown (no peers/channels admitted)".
- **Pairing code shape** (leg 1b): `config["pairing"] = {"code": str (non-empty), "issued_at": str (ISO with T separator)}`. Leg 4 generates the code on the operator's click (server-side; not in JS). Regenerate replaces the code immediately. Pairings already made survive (their `peer_id` persists in the allowlist).
- **Reverse-lookup API**: leg 4 needs a list of agents whose `connector_account_ids` includes the current account_id. Two viable shapes:
  - (a) NEW endpoint `GET /api/connector-accounts/{id}/attached-agents` returning a small list `[{name, connector_acls_summary: {peers_count, channels_count}}, ...]`
  - (b) Extend `GET /api/agents` payload with `connector_account_ids` + `connector_acls` and filter client-side
  - **Decision**: (a). New endpoint. Rationale: `/api/agents` payload is already heavy (full AgentConfig per agent); filtering client-side scales poorly with many agents; the new endpoint shape matches the rendering need exactly.
- **Pairing code generation**: server-side, NEW endpoint `POST /api/connector-accounts/{id}/pairing-code` that generates an 8-hex-char code (mirror the existing `secrets.token_hex(4)` pattern used elsewhere), updates the account's `config["pairing"] = {"code": ..., "issued_at": now_iso()}` via the repository, and returns the new code + issued_at. The endpoint is the ONLY writer for the pairing key — the operator does not type the code (UX trade-off: shorter codes, no whitespace bugs, no typo-vs-empty ambiguity). Code is shown ONCE on generation and again on regeneration; subsequent loads of the detail page show `(generated YYYY-MM-DDTHH:MM:SS — copy from initial response or regenerate)` with a "Copy" button that copies the stored code. Pairing code stored in `config` (plaintext per leg-1b decision; the threat model is one-time low-entropy admission).
- **Studio Connectors detail page mount**: `studio.js:710` `renderConnectorAccountEditor(sectionContentEl, editingConnectorAccount, CONNECTOR_TYPES, {...})` — the existing mount site. Leg 4 widens the editor's sections without changing the mount contract.
- **Editor section pattern** (per `connector-account-editor.js:1-28`): `<div class="editor-section">` blocks with H3 headings. Leg 4 adds three sections after the existing Lifecycle section: Pairing, Allowlist, Attached Agents. The "Test Connection" and "Danger Zone" sections stay at the bottom.
- **Allowlist editor UX**: list-of-text-inputs with "Add peer" / "Add channel" buttons appending an empty row; each row has a "Remove" button. Empty rows collapse to nothing on save (trim empty strings; result is `["u1", "u2", ...]`). The "lockdown vs default-permit" toggle is a checkbox `[ ] Enable allowlist (uncheck for default-permit on this account)` that gates the peer/channel inputs.
- **Pre-existing `config` keys preservation**: the editor's current "Config (key/value)" section round-trips arbitrary `config` keys. The new Pairing + Allowlist sections operate on the RESERVED keys (`config["pairing"]`, `config["allowlist"]`). The save flow must NOT overwrite arbitrary `config` keys (e.g. `intent`) when round-tripping the reserved ones — merge on save.
- **No HAT for leg 4 by itself**: the HAT closer (leg 7) will exercise the entire Studio surface. Leg 4's tests are limited to: API endpoint integration tests (no JS unit tests — the Studio JS layer is not unit-tested in this project; F5 HAT validated visually) and a browser-test happy-path via the existing Playwright fixture if one exists. The leg accepts "no JS unit test" as the F5 precedent.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — 1008-line existing editor; leg 4 extends with 3 sections
- `the_one/interfaces/web/static/js/areas/studio.js:680-826` — mount site (`renderConnectorAccountsSection` + the editor render call at L710)
- `the_one/interfaces/web/api.py:2087-2240` — existing connector-account endpoints (GET list, GET one, POST, PUT, DELETE); leg 4 adds two new routes
- `the_one/db/models.py:ConnectorAccount.config` — leg-1b's pairing+allowlist schema
- `the_one/db/repositories.py:ConnectorAccountRepository,SQLiteAgentStore` — used by the new reverse-lookup endpoint
- `tests/test_db_api.py` — existing API tests; leg 4 extends with the two new endpoints' tests
- F5 design-language tokens — verify by reading the existing editor's class names

## Outputs

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — three new section renderers (Pairing, Allowlist, AttachedAgents), data collection extensions in `collectFormData` for the allowlist toggle + lists, new event handlers for generate/regenerate-code button, allowlist add/remove rows
- `the_one/interfaces/web/api.py` — two new endpoints: `POST /api/connector-accounts/{id}/pairing-code` (generate/regenerate) and `GET /api/connector-accounts/{id}/attached-agents`
- `tests/test_db_api.py` — integration tests for the two new endpoints (≥6 tests covering generate, regenerate-invalidates-old, attached-agents-empty, attached-agents-populated, attached-agents-includes-acl-counts, error paths)
- The flight log gains a leg-4 entry

## Acceptance Criteria

- [ ] `POST /api/connector-accounts/{id}/pairing-code` exists, returns `{code: str (8-hex), issued_at: iso}` on 200; updates `account.config["pairing"]` via `ConnectorAccountRepository.update`; preserves all other `config` keys; 404 on unknown account
- [ ] `GET /api/connector-accounts/{id}/attached-agents` returns `[{name: str, peers_count: int, channels_count: int}, ...]` for agents whose `connector_account_ids` includes `id`; per-agent `peers_count` and `channels_count` derive from `agent.connector_acls[id]["peers"]` and `[id]["channels"]` (both 0 when no per-agent ACL set for this account)
- [ ] `connector-account-editor.js` renders three new sections in edit mode (post-create; sections show placeholders or are hidden in create mode until first save): Pairing, Account-scope allowlist, Attached agents (read-only)
- [ ] Pairing section displays the current `issued_at` timestamp (if present) + "Generate code" / "Regenerate" button + an inline display of the newly-generated code (visible until the editor re-renders); a "Copy" affordance for the displayed code
- [ ] Allowlist section: a checkbox toggling allowlist-enabled; when enabled, two list editors (peers, channels) with add/remove buttons; when disabled, the lists are hidden and saving sends NO `config["allowlist"]` key (default-permit). When enabled with empty lists, save sends `{"peers": [], "channels": []}` (lockdown — the leg-1b empty-preservation invariant)
- [ ] Attached agents section: read-only list of `{name, peers_count, channels_count}` rows with a "Open agent" link for each (deep-link to `/#studio/agents/{name}/connectors`)
- [ ] Save flow merges `config["pairing"]` + `config["allowlist"]` with the existing arbitrary `config` keys (the editor's current key/value table) — no key is silently dropped
- [ ] F4/F5 existing tests pass byte-identically (no regression in the editor's existing Config/Credentials/Lifecycle/Test sections); F1-F3 + leg-1a/1b/1c/2/3 regression byte-identical
- [ ] `ruff check` clean on `api.py`; JS additions follow the existing editor's style (semi, var, JSDoc-light)
- [ ] Empty-list lockdown invariant tested at the API layer: PUT `{config: {allowlist: {peers: [], channels: []}}}` round-trips through `/api/connector-accounts/{id}` and the GET returns the empty lists verbatim (not absent)

## Verification Steps

- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — new + existing endpoint tests pass
- `docker exec the-one pytest -x --timeout 30` — full suite passes
- Manual smoke (cannot autonomously): the operator generates a pairing code, regenerates, edits the allowlist, sees the attached-agents list

## Implementation Guidance

1. **Add the pairing-code generation endpoint** in `the_one/interfaces/web/api.py` near the existing connector-account routes (around L2244):

   ```python
   @router.post("/connector-accounts/{account_id}/pairing-code")
   async def generate_connector_account_pairing_code(
       account_id: str,
   ) -> dict[str, str]:
       import secrets
       repo = await _connector_repo()
       try:
           account = await repo.get(account_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=...)
       code = secrets.token_hex(4)  # 8 hex chars
       issued_at = now_iso()
       account.config["pairing"] = {"code": code, "issued_at": issued_at}
       await repo.update(account)
       # Evict warm pool entries (config-only change, but pool may re-read
       # config on next acquire; safer to evict). Actually — config-only
       # change does NOT require pool eviction per F2 L6's logic; keep
       # consistent with the PUT handler's behavior (only secrets change
       # triggers eviction).
       return {"code": code, "issued_at": issued_at}
   ```

   Verify the existing PUT handler's eviction logic — pairing-code update does NOT touch secrets, so no eviction needed.

2. **Add the attached-agents endpoint** in `the_one/interfaces/web/api.py`:

   ```python
   @router.get("/connector-accounts/{account_id}/attached-agents")
   async def list_attached_agents(account_id: str) -> list[dict[str, Any]]:
       # Verify account exists (404 on miss).
       conn = await get_connection()
       async with conn.execute(
           "SELECT 1 FROM connector_accounts WHERE id = ?", (account_id,)
       ) as cur:
           if await cur.fetchone() is None:
               raise HTTPException(status_code=404, ...)
       store = SQLiteAgentStore(conn)
       names = await store.list_names()
       result = []
       for name in names:
           cfg = await store.load(name)
           if account_id in cfg.connector_account_ids:
               acl = (cfg.connector_acls or {}).get(account_id, {})
               result.append({
                   "name": name,
                   "peers_count": len(acl.get("peers", [])),
                   "channels_count": len(acl.get("channels", [])),
               })
       return result
   ```

   The N-load pattern is O(N agents) — acceptable for the operator's small agent count (<50 typically). If performance becomes a concern, add a JSON-extract query later; F10 territory.

3. **Extend `connector-account-editor.js`** with three new section renderers. Place them AFTER the Lifecycle section (search for the section heading `Lifecycle` to find the insertion point — the Test Connection section follows). The Pairing + Allowlist + AttachedAgents sections render only in edit mode (gate on whether `account.id` exists pre-save; the editor's existing pattern at the Test Connection section is the precedent).

4. **Pairing section JS** — render the existing `config.pairing` if present (show `issued_at`); render a button `[Generate code]` or `[Regenerate]` (label depends on presence). Click handler:
   - POST to `/api/connector-accounts/{id}/pairing-code`
   - On 200, show the returned `code` in a read-only input with a Copy button
   - Update local state so the next render shows the new `issued_at`

5. **Allowlist section JS** — render with the leg-1b semantics:
   - Checkbox `[x] Enable account-level allowlist` — checked when `config.allowlist` is present
   - When checked: two list editors (peers, channels), each with an add button and per-row remove buttons; existing entries pre-populated from `config.allowlist`
   - When unchecked: lists hidden; the save payload omits `config.allowlist` (default-permit)
   - Save handler: if checked, gather peer + channel lists (trim empties); set `config.allowlist = {peers, channels}`. If unchecked, DELETE `config.allowlist` from the merged config.

6. **Attached agents section JS** — fetch from `GET /api/connector-accounts/{id}/attached-agents` on editor mount (or via a "refresh" button). Render `{name, peers_count, channels_count}` rows. Each row has a link to the Agent Editor's Connectors tab — URL shape per the existing Studio routing (`#studio/agents/{name}` plus a hash-fragment for the tab; the existing routing pattern is at `studio.js:161` — leg 5 will add the `connectors` tab id).

7. **`collectFormData` extension** — the existing function gathers form fields; extend to also gather `config.pairing` (read from local state, NOT a form input — set by the pairing-code button) and `config.allowlist` (from the checkbox + list editors). Merge into `config` alongside the existing arbitrary key/value table.

8. **API integration tests** in `tests/test_db_api.py` — append a new section or new test class `TestConnectorAccountPairingCodeAndAttached`. At minimum:
   - `test_generate_pairing_code_returns_8_hex_code_and_iso_issued_at`
   - `test_generate_pairing_code_updates_account_config_pairing`
   - `test_regenerate_pairing_code_replaces_previous_code` (call twice; second response differs from first)
   - `test_generate_pairing_code_preserves_other_config_keys` (account with `config = {intent: "x"}` survives generation)
   - `test_generate_pairing_code_404_on_unknown_account`
   - `test_attached_agents_empty_when_no_agents_attached`
   - `test_attached_agents_returns_attached_with_zero_counts_when_no_acl`
   - `test_attached_agents_includes_acl_peer_and_channel_counts`
   - `test_attached_agents_404_on_unknown_account`
   - `test_put_account_with_empty_allowlist_lockdown_survives_get` (leg-1b empty-preservation invariant at the API edge)

9. **Run verification budget**:
   1. `pytest tests/test_db_api.py` — new + existing endpoint tests pass
   2. `pytest tests/test_db_repositories.py tests/test_db_migration.py` — leg-1b/1c regression byte-identical
   3. `pytest tests/test_connector_send_tool.py tests/test_connectors_inbound.py tests/test_connectors_resolver.py` — leg-1a/2/3 regression
   4. `pytest tests/test_connectors.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — F1/F3/F4/F5
   5. `pytest` — full suite
   6. `ruff check the_one/interfaces/web/api.py tests/test_db_api.py` — clean

10. **Update flight log** with leg-4 entry: section additions, endpoint shapes, attached-agents O(N) acknowledgment, leg-1b empty-preservation invariant tested at API edge, test counts. JS code is not ruff-checked; rely on existing editor style as the linter.

11. **Set leg status to `landed`**. Do NOT commit.

## Edge Cases

- **Pairing code generation on an account with NO existing `config["pairing"]`**: the endpoint creates the key. Test covers this.
- **Pairing code generation preserves `config["allowlist"]`** if present, and vice versa: both are independent reserved keys; one's modification doesn't touch the other.
- **`config` contains arbitrary non-reserved keys** (`{"intent": "guild_messages"}`): preserved across pairing-code and allowlist updates (leg-1b's schema-loose promise).
- **Operator deletes allowlist mid-pairing-flow**: a pairing peer-id was added by leg-2's dispatcher; the operator then deletes the entire allowlist via the editor. The dispatcher reads fresh state per-inbound; the peer is no longer admitted. Not a leg-4 bug.
- **Many attached agents (N>100)**: O(N) load. F10 territory if it becomes a problem.
- **Pairing-code click while editor is dirty** (unsaved changes): the generate endpoint is an independent call; the operator's other unsaved changes are NOT submitted by this click. Document via a transient banner: "Pairing code generated. Click Save to persist other changes."
- **Deep-link to leg-5's tab BEFORE leg 5 lands**: the link target is `#studio/agents/{name}/connectors` but the `connectors` tab doesn't exist yet. The Agent Editor will silently default to the General tab (existing routing fallback at `studio.js:161` whitelist). Acceptable interim — leg 5 closes the loop.
- **Empty pairing code from a malformed response**: defensive — the JS layer should validate the response shape before updating local state.
- **JSON-encode of `config` with the new reserved keys**: the existing PUT handler at `api.py:2218` round-trips via `model_validate(merged)` → leg-1b's validator fires on read AND write. Malformed leg-4 payloads surface as 422.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ~150 lines added (three new section renderers + collectFormData extension + event handlers)
- `the_one/interfaces/web/api.py` — two new endpoints (~80 lines)
- `tests/test_db_api.py` — ≥10 new tests (~250 lines)
- `the_one/interfaces/web/static/js/areas/studio.js` — UNCHANGED (mount contract untouched)
- `the_one/db/repositories.py` — UNCHANGED (consumes existing `update`)
- `the_one/db/models.py` — UNCHANGED (leg-1b schema)
- `the_one/agent/config.py` — UNCHANGED (leg-1c shape)
- The flight log gains a leg-4 entry

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT modify flight.md
- [ ] Do NOT commit (deferred-batched workflow)

## Citation Audit

Citations verified at design time:
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1-28,157,635,1007` — confirmed
- `the_one/interfaces/web/static/js/areas/studio.js:680-826,710` — confirmed
- `the_one/interfaces/web/api.py:2087-2240,2244+` — confirmed
- `the_one/db/models.py:ConnectorAccount.config` — confirmed (leg 1b schema)
- `the_one/agent/config.py:connector_acls` — confirmed (leg 1c field)
- `the_one/db/repositories.py:ConnectorAccountRepository.update` — confirmed
- `the_one/db/repositories.py:SQLiteAgentStore` — confirmed
- `tests/test_db_api.py` — confirmed (connector-account API tests)

All citations verified clean.
