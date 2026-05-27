# Flight Log: ACL DM-admission + channels-axis UI split

**Flight**: [ACL DM-admission + channels-axis UI split](flight.md)

## Summary

(Populated during and after execution.)

---

## Reconnaissance Report

**Date**: 2026-05-27 (Phase 1b, F10 planning)

**Source artifacts**:
- F9 flight log Known Issues (`missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md`) — 2 items surfaced by L8 HAT
- F9 L8 leg artifact (`missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/legs/08-hat-pairing-and-detach.md`) — per-step record + Findings sections

### Item classification

| Item | Classification | Evidence | F10 decision |
|------|----------------|----------|--------------|
| **ACL DM-admission gap** (F9 L8 finding 1) | `confirmed-live` | `the_one/connectors/_acl.py:323-329` account-scope channels-axis check lacks `is_dm` parameter; per-agent equivalent at `:372-378` has it. Verified by reading the function. | **Closed by L1** (substrate re-order + new `dm_admission` axis). |
| **ACL UI axis conflation** (F9 L8 finding 2) | `confirmed-live` | `connector-account-editor.js:2045-2057` renders one `channels` chip-list with no DM/guild distinction; `connectors-tab.js:522` per-agent ACL editor mirrors. Verified by reading the source. | **Closed by L2 + L3** (account-scope row + per-agent checkbox). |
| **L8 deferred steps (5-8)** | `confirmed-live` | Detach + PAIR-prefix fallback not exercised; both believed correct from unit/browser tests. | **Re-run via L5 HAT** (optional but recommended). |

All 3 items are real work; none are already-satisfied. Recon is short because L8 just generated these findings hours ago — no drift between source artifact and current code.

---

## Operator decisions during F10 planning

- **Substrate shape**: (b) new `dm_admission` axis (preferred over the simpler `is_dm` short-circuit because it preserves F8 L8 guilds-axis posture as an independent decision and gives the operator explicit per-account control).
- **Per-agent overlay shape**: opt-out checkbox only ("can uncheck in agent override (not add new)"). Tri-state field `admit_dms: bool | None` but UI only produces `null` (inherit) or `false` (opt-out).
- **HAT inclusion**: yes, optional L5.
- **Debrief sequencing**: F9 and F10 debriefed together AFTER F10 lands. No standalone F9 debrief — one combined retrospective covers the dual-flow + axis-split arc end-to-end.
- **Mission outline reorder**: F10 inserted between former F9 and former F10; downstream flights renumbered (F10→F11, F11→F12, F12→F13, F13→F14).

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

- Loaded `/flight` skill. Recon scoped to F9 L8 findings (3 items, all `confirmed-live`).
- Operator confirmed: substrate shape (b) `dm_admission` axis; per-agent opt-out checkbox; F9+F10 combined debrief; mission outline reorder.
- 4 mandatory + 1 optional HAT leg = right-sized for a substrate-extension + UI-affordance flight.
- F8 stray `docker-compose.yml` in working tree is now FOURTH flight inheriting it (F7 L12 → F8 → F9 → F10). Long-running operator-side stash candidate; flag at L1 start.
- F10 branches from F9 HEAD (`07d3093`) rather than blocking on PR #78 merge. Rebase onto main once F9 lands.

### 2026-05-27 — Cycle-1 Architect review

**needs-rework**. Two HIGH-severity findings:
- §1 / §3 understated the Pydantic validator extensions needed. Both `db/models.py:305-341` (account-scope allowlist validator) and `agent/config.py:230,262-322` (per-agent connector_acls validator) are strict per-key validators that reject unknown keys AND enforce per-key value types as `list[str]`. The new `dm_admission` (Literal-string) and `admit_dms` (bool) both violate the type-uniformity invariant. **Resolution**: §1 + §3 rewrote to explicitly call out the validator-extension surface (add to allowed-keys set + branch by key for value-type validation). L1 description updated.

Two MEDIUMs:
- L1 named `tests/test_acl_admits_inbound.py` — wrong; actual file is `tests/test_connectors_acl.py` (730 LOC, 58 tests). Plus 3 specific tests at `:486`, `:592`, `:605` pin the F8 L8 posture being inverted; they MUST be inverted (not added-around). **Resolution**: L1 description renamed the file + listed the 3 inversions explicitly.
- §6 should add a NEW sibling helper for the boolean opt-out checkbox (not parameter-extend `_buildAxisRow` which is axis-shaped for `list[str] | None`). **Resolution**: L3 description prescribes `_buildAdmitDmsRow` sibling helper.

One LOW:
- §4 migration cited v17/v18/v20/v21 as precedents; those are ALTER ADD COLUMN, wrong for the row-rewrite L1 needs. **Resolution**: §4 cites v7 row-rewrite at `schema.py:286-303` instead.

### 2026-05-27 — Cycle-2 Architect review

**approve**. All six cycle-1 issues verified resolved. Two non-blocking cosmetic suggestions (validator-default explanation density; line-citation notation) accepted as-is.

Flight design ready for execution. Spec status: planning → ready (next session).
