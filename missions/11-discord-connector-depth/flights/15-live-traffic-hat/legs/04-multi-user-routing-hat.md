# Leg: multi-user-routing-hat

**Status**: completed — live run PASS 4/4 (2026-06-02); closes mission #5 + #13. See flight log L4 entry.
**Flight**: [Live-Traffic HAT Capability](../flight.md)

> **Status transition (Developer, 2026-06-01):** ready → in-flight → landed.
> The BUILD portion (driver ACL helpers + `test_multi_user.py` + behavior-spec
> update) is complete and non-live validation passed (ruff clean, imports OK,
> skips cleanly without env, backend suite green / HAT not collected). The
> **live run against the real guild is PENDING the FD** — it posts real
> messages and mutates the operator's live agents, so the Developer does NOT
> run it. See the L4 flight-log entry.

## Objective

Close mission criteria **#5 (multi-user routing)** and **#13 (peer-name attribution)** against real Discord traffic: drive all 3 burner bots into ONE channel and prove (a) they share ONE channel-scoped session, (b) each is attributed with its own F6 `peer_name`, and (c) a per-agent ACL overlay routes the same peer to a *different* agent under real traffic — exercising the F6 per-(agent, peer) overlay that M10 only structurally tested. Ships as a committed `discord_hat` test plus the updated `discord-multi-user-routing` behavior-test spec.

## Context

