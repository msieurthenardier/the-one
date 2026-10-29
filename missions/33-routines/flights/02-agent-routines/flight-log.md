# Flight Log: Agents Schedule Their Own Routines

**Flight**: [Agents Schedule Their Own Routines](flight.md)

## Summary

*(Written at landing.)*

---

## Leg Progress

---

## Decisions

### Planned without a planning conversation (operator)
**Context**: The operator asked for this flight to be planned and flown
directly after the Flight 1 debrief and merge (2026-10-29).
**Decision**: Every decision the mission left open is settled in the flight
spec as an *(autonomous judgement call)*, marked *(J)*. The mission's Flight 3
HAT reviews them with the operator.
**Impact**: DD1, DD2 and DD5-DD13 carry *(J)* marks.

### Design review cycle 1 (planning)
**Context**: The Architect (Opus) approved with changes: four high issues,
eight medium and six low, plus suggestions.
**Decision**: All were applied.

**High:**
- **DD3:** the service takes `conn` from its caller, because
  `test_routines_api.py` patches `api.get_connection`. Without this the
  "unedited" guard trips. `NameRuleError` and the scheduler poke move in too.
- **DD4:** `save` leaves the two switches out of its `ON CONFLICT` update, so
  a General Save cannot turn Routines off.
- **DD7:** routine taint now spans the whole conversation. A history scan of
  `routine_id`s, with flags looked up and `routine:unknown` for a gone
  routine, covers later turns and a resumed pause.
- **DD7:** the `list_my_routines` marker moved from a per-turn set to a fixed
  sentinel in the stored result.

**Medium:**
- a separate `routine_writes` counter;
- the proposal and caps writes composed inside the repository's one
  transaction;
- `payload` is the validated request with an absolute `at`, `base` is the raw
  fields, and approval runs the full service write;
- squawk 0277 is limited to the provider, because dangling `kb_ids` are
  designed (M24 DD-14);
- `this_chat` resolves `turn.session_id` first, and the eval harness creates
  a chat row;
- a Routines-on token measure;
- the pinned trusted-set test is an intended edit, with a leaf names module;
- leg 3 split into tools (3) and evals (4), with Ollama and the token
  re-checked at leg time.

**Low:**
- refuse only changes that raise a capped measure;
- DD9 re-pointed: a cancel cascades the run's history, and the drawer fact is
  pinned;
- `ValueError`, not `ToolError`;
- name matching is case-insensitive;
- the target adapter;
- no `routines=` capability flag;
- the approve and dismiss routes are classified.

**Suggestions taken:**
- the revisions route's stale keys, and an idempotent dismiss;
- the `name_repair` note;
- the newest 500 resolved proposals kept per agent;
- a pending create never reaches `list_due`;
- a Python describer.

**Not taken:** `describe_my_capabilities` mentioning the routine tools. The
seeded tool descriptions already tell the model.

**HAT notes recorded**: an agent write to an operator routine flags the whole
routine; an allowlisted-peer exemption to connector-chat flagging.

**Impact**: This was a substantive change, so a second review cycle runs.

### Design review cycle 2 (planning)
**Context**: The Architect (Opus) approved with changes: two new high issues,
five medium and six low, plus suggestions. All of its spot-checked citations
held.
**Decision**: All were applied.

**High:**
- **DD5:** every routine tool call re-reads the switch and the approval flag
  in its transaction and refuses when the item is off. A cached web `Agent`
  outlives a switch-off, which is the notes `NotesDisabledError` pattern.
  The HAT note: turning Routines on reaches an open web chat only after a
  rebuild.
- **DD7:** the history taint snapshots the flag on the USER message at bind
  time (`Message.routine_untrusted_sources`), instead of reading the
  routine's current flag. That closes the fail-open after an operator clear
  and the permanent `routine:unknown` noise after a delete. The scan is
  pure, with no DB access, so the notes tools need nothing new.

**Medium:**
- the stale 0277 checkpoint wording;
- a new `GET`/`PUT .../self-configuration/routines` pair, with the existing
  GET and POST byte-identical (a pinned shape);
- every count and frequency cap moved into leg 2;
- the proposal operations (`insert_applied`, `insert_pending`, `resolve`),
  the flag mode `merge`/`clear` and the stale check, all inside the mutator
  transaction;
- the eval `compute_taint` mirror named.

**Low:**
- the sentinel fires on any flagged routine or proposal, `head`
  truncation is pinned, and the write tools never echo stored text;
- the describer omits chat titles;
- the lane globs stay disjoint;
- the payload stores the adapted target;
- INSERT uses the literal defaults;
- a CLI write refuses;
- the doc ownership is assigned per leg.

**Suggestions taken:**
- conservative runs-per-day weights;
- the tool says when it replaced an earlier pending change;
- an operator delete supersedes that routine's pending proposals;
- refused calls are not recorded *(J)*.

**Impact**: The maximum two cycles are done. The fixes are precise, so there
is no third review. The flight is `ready`.

---

## Deviations

---

## Anomalies

---

## Session Notes

### Flight Director Notes
