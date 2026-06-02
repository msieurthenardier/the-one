# Leg: multi-channel-routing-hat

**Status**: completed — live run PASS 4/4 (2026-06-02); closes mission #6. See flight log L5 entry.
**Flight**: [Live-Traffic HAT Capability](../flight.md)

## Objective

Close mission criterion **#6 (multi-channel routing)** against real Discord traffic: with the test connector's routing-rules configured so ≥3 channels each default to a different agent, drive a bot into each channel and prove each message routes (via a `channel`-scope rule) to that channel's configured agent in its own separate session — then exercise a **channel-scoped override** (add/change a channel rule and confirm the re-route). Ships as a committed `discord_hat` test plus the `discord-multi-channel-routing` behavior-test spec.

## Context

- **Builds on the L3/L4 driver** (`tests/live/discord_hat/`): `BotDriver`, `wait_for_session(..., until=...)`, `latest_routing_entry`, `post_and_wait_new_routing`, the dev-mode lookup seam `GET /api/_test/chat/sessions/lookup`, and the connector-PUT pattern used in L3/L4 (GET connector → mutate `config` → PUT, **omit `secrets` so the token is preserved** — `update_connector` at `api.py:2489` preserves `existing.secrets` when `secrets` is absent).
- **Environment (live):** connector `58f1fe5a833f` (`ingest_bots=true`, `always_listen=false`, `dm_admission=all`), guild `1447766672441348150`, **Connector Agent 1 + 2** attached. Channels: test-channel-1 = `1511160772305092827`, test-channel-2 = `1511160809391128728`, test-channel-3 = `1511160859622379591`. Account-scope `allowlist.channels = [{guild_id, channel_id: "*"}]` → ALL guild channels admitted (so any test channel passes ACL; routing rules then pick the agent). the-one bot user id = `1506767486002135280`.
- **Routing config shape** (`models.py:239-240`; validator `models.py:528-540`): `config["routing"] = {"rules": list[RoutingRule], "default": str | None}` — BOTH keys required when `routing` is non-None (`routing` itself may be `None` = no routing → first-eligible). `RoutingRule = {"scope": "channel"|"thread"|"dm"|"peer", "match": list[str], "agent": str}` (OR-semantics: fires if ANY `match` value matches; `match` is a LIST).
- **Rule-walk** (`_routing.py:resolve_routing`, step 2): for each rule in operator order, `_scope_matches(rule["scope"], rule["match"], envelope)`; on a channel-scope match it returns `RoutingDecision(agent=rule["agent"], rule_index=i, scope="channel", match=<matched channel_id>, reason="rule-match")` — PROVIDED `rule["agent"]` is an attached, ACL-admitting agent. So a routing entry for a channel-routed message has `scope == "channel"`, `reason == "rule-match"`, and `agent == <configured agent>`. Step 3 (per-account `default`) catches channels with no matching rule (`scope="default"`).
- **Per-channel session isolation:** each channel has a distinct `channel_id` → distinct `(platform, connector_id, channel_id, thread_id)` 4-tuple → a SEPARATE session (`_session.py:123`). So a bot posting into ch1 vs ch2 creates two sessions; the lookup seam resolves each independently. **This removes the L4 peer-correlation problem** — a single bot posting one message per channel uniquely identifies which channel's routing entry to read.
- **Freshness:** the dispatcher reloads the account per inbound (`_inbound.py` step 2) and `resolve_routing` reads `account.config["routing"]` fresh — so routing-rules changes take effect on the NEXT inbound with NO restart (unlike the `ingest_bots` connect-time-closure gate). Verify with the first post; if a rule change doesn't take, the account is cached (not expected — flag).
- **Engagement:** `always_listen=false`, so every post MUST `@mention` to engage (else `policy-silent`, no routing decision recorded).

## Inputs

- `tests/live/discord_hat/driver.py` — `BotDriver`, `wait_for_session`, `latest_routing_entry`, `post_and_wait_new_routing`, plus the existing connector/agent HTTP helpers' style (the L4 `set_agent_connector_acl` shows the GET-mutate-PUT round-trip).
- `the_one/db/models.py:239-240` — routing shape; `models.py:528-540` — `_validate_*` routing dict-keys rule (exactly `{rules, default}`).
- `the_one/connectors/_routing.py:resolve_routing` (step 2 rule-walk, step 3 default) + `_scope_matches`.
- `the_one/interfaces/web/api.py:2489` — `PUT /connectors/{account_id}` (shallow-merges `config`; preserves `secrets` when omitted).
- `tests/live/discord_hat/config.py` — `HatConfig.channel_ids` (the 3 test channels).
- `tests/behavior/discord-multi-channel-routing.md` — named in the flight Verification section but not yet written; author it here.

## Outputs

