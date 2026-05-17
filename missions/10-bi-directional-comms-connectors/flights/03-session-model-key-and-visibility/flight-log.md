# Flight Log: Session Model — Schema, Key Normalization, Visibility

**Flight**: [Session Model — Schema, Key Normalization, Visibility](flight.md)

## Summary

Status: planning. Flight created 2026-05-17. Awaiting design-review pass before execution.

---

## Reconnaissance Report

**Date**: 2026-05-17
**Scope**: F1 + F2 debrief carry-forward items + Flight 3 code surface

Source artifacts walked:
- `flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-debrief.md` (Action Items + Recommendations)
- `flights/02-admin-surface-for-connector-accounts/flight-debrief.md` (Action Items + Recommendations)
- `the_one/agents.md` (Known Issues, Project Conventions, Connector subsystem decisions)
- `maintenance/2026-05-15.md` (most recent maintenance report)

### Classification table

| # | Source | Item | Classification | Evidence | Recommendation |
|---|--------|------|----------------|----------|----------------|
| 1 | F1 | Patch F1 flight.md leg-6 bullet (lifespan wiring shipped this flight, not deferred) | confirmed-live | F1 flight.md:175 already updated | Retire — already done |
| 2 | F1 | Add `function-local-import-to-break-load-cycle` convention to agents.md Project Conventions | confirmed-live | agents.md:86-94 documents pattern with three citations | Retire — already done |
| 3 | F1 | Lift `_secrets_to_ciphertext` / `_ciphertext_to_secrets` to shared helper | needs-human-recheck | Recon could not locate the refactor in current `db/repositories.py`. F2 design decisions said L0 would do this; may have shipped but not verified at code level in this recon pass. | Flag for user — confirm whether shipped in F2 L0; if not, schedule for next maintenance |
| 4 | F1 | F2 leg artifact: include `_evict_all_for_account` wiring in rotation | confirmed-live | F2 debrief §Outcome Assessment confirms wiring at `rotate_encryption_key` with `test_rotation_evicts_warm_pool_entries` as the regression net | Retire — done |
| 5 | F1 | F2 leg artifact: cite `__MASKED__` sentinel contract at `db/repositories.py:447` | needs-human-recheck | Not verified in recon; F2 debrief does not flag missing | Flag for user — likely satisfied; defer |
| 6 | F1 | **Flight 3 leg artifact: include `last_activity` per-inbound-acquire ratification as Design Decision** | confirmed-live in this flight | This flight's Design Decisions section ("`last_activity` per-inbound-acquire — RATIFY") and leg 4 acceptance criteria address it directly. The pool's `acquire()` at `connectors/_pool.py:479` already touches `last_activity`; dispatcher calls `acquire` per inbound. | Retire on this flight's completion — cite leg 4 as the contract anchor in agents.md Known Issues |
| 7 | F1 | F4 leg artifact: `ConnectorClient` Protocol-widening pattern | needs-human-recheck | Out of F3 scope; defer to F4 planning | Defer to F4 |
| 8 | F1 | F10 leg list: add untested edge cases | forwarded | Out of F3 scope | Defer to F10 |
| 9 | F1 | Add "Skeleton for a real plugin" code block to `connectors/README.md` §3 | needs-human-recheck | F2 L0 design decision said it would land; F2 debrief recommendation 5 says it still needs API-edge contract paragraph + non-empty `message` example. Mixed signal; partial state likely. | Flag for user — schedule for next maintenance unless already done |
| 10 | F1 | Fix 2 `AsyncMock-never-awaited` warnings on `test_provider_api.py` | drifted | Maintenance report 2026-05-15 confirms "third consecutive flight carrying these" | Schedule for next maintenance flight (not F3 scope) |
| 11 | F2 | Symmetric `model_copy(update=...)` → `model_validate(existing.model_dump() \| data)` fix on MCP + provider PUT routes | confirmed-live | F2 debrief §What Could Be Improved confirms `model_copy` pattern still present at `api.py:2393`, `:2606` | Schedule for next maintenance flight (not F3 scope; would touch surfaces F3 does not edit) |
| 12 | F2 | Codify two-pass planning grep + schema-ALTER column-set audit as agents.md conventions | needs-human-recheck | F2 debrief flagged both as standardization; not verified to be in current agents.md as named conventions | Schedule for mission-control / agents.md update (cross-cutting; not F3) |
| 13 | F2 | **Flight 3 planning input: decide eviction trigger for chat-session lifecycle field explicitly** | confirmed-live in this flight | This flight's Design Decisions section ("Eviction trigger for `session_continuation_seconds` change — NONE") addresses it directly; leg 5 acceptance criterion `test_session_continuation_change_does_not_evict` is the verification anchor | Retire on this flight's completion |
| 14 | F2 | Stub-visibility policy before Flight 8 | needs-human-recheck | Out of F3 scope; defer to pre-F8 decision | Defer to pre-F8 |
| 15 | F2 | `connectors/README.md` §3: API-edge masked-sentinel contract paragraph + skeleton plugin `message`-field example | needs-human-recheck | Documentation gap; likely still open | Schedule for next maintenance |
| 16 | F2 | Document rotation-inter-commit-and-`install_key` race + shared-pool divergence in mission Known Issues | needs-human-recheck | Mission.md Known Issues currently has 1 entry (M07 `_pool.py` carry-forward); rotation race + shared-pool divergence not explicitly added | Schedule for mission housekeeping (not F3-blocking) |
| 17 | F2 | Human review of design-language screenshots | needs-human-recheck | Mission criterion gating; out of F3 scope | Defer to design-language gate at mission end |

