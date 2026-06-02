# Flight Log: Live-Traffic HAT Capability

**Flight**: [Live-Traffic HAT Capability](flight.md)

## Summary

Planning in progress. Flight scoped to the live-traffic HAT capability (mission criteria #5/#6/#7/#9/#11/#13) plus four carry-forward fold-ins. Rate-limiting (#17) deferred to the daily-driver flight (F16) per operator decision (discord.py pre-empts per-route limits; no cascade observed). Apparatus resolved to **hybrid** (committed discord.py multi-bot driver + operator Chrome-MCP pass), de-risked by a planning-time premise audit.

---

## Reconnaissance Report

Source artifacts: M11 mission.md success criteria + Known Issues; F14 debrief Action Items; F13 debrief Recommendations/Action Items. Each item F15 sources was walked against current code during planning.

| Item | Classification | Evidence | Recommendation |
|------|---------------|----------|----------------|
| F14: wire connector loggers to stdout | `confirmed-live` | No central logging setup anywhere in `the_one/` or `scripts/` (no `basicConfig`/`dictConfig`/`StreamHandler`); loggers are `getLogger(__name__)` only — not propagated to `docker logs` under uvicorn | L1 — diagnostic prerequisite for the HAT |
| F14: add `tini` as PID 1 | `confirmed-live` | `Dockerfile:37` `ENTRYPOINT ["/entrypoint.sh"]` → `entrypoint.sh` `exec "$@"` → CMD `the-one serve` becomes PID 1; no `tini` referenced in Dockerfile/compose | L1 — bundle with loggers (shared container/startup surface) |
| F14/F13: re-run `audit-log-inspector` behavior test (deferred at F14) | `confirmed-live` | F14 debrief deviation: deferred due to seeding drift + the PUT-drops-metadata bug below | L2 — fix seeding, re-run to PASS |
| F13: `ChatSessionRepository.update` drops `session_metadata` on PUT | `confirmed-live` | `repositories.py:936` UPDATE sets only `title, messages, updated_at`; docstring states the 7 connector-identity columns (incl. `session_metadata`) are intentionally NOT round-tripped | L2 — seed audit entries via test-only session/fixture or direct write (not PUT) |
| F13/F14: 2 pre-existing browser test failures (since pre-F10) | `drifted` | Files exist (`tests/browser/test_flow_agent_tabs.py`, `test_flow_studio_navigation.py`) but the debrief-cited function names (`test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`) did not match a `def` grep — names drifted or parametrized | L2 — re-locate the failing tests first, then fix |
| Mission #9 detach-from-Connectors-screen | `partially-satisfied` | F9 substrate landed (DELETE endpoint, pool release, detail-page button, grid badge per mission.md:33); L8 HAT did NOT exercise the detach step | L7 — close via the hybrid HAT pass |
| Mission #5/#6/#7 live routing | `confirmed-live` (unverified-against-real-traffic) | F6/F7 substrate landed; never exercised against real multi-X Discord traffic (M10 deferrals) | L4/L5/L6 — the core HAT scenarios |
| Mission #11 committed HAT script | `partially-satisfied` | `[~]` — F14 shipped the slash-only `discord-slash-end-to-end` spec; multi-user/channel/agent/pairing/mentions coverage owed | L3–L8 — the committed multi-bot driver closes it |
| Mission #13 peer-name attribution | `confirmed-live` (unverified-against-real-traffic) | F6 substrate landed (6-surface lockstep per mission.md:136); not yet observed end-to-end under real multi-user traffic | L4 — observe in Chat UI under multi-peer load |

**Planning-time premise audits (F14 "verify-before-lock" discipline):**
- ✅ **Multi-bot driver viability** — `ingest_bots` config flag at `_discord.py:935` disables the bot-author inbound filter; `peer_id=str(author.id)` at `_discord_translate.py:124` gives distinct burner bots distinct peers. Apparatus de-risked *before* lock (vs F14 L9 which lost a cycle to an unaudited apparatus premise).
- ⏳ **Bot-peer vs human-peer path equivalence** — deferred to L3 (grep `_routing.py`/`_acl.py` for author-type branches + live smoke assert) before L4 relies on it. Pre-authorized as a Divert trigger.
- ⏳ **Author-agnostic mention detection** — deferred to L7; fallback to human-sender Chrome-MCP pass if bot mentions don't register.

**Operator-confirmed planning decisions:** apparatus = hybrid; fold-ins = all four (loggers, tini, audit-log re-run, 2 browser fails); #17 deferred to F16.

---

## Leg Progress

_None yet — flight in planning._

---

## Decisions

_Runtime decisions will be recorded here during execution._

---

## Deviations

_None yet._

---

## Anomalies

_None yet._

---

## Session Notes

### 2026-06-01 — Planning
- Context gathered: M11 mission, F13/F14 debriefs, existing Discord behavior-test specs (`discord-slash-end-to-end`, `discord-engagement`), full codebase interrogation of the connector subsystem.
- Scope debated: operator pushed back on rate-limiting necessity → resolved to defer #17 to the daily-driver flight.
- Premise audit surfaced `ingest_bots` + author-id peers → unlocked the fully-automatable multi-bot driver apparatus.
- Draft behavior-test spec authored: `tests/behavior/discord-multi-user-routing.md` (status `draft`).

### 2026-06-01 — Design Review (Architect, 2 cycles)

**Cycle 1 → needs rework.** Apparatus premise verified (ingest_bots + author-id peers; no author-type branch in routing/ACL). Two HIGH issues:
- **H1 — session keying excludes `peer_id`** (`_session.py:123`): ≥3 senders in one channel share ONE session, contradicting the spec's "3 distinct sessions" and mission #5's "peer-scoped session." Escalated to operator → resolved: shared-channel = one session (attribution + ACL + routing carry per-peer-ness); DM = its own session ("channel of 1"). mission.md #5 reworded; "Shared-channel session semantics" DD added; spec steps reframed + DM-isolation step added. No substrate change.
- **H2 — channel messages silent by default** (policy gate): plain non-mention posts need `always_listen` or `@mention`. Resolved.
- M1 (disposition vocab → `no-eligible` for ACL-deny), M2 (`ingest_bots` feedback-loop guard: burner bots posting-only + isolated guild), L1 (`make test-live` is hardcoded to `test_aiat.py`; added dedicated `discord_hat` marker + `make test-discord-hat`). All incorporated.

**Cycle 2 → approve with changes.** All five resolutions verified against code. One residual (N1): the `always_listen` path STILL runs the engagement inference, which is strongly biased to silence (`_inference.py:73,81`) — so `always_listen=true` alone doesn't deterministically engage; plain messages could land `policy-silent` and read as false routing failures. **Resolution (better than the suggested wording fix):** switch the routing-leg engagement to `@mention`, which engages via the mention path with NO inference. Verified `is_mention` (`_discord.py:1825`) checks the bot's id in `message.mentions` independent of author → a burner-bot mention registers. DD reframed (`@mention` primary, `always_listen`+substantive fallback); L3 smoke now also verifies bot-mention registration; spec updated. N2 (cosmetic disposition wording) tightened.

**Design review complete (2/2 cycles).** No open blocking issues.