- `tests/live/discord_hat/driver.py` — `set_connector_routing(base_url, connector_id, routing)` (GET connector → set `config["routing"] = routing` → PUT full config WITHOUT `secrets`; returns the PRIOR `config.get("routing")` for restore) + `restore_connector_routing(base_url, connector_id, prior)`.
- `tests/live/discord_hat/test_multi_channel.py` — NEW `discord_hat`-marked committed test: configures routing rules, drives per-channel posts, asserts per-channel routing + the channel-scoped override, restores routing in `finally`.
- `tests/behavior/discord-multi-channel-routing.md` — NEW Witnessed spec for the multi-channel scenario (the committed test is its machine-checked counterpart).

## Acceptance Criteria

- [ ] **Per-channel default routing (#6):** with `config.routing = {"rules": [{"scope":"channel","match":[ch1],"agent":"Connector Agent 1"}, {"scope":"channel","match":[ch2],"agent":"Connector Agent 2"}], "default":"Connector Agent 1"}`: a bot `@mention` in **ch1** yields (in ch1's session) a latest routing entry with `agent=="Connector Agent 1"`, `scope=="channel"`, `reason=="rule-match"`; a bot `@mention` in **ch2** yields (in ch2's SEPARATE session) `agent=="Connector Agent 2"`, `scope=="channel"`. The two sessions are distinct ids.
- [ ] **Default fall-through (#6):** a bot `@mention` in **ch3** (no matching rule) yields (in ch3's session) `agent=="Connector Agent 1"` with `scope=="default"` (the per-account default catches it) — distinguishing rule-match from default.
- [ ] **Channel-scoped override (#6):** after adding a rule `{"scope":"channel","match":[ch3],"agent":"Connector Agent 2"}` to `config.routing.rules` and re-posting an `@mention` in **ch3**, the NEW routing entry in ch3's session shows `agent=="Connector Agent 2"`, `scope=="channel"`, `reason=="rule-match"` — i.e. the channel-scoped override re-routes ch3 away from the default. (This is the mission's "channel-scoped agent overrides are exercised".)
- [ ] **Separate sessions:** the lookup seam resolves three distinct session ids for ch1/ch2/ch3 (channel-keyed isolation).
- [ ] **Self-contained + restoring:** the test captures the connector's prior `config.routing` (currently absent → `None`) and RESTORES it in a `finally` (sets `config.routing` back to the captured value); the token/allowlist are never touched (secrets omitted on every PUT). Re-runnable.
- [ ] `tests/behavior/discord-multi-channel-routing.md` authored (Witnessed spec; references `test_multi_channel.py`).
- [ ] ruff clean; full backend suite green and does NOT collect `discord_hat`; the new test SKIPs cleanly with no env.
- [ ] **(FD-run, live):** `pytest -m discord_hat tests/live/discord_hat/test_multi_channel.py` PASSES against the real guild; per-criterion report recorded in the flight log; connector `config.routing` restored to its pre-test value (verified post-run).

## Verification Steps

- `docker exec the-one ruff check tests/live/discord_hat/` — clean.
- `docker exec the-one pytest -m discord_hat tests/live/discord_hat/test_multi_channel.py -q` with NO env → SKIP.
- FD live: `docker exec the-one bash -lc 'set -a; source /app/tests/live/discord_hat/.env.hat; set +a; cd /app && pytest -m discord_hat tests/live/discord_hat/test_multi_channel.py -v -s --timeout 300'` → PASS; capture the report.
- Post-run restore check: `curl -s "$URL/api/connectors/58f1fe5a833f" | jq '.config.routing'` → restored to pre-test value (currently `null`).
- `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' -x --timeout 30 -q` — backend green.

## Implementation Guidance

1. **Driver helpers** (`driver.py`) — `async def set_connector_routing(base_url, connector_id, routing) -> dict | None`: httpx `GET /api/connectors/{connector_id}` → take `config = body["config"]` → record `prior = config.get("routing")` → `config["routing"] = routing` → `PUT /api/connectors/{connector_id}` with body `{"config": config}` (NO `secrets` key → token preserved) → return `prior`. `restore_connector_routing(base_url, connector_id, prior)`: GET → `config["routing"] = prior` (may be `None`) → PUT `{"config": config}`. Mirror the L4 ACL-helper style; ruff-clean, typed, commented.
2. **`test_multi_channel.py`** — one `@pytest.mark.discord_hat` test (`skip_if_unconfigured`), unique nonce per run:
   - Capture `prior_routing = await set_connector_routing(base, CID, {"rules": [ch1→Agent1, ch2→Agent2], "default": "Connector Agent 1"})`. Wrap the rest in try/finally.
   - **Per-channel default (PRIME each cold channel — do NOT use `post_and_wait_new_routing` here; it requires a pre-existing session and would block on a cold channel):** for (ch1, "Connector Agent 1", "channel"), (ch2, "Connector Agent 2", "channel"), (ch3, "Connector Agent 1", "default"): `await bots.post(0, channel_id, bots.mention(f"mc {nonce} {channel_id}"))`; then `detail = await wait_for_session(base, CID, channel_id, until=lambda d: (latest_routing_entry(d) or {}).get("disposition") == "stepped", timeout=120)`; `entry = latest_routing_entry(detail)`; assert `entry["agent"] == expected_agent` and `entry["scope"] == expected_scope`; capture `detail["id"]` into a set. (ch3 routes to the default agent → still `disposition=="stepped"`, but `scope=="default"`.) Record each.
   - Assert the three captured `detail["id"]`s are distinct (channel-keyed isolation): `len({id1, id2, id3}) == 3`.
   - **Channel-scoped override (ch3's session now EXISTS from the prime, so `post_and_wait_new_routing` is correct here):** `await set_connector_routing(base, CID, {"rules": [ch1→Agent1, ch2→Agent2, ch3→Agent2], "default": "Connector Agent 1"})`; `entry = await post_and_wait_new_routing(base, CID, ch3, bots, 0, bots.mention(f"mc-override {nonce}"), timeout=120)`; assert `entry["agent"] == "Connector Agent 2"`, `entry["scope"] == "channel"`, `entry["reason"] == "rule-match"`.
   - `finally: await restore_connector_routing(base, CID, prior_routing)`.
   - Build a `HatReport`, `print(report.render())` under `-s`.
   - RoutingRule `match` is a LIST: `{"scope":"channel","match":[channel_id],"agent":"Connector Agent 1"}`.
3. **Behavior spec** `tests/behavior/discord-multi-channel-routing.md` — Witnessed spec (mirror the `discord-multi-user-routing.md` structure): preconditions (connector + 2 agents + 3 channels), steps driving per-channel posts + asserting per-channel routed agent (`[mixed-frame]` via the session detail's routing entry `agent`/`scope`), and the channel-scoped override. Reference `test_multi_channel.py` as the committed counterpart. Status `draft`.

## Edge Cases

- **`routing` requires BOTH keys** — `{"rules": [...], "default": ...}`; omitting `default` fails the `models.py:528-540` validator. Always include `default` (a valid attached agent name or `None`... but `None` default means fall-through to first-eligible — use a real agent name to make the ch3 fall-through assertion `scope=="default"`).
- **`match` is a list** — `[channel_id]`, not a bare string. A bare string would not match.
- **Secrets preservation** — every connector PUT omits `secrets`; never round-trip the masked `BOT_TOKEN` (the `__MASKED__` handling at `api.py:2512` preserves it, but omission is cleaner and is what L3/L4 did).
- **Restore-on-failure** — `finally` restores `config.routing` to the captured prior (currently `None`); document the manual restore (`PUT config.routing=null`) if the test is SIGKILLed mid-run.
- **always_listen=false** — every post `@mention`s (else policy-silent, no routing entry).
- **Per-channel agent must admit** — both agents currently admit all peers/channels (no overlays; restored after L4), so the configured agent admits. If a future overlay denied the configured agent in that channel, the rule would fall through — out of scope here (that's L4/L6 ACL territory).
- **Timing** — each post drives an `agent.step` (LLM); separate channels = separate sessions = separate per-session locks (can overlap), but `post_and_wait_new_routing` waits per-channel. Use 120s per-channel timeout.

## Files Affected

- `tests/live/discord_hat/driver.py` — `set_connector_routing` / `restore_connector_routing`.
- `tests/live/discord_hat/test_multi_channel.py` — NEW.
- `tests/behavior/discord-multi-channel-routing.md` — NEW.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (FD live run PASS; routing restored)
- [ ] Tests passing (live multi-channel PASS; backend green; HAT excluded)
- [ ] ruff clean
- [ ] Update flight-log.md with the L5 entry (report table; findings)
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md; check off mission criterion #6 in mission.md
- [ ] Not the final leg — commit at flight-level Phase 2d

## Citation Audit

Verified against current code at L5 design time: `_routing.py:resolve_routing` (step 2 rule-walk returns `scope=rule["scope"]`/`reason="rule-match"`; step 3 default `scope="default"`) OK; `models.py:239-240` (routing/RoutingRule shape) OK; `models.py:528-540` (routing requires `{rules, default}`) OK; `api.py:2489` (`PUT /connectors/{id}`, preserves secrets when omitted) OK; `_session.py:123` (4-tuple channel keying) OK; `_inbound.py` step-2 account reload (fresh routing per dispatch) OK; driver helpers from L3/L4 verified present. All clean.
