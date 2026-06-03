# Leg: fix-gateway-idle-reap

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (substrate fix) — surfaced by the L3 soak (finding F2)

## Objective

Make a Discord (gateway-style) connector's inbound listener **stay connected indefinitely while it is meant to be listening** — never idle-reaped — and **auto-connect on startup** without a manual Test Connection, so the bot survives a full working day (and quiet lulls) without operator intervention.

## Context

- **Finding F2 (L3 soak, root cause confirmed in code):** the connector pool's idle-TTL reaper (`_reap_once`, `_pool.py:448-478`) evicts ANY entry where `(now - last_activity) > ttl_seconds` (default `_DEFAULT_TTL_SECONDS = 1800` / 30 min). Eviction runs `plugin.disconnect(client)` (`_pool.py:357`), which **closes the Discord Gateway WebSocket**. `last_activity` is only bumped on `account_acquire` (inbound dispatch / outbound send). The pool docstring states eviction operates **"uniformly"** across gateway entries (`_pool.py:26-28`) — there is **no exemption for the inbound listener**. So after ~30 min of no traffic the gateway is reaped as "idle", the bot silently goes offline, and the next inbound can't arrive (it's disconnected) → the operator must click **Test Connection** to re-warm. That is the "why do I constantly click Test Connection" symptom.
- **Operator requirement (verbatim):** *"this should not get reaped at all, and should fire itself up on restart."*
- **Two distinct fixes:**
  - **(A) Never idle-reap the inbound gateway listener.** The acquire→idle→reap→disconnect model fits per-agent *outbound* MCP-style clients (`agent_acquire`, acquire-use-release). It is wrong for the account-keyed *inbound* gateway listener (`account_acquire` / `_ACCOUNT_POOL_AGENT_SLOT`), which is a persistent subscription, not an idle resource.
  - **(B) Auto-warm on startup — already implemented; the gap was agent-deletion (design-review corrected).** The lifespan warmup EXISTS (`app.py:148-172`) and DOES `account_acquire` every connector with ≥1 attached agent on boot, including under `uvicorn --reload`. The operator's connector was cold because its F15 test agents (Connector Agent 1/2) had just been DELETED → no attached agents → warmup skips it (`app.py:152-158`). So "fire itself up on restart" already holds for a connector WITH an attached agent — the fix is to (i) confirm + test that path and (ii) document ≥1-attached-agent as the listen criterion. A no-agent connector has nothing to dispatch to, so it deliberately stays cold (no zero-agent `listen_always` mode unless the operator asks).
- **Related but OUT of scope here (separate finding F1):** there is no operator-facing connection-status signal (the UI shows the connector as present even when its gateway is down). Tracked separately as a `ui-fix-*` candidate; this leg fixes the robustness defect, not the status UI.
- **Mission constraints:** agent loop (`agent/core.py`/`factory.py`) NOT modified. Substrate pool-keying/lifecycle refactors ARE in scope (M11 constraint). No env-var-driven runtime test seams (DI/code-side stubs).

## Inputs

- `the_one/connectors/_pool.py` — `_RegistryEntry` (`:144-200`), `_reap_once` (`:448-478`, the eviction predicate `(now - entry.last_activity) > entry.ttl_seconds`), `_evict`/`_entry_worker` (the `finally: plugin.disconnect` at `:357`), `account_acquire`/`_ACCOUNT_POOL_AGENT_SLOT`, `_resolve_ttl_seconds` + the per-account `Connector.idle_timeout_seconds` override.
- The FastAPI `lifespan` startup (in `the_one/interfaces/web/app.py`) — the "lifespan listener-warmup" path that should auto-acquire listening connectors on boot (confirm it exists + what gates it).
- The gateway liveness / reconnect machinery in `the_one/connectors/_discord.py` (`is_alive` `:398-413`, the outer reconnect backoff) — a never-idle-reaped listener whose gateway genuinely DIES must still be detected + recovered, not pinned-broken-forever.

## Outputs

- The account-keyed inbound gateway listener entry is exempt from idle-TTL eviction (stays connected through arbitrary lulls).
- Per-agent (`agent_acquire`) outbound entries keep their idle-TTL reaping (no regression).
- A genuinely-dead listener (gateway not alive) is still detected and recovered (reconnect or clean-then-rewarm), not left pinned-and-broken.
- On lifespan startup, connectors that should be listening auto-connect (gateway up) without a manual Test Connection.
- Tests covering all of the above. Full backend suite green.

## Acceptance Criteria

- [x] **(A) Inbound gateway listener is never idle-reaped.** `_reap_once` (`_pool.py:469-474`) skips idle-eviction for **account-keyed entries** (`key[0] == _ACCOUNT_POOL_AGENT_SLOT`, using the module-level constant at `_pool.py:255`, not the literal) whose client `is_alive()` — the Discord gateway WebSocket stays connected through an arbitrarily long traffic lull. (Confirmed safe: every `account_acquire` entry IS the single gateway-listener entry per account; there is no pure-outbound account entry.) Per-agent `agent_acquire` entries (`key[0] != _ACCOUNT_POOL_AGENT_SLOT`) still idle-reap **unchanged**.
- [x] **Dead-listener self-heal (HIGH — mandatory companion to A).** An account-keyed entry whose gateway is **not** alive (`is_alive()` False — connection task failed / `client.is_closed()`) is NOT idle-exempt: it is evicted by a **liveness path** and **immediately re-warmed** (re-`account_acquire`) so the bot self-heals within one reaper interval (~30s) with no operator action. Implemented as a second pass in `_reap_once` (`dead_evicted` list → `_evict` → rewarm in `_reap_loop` via `_rewarm_dead_listeners`), keeping `_reap_once`'s core scope narrow. A test forces a dead account entry and asserts evict→rewarm.
- [x] **(B) Auto-warm on startup — confirmed + tested.** The existing lifespan warmup (`app.py:148-172`) `account_acquire`s every connector with ≥1 attached agent on boot. Added `test_lifespan_warms_connector_with_attached_agent` asserting a connector **with an attached agent** is warm-acquired at lifespan startup (gateway connected, no manual Test Connection). ≥1-attached-agent documented as the listen criterion in `agents.md`. **No new flag / no migration** (a zero-agent connector deliberately stays cold).
- [x] **No regression to per-agent reaping.** `test_agent_acquire_entry_still_reaps_on_ttl` asserts an idle `agent_acquire` entry is still evicted on TTL. The `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` / per-account `idle_timeout_seconds` override still governs `agent_acquire` entries; documented in `agents.md` that it no longer drives account-entry eviction (account entries are slot-exempt for idleness).
- [x] **Disposition/observability intact.** L1's `record_disposition` counters + snapshot endpoint still behave (the exempt entry stays warm → counters persist longer — fine, better). Updated the `_refresh_discoverable_entities_for_account` docstring comment ("do NOT touch last_activity") to note that for account entries last_activity is now unused for eviction (slot-exemption protects them). No double-warming / leaked entries.
- [x] Mission-constraint compliance (no agent-loop change; no env-var test seam). Unit tests via DI/code-side stubs. Full backend suite green: **2888 passed / 4 skipped / 529 deselected**.

## Design Decisions (RESOLVED at design review)

- **Exemption predicate (A): exempt all `_ACCOUNT_POOL_AGENT_SLOT` entries by slot kind, gated on `is_alive()`.** Evidence: `account_acquire` (`_pool.py:933-951`) is a thin wrapper over `agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)`; ALL connector callers (inbound `_inbound.py:590/627/1116`, F4 send `connector_send.py:193`, history `connector_history.py:593`, Test Connection `api.py:2900`, lifespan `app.py:160`) resolve to the **one** account entry, which always carries the gateway `on_message` listener (installed in `plugin.connect()`, `_discord.py:967`). So there is no "outbound-only" account entry to wrongly exempt. Use the constant `_ACCOUNT_POOL_AGENT_SLOT` (`_pool.py:255`), not `"__connector__"`.
- **"Should be listening" (B): ≥1 attached agent — already the existing gate (`app.py:152-158`).** No `listen_always` flag (zero-agent connector has nothing to dispatch to). The cold-boot the operator hit was agent-deletion, not a warmup bug.
- **Dead-listener handling: liveness-based evict+immediate-rewarm.** The outer reconnect backoff (`_discord.py:868-925`) only covers initial connect; post-READY the SDK auto-resumes transient drops but a terminal death surfaces as `is_alive()` False (`_discord.py:400-415`) with no pool cleanup once idle-reap is removed. So a liveness sweep is required (the HIGH AC above). Rewarm immediately (self-heal) per the operator's "fire itself up".

## Verification Steps

- Reaper exemption: a unit test warms an account-keyed listener entry, advances `last_activity` past TTL (monkeypatch the clock / TTL), runs `_reap_once`, asserts the listener entry SURVIVES while an idle per-agent entry is evicted.
- Dead-listener: force `is_alive()` False on the exempt entry; assert it is detected + recovered (not pinned-broken).
- Startup warm: assert the lifespan path `account_acquire`s a listening connector on boot (test-level), and/or a live check after restart that the bot receives a DM with no manual Test Connection.
- Live confirm (operator, during the resumed soak): restart → bot online automatically → DM from a real account gets a response → leave it idle >30 min → DM again → still responds (no Test Connection needed).
- Suite: `docker exec the-one pytest tests/test_connectors_pool.py tests/test_lifespan.py -x --timeout 30 -q` (adjust to real names), then full backend suite once at leg end.

## Implementation Guidance

1. **(A) Reaper idle-exemption** — in `_reap_once` (`_pool.py:469-474`), add to the eviction filter a skip for `key[0] == _ACCOUNT_POOL_AGENT_SLOT and entry.client is not None and getattr(entry.client, "is_alive", None) is not None and entry.client.is_alive()` (use the `_ACCOUNT_POOL_AGENT_SLOT` constant at `_pool.py:255`; the `getattr` guard keeps non-Discord plugins safe). Per-agent entries untouched.
2. **Dead-listener self-heal** — in the same sweep collect account-keyed entries that are NOT alive into a `dead_listeners` list, `_evict` them, and in `_reap_loop` (the caller) re-`account_acquire` each (`_rewarm_dead_listeners(keys)`) so the gateway re-establishes within ~30s. Keep `_reap_once`'s return shape compatible with `_reap_loop`.
3. **(B) Boot warm-up** — confirm `app.py:148-172` warms connectors with ≥1 attached agent on boot; add a `tests/test_lifespan.py` assertion for it. Do NOT change the ≥1-agent gate; do NOT add a flag/migration.
4. **Comment hygiene** — update `_pool.py:554`'s "do NOT touch last_activity" note to reflect that account entries are now slot-exempt for idle eviction.
5. **Tests** (DI/code-side stubs): (a) an `is_alive` account entry idle past TTL SURVIVES `_reap_once`; (b) a dead account entry is evicted + rewarmed; (c) an idle `agent_acquire` entry is STILL evicted (no regression); (d) lifespan warms a connector-with-an-attached-agent. Run `docker exec the-one pytest tests/test_connectors_pool.py tests/test_lifespan.py -x --timeout 30 -q`, then the full backend suite once at leg end.

## Files Affected

- `the_one/connectors/_pool.py` — `_reap_once` idle-exemption for live account-keyed entries + dead-listener liveness sweep; `_rewarm_dead_listeners` in `_reap_loop`; the `:554` comment update. (No `_RegistryEntry` field needed — slot-kind + `is_alive()`.)
- `the_one/interfaces/web/app.py` — NO change expected (the ≥1-agent warmup already exists); touched only if the new test reveals a gap.
- `tests/test_connectors_pool.py` — alive-account-survives-idle, dead-account-evict+rewarm, agent-entry-still-reaps.
- `tests/test_lifespan.py` — connector-with-attached-agent warm-acquired on boot.
- *(No `_discord.py` change — dead-listener handled in the pool via `is_alive()` + rewarm.)*

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(injected mid-L3 — commits as its OWN follow-up commit on the flight branch; no amend)*

- [x] All acceptance criteria verified
- [x] Tests passing (targeted + full backend suite green: 2888/4/529)
- [x] Update flight-log.md with leg progress entry (under F2)
- [x] Leg status set to `landed` (set to `completed` post-commit)
- [ ] Check off this leg in flight.md (add it to the Legs list as an injected leg)
- [ ] Commit as a standalone follow-up commit (`flight/17: fix gateway idle-reap + boot warm-up (injected)`)
- [ ] Operator re-verifies live during the resumed soak (restart → auto-online → survives idle lull)
