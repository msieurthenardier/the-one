# Leg: multi-agent-routing-hat

**Status**: completed — live run PASS 3/3 (2026-06-02); with L4, closes mission #7. See flight log L6 entry.
**Flight**: [Live-Traffic HAT Capability](../flight.md)

## Objective

Close mission criterion **#7 (multi-peer / multi-agent routing)** by verifying its one remaining facet against real traffic: the **peer-issued `/talk-to <agent>` override**. A bot issues the text-prefix `/talk-to` command in a channel; the next message in that session routes to the named agent via routing step 1 (`scope="override"`), taking precedence over channel rules and first-eligible. The other #7 facets — multiple agents on one connector, multiple peers, and the per-(agent, peer) ACL precedent — were already verified live in **L4** (PASS 4/4); L6 cites that and closes the override facet.

## Context

- **#7 scope split (operator-relevant):** mission #7 = "multiple agents attached to one connector account, multiple users sending to the same connector — including the per-(agent, peer) ACL precedent from F6 and the peer-issued `/talk_to` override from F7." **L4 already proved** the multi-agent (Connector Agent 1+2) + multi-peer (3 bots) + per-(agent, peer) ACL differentiation against real traffic. **L6 = the override.** Together L4+L6 close #7.
- **Override mechanics (verified at design time):**
  - Commands parse at dispatch **step 11** (`_parse_command(working_envelope.text)`) which runs BEFORE the policy gate at step 11.5 — so a plain `/talk-to …` message needs NO `@mention` to be processed (it is intercepted, never reaching the engagement gate). Canonical command name is **`talk-to`** (hyphen); the slash form `/talk_to` (underscore) is normalized to the same handler.
  - `_handle_talk_to` (`_commands.py:151`): `target = " ".join(args)` (joins multi-word names — the F14 Bug G fix, so "Connector Agent 2" works), checks `target in _permitted_agents(context)` (must be attached + ACL-admitting), then `set_session_metadata_key(session_id, "routing_override", target)`. Returns "Now routing your messages to {target}." A `/talk-to` message produces a routing entry with `disposition == "command-intercepted"` (`_inbound.py:693`/`:730`).
  - The routing engine **step 1 — override** (`_routing.py:resolve_routing`): reads `session_metadata["routing_override"]`; if it names an attached, ACL-admitting agent, returns `RoutingDecision(agent=override, scope="override", reason="override")` — BEFORE rule-walk (step 2) and first-eligible (step 4). So the override beats a channel rule.
  - **`/new` / `/reset`** (`_commands.py:198`): writes `session_metadata["ended_at"]`; the next inbound's `resolve_session` sees the `ended_at` sentinel and starts a FRESH session — which carries no `routing_override`. This is the re-runnable cleanup (clears the override by rotating to a new session).
