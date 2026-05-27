# Flight Log: Pairing Resolution + Connectors-Screen Detach

**Flight**: [Pairing Resolution + Connectors-Screen Detach](flight.md)

## Summary

(Populated during and after execution.)

---

## Reconnaissance Report

**Date**: 2026-05-27 (Phase 1b, F9 planning)
**Source artifacts**:
- Mission Open Questions (`missions/11-discord-connector-depth/mission.md`)
- F7 flight debrief (`missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-debrief.md`) — Recommendation #3 (routine-maintenance candidates) and Action Items
- F8 flight debrief (`missions/11-discord-connector-depth/flights/08-provider-shape-portability-hardening/flight-debrief.md`) — Action Items

### F9 production-code surfaces (verified)

**Pairing resolution**:
- `the_one/connectors/_pairing.py:_validate_pairing_prefix` (lines 18-42) — text-prefix validator; pure function; STAYS UNCHANGED.
- `the_one/connectors/_inbound.py:410-449` — step-6 NeedsPairing handler (dispatcher); F9 extends to emit `pending-approval` audit event when no PAIR prefix is present.
- `account.config["pairing"]["code"]` (read at `_inbound.py:411`); `account.config["allowlist"]["peers"]` (mutated at `_inbound.py:428-438`) — same data model for both flows.
- `the_one/connectors/_discord.py:resolve` (line TBD — verify at L1) — must return `NeedsPairing` for unknown DMs; widen if currently returns Deny.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:489-510` — `renderPairingSection`; existing pairing UI; no F9 change.

**Connectors-screen detach**:
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1-82` — connector account detail page; "Attached Agents" section currently read-only summary (lines 19-20); F9 adds detach button per row.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js:88-150` — Connectors grid per-account tile; F9 adds agent-count badge.
- Detach API endpoint: new `DELETE /api/connector-accounts/{account_id}/agents/{agent_name}` (to be added at L3).

**Chat UI pending-approval surface**:
- `the_one/interfaces/web/static/js/areas/chat.js:116-134` — `addMsg` dispatcher on 5 event types (user, assistant, tool_call, tool_result, system); F9 adds the 6th type `pending-approval`.
- `the_one/db/codec.py:messages_to_ui_events` — codec projection; F9 adds new event-type case.

### Carry-forward item classification

| Item | Classification | Evidence | F9 decision |
|------|----------------|----------|-------------|
| **F7 Rec #3(a)** — `.tool-enable-switch` CSS default flip | `confirmed-live + shares-F9-surface` | `studio.css:750-761` shows n=4 override rules; default is `position: absolute` (designed for tile-corner consumers); studio.css L761 already flips to `relative` for `kv-sensitive-cell`. F9's connector-detail page will mount per-agent rows in the same CSS surface; fixing default now prevents accumulating override #5. | **Fold in as L5** |
| **F7 Rec #3(c)** — studio-event-bus n=3 inline-CustomEvent lift | `confirmed-live + shares-F9-surface` | 3 inline `new CustomEvent()` dispatches: `connector-account-always-listen-changed` (`connector-account-editor.js:1092`), `connector-account-pool-warmed` (`:1741`), `connector-account-discoverable-refresh-requested` (`:3266`). F9's L3 adds the 4th (`connector-agent-detached`). | **Fold in as L4** |
| **F7 Rec #3(b)** — `_inbound.py` numbered steps extraction | `confirmed-live + separate-surface` | `_inbound.py` at 1046 LOC; steps 1-12 documented at lines 55-103. F9 adds pairing pre-step inline (small ~20 LOC addition to step 6 handler); doesn't justify refactor. | **Defer to routine-maintenance** |
| **F7 Rec #3(d)** — field-row-3-column primitive | `confirmed-live + separate-surface` | F9 adds detach buttons in per-agent rows; uses button-row layout, not field-row primitive. | **Defer to routine-maintenance** |
| **F7 Action Item** — Plugin-author docs (`PLUGIN_AUTHORS.md`) | `confirmed-live + separate-surface` | No corresponding `the_one/connectors/PLUGIN_AUTHORS.md` exists. F9 doesn't add new plugin hooks (uses existing resolver + pairing). | **Defer to routine-maintenance** |
| **F8 Action Item** — Hoist dead `content is None` branch in `_inference.py` | `confirmed-live + separate-surface` | F9 doesn't touch `_inference.py` or the engagement-inference engine. | **Defer to routine-maintenance** |
| **F8 Action Item** — Extend `provider-shape-portability` convention with runbook | `confirmed-live + low-cost-doc` | F9 touches `agents.md` anyway for L4's studio-event-bus citation. Bundling is essentially free. | **Fold in as L5 second axis** |

### Operator decisions during F9 planning (logged for traceability)

- **Carry-forwards**: fold in 3 items (F7 #3(a) + F7 #3(c) + F8 convention runbook); defer 4 items. Operator-confirmed.
- **Pairing OQ**: (c) Discord-native primary + PAIR text-prefix fallback. Substrate primitive unchanged. Operator-confirmed.
- **Detach UI OQ**: detail-page only (mission default). Operator-confirmed.
- **Approval event type shape**: new top-level `pending-approval` event type (vs system-type variant). Operator-confirmed.
- **HAT inclusion**: yes, optional final leg covering the 8-step scenario.

### Pairing-architecture key findings

1. **Pairing is dispatcher step-6 (pre-routing), not post-routing.** F9's Discord-native flow extends the existing NeedsPairing handler at `_inbound.py:410-449`; does not add a new numbered step.
2. **Successful pairing = immediate allowlist mutation.** Both flows (text-prefix and Discord-native) mutate `account.config["allowlist"]["peers"]` synchronously inside the dispatcher's critical section (text-prefix) or via the new API endpoint (Discord-native). Same data path; same audit shape.
3. **Pairing code is account-scoped, not per-agent.** F9's dual-flow doesn't change this — all agents on the account inherit allowlist membership uniformly.
4. **Audit-log shape accommodates both paths.** Free-form JSON at `session_metadata["routing"]`; F9 audit entries add a `path: "text-prefix" | "discord-native"` discriminator for the F11 inspector to render uniformly.

---

## Leg Progress

(Populated as legs execute.)

---

## Decisions

(Runtime decisions not in original plan.)

---

## Deviations

(Departures from planned approach.)

---

## Anomalies

(Unexpected issues encountered.)

---

## Session Notes

(Chronological notes from work sessions.)

---

## Flight Director Notes

### 2026-05-27 — Flight planning

- Loaded `/flight` skill. Recon scoped to F9's natural surfaces + 7 carry-forward items from F7/F8 debriefs.
- Operator confirmed: fold in F7 Rec #3(a) CSS default flip + F7 Rec #3(c) studio-event-bus lift + F8 provider-shape-portability convention runbook (3 fold-ins); defer the other 4.
- Pairing OQ: (c) dual-flow (Discord-native primary + PAIR fallback). Detach UI: detail-page only. Approval event type: new top-level `pending-approval`. HAT: optional final leg.
- 5 mandatory + 1 optional HAT leg = right-sized for a UX-and-substrate-extension flight.
- F8 stray `docker-compose.yml` in working tree is now THIRD flight inheriting it (F7 L12 → F8 → F9). Long-running operator-side stash candidate; flag for operator at L1 start.