- **Builds on L3's proven driver** (`tests/live/discord_hat/`): `BotDriver` (3 clients), `wait_for_session(..., until=...)` (the timing fix — session row appears before messages/routing persist, so poll the detail until the expected state lands), `latest_routing_entry`, `inbound_peer_names` (role==user `peer_name`), and the dev-mode lookup seam `GET /api/_test/chat/sessions/lookup`. L3's smoke confirmed `@mention → stepped`, F6 `peer_name`, and the `always-listen-off` negative control.
- **Environment (provisioned, live):** test connector `58f1fe5a833f` (`ingest_bots=true`, `always_listen=false`, `dm_admission=all`), guild `1447766672441348150`, **Connector Agent 1 + Connector Agent 2** attached (alphabetical order matters for first-eligible). Bots: HAT Test Bot 1/2/3 = `1511192509483843604` / `1511192652140249168` / `1511192722252234812`, display names "HAT Test Bot 1/2/3". Channel under test: test-channel-1 = `1511160772305092827`. the-one bot user id (mention/DM target) = `1506767486002135280`. All in `tests/live/discord_hat/.env.hat` (gitignored).
- **Session topology** (the #5 acceptance shape, operator-confirmed at planning): sessions key on `(platform, connector_id, channel_id, thread_id)` (`_session.py:123`), `peer_id` EXCLUDED → 3 bots in one channel = ONE session. "Peer-scoped" is satisfied by per-message attribution + per-user ACL + routing within that one session, NOT session isolation.
- **Per-agent ACL shape** (`AgentConfig.connector_acls`, `config.py:235`; validator `config.py:267`): `dict[account_id → {peers, channels[, guilds, roles, admit_dms]}]`. Required keys `{peers, channels}`. Per-agent `peers`: `list[{id: str}]` (NO `dm_allowed` — F13 L2 retired it). **Tri-state per axis** (`_acl.py:31-48`): `None` → inherit account-scope; `[]` → explicit empty (peers: no peer admitted; **channels: DMs-ONLY sentinel — would deny all guild messages**); `[items]` → narrowing subset. ⚠️ **To narrow `peers` while still admitting guild channels, set `channels: None` (inherit) — NEVER `channels: []`** (that is the DMs-only trap).
- **Routing first-eligible fallthrough** (`_routing.py` step 4, "First-eligible-alphabetical"): iterate `eligible_attached_agents` (alphabetical: Connector Agent 1, then 2); return the first whose `admits_inbound` permits; if all deny → `no-eligible-agent`. So if Agent 1's overlay denies a peer, that peer falls through to Agent 2.
- **KEY INSIGHT — routing entries lack `peer_id`.** A `stepped` audit entry is `{ts, agent, rule_index, scope, match, reason, disposition}` (L3 finding) — no `peer_id`. So a routing entry CANNOT be mapped to a specific bot by inspection. To correlate "which bot routed to which agent," the ACL phases post bots **one at a time** and read the single new routing entry's `agent`. (Bulk-posting only proves "both agents appear"; isolated posting proves "this peer → this agent.")
- **Agent-config freshness:** the dispatcher resolves `eligible_attached_agents` via `list_by_connector` per inbound (a fresh DB read) — so `connector_acls` changes take effect on the NEXT inbound with NO restart (unlike the `ingest_bots` connect-time-closure gate). Verify with the first ACL phase; if a change doesn't take, the agent store is caching and the test must evict (flag — not expected).

## Inputs

- `tests/live/discord_hat/driver.py` — `BotDriver`, `wait_for_session(base_url, connector_id, channel_id, *, until, timeout)`, `latest_routing_entry(detail)`, `inbound_peer_names(detail)`.
- `tests/live/discord_hat/config.py` — `skip_if_unconfigured()` → `HatConfig` (tokens, channel_ids, connector_id, bot_user_id, base_url).
- `the_one/agent/config.py:235` — `connector_acls: dict[str, dict[str, Any]] | None`; `config.py:267` — `_validate_connector_acls` (required `{peers, channels}`, optional `{guilds, roles, admit_dms}`).
- `the_one/connectors/_acl.py:31-48` — tri-state narrowing/defaulting semantics.
- `the_one/connectors/_routing.py` — `resolve_routing`, first-eligible-alphabetical (step 4).
- `the_one/interfaces/web/api.py:490` — `PUT /agents/{name}` (FULL-config replace via `AgentConfig.model_validate(data)` — GET the full agent, mutate `connector_acls`, PUT it whole; a partial PUT wipes other fields).
- `tests/behavior/discord-multi-user-routing.md` — the planning-draft spec to update to proven shapes.

## Outputs

- `tests/live/discord_hat/test_multi_user.py` — NEW `discord_hat`-marked committed test implementing the multi-user scenario (topology + attribution + per-user ACL routing differentiation + optional hard-deny), self-contained (sets + restores agent overlays via try/finally).
- `tests/live/discord_hat/driver.py` — small additions: `set_agent_connector_acl(base_url, agent_name, account_id, acl)` and `clear_agent_connector_acl(base_url, agent_name, account_id)` helpers (GET agent → mutate connector_acls → PUT full). Optionally a `post_and_wait_new_routing` helper.
- `tests/behavior/discord-multi-user-routing.md` — updated to the proven shapes (stepped not policy.outcome; F6 peer_name attribution; ACL-overlay-changes-routed-agent demonstration; the routing-entry-lacks-peer_id → isolated-posting note).

## Acceptance Criteria

- [ ] **Topology (#5):** posting `@mention` messages from all 3 bots into test-channel-1 resolves (via the lookup seam) to exactly ONE session id; that session's `messages` contain all 3 bots' inbound messages (verified by 3 distinct `peer_name`s). The lookup for `(connector_id, channel_id)` returns the SAME session id across all three.
- [ ] **Attribution (#13):** `inbound_peer_names(detail)` for the shared session contains all three distinct display names — "HAT Test Bot 1", "HAT Test Bot 2", "HAT Test Bot 3" — each attributed to its own inbound message (no anonymous/blank peer_name; no collapse to a single name).
- [ ] **Per-user ACL routing differentiation (#5):** with Connector Agent 1 carrying a per-agent overlay `connector_acls["58f1fe5a833f"] = {"peers": [{"id": bot0}, {"id": bot1}], "channels": None}` (narrow to bot0/bot1; channels=None inherits → guild channels still admitted): a message from **bot0** (admitted by Agent 1) yields a new `stepped` routing entry with `agent == "Connector Agent 1"`; a message from **bot2** (denied by Agent 1, falls through) yields a new `stepped` routing entry with `agent == "Connector Agent 2"`. Posted one-at-a-time so each new entry correlates to its sender. This proves the F6 per-(agent, peer) overlay routes the SAME-channel peers to different agents under real traffic.
- [ ] **Hard-deny → no-eligible (#5, demonstrates the deny path):** with BOTH agents' overlays narrowed to exclude bot2 (`peers` lists omit bot2, `channels: None`), a message from bot2 yields a routing entry with `disposition == "no-eligible"` (every agent denied). [May be marked optional if it proves flaky, but attempt it.]
- [ ] **Response correctness:** in the no-overlay baseline, the agent's reply is observable (the-one auto-relays — confirmed via `docker logs` "Auto-relayed agent … reply" and/or the assistant message in the session). Not asserting reply CONTENT (LLM-nondeterministic), only that the engaged path produced a reply.
- [ ] **Self-contained + restoring:** the test sets the overlays it needs and RESTORES both agents' `connector_acls` to their pre-test value in a `finally` (so a failure mid-test doesn't leave the operator's agents narrowed). Re-runnable: a second run passes without manual cleanup.
- [ ] `tests/behavior/discord-multi-user-routing.md` updated to the proven shapes; the committed test is referenced as its machine-checked counterpart.
- [ ] ruff clean on the new/changed driver + test files; the full backend suite stays green and does NOT collect `discord_hat`.
- [ ] **(FD-run, live):** `pytest -m discord_hat tests/live/discord_hat/test_multi_user.py` PASSES against the real guild; the per-criterion report (PASS rows for #5 topology, #5 ACL-differentiation, #5 hard-deny, #13 attribution) is recorded in the flight log.

## Verification Steps

- `docker exec the-one ruff check tests/live/discord_hat/` — clean.
- `docker exec the-one pytest -m discord_hat tests/live/discord_hat/test_multi_user.py -q` with NO env → SKIP (suite-safety).
- FD live run (env sourced): `docker exec the-one bash -lc 'set -a; source /app/tests/live/discord_hat/.env.hat; set +a; cd /app && pytest -m discord_hat tests/live/discord_hat/test_multi_user.py -v -s --timeout 300'` → PASS; capture the report table.
- After the run, confirm cleanup: `curl -s "$URL/api/agents/Connector%20Agent%201" | jq '.connector_acls'` and `…Agent%202…` → both restored to their **pre-test value** (currently `null` for these test agents, but assert against the captured prior value, not a hardcoded `null`, so a future operator-curated baseline overlay wouldn't read as a false failure).
- `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' -x --timeout 30 -q` — backend green, HAT excluded.

## Implementation Guidance

1. **Driver ACL helpers** (`driver.py`) — `async def set_agent_connector_acl(base_url, agent_name, account_id, acl: dict)`: httpx `GET /api/agents/{name}` → take the full body → `body["connector_acls"] = {**(body.get("connector_acls") or {}), account_id: acl}` → `PUT /api/agents/{name}` with the full body. `clear_agent_connector_acl(...)`: GET → remove `account_id` from `connector_acls` (or set to `{}` / `None`) → PUT. URL-encode the agent name (`Connector Agent 1` has a space). Return the prior value so the caller can restore exactly.

2. **`test_multi_user.py` — phases** (one `@pytest.mark.discord_hat` test, or a small class; use a unique nonce per run so re-runs don't read stale messages):
   - **Phase A — topology + attribution (no overlay):** post `bots.mention("u{nonce} from b{i}")` from bots 0,1,2 into `channel_ids[0]`. `detail = await wait_for_session(..., until=lambda d: len({n for n in inbound_peer_names(d)}) >= 3, timeout=180)`. Assert the lookup session id is stable; assert the 3 expected display names ⊆ `set(inbound_peer_names(detail))`. (Display names via `bots._clients[i].user.display_name`.)
   - **Phase B — per-user ACL differentiation:** capture pre-test `connector_acls` for both agents (for restore). `set_agent_connector_acl(base, "Connector Agent 1", CID, {"peers": [{"id": bot0}, {"id": bot1}], "channels": None})`. Then, ISOLATED posts (one at a time, each waiting for a NEW stepped entry): post bot0 → `until` routing length grew AND latest disposition==stepped → assert `latest.agent == "Connector Agent 1"`; post bot2 → new stepped entry → assert `latest.agent == "Connector Agent 2"`. Use a `post_and_wait_new_routing(detail_before, sender_idx)` helper that records the routing length before, posts, and polls until `len(routing) > before and latest.disposition in {"stepped","no-eligible"}`, returning the new entry.
   - **Phase C — hard-deny (optional-but-attempt):** `set_agent_connector_acl` BOTH agents to `{"peers": [{"id": bot0}, {"id": bot1}], "channels": None}` (exclude bot2). Post bot2 → new entry → assert `disposition == "no-eligible"`.
   - **finally:** restore both agents' `connector_acls` to the captured pre-test values (PUT). Assert restoration in the test teardown or a follow-up check.
   - Build a `HatReport` and `print(report.render())` under `-s`.

3. **Timing:** each engaged post triggers an LLM `agent.step` (seconds) under a per-session lock → serialize. Use generous timeouts (Phase A waits for 3 sequential steps → 180s; per-isolated-post 90s). Poll interval 1-2s. The `no-eligible` path is fast (no LLM).

4. **Update `tests/behavior/discord-multi-user-routing.md`:** rewrite Step 2's expectation to "ONE shared session; routing entries `disposition: stepped`" (drop any `policy.outcome` on stepped); make the ACL step the routing-differentiation demonstration (overlay on Agent 1 → bot2 routes to Agent 2), noting the routing-entry-lacks-peer_id → isolated-posting technique; keep the `[mixed-frame]` lookup-seam probe. Reference `test_multi_user.py` as the committed machine-checked counterpart.

## Edge Cases

- **`channels: []` trap** — setting per-agent `channels: []` means DMs-only and DENIES all guild-channel messages. Always use `channels: None` to inherit when narrowing only `peers`. (Called out in AC + Context.)
- **Restore-on-failure** — the overlay mutates the operator's live agents; the `finally` MUST restore (capture prior `connector_acls` first). If the test is killed (SIGKILL) mid-run, document the manual restore (`PUT connector_acls=null`).
- **Routing-to-bot correlation** — never assert "entry N is bot X" from a bulk post (no peer_id on entries). Isolated one-at-a-time posting is the only reliable correlation.
- **Stale-message reads** — unique nonce per run; Phase B/C read the LATEST routing entry, not historical ones (the session accumulates across phases).
- **Agent-config caching** — expected fresh per-dispatch; if Phase B's first assertion shows the overlay didn't take (bot2 still → Agent 1), the agent store is caching — surface it (would be a real product finding, not a test bug).
- **always_listen=false** — every routing post MUST `@mention` (else policy-silent, no routing-to-agent). The hard-deny bot2 post still `@mentions` (so it reaches routing, then no-eligible).
- **dm_admission=all / roles** — not exercised here (channel path only); roles-axis ACL is L6 territory.

## Files Affected

- `tests/live/discord_hat/test_multi_user.py` — NEW.
- `tests/live/discord_hat/driver.py` — ACL set/clear helpers (+ optional post_and_wait_new_routing).
- `tests/behavior/discord-multi-user-routing.md` — updated to proven shapes.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (FD live run PASS; overlays restored)
- [ ] Tests passing (live multi-user PASS; backend green; HAT excluded by default)
- [ ] ruff clean
- [ ] Update flight-log.md with the L4 entry (report table; any findings)
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md; check off mission criteria #5 + #13 in mission.md
- [ ] Not the final leg — commit at flight-level Phase 2d (deferred-commit model)

## Citation Audit

Verified against current code at L4 design time: `config.py:235` (`connector_acls` field) OK; `config.py:267` (`_validate_connector_acls`, required `{peers,channels}`, per-agent peers `{id}` only) OK; `_acl.py:31-48` (tri-state narrowing; `[]` channels = DMs-only) OK; `_routing.py` first-eligible-alphabetical step 4 OK; `api.py:490` (`PUT /agents/{name}`, full `AgentConfig.model_validate` replace) OK; `_session.py:123` (4-tuple keying) OK; driver helpers (`wait_for_session`/`inbound_peer_names`/`latest_routing_entry`) verified present from L3. All clean.
