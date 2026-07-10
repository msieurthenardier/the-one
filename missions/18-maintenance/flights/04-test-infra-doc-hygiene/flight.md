# Flight: Test-infra & doc hygiene

**Status**: ready
**Mission**: [Post-Mission-16 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] aiosqlite teardown durably fixed (T1)
- [ ] Doc/coverage hygiene: live-thinking `visibility` (DOC1), `agents.md` promotions (DOC2), behavior-test specs (T2/T3)

---

## Pre-Flight

### Objective
Clear the test-infra and documentation debt: durably fix the long-carried aiosqlite
teardown flake, emit the live-thinking `visibility` field, promote two conventions
into `agents.md`, correct two overstated Mission-16 lines, and author the two
recommended behavior-test specs. Hygiene flight — can slip if the mission shrinks.

### Open Questions
N/A.

### Design Decisions
N/A (maintenance).

### Prerequisites
- [x] `tests/conftest.py` aiosqlite worker daemonization present (the partial fix)

### Pre-Flight Checklist
- [x] Open questions — N/A
- [x] Design decisions — N/A
- [x] Prerequisites verified
- [x] Validation approach defined (suite green + no teardown warning; specs authored)
- [ ] Legs defined (during `/agentic-workflow`)

---

## In-Flight

### Technical Approach

**Leg 1 — Durable aiosqlite teardown fix (T1).**
Evidence: the `Event loop is closed` teardown surfaces as a
`PytestUnhandledThreadExceptionWarning` (`test_db_migration.py::TestSchemaV17`,
`RuntimeError('Event loop is closed')` in the aiosqlite worker thread). Presents as
cosmetic-Pass across two consecutive green runs, BUT F09 witnessed a real
intermittent hard failure (`test_lifespan.py::test_lifespan_drains_session_registry`)
from cross-test loop-teardown pollution — load-order-dependent, so a green run
doesn't retire it. `tests/conftest.py:62-99` (`_daemonize_aiosqlite_worker_threads`)
daemonizes the worker so the interpreter can't wedge, but doesn't stop the
cross-loop `close()` from raising into the warning. Durable fix: a fixture-scope /
`asyncio_mode` change so each raw `aiosqlite.connect` in the migration tests is
closed within its own loop (or a warning-swallow-at-source that addresses the
root, not a blanket filter). Verify by running the full suite (ideally a few
passes / a shuffled order) and confirming the teardown warning is gone and no
intermittent red surfaces. Oldest carried item — fix, don't accept.

**Leg 2 — Doc & coverage hygiene (DOC1 + DOC2 + Mission-16 corrections + T2/T3).**
- **DOC1 — live-thinking `visibility` (F10 debrief action item).** `app.py:1613`
  broadcasts `{"type":"thinking","content":_thinking_text}` with no `visibility`,
  while replay `codec.py:381-387` spreads it. Add the `visibility` field to the
  live broadcast to match replay (low severity — broadcast-only, re-derived on
  rejoin — but closes the F10 action item).
- **DOC2 — `agents.md` promotions (F11/F12 debriefs).** Promote two conventions
  that currently live only in code comments: (a) the OpenAI-compat mapping
  "rule-of-three" duplication note (cite both the A4 request-kwargs and A2
  content-block pairs); (b) the F11 seed-before-overlay provider-config save
  pattern.
- **Mission-16 corrections** (documentation only): in
  `missions/16-llm-provider-hardening/mission-debrief.md`, correct the Leg-09
  "verified dead code" claim to "conditionally-reachable defensive backstop,
  retained" (inspection Q1: narrow-but-reachable + tested), and mark the
  Windows-packaging references resolved. In `.../mission.md`, strike/mark-resolved
  the Windows seed-packaging Known Issue and the criterion-#8 footnote
  (fixed in commit `69512d2`; verified by the 2026-07-10 maintenance report).
  *(These corrections may already be applied when this flight runs — verify and
  skip if so.)*
- **T2/T3 — behavior-test specs** (author inline, per `.claude/skills/behavior-test/
  AUTHORING.md`): `tests/behavior/save-preserves-config.md` (F11 — open Admin, set
  `response_format`+`stop` via API, edit `reasoning_effort` in the UI editor, Save,
  re-fetch, assert all keys survive) and `tests/behavior/vision-round-trip.md` (F12
  — attach an image, assert the model's reply is grounded in the image; image-only
  no-text; rejoin-no-crash). Specs only — runs happen later via `/behavior-test`.

### Checkpoints
- [ ] Full suite green with NO `Event loop is closed` teardown warning (multi-pass)
- [ ] Live thinking broadcast carries `visibility`
- [ ] Two `agents.md` conventions written; two Mission-16 lines corrected
- [ ] `save-preserves-config` + `vision-round-trip` specs authored

### Adaptation Criteria
**Divert if**: the durable aiosqlite fix requires reworking the migration-test
harness beyond a fixture change — surface the larger scope rather than expanding
silently.
**Acceptable variations**: exact fixture-scope mechanism.

### Legs
> Planned one at a time during `/agentic-workflow`.
- [ ] `aiosqlite-teardown-durable-fix` — fixture-scope/`asyncio_mode` close (T1)
- [ ] `doc-coverage-hygiene` — visibility emit + agents.md promotions + M16 corrections + 2 behavior-test specs (DOC1/DOC2/T2/T3)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (no teardown warning across passes)
- [ ] Documentation updated (`agents.md`, Mission-16 artifacts, 2 behavior specs)

### Verification
Multi-pass green suite with the teardown warning gone; `agents.md` + Mission-16
corrections in place; both behavior-test specs authored and ready to run.