### Items consumed by Flight 3

- **#6** — `last_activity` per-inbound-acquire ratification → Design Decisions + leg 4
- **#13** — Eviction trigger for `session_continuation_seconds` → Design Decisions + leg 5 test

### Items NOT consumed by Flight 3 (forwarded)

- **#3, #5, #9, #15** (documentation / refactor housekeeping) — schedule for the next maintenance flight
- **#10, #11** (test warnings + PUT validator bypass) — schedule for the next maintenance flight
- **#12, #16** (agents.md / mission Known Issues codification) — mission-control / housekeeping
- **#14, #17** (stub-visibility, design-language gate) — pre-F8 / mission-end decisions

### Code anchors verified

- `the_one/db/schema.py:11` — `CURRENT_VERSION = 15`
- `the_one/llm/base.py:42-66` — `Message` dataclass shape (unfrozen; 5 fields)
- `the_one/db/codec.py:54-94` — `message_to_dict / message_from_dict` (optional-field pattern via `d.get`)
- `the_one/db/codec.py:107-172` — `messages_to_ui_events` (4 event types; no current visibility projection)
- `the_one/connectors/_pool.py:85-112` — `_RegistryEntry` with `last_activity` field + the F1-debrief comment noting Flight 3 must ratify
- `the_one/connectors/_pool.py:479` — `entry.last_activity = time.monotonic()` (the acquire-touch site)
- `the_one/connectors/base.py:32-140` — `InboundEnvelope`, `OutboundTarget`, `SessionKey`, `DoctorReport` dataclass shapes
- `the_one/connectors/_stub.py:117-124` — `StubPlugin.push_inbound` recorder
- `the_one/agents.md:338-345` — Known Issues entry for `last_activity` (will be updated by this flight)

---

## Leg Progress

(none yet — flight in `planning`)

---

## Decisions

(none yet — runtime decisions logged during execution)

---

## Deviations

(none yet)

---

## Anomalies

(none yet)

---

## Session Notes

**2026-05-17** — Flight created. Phase 1 (mission + F1/F2 debrief review), Phase 1b (recon against current code), and Phase 5 (spec draft) complete. Phase 5b (architect design review) pending. Phases 3+4 (user framing + crew interview) compressed: user pin "work without stopping for clarifying questions" — reasonable design calls made and embedded in spec with rationale; user invited to redirect via review.
