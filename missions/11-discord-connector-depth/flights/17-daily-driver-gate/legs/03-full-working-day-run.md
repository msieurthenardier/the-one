# Leg: full-working-day-run

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: interactive / operator-judgment (no autonomous implementation)

> **Closure (operator-judged, 2026-06-03):** the UI once-over portion completed in full — it surfaced findings F1–F4 and the entire injected A–F batch, all designed/reviewed/implemented/committed with two Witnessed behavior tests passing 7/7 against the real environment (incl. a live Discord round-trip). The daily-driver soak (#19) is accepted on the strength of this session's **real-traffic live use** rather than a separate stopwatch 8-hour run: the bot ran live throughout (incl. a clean restart that auto-reconnected — L4), L1's disposition stream + the new live connection status proved out as evidence surfaces, and every robustness issue the live use surfaced (silent-offline reaper F2→L4; the two-step DM-grant F3a→D) was root-caused and fixed in-flight. The formal HAT entry-gate was deliberately skipped at kickoff (soak on real config, not HAT-reconfig). #17 (rate-limiting) closes passively: the 429 substrate is code-correct and no cascade appeared under live use. *(The mission-debrief makes the final #19/#17 criteria call.)*

## Objective

Validate mission criterion **#19** (the connector survives a full working day of daily-driver use with no operator intervention) against a real working day, while passively watching **#17** (rate-limiting), running a deliberate **once-over of every UI surface** (surfacing `ui-fix-*` legs), and assessing the parked F16 pairing two-step DM-grant gap.

## Context

- This is the mission's final operational gate. It rides on L1's instrumentation (the disposition stdout stream + the `GET /api/connectors/{id}/disposition-counters` endpoint) as the evidence surface and L2's hardened HAT driver as the entry-gate regression check.
- **Interactive leg**: the Flight Director guides; the operator performs. No Developer/Reviewer agents drive the soak. UI-sweep findings become injected `ui-fix-*` legs (expected, pre-authorized).
- Watch-list: the parked F16 Known Issue — an approved peer gets channel access immediately but can't DM until the operator flips the per-peer toggle, with no UX signal. The full-day run is the trigger to decide whether that needs a focused follow-on.

## Acceptance Criteria (verification steps)

- [ ] **Entry gate:** the committed HAT driver runs green against the live guild (`make test-discord-hat`) — confirms the live baseline before the soak. (Needs `.env.hat` + a container restart after any connector reconfig, since `ingest_bots` is read at connect time.)
- [ ] **Full working day, no intervention:** the bot runs across a real working day with **no manual restarts, no token re-decryption issues, no stuck sessions, no silently-dropped inbound** — evidenced by the L1 disposition stream (`docker logs the-one | grep -E 'connector\.(inbound|outbound)'`: every inbound accounted for; no unexplained gaps) + the counters endpoint + session `last_inbound_at` advancing.
- [ ] **Passive #17:** no 429 cascade observed (`grep 'disposition=rate_limited'` empty or, if any, handled gracefully — no tool-failure cascade). If a cascade surfaces, it is documented as the trigger for a backpressure follow-on (NOT built in-flight).
- [ ] **Full-UI once-over:** every operator-facing surface walked while the bot is live (Chat; Studio agent editor + connector editor incl. the Discord-shaped creation form, allowlist + routing dropdowns, detach, per-agent ACL overlay; Administration; the audit-log inspector). Every finding logged in the flight log and triaged: fixed via an injected `ui-fix-*` leg, or filed as out-of-scope (Known Issue / follow-on) with rationale.
- [ ] **#1–4 opportunistic check:** the sweep confirms the Discord-shaped UX criteria (#1 creation form, #2 vocabulary, #3 allowlist dropdowns, #4 routing dropdowns) are genuinely satisfied — reconciling the stale mission checkboxes — or surfaces gaps as `ui-fix-*`.
- [ ] **Parked pairing DM-grant gap assessed:** during the day, note whether an approved peer's DM silently failing causes real confusion → decide keep-parked vs scope a follow-on.

## Verification Steps

- Entry gate: `make test-discord-hat` → green (or the targeted scenario files).
- Disposition evidence: `docker logs the-one | grep -E 'connector\.(inbound|outbound)'`; `curl -s localhost:8484/api/connectors/{id}/disposition-counters`.
- Liveness: bot stays online (no restarts in the operator's docker); `is_alive` healthy; sessions advance.
- UI once-over: walk each surface; capture findings (screenshots gitignored per the snapshot rule).

## Implementation Guidance

This leg is not implemented by agents. The Flight Director:
1. Confirms the entry gate green (guides the operator through the restart + `make test-discord-hat`).
2. Drives / co-walks the full-UI once-over, logging and triaging findings.
3. For each actionable UI defect, injects a `ui-fix-*` leg (designed + implemented via the normal 2a/2b cycle, committed in follow-up commits — no amend).
4. Tracks the full-day soak as operator wall-clock; collects the L1 evidence at end-of-day.
5. Lands the flight (status → `landed`, check off in mission.md) only after the day's evidence is in and the UI sweep is triaged.

## Files Affected

- None directly (verification + flight-log evidence). Injected `ui-fix-*` legs touch their own surfaces.

---

## Post-Completion Checklist

- [ ] Entry gate green
- [ ] Full-day evidence collected + assessed (#19)
- [ ] #17 passive watch resolved (no cascade, or follow-on scoped)
- [ ] UI once-over complete; all findings triaged; `ui-fix-*` legs landed or filed
- [ ] Parked pairing DM-grant gap assessed
- [ ] Update flight-log.md with the run evidence
- [ ] Flight → `landed`; check off F17 in mission.md (this IS the final leg)
