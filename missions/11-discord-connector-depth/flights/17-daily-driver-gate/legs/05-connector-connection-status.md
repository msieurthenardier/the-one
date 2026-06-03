# Leg: connector-connection-status

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (UI + backend) — L3 once-over Leg A. **Ships with Leg B (`intents-ux`).** Rolls up finding F1; improves F3b.

## Objective

Replace the connector editor's manual, session-only "Test Connection / Not tested" model with a **live connection status** that reflects the real gateway, make **Save open/reconnect the WS**, demote Test Connection to an optional **Validate**, contextualize the **invite link**, and **relocate the discoverable-entities** freshness surface — so the operator can always see whether the bot is actually connected (the F1 gap) and a working connector "just works" on save.

## Context

- **F1 (this flight):** there is no live connection indicator anywhere — the operator discovered the bot was offline only by a dead DM. The closest signals today are the **session-only doctor result** ("Not tested" until Test Connection is clicked) and the discoverable-entities 404 (cold-pool proxy). Recon facts:
  - **Save only persists config** — `update_connector` (`api.py:2489`) writes the row; it does NOT `account_acquire`/open the WS (it only *evicts* on secret-change).
  - **Test Connection** (`POST …/test/connect`, `api.py:2832`) runs the doctor probe AND `account_acquire` (the only UI path that opens the gateway). Rendered at `connector-editor.js:2020` (`renderTestConnectionRow`); status banner `renderTestConnectionBanner` (`:1866`); statuses ok/degraded/failed/error.
  - **"Not tested"** is hardcoded session state (`connector-editor.js:2028`), not a persisted/live field.
  - **"Last refreshed"** (`connector-form-discord.js`, allowlist banner `:4506`) is the **discoverable-entities cache age** (`fetched_at`) — a different concept from connection.
  - **Invite link** (`connector-form-discord.js:78`) renders only after Test Connection (needs `application_id` from the doctor `report.details.application_id`, cached ephemerally, not persisted).
- **L4 already made connectors auto-warm on boot and stay warm** — so a live status now has a stable thing to reflect.
- **Mission constraints:** no agent-loop change; no env-var test seam; Single-User-Local posture.

## Design Decisions (resolved at design review — implement to these)

