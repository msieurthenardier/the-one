# Leg: detach-end-to-end

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Ship the operator-facing detach affordance: a DELETE endpoint that removes an account from an agent's `connector_account_ids` and releases the corresponding pool entry; a per-row detach button in the connector account editor's "Attached Agents" section; an agent-count badge on the Connector Accounts grid tile that links to the detail page.

## Context

**Why this leg.** Today, the operator detaches an agent from a connector by navigating to Studio → Agents → {agent} → Connectors tab and unchecking the connector — three clicks deep and conceptually backwards (the connector account doesn't appear to "own" the relationship even though it does, structurally). L5 brings the detach affordance to the connector account detail page where the operator already sees the attached-agents table.

**Design Decision §3 (locked at flight planning)**: detach source-of-truth is the agent-side `agents.connector_account_ids` field. The DELETE endpoint URL lives on the agent resource path — `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` — even though the UI lives on the connector detail page. URL is internal; architectural cleanliness wins.

**Design Decision §4 (locked at flight planning)**: pool primitive naming. The F8-introduced primitives are `agent_acquire(agent_name, account_id)` (line 748) and `account_acquire(account_id)` (line 830). For release, the existing private `_evict(key: tuple[str, str])` already does the work (line 341). L5 needs a PUBLIC per-(agent, account) release primitive. **Pick: `release_agent_on_account(agent_name, account_id)`** — verb-then-scope shape, matching `agent_acquire` / `account_acquire`'s noun-then-scope pattern. The alternative `evict_agent_on_account` would mirror the existing `_evict_all_for_account` (line 365) family but inherits the verb "evict" which suggests an account-credentials-rotation context rather than an operator-driven detach. Pick the cleaner public-API shape; the implementation still calls `_evict` internally.

**Pool release scope**: only the per-(agent, account) entry is released. If the same account is also warm under `account_acquire(account_id)` (i.e., the system-outbound slot keyed by the `_ACCOUNT_POOL_AGENT_SLOT` sentinel), that entry stays — other agents may still depend on the account being live. Per-agent detach evicts only the specific agent's slot.

**Audit-log**: the DELETE endpoint logs the detach event at WARNING level for operator-visible traceability without inventing a new persistence shape. Pick WARNING (not INFO) because uvicorn's default root-logger threshold filters INFO — INFO would be invisible at runtime (the comment block at `api.py:1308-1313` documents this precedent and motivated the local `_log` in that function). Future routine-maintenance can lift this into a structured audit table if F11's audit-log inspector grows a detach-event surface.

**Required side-effect of this leg**: `api.py` lacks a module-level `logger`. L5 adds `logger = logging.getLogger(__name__)` near the existing imports as a one-line companion change. (Some functions in `api.py` define their own local `_log`; that pattern is for the `app.py` precedent comment at line 1308-1313 — not a contraindication here. The module-level `logger` is the convention everywhere else in `the_one/`.)

**Idempotency**:
- DELETE on (agent, account) where the agent's `connector_account_ids` already excludes the account → 200 + the agent's current state (no-op).
- DELETE on a non-existent agent → 404.
- DELETE with a non-existent account_id (regardless of agent state) → if the agent's list contains the account id, the DELETE strips it (the row is corrupt-but-curable); if it doesn't, the call is a no-op 200. **Pick**: simpler semantics — return 200 in both cases (the post-state is the same: the account_id is not in the agent's list). 404 ONLY for unknown agent.

**Grid agent-count badge**: replace the existing `entity-tile-meta` "—" placeholder at `connector-accounts-grid.js:95` with a live count rendered as `"{N} agent{s}"` or `"no agents"`. The count comes from a new field `attached_agents_count` in the `list_connector_accounts` endpoint response (computed per row via `store.list_by_connector_account(account.id)`; O(N accounts × M agents) — acceptable for the operator's small inventory).

**CustomEvent emission** (carry-forward F7 Rec #3(c)): the detach handler emits `new CustomEvent('connector-agent-detached', {detail: {agent_name, account_id}})` on `document`. **L6 will later refactor all CustomEvent sites including this one into the shared studio-event-bus**. L5 ships the raw `document.dispatchEvent` inline; L6 lifts it. This is intentional — L5 introduces the EVENT; L6 introduces the BUS abstraction. (Per the flight's "Acceptable variation": L6 may also land before L5 if scheduling-convenient. L5 prefers L6-after to keep the inline-then-lifted refactor narrative coherent.)

**Render-without-page-reload contract**: after a successful detach, the connector detail page's "Attached Agents" section re-fetches `attached-agents` and re-renders. The Connectors grid (if the operator navigates back) re-fetches the list and re-renders. The CustomEvent is the bridge — the connectors grid's mounted state listens for it.

## Inputs

- `the_one/agent/config.py:181` — `connector_account_ids: list[str]` (source of truth).
- `the_one/agent/store.py` — `SQLiteAgentStore.list_by_connector_account(account_id)` (existing).
- `the_one/connectors/_pool.py:341-389` — `_evict(key)`, `_evict_all_for_account(account_id)` (existing private primitives).
- `the_one/connectors/_pool.py:748` — `agent_acquire(agent_name, account_id)` (existing public).
- `the_one/connectors/_pool.py:830` — `account_acquire(account_id)` (existing public).
- `the_one/interfaces/web/api.py:478-494` — `update_agent` (existing PUT endpoint mutating `connector_account_ids`).
- `the_one/interfaces/web/api.py:497-504` — `delete_agent` (precedent for DELETE-on-agent shape).
- `the_one/interfaces/web/api.py:2359-2363` — `list_connector_accounts` (where the count gets added).
- `the_one/interfaces/web/api.py:2692-2785` — `list_attached_agents_for_connector_account` (refetch target after detach).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2827-2896` — `renderAttachedAgentsList` (where the detach button lands).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2898+` — `fetchAttachedAgents` (the refetch helper after detach).
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js:84-98` — tile rendering (where the badge replaces `"—"`).
- `tests/test_db_api.py` — API endpoint test patterns.
- `tests/test_connectors_pool.py` — pool primitive test patterns.
- `tests/browser/test_flow_*.py` — browser test patterns for the new detach UI.

## Outputs

- `the_one/connectors/_pool.py` — new public `release_agent_on_account(agent_name, account_id)` async function wrapping `_evict((agent_name, account_id))`. Idempotent (mirrors `_evict`).
- `the_one/interfaces/web/api.py` — new endpoint `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` (404 on unknown agent; 200 idempotent otherwise; calls pool release after the store mutation). Extends `list_connector_accounts` response with `attached_agents_count` per row.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `renderAttachedAgentsList` adds a "Detach" button per agent row; click handler issues the DELETE + on-success refetches the list + dispatches `connector-agent-detached` CustomEvent.
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` — tile rendering reads `account.attached_agents_count` (new field) and renders it in the `entity-tile-meta` slot.
- `the_one/interfaces/web/static/css/studio.css` — small CSS additions for the detach button and the grid meta-count style (if not already covered by existing classes; check `.btn-outlined-secondary` / `.btn-link-danger` precedents first).
- `tests/test_db_api.py` — new tests for the DELETE endpoint (or new test file `tests/test_api_agent_connector_detach.py`).
- `tests/test_connectors_pool.py` — new tests for `release_agent_on_account` (idempotent; releases only the specified slot; doesn't touch `account_acquire`'s slot or other agents' slots).
- `tests/browser/test_flow_connector_account_detach.py` — NEW browser test for the detach button + the grid badge.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L5 progress entry.

## Acceptance Criteria

- [ ] `the_one/connectors/_pool.py` exports `release_agent_on_account(agent_name: str, account_id: str) -> None` (async). Implementation: `await _evict((agent_name, account_id))`. Idempotent on missing key (inherits `_evict`'s contract).
- [ ] `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` exists with:
  - 404 when `agent_name` is unknown.
  - 200 + the updated agent JSON when the agent's `connector_account_ids` contains `account_id` (account_id removed from the list; pool slot released).
  - 200 + the agent JSON when the agent's `connector_account_ids` does NOT contain `account_id` (idempotent no-op; pool release still attempted, idempotent on missing key).
  - On success, the response body matches the existing `PUT /api/agents/{name}` shape (agent config dict via `cfg.model_dump()`).
- [ ] `list_connector_accounts` response items each carry an `attached_agents_count: int` field reflecting the count of agents whose `connector_account_ids` includes the account.
- [ ] The connector account editor's `renderAttachedAgentsList` renders a Detach button per agent row with `data-testid="connector-attached-agent-detach-{name}"`.
- [ ] Clicking Detach:
  - Issues `fetch('/api/agents/{name}/connector-accounts/{account_id}', {method: 'DELETE'})`.
  - On 200: re-fetches `attached-agents` and re-renders the section; dispatches `new CustomEvent('connector-agent-detached', {detail: {agent_name, account_id}})` on `document`.
  - On non-200: surfaces an inline error in the section (use the existing "Could not load…" placeholder shape, or a transient row-level error message).
- [ ] The Connectors grid tile renders `{N} agent{s}` (singular/plural) or `No agents` in the `entity-tile-meta` slot. The grid also listens for the `connector-agent-detached` CustomEvent and re-fetches `list_connector_accounts` on receipt (or the operator's next navigation back — whichever shape matches existing grid-mount conventions).
- [ ] No-page-reload: after detach, the detail page's "Attached Agents" section updates without a full reload, and the grid count updates on the operator's next return to it (via the CustomEvent listener OR the natural re-fetch on grid mount — whichever is simpler).
- [ ] New tests:
  - Pool: `release_agent_on_account` evicts the specific (agent, account) entry; leaves other entries alone; idempotent on missing key.
  - API: DELETE on (agent, account) where the account is in the list → 200, account removed, pool slot released.
  - API: DELETE on (agent, account) where the account is NOT in the list → 200 (idempotent no-op).
  - API: DELETE on unknown agent → 404.
  - API: `list_connector_accounts` response includes `attached_agents_count` matching the actual count.
  - Browser: navigate to a connector account detail page with attached agents; click Detach on one row; verify the row disappears (or the section re-renders) and the agent's `connector_account_ids` no longer contains the account (verify via direct API GET).
  - Browser: navigate to the Connectors grid; verify the agent-count badge renders the expected count for a seeded account with N attached agents.
- [ ] Existing tests pass unchanged.

## Verification Steps

```bash
# Pool tests
docker exec the-one pytest tests/test_connectors_pool.py -k "release_agent_on_account" -x --timeout 30 -v

# New API endpoint tests
docker exec the-one pytest tests/test_db_api.py -k "detach or attached_agents_count" -x --timeout 30 -v

# Existing API tests stay green
docker exec the-one pytest tests/test_db_api.py -x --timeout 30

# Pool regression
docker exec the-one pytest tests/test_connectors_pool.py -x --timeout 30

# Browser tests
docker exec the-one pytest tests/browser/test_flow_connector_account_detach.py -x --timeout 120 -v
docker exec the-one pytest tests/browser/test_flow_chat_pending_approval.py tests/browser/test_flow_chat_peer_attribution.py -x --timeout 120 -v

# Full suite (post-L4 baseline: 2712)
docker exec the-one pytest --timeout 120 -q
```

Expected: green; suite count rises by ~9-10 (2-3 pool tests + 4-5 API tests + 2 browser tests).

## Implementation Guidance

### Sub-step A — Pool release primitive

Edit `the_one/connectors/_pool.py`. Add after `_evict_all_for_account` (line 388):

```python
async def release_agent_on_account(agent_name: str, account_id: str) -> None:
    """Release the per-(agent, account) pool entry, if any.

    M11 F9 L5 — operator-driven detach. Idempotent on missing key
    (inherits :func:`_evict`'s contract). Releases ONLY the specified
    slot; if the account is also warm under
    :func:`account_acquire` (system-outbound), that entry stays — other
    agents may still depend on the account being live.

    Public counterpart to :func:`_evict_all_for_account` (which evicts
    every slot for the account, e.g. on credentials rotation). The
    per-slot scope here is appropriate for operator-driven detach where
    only one agent is being disconnected.
    """
    await _evict((agent_name, account_id))
```

### Sub-step B — DELETE endpoint + grid response augmentation

Edit `the_one/interfaces/web/api.py`:

1. Add the DELETE endpoint after `update_agent` (line 494) or after `delete_agent` (line 504), wherever the agent-resource endpoints cluster:

```python
@router.delete("/agents/{agent_name}/connector-accounts/{account_id}")
async def detach_agent_from_connector_account(
    agent_name: str,
    account_id: str,
) -> dict[str, Any]:
    """Detach a connector account from an agent.

    M11 F9 L5 — operator-driven detach. Removes ``account_id`` from
    ``agents.connector_account_ids`` (idempotent — missing entry is a
    no-op), then releases the per-(agent, account) pool slot.

    Returns the agent's updated config JSON (same shape as PUT). 404
    only on unknown agent; missing account_id is a 200 no-op (the
    post-state is the same: account_id is not in the agent's list).
    """
    from the_one.agent.config import AgentConfig
    from the_one.connectors._pool import release_agent_on_account

    store = await _agent_store()
    try:
        cfg = await store.load(agent_name)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Agent not found: {agent_name}"
        )

    if account_id in cfg.connector_account_ids:
        new_ids = [a for a in cfg.connector_account_ids if a != account_id]
        cfg = cfg.model_copy(update={"connector_account_ids": new_ids})
        # No model_validate round-trip — model_copy returns a validated
        # AgentConfig. The PUT endpoint's model_validate is for untrusted
        # client JSON; here the input is already a model.
        await store.save(cfg)
        logger.warning(
            "detach_agent_from_connector_account: removed %s from %s.connector_account_ids",
            account_id,
            agent_name,
        )

    # Always attempt pool release — idempotent on missing key.
    await release_agent_on_account(agent_name, account_id)

    return cfg.model_dump()
```

Add `logger = logging.getLogger(__name__)` near the existing top-of-file imports in `api.py` (verified absent at design time per the cycle-1 review; this is a required side-effect, not conditional). Also extend the existing `import logging` statement if it's not already imported.

2. Augment `list_connector_accounts` (line 2359):

```python
@router.get("/connector-accounts")
async def list_connector_accounts() -> list[dict[str, Any]]:
    repo = await _connector_repo()
    accounts = await repo.list()
    store = await _agent_store()
    results = []
    for account in accounts:
        response = _connector_account_response(account)
        attached = await store.list_by_connector_account(account.id)
        response["attached_agents_count"] = len(attached)
        results.append(response)
    return results
```

Do NOT add the count to the single-get / create / update responses; the grid is the only consumer. If a future surface needs it, add then.

### Sub-step C — Editor detach button + click handler

Edit `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`:

1. **Change `renderAttachedAgentsList`'s signature** from `(container, rows, account)` to `(container, rows, account, checkDirty, recaptureSnapshot)`. Single call site is inside `fetchAttachedAgents` at line ~2921; both `checkDirty` and `recaptureSnapshot` are already in `fetchAttachedAgents`'s param list — pass them through (one-line change at the call site). The new parameters are needed by the detach-click closure to chain into the post-refetch dirty-tracker recapture.

2. **Extend `renderAttachedAgentsList`** (line 2869-2895) — add a fourth `<th>` column AND a fourth `<td>` per row with a Detach button. Snippet (within the existing for-loop at line 2877):

```javascript
html += '<td class="connector-attached-agent-actions">' +
  '<button type="button" class="btn-link-danger connector-attached-agent-detach-btn" ' +
  'data-testid="connector-attached-agent-detach-' + escapeAttr(name) + '" ' +
  'data-agent-name="' + escapeAttr(name) + '" ' +
  'data-account-id="' + escapeAttr(account.id) + '">Detach</button>' +
  '</td>';
```

Insert a fourth `<th></th>` (for the detach action column) immediately before the existing `</tr></thead>` close at line 2875.

3. **Wire click handlers** after `listEl.innerHTML = html;` at line 2895 — attach event listeners to all detach buttons:

```javascript
var detachBtns = listEl.querySelectorAll('.connector-attached-agent-detach-btn');
for (var b = 0; b < detachBtns.length; b++) {
  (function (btn) {
    btn.addEventListener('click', function () {
      var agentName = btn.dataset.agentName;
      var accountId = btn.dataset.accountId;
      if (!agentName || !accountId) return;
      btn.disabled = true;
      btn.textContent = 'Detaching…';
      var url = '/api/agents/' + encodeURIComponent(agentName) +
        '/connector-accounts/' + encodeURIComponent(accountId);
      fetch(url, {method: 'DELETE'})
        .then(function (resp) {
          if (!resp.ok) {
            btn.disabled = false;
            btn.textContent = 'Detach';
            // Inline error — replace section content with a recoverable error
            // and a Retry affordance. Simplest: log + leave the row in error
            // state; operator can re-click. Matches the F8-era pattern of
            // not-introducing-a-toast-system.
            var listEl = container.querySelector('[data-testid="connector-attached-agents-list"]');
            if (listEl) {
              var errEl = document.createElement('div');
              errEl.className = 'form-hint connector-attached-agent-detach-error';
              errEl.textContent = 'Detach failed (HTTP ' + resp.status + '). Click Detach again to retry.';
              listEl.appendChild(errEl);
            }
            return;
          }
          // Success: re-fetch the section + dispatch the CustomEvent.
          fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot);
          document.dispatchEvent(new CustomEvent('connector-agent-detached', {
            detail: {agent_name: agentName, account_id: accountId},
          }));
        })
        .catch(function (e) {
          btn.disabled = false;
          btn.textContent = 'Detach';
          // Same error treatment as non-200.
        });
    });
  })(detachBtns[b]);
}
```

All four closure references (`container`, `account`, `checkDirty`, `recaptureSnapshot`) are in scope after the signature extension in step 1. The refetch via `fetchAttachedAgents(container, account, checkDirty, recaptureSnapshot)` re-uses the existing helper without changes.

### Sub-step D — Connectors grid badge

Edit `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js`:

1. **Replace the entity-tile-meta** at line 95:

```javascript
var attachedCount = (typeof a.attached_agents_count === 'number') ? a.attached_agents_count : 0;
var metaText = attachedCount === 0
  ? 'No agents'
  : (attachedCount + ' agent' + (attachedCount === 1 ? '' : 's'));
html += '<span class="entity-tile-meta">' + escapeHtml(metaText) + '</span>';
```

(The exact wording can vary — match existing copy conventions if any exist for similar tiles.)

2. **Listen for the CustomEvent** to refresh on detach. The precedent for this codebase is `connectors-tab.js:73` — module-level `document.addEventListener` installed ONCE at IIFE init, never torn down (the file's own comment explicitly explains why per-render registration would leak handlers). Match that pattern.

   Placement: the listener lives in `studio.js` (NOT in `connector-accounts-grid.js`), because `studio.js` owns `fetchConnectorAccounts_` — the function that fetches the list and feeds the grid. The grid render module only knows how to render an already-fetched list. Install at module init in `studio.js`:

   ```javascript
   document.addEventListener('connector-agent-detached', function () {
     // If the Connectors grid is currently mounted, re-fetch + re-render.
     // Pattern: read whatever flag/state studio.js uses to know which area
     // is mounted, then call the existing fetch+render path.
     if (currentArea === 'connector-accounts') {  // adjust per actual studio.js state
       fetchConnectorAccounts_();
     }
   });
   ```

   Inspect `studio.js` first to find the current-area state and the fetch entrypoint; mirror the existing pattern. NO teardown is needed (matches `connectors-tab.js:73` precedent).

### Sub-step E — CSS

Edit `the_one/interfaces/web/static/css/studio.css`. The classes used in Sub-step C / D:
- `.btn-link-danger` — check if exists; if not, add a minimal rule:

```css
.btn-link-danger {
  background: transparent;
  border: 1px solid transparent;
  color: var(--fg-error, #c33);
  cursor: pointer;
  padding: 2px 8px;
  text-decoration: underline;
}
.btn-link-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

- `.connector-attached-agent-actions` — likely doesn't need explicit CSS (inherits `<td>` defaults). Add only if alignment quirks emerge.
- `.connector-attached-agent-detach-error` — minimal:

```css
.connector-attached-agent-detach-error {
  color: var(--fg-error, #c33);
  margin-top: 8px;
}
```

Reuse `.entity-tile-meta` for the grid badge — it already exists per the current `—` placeholder usage; the change is just the text content.

### Sub-step F — Tests

**Pool test** (in `tests/test_connectors_pool.py`):

```python
class TestReleaseAgentOnAccount:
    """M11 F9 L5 — public per-(agent, account) release primitive."""

    async def test_release_agent_on_account_evicts_specific_slot(self):
        # Acquire two distinct entries (agent-A/acc-1 and agent-B/acc-1);
        # call release_agent_on_account("agent-A", "acc-1"); verify only
        # the agent-A slot is gone (using _keys_for_test).
        ...

    async def test_release_agent_on_account_idempotent_on_missing_key(self):
        # Call release_agent_on_account on a slot that was never acquired.
        # Verify no error.
        ...

    async def test_release_agent_on_account_does_not_touch_account_slot(self):
        # Acquire via account_acquire (uses _ACCOUNT_POOL_AGENT_SLOT sentinel);
        # call release_agent_on_account("real-agent-name", account_id);
        # verify the account_acquire-keyed slot is still warm.
        ...
```

Use the existing pool-test fixture pattern in `test_connectors_pool.py`.

**API tests** (in `tests/test_db_api.py`, new class `TestAgentConnectorDetach`):

1. `test_detach_removes_account_from_agent_connector_account_ids` — seed agent + connector; PUT the agent with the connector attached; DELETE; verify GET of the agent shows the account removed.
2. `test_detach_idempotent_on_already_detached` — agent's `connector_account_ids` empty; DELETE; 200; agent state unchanged.
3. `test_detach_unknown_agent_returns_404` — DELETE against bogus agent name; 404.
4. `test_detach_releases_pool_slot` — acquire the (agent, account) slot via the pool; DELETE; verify the slot is no longer in `_keys_for_test`. Skip if pool-test fixtures are too heavy to wire here; the pool tests above cover the primitive.
5. `test_list_connector_accounts_includes_attached_agents_count` — seed 2 accounts; attach agent-A to account-1 only; GET /api/connector-accounts; verify response[0]["attached_agents_count"] == 1; response[1] == 0.

**Browser test** (`tests/browser/test_flow_connector_account_detach.py`):

1. `test_detach_button_removes_agent_from_attached_list` — seed connector account + an agent attached to it; navigate to the detail page; click the Detach button; verify the row disappears from the "Attached Agents" table; verify (via /api/agents/{name} GET inside the test) that `connector_account_ids` no longer contains the account.
2. `test_connectors_grid_displays_attached_agents_count` — seed THREE accounts: one with 2 attached agents (expect `"2 agents"`), one with 1 (expect `"1 agent"` — singular form), one with 0 (expect `"No agents"`). All three forms tested in one navigation.

Mirror `test_flow_chat_pending_approval.py` fixture / seeder shape.

### Sub-step G — Flight log

Append to `flight-log.md`:

```
### {date} — L5 detach-end-to-end (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `the_one/connectors/_pool.py` — added public `release_agent_on_account(agent_name, account_id)` wrapping `_evict`.
- `the_one/interfaces/web/api.py` — added `DELETE /api/agents/{agent_name}/connector-accounts/{account_id}` endpoint; extended `list_connector_accounts` response with `attached_agents_count` per row.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `renderAttachedAgentsList` adds a Detach button per row; click handler issues DELETE, on success re-fetches the section and dispatches `connector-agent-detached` CustomEvent.
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` — tile renders `attached_agents_count` in `entity-tile-meta`; grid mount listens for the CustomEvent to refresh.
- `the_one/interfaces/web/static/css/studio.css` — minimal additions for `.btn-link-danger` and the detach-error message styling (if not already present).
- `tests/test_connectors_pool.py` — added `TestReleaseAgentOnAccount` (3 tests).
- `tests/test_db_api.py` — added `TestAgentConnectorDetach` (4-5 tests).
- `tests/browser/test_flow_connector_account_detach.py` — NEW (2 tests).

**Test outcomes**: new tests pass; pre-existing pool + API + browser tests pass unchanged. Suite count: 2712 → {N}.

**Anomalies**: {document any}
```

## Edge Cases

- **Agent has the account_id listed but the pool slot was never acquired** — `release_agent_on_account` is idempotent on missing key; no error. Same disposition as the slot-was-evicted-by-reaper-already case.
- **Concurrent detach: two browser windows click Detach for the same (agent, account) simultaneously** — first wins (mutation persists); second sees the account is already absent → idempotent 200 no-op. Both UIs re-fetch and render the same final state.
- **Operator detaches the LAST connector from an agent** — `connector_account_ids` becomes empty list `[]`. The agent's `is_connector_attached` derived state at `factory.py:307` flips to False. Per-agent behavior in the connector subsystem (mentions-aware, etc.) routes the agent as operator-only on next session.
- **Operator detaches an agent that was in the middle of processing an inbound message** — the inbound dispatcher's per-session lock holds; the in-flight turn completes before the next inbound. The detach happens between turns. The dispatcher's `list_by_connector_account` call at step 4 will exclude the detached agent on the next inbound. No race-condition surface within a single turn.
- **DELETE called with a malformed (non-string-coerceable) account_id in the URL** — FastAPI's path-parameter validation kicks in; non-string would 422. Cosmetic edge case; not addressing here.
- **`store.list_by_connector_account` is slow with many agents** — O(N agents) per account per grid load. For N < 50 (operator-typical), fine. If the operator's setup grows past N agents × M accounts, consider denormalizing the count into the connector_accounts table (routine-maintenance territory).
- **The agent-side `connector_acls` field has an entry for the now-detached account_id** — STAYS in place. ACLs are an agent-side configuration; detaching the account doesn't strip the ACL. The next attach would re-use the same ACLs. Per the cycle-2 architect note ("no defensive check"), this is acceptable.

## Files Affected

- `the_one/connectors/_pool.py` — +15 LOC (new function).
- `the_one/interfaces/web/api.py` — +50 LOC (new endpoint + list augmentation).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — +50-70 LOC (detach button, click handler, error inline).
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js` — +15-25 LOC (badge text + CustomEvent listener).
- `the_one/interfaces/web/static/css/studio.css` — ~15 LOC (button + error message; may already exist).
- `tests/test_connectors_pool.py` — +60 LOC.
- `tests/test_db_api.py` — +200 LOC.
- `tests/browser/test_flow_connector_account_detach.py` — +200 LOC.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — L5 entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new tests pass; pre-existing tests pass unchanged
- [ ] Update flight-log.md with L5 progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

10 citations verified against current code at leg design time:
- `the_one/agent/config.py:181` (`connector_account_ids`) — OK
- `the_one/connectors/_pool.py:341` (`_evict`) — OK
- `the_one/connectors/_pool.py:365` (`_evict_all_for_account`) — OK
- `the_one/connectors/_pool.py:748` (`agent_acquire`) — OK
- `the_one/connectors/_pool.py:830` (`account_acquire`) — OK
- `the_one/interfaces/web/api.py:478-494` (`update_agent`) — OK
- `the_one/interfaces/web/api.py:497-504` (`delete_agent`) — OK
- `the_one/interfaces/web/api.py:2359-2363` (`list_connector_accounts`) — OK
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:2827-2896` (`renderAttachedAgentsList`) — OK
- `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js:84-98` (tile loop) — OK