- **Environment (live):** connector `58f1fe5a833f` (`ingest_bots=true`, `always_listen=false`, `dm_admission=all`, Connector Agent 1+2 attached). **Channel under test: test-channel-2 = `1511160809391128728`** (L4 used ch1, L5 exercised ch1-3 rules — ch2 is a clean lane; assertions read the LATEST routing entry so prior state doesn't interfere). the-one bot user id = `1506767486002135280`. Both agents are ACL-unrestricted (overlays restored after L4), so both are valid `/talk-to` targets.
- **Builds on the proven driver** (`tests/live/discord_hat/`): `BotDriver`, `wait_for_session(..., until=...)`, `latest_routing_entry`, `post_and_wait_new_routing`, `set_connector_routing`/`restore_connector_routing` (L5). The override message routes via `agent.step` (LLM latency) under the per-session lock; the `/talk-to` and `/new` commands are intercepted fast (no LLM).

## Inputs

- `the_one/connectors/_commands.py:151` — `_handle_talk_to` (`" ".join(args)`, `_permitted_agents` gate, `routing_override` write); `_commands.py:198` — `_handle_new` (`ended_at` sentinel); `_commands.py:48` — `_parse_command`; the `_HANDLERS` map keyed by `"talk-to"`/`"new"`/`"reset"`.
- `the_one/connectors/_inbound.py` — step 11 command parse+intercept (before step 11.5 policy gate); `disposition == "command-intercepted"` at `_inbound.py:693`/`:730`.
- `the_one/connectors/_routing.py:resolve_routing` — step 1 override (`scope="override"`, `reason="override"`).
- `tests/live/discord_hat/driver.py` — `BotDriver`, `wait_for_session`, `latest_routing_entry`, `post_and_wait_new_routing`, `set_connector_routing`/`restore_connector_routing`.
- `tests/behavior/discord-multi-agent-routing.md` — named in the flight Verification section but not yet written; author it here.

## Outputs

- `tests/live/discord_hat/driver.py` — generalize `post_and_wait_new_routing` to accept an optional `until_entry: Callable[[dict], bool]` (default: `disposition in {"stepped","no-eligible"}`) so callers can wait for a `command-intercepted` entry too; OR add a thin `post_command_and_wait(...)` sibling. Keep the existing default behavior for L4/L5 callers.
- `tests/live/discord_hat/test_multi_agent.py` — NEW `discord_hat`-marked committed test: the 3-phase `/talk-to` override scenario, self-contained (cleans up via `/new` + restores connector routing in `finally`).
- `tests/behavior/discord-multi-agent-routing.md` — NEW Witnessed spec (the committed test is its machine-checked counterpart).

## Acceptance Criteria

- [ ] **`/talk-to` is intercepted (#7):** a bot posting plain `/talk-to Connector Agent 2` (no `@mention`) into test-channel-2 produces, in that channel's session, a routing entry with `disposition == "command-intercepted"`.
- [ ] **Override takes effect (#7):** the bot's NEXT `@mention` message in that channel yields a routing entry with `scope == "override"`, `agent == "Connector Agent 2"`, `reason == "override"` (routing step 1 honored the `routing_override`).
- [ ] **Override beats a channel rule (#7):** with a `config.routing` channel rule mapping test-channel-2 → "Connector Agent 1", a re-issued `/talk-to Connector Agent 2` followed by an `@mention` STILL routes to "Connector Agent 2" with `scope == "override"` — proving step-1 override precedence over the step-2 rule.
- [ ] **Dynamic re-override (#7):** `/talk-to Connector Agent 1` then an `@mention` yields `agent == "Connector Agent 1"`, `scope == "override"` — the override is re-settable at runtime.
- [ ] **Self-contained + re-runnable:** the test cleans up via `/new` (rotates the session, clearing the override) and restores `config.routing` to its captured pre-test value in a `finally`; a second run passes without manual cleanup. Token/allowlist never touched (secrets omitted on every connector PUT).
- [ ] `tests/behavior/discord-multi-agent-routing.md` authored (Witnessed; references `test_multi_agent.py`); the leg/spec note that #7's multi-agent/multi-peer/per-(agent,peer)-ACL facets are L4-covered.
- [ ] ruff clean; full backend suite green and does NOT collect `discord_hat`; the new test SKIPs cleanly with no env; L4/L5 tests still pass (the `post_and_wait_new_routing` generalization must not change their behavior).
- [ ] **(FD-run, live):** `pytest -m discord_hat tests/live/discord_hat/test_multi_agent.py` PASSES against the real guild; report recorded in the flight log; `config.routing` restored post-run.

## Verification Steps

- `docker exec the-one ruff check tests/live/discord_hat/` — clean.
- `docker exec the-one pytest -m discord_hat tests/live/discord_hat/test_multi_agent.py -q` with NO env → SKIP.
- Regression: `docker exec the-one pytest -m discord_hat tests/live/discord_hat/ -q` with NO env → all SKIP (the generalized helper didn't break collection).
- FD live: `docker exec the-one bash -lc 'set -a; source /app/tests/live/discord_hat/.env.hat; set +a; cd /app && pytest -m discord_hat tests/live/discord_hat/test_multi_agent.py -v -s --timeout 300'` → PASS; capture the report.
- Post-run: `curl -s "$URL/api/connectors/58f1fe5a833f" | jq '.config.routing'` → pre-test value (currently `null`).
- `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' -x --timeout 30 -q` — backend green.

## Implementation Guidance

1. **Driver: generalize `post_and_wait_new_routing`** — add `until_entry: Callable[[dict], bool] | None = None`; when `None`, keep the current `disposition in {"stepped","no-eligible"}` default (so L4/L5 are byte-unchanged). The poll waits until `len(routing) > before and until_entry(latest)`. For a `/talk-to` post, pass `until_entry=lambda e: e.get("disposition") == "command-intercepted"`.
2. **`test_multi_agent.py`** — one `@pytest.mark.discord_hat` test (`skip_if_unconfigured`), unique nonce, channel = `cfg.channel_ids[1]` (test-channel-2). Capture `prior_routing = (await GET connector).config.get("routing")`; try/finally.
   - **Phase A — override:** `await post_and_wait_new_routing(base, CID, ch2, bots, 0, "/talk-to Connector Agent 2", until_entry=lambda e: e["disposition"]=="command-intercepted")` → assert that entry's disposition. Then `entry = await post_and_wait_new_routing(base, CID, ch2, bots, 0, bots.mention(f"ma {nonce}"))` (default until = stepped) → assert `entry["scope"]=="override"`, `entry["agent"]=="Connector Agent 2"`, `entry["reason"]=="override"`.
   - **Phase B — override beats channel rule:** `await set_connector_routing(base, CID, {"rules":[{"scope":"channel","match":[ch2],"agent":"Connector Agent 1"}], "default":"Connector Agent 1"})`. Re-issue `/talk-to Connector Agent 2` (command-intercepted), then `@mention` → assert `entry["scope"]=="override"`, `entry["agent"]=="Connector Agent 2"` (override beat the ch2→Agent1 rule).
   - **Phase C — dynamic re-override:** `/talk-to Connector Agent 1` (command-intercepted), then `@mention` → assert `entry["agent"]=="Connector Agent 1"`, `entry["scope"]=="override"`.
   - **finally:** post `/new` (`await bots.post(0, ch2, "/new")`) to end the session + clear the override for re-runnability; `await restore_connector_routing(base, CID, prior_routing)`.
   - Build a `HatReport`, `print(report.render())` under `-s`.
3. **Behavior spec** `tests/behavior/discord-multi-agent-routing.md` — Witnessed spec mirroring the multi-user/channel specs: preconditions (connector + Agent 1+2 + test-channel-2), steps driving `/talk-to` → `@mention` and asserting `scope=override`/`agent` via the `[mixed-frame]` session-detail routing entry, plus override-beats-rule. Note #7's other facets are L4-covered. Status `draft`. Reference `test_multi_agent.py`.

## Edge Cases

- **`/talk-to` target must be permitted** — both agents are ACL-unrestricted now (overlays restored post-L4), so both are valid targets. A target not in `_permitted_agents` → handler returns an error and does NOT set the override (don't assert override in that case).
- **`/talk-to` needs no `@mention`** (parsed at step 11 before the policy gate); the SUBSEQUENT routing message DOES need an `@mention` (else `always_listen=false` → policy-silent, no routing decision).
- **Override persists in the session** until changed or the session rotates (`/new` → `ended_at`). The Phase-A override (Agent 2) is still set entering Phase B; Phase B re-issues it for clarity but the assertion holds regardless. Cleanup `/new` rotates the session so the next run starts override-free.
- **`/new` rotates the session id** — after the cleanup `/new`, the next inbound in ch2 creates a new session (same channel 4-tuple, new id; the lookup returns most-recent). Don't assert on session-id stability across a `/new`.
- **`post_and_wait_new_routing` generalization MUST be backward-compatible** — default `until_entry=None` → the existing `{stepped,no-eligible}` behavior; L4/L5 call sites pass no `until_entry`. Re-run L4/L5's no-env SKIP collection to confirm no import/signature breakage.
- **Restore-on-failure** — `finally` posts `/new` and restores `config.routing`; document the manual restore (`PUT config.routing=null`) + that a stuck override self-clears on the operator's next `/new` if the test SIGKILLs mid-run.
- **Timing** — `/talk-to` and `/new` are command-intercepts (fast, no LLM); each `@mention` drives an `agent.step` (LLM, seconds). Use the `until`/`until_entry` predicates; 120s per routed post.

## Files Affected

- `tests/live/discord_hat/driver.py` — `post_and_wait_new_routing` gains optional `until_entry`.
- `tests/live/discord_hat/test_multi_agent.py` — NEW.
- `tests/behavior/discord-multi-agent-routing.md` — NEW.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (FD live run PASS; routing restored)
- [ ] Tests passing (live multi-agent PASS; L4/L5 unaffected; backend green; HAT excluded)
- [ ] ruff clean
- [ ] Update flight-log.md with the L6 entry (report table; findings)
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md; check off mission criterion #7 in mission.md (citing L4 for the multi-peer/ACL facet + L6 for the override)
- [ ] Not the final leg — commit at flight-level Phase 2d

## Citation Audit

Verified against current code at L6 design time: `_commands.py:151` (`_handle_talk_to`: `" ".join(args)`, `_permitted_agents` gate, `routing_override` write) OK; `_commands.py:198` (`_handle_new` `ended_at` sentinel) OK; `_commands.py:48` (`_parse_command`) + `_HANDLERS` `"talk-to"` key OK; `_inbound.py:693`/`:730` (`command-intercepted` disposition) OK; `_inbound.py` step-11-before-11.5 ordering OK; `_routing.py:resolve_routing` step-1 override (`scope="override"`/`reason="override"`) OK; driver helpers from L3/L4/L5 verified present. All clean.