- **Status read-path:** new `GET /api/connectors/{id}/status` → `{state: connected|connecting|disconnected|error, alive, last_error, last_error_link}`, backed by a `_get_account_status_snapshot(account_id)` in `_pool.py` (mirror `_get_account_counters_snapshot` `:869`; reads `entry.client is not None`, `entry.client_ready.is_set()`, `entry.client.is_alive()`, `entry.failure`). Degrades to `disconnected` when cold. **Do NOT** extend the L1 disposition-counters endpoint (separate concern). **Live update via a 2–5s poll** that stops on editor unmount (mirror the discoverable banner's `isConnected` guard, `connector-editor.js:~4539`) — there is no existing server-push channel (`App.studio.eventBus` is in-page only); a WS is disproportionate for this leg.
- **Save-warm (background, non-blocking):** in `update_connector` (`api.py:2489`, prior config is `existing` at `:2494`) + create, add `_connection_relevant_changed(existing, updated)` (compare `secrets`, `config.intents`, `config.presence`, and any key feeding `plugin.connect()` — NOT the whole config dict, so kv-table edits don't bounce the gateway). When it changed AND ≥1 attached agent: `_evict_all_for_account` then `account_acquire` **wrapped in `asyncio.create_task`** so the PUT responds immediately; the status poll surfaces `connecting`→`connected`/`error`. Deadlock-safe (review-confirmed: no `_lock` held across an await that re-enters `_lock`). Extend the existing secret-change eviction branch (`:2544-2559`).
- **Connect-error mapping (shared w/ Leg B):** `_map_connect_error(exc)` module-level in `api.py` near the test/connect handler (`:2832`); **walk `exc.__cause__`** (errors arrive as `ConnectorConnectionError` wrapping the original discord exc, re-raised to the `account_acquire` caller at `_pool.py:1018`) → `{message, action_link}`. `PrivilegedIntentsRequired` → message + Developer-Portal "Privileged Gateway Intents" link; `LoginFailure`/bad-token + generic → their own copy. Called by the status endpoint AND the Validate response; **Leg B reuses it verbatim.**
- **application_id:** persist in `account.config["application_id"]` on save (frontend includes the cached id in the PUT; no migration — config dict key); read back in `renderInviteSection` (`connector-form-discord.js:445`) so the invite renders without a prior Test. The doctor/Validate path still refreshes it. **Update the stale hint** copy ("Refresh connection first to fetch your application ID." → "Run Validate to fetch your application ID.", shown only when truly absent).
- **New `data-testid`s (Leg A must add — the behavior test depends on them):** `connector-live-status` (the indicator replacing "Not tested"; steps 1/2/8), `connector-live-status-error` + `connector-live-status-error-link` (step 8). **Keep** `connector-test-connection-btn` (relabel visible text → "Validate"; don't change the testid → existing browser tests survive).
- **Discoverable-entities new location:** move the "last refreshed"/refresh banner (`connector-editor.js:~2165-2201`, currently in the Users subsection) to the **top of the Access-and-Routing tab** (above Users + Servers), relabel "entries last refreshed," with a stable test-id in the new spot. Purely frontend.
- **Browser tests:** `connector-test-connection-btn` testid stays → `test_connector_test_connection_button.py`, `test_flow_studio_connector_editor.py`, `_create_and_test.py`, `_invite_section.py`, `_discoverable_dropdown.py` keep passing; update only label/text assertions + (optionally) the invite tests to assert the URL renders pre-Test. Step 8 of the behavior test needs a Playwright route-stub returning a `PrivilegedIntentsRequired` status (not live-drivable).

## Outputs

- A live connection-status indicator on the General tab (Connected / Connecting / Disconnected / Error), driven by the real gateway (`is_alive()` on the warm pool entry), updated live (WS push preferred; poll acceptable).
- Save opens/reconnects the gateway (evict + re-`account_acquire`, gated ≥1 attached agent, only when connection-relevant config changed).
- Test Connection re-roled to an optional "Validate" (doctor probe) — no longer the way you "connect."
- The invite link: info-icon explaining its purpose; `application_id` sourced so it renders without a prior Test Connection.
- The discoverable-entities cache/"last refreshed"/refresh surface relocated to a better spot + relabeled, distinct from connection status.
- A single, actionable connect-error display (incl. `PrivilegedIntentsRequired` → Developer-Portal link) surfaced by the live status AND the Validate action. **(Leg B depends on this.)**

## Acceptance Criteria

- [x] **Live connection status (General tab).** A status indicator reflects the actual gateway: **Connected** (warm entry + `is_alive()` True), **Disconnected/Cold** (no warm entry), **Connecting** (entry warming), **Error** (last connect failed — with the reason). Backed by a status read-path that exposes `is_alive()` for the account's warm pool entry (a small endpoint, or extend an existing connector read-path — NOT the doctor probe, which has no warm-entry access). Updates live without a manual refresh (WS push on connect/disconnect events preferred; a lightweight poll is an acceptable fallback). Replaces the "Not tested" string.
- [x] **Save opens/reconnects the WS.** `update_connector` (and create) trigger a gateway connect: on save, if connection-relevant config changed (token/intents/guilds/ingest_bots/…) evict the warm entry and re-`account_acquire`, **gated on ≥1 attached agent** (mirror the lifespan/L4 gate; a no-agent connector stays cold). A label-only edit does NOT bounce the gateway. After a successful save the live status shows Connected without a manual Test Connection. (Bonus: a save-reconnect is a fresh connect → picks up `ingest_bots` and other connect-time-closure config, removing most "restart after reconfig" friction.)
- [x] **Test Connection → "Validate" (optional).** The button is re-roled to a pre-flight validation (the doctor probe: token/intents/gateway-smoke), useful mainly at first setup before a row exists to `account_acquire`. It is no longer presented as the primary connect mechanism; copy + placement reflect "validate", not "connect". (Keep the underlying `…/test/connect` doctor capability; reframe the UI.)
- [x] **Actionable connect-error display (shared surface — Leg B depends on it).** When a connect (save-warm, boot-warm, or Validate) fails, the live status shows **Error** with a single, actionable message. `PrivilegedIntentsRequired` (`_discord.py:1308`) renders a specific message + a link to the bot's Discord Developer-Portal "Privileged Gateway Intents" page; `LoginFailure`/bad-token and generic failures render their own clear copy. The message is single-sourced (one mapping) and rendered consistently by both the live status and the Validate action.
- [x] **Invite link contextualized.** Its info-icon/tooltip states what it's for ("Open this to add the bot to a Discord server — needed once per server at setup"). The `application_id` it needs is sourced so the link renders **without** requiring a prior Test Connection (persist `application_id` on save, or fetch it via a cheap lookup) — no more blank-until-tested invite.
- [x] **Discoverable-entities surface relocated.** The dropdown-data cache status ("last refreshed" + the refresh control) moves to a better location (design picks — co-located with the dropdowns it powers and/or a data-status area), relabeled "entries last refreshed" so it is clearly the *dropdown data age*, NOT connection status.
- [x] No regression: existing connector-editor browser tests pass (update any that asserted the old "Not tested"/Test-Connection shape); the doctor/Validate path still works; full backend + browser suites green.
- [ ] **Visual acceptance (Witnessed):** `tests/behavior/connector-editor-ux.md` — the Chrome-MCP behavior test (steps 1–3, 6, 7 cover Leg A: live status, save-warm-no-Test, Validate, invite-renders-with-tooltip, discoverable-entities relocated). The behavior test is the cluster's visual gate (shared with Legs B/C); it is **run once after A/B/C land** (not per-leg). Leg A's job is to make its steps pass.

## Verification Steps

- Live status: warm connector → status Connected; stop/disconnect (or cold connector) → Disconnected; force `PrivilegedIntentsRequired` (request a privileged intent not enabled in a test portal stub) → Error with the portal-link message.
- Save-warm: edit a connection-relevant field on a connector with an attached agent → save → status goes Connected with no Test Connection; label-only edit → no gateway bounce.
- Validate: click Validate on a not-yet-saved/first-setup connector → doctor result shown; it does not claim to be the connect path.
- Invite: on a freshly-loaded configured connector (no Test this session) → invite link renders; info-icon copy present.
- Discoverable-entities: the "last refreshed" surface appears in its new location, labeled as data age.
- Suites: `docker exec the-one pytest …` backend; the browser/pixel connector-editor tests.

## Implementation Guidance

1. **Status read-path:** add a small connector status endpoint (or extend a connector read-path) returning `{connected, alive, state, last_error}` from the warm `_RegistryEntry` (`is_alive()`), degrading to Disconnected/Cold when no warm entry. Wire a WS event on connect/disconnect for live updates; fall back to a short poll if a WS hook is heavier than the leg warrants.
2. **Save-warm:** in `update_connector`/create, after persisting, if ≥1 attached agent AND connection-relevant fields changed → `_evict` + `account_acquire` (reuse the L4/lifespan helpers). Surface connect failures into the status `last_error`.
3. **Connect-error mapping:** one helper mapping connect exceptions (`PrivilegedIntentsRequired`, `LoginFailure`, generic) → {message, actionLink}. Render in the live status + Validate banner. **Export/structure it so Leg B reuses it** for the always-request-3 portal error.
4. **Test→Validate:** relabel/reposition `renderTestConnectionRow`/banner; keep the doctor call.
5. **Invite:** persist or lazily fetch `application_id` so `_computeInviteUrl` has it without a doctor run; add the info-icon copy.
6. **Discoverable-entities:** move the "last refreshed"/refresh markup to the chosen location; relabel.
7. Tests: backend (status endpoint, save-warm trigger, error mapping) + browser (status renders, save-warm flow, invite renders pre-test). DI/code-side stubs only.

## Edge Cases

- **No attached agent:** status reads Disconnected/Cold by design (nothing to warm); save does NOT warm. Make the status copy non-alarming for this intended-cold case ("No agent attached" vs "Error").
- **Save of a label-only change:** must not bounce a healthy gateway.
- **Validate before first save (no row):** doctor runs against entered creds; cannot `account_acquire` a non-existent connector — that's fine (Validate is probe-only).
- **`PrivilegedIntentsRequired` after Leg B lands** (always-request-3): the error becomes the operator's only guidance — the message + portal link must be solid. (Ship-together with B.)

## Files Affected

- `the_one/interfaces/web/api.py` — status read-path; save-warm in `update_connector`/create; connect-error mapping.
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — live status render (replace "Not tested"); Test→Validate; wire status updates.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — invite info-icon + application_id sourcing; discoverable-entities relocation/relabel.
- `the_one/connectors/_pool.py` / `_discord.py` — expose `is_alive`/state for the status path + connect-error surfacing if needed (no behavior change).
- `tests/…` — backend (status, save-warm, error map) + browser (status, save-warm, invite-pre-test).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(injected batch — commit deferred to the end-of-batch review per /agentic-workflow)*

- [x] All acceptance criteria verified
- [x] Tests passing (backend + browser; connect-error + portal-link message verified)
- [x] Update flight-log.md with leg progress entry
- [x] Leg status `landed` (→ `completed` at batch commit)
- [ ] Check off Leg A in flight.md (at batch commit)
- [ ] Ships with Leg B — verify the shared connect-error surface is reused by B
