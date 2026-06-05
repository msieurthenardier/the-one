# Flight Debrief: Retention Setting

**Date**: 2026-06-05
**Flight**: [Retention Setting](flight.md)
**Status**: landed
**Duration**: 2026-06-05 (single session)
**Legs Completed**: 2 of 2

## Outcome Assessment

### Objectives Achieved

The flight delivered the per-agent `chat_history_retention_days` setting end to end: the
`AgentConfig` field (`Field(ge=1, le=365, default=30)`), its v30 schema migration
(`NOT NULL DEFAULT 30`, backfilling existing agents), the `save()`/`_row_to_config()` round-trip,
and the General-tab Behavior-section number input above Max Iterations with raw-value-preserving
form collection. No purge logic or scheduler (correctly scoped out to Flights 2 and 3). The
rebuilt live instance serves the field at 30 on all five existing agents — the migration was
verified against the real DB, not only fixtures.

### Mission Criteria Advanced

- **Criterion 1** (retention setting exists in the Behavior section above Max Iterations,
  1–365, default 30) — advanced and substantiated by the browser placement test
  (`compareDocumentPosition`), the live-instance field check, and the `Field` default.
- **Criterion 2** (persists across save/reload; out-of-range rejected, not clamped) — advanced
  and substantiated by the `test_db_api.py` persist round-trip + out-of-range 422, plus DD6
  raw-value preservation. The *rendered* reload + visible-error UX remains verified only by the
  deferred behavior test (see What Could Be Improved).

All flight checkpoints met except the behavior-test acceptance gate, which was deferred by
operator decision (session lacked SendMessage continuation for the Witnessed crew).

## What Went Well

- **Per-leg design review caught three real issues before any code shipped.** The Developer
  design reviews surfaced (and the Flight Director independently verified): the two literal
  `assert CURRENT_VERSION == 29` pins (`test_db_migration.py:278`, `:5018`) that the v30 bump
  would break; the E501 violation in the un-split ALTER (119 chars > 100); and — most valuable —
  that a bare `pytest tests/browser/...` runs **zero** tests because `pyproject.toml:76` `addopts`
  deselects `browser`, which would have been a silent false-green. That last catch alone saved a
  bogus "tests pass" claim.
- **The atomic-leg discipline (DD1) was correct and frictionless.** Bundling field + migration +
  `save()` + decode in one leg meant no agent load ever hit a missing column; the `IndexError`
  failure mode the design feared never had a window to occur.
- **Declarative `Field(ge/le)` → 422 (DD2) was zero-cost.** The existing
  `model_validate → ValidationError → 422` path needed no endpoint changes; the 422 test confirms
  it works exactly as predicted.
- **Live-DB verification, not just mocks.** Confirming all five real agents serve the backfilled
  value (30) closed the gap the M12 F01 debrief warned about ("verify against the live database,
  not just mocks").
- **Independent code + accessibility review both passed clean.** WCAG AA pass on the new input
  (proper label/`for` association, native spinbutton, focus/contrast at parity with the sibling).

## What Could Be Improved

### Process

- **Live behavior-test execution prerequisites must be a Pre-Flight Checklist item, not an
  acceptance-gate assumption.** Both the Developer and Architect independently flagged this. The
  flight spec correctly listed the *environmental* preconditions for the behavior test (instance
  up, Chrome MCP, seeded agent) and even premise-audited the apparatus on both axes (DD5) — but it
  did not list the *crew-execution* prerequisite: a session with SendMessage continuation for the
  live Executor/Validator pattern. That gap surfaced only at the acceptance gate, forcing a
  binary choice between a degraded ~12-spawn re-spawn-per-step run and deferral. This is a
  methodology gap, not a flight error — see Recommendations.
- **One prerequisite (Playwright/Chromium system libs in the running container) was discovered at
  execution time, not planning time.** Leg 2 had to manually `apt-get install` missing `.so` files
  (`libglib-2.0.so.0`, `libnspr4`, `libnss3`) because the running container's Playwright revision
  drifted from the baked image. `make rebuild` rebakes them, but the gap cost mid-leg time and
  blocked a clean browser-suite timing capture at debrief.

### Technical

- **Test metrics (this flight vs. priors).** Unit suite
  (`pytest -m "not browser and not live and not pixel and not requires_bwrap and not discord_hat"`):

  | Flight | Passed | Skipped | Deselected | Wall (s) |
  |--------|--------|---------|------------|----------|
  | M11 F17 (daily-driver-gate) | 2935 | 4 | 536 | ~282 |
  | M12 F01 (dep-bump) | 2935 | 4 | 538 | 289.51 |
  | **M13 F01 (this)** | **2957** | **4** | **544** | **293.40** |

  Delta vs. M12 F01: **+22 passed** (exactly this flight's new tests), **+3.89 s wall (~1.3%,
  within the historical ±25 s band — not a regression)**, skip count unchanged. The three run
  warnings are the **pre-existing `aiosqlite` "Event loop is closed" teardown warning in
  `test_db_migration.py::TestSchemaV17`** — carried in every debrief since F11; the M12 debrief
  already recommended a `filterwarnings` entry or a standing ticket. It is ripe for action.
  Browser-suite standalone timing could **not** be captured (Playwright libs missing in the
  running container); no prior debrief has a browser-suite baseline either, so this remains
  un-seeded.
- **The behavior test's marginal coverage is a genuine (if narrow) gap.** Automated tests cover
  the *data* round-trip and the *API* 422, but two **rendered-UX** paths have no mechanical
  verification: after a Save, does the input reflect the saved value on the next paint
  (`studio.js:2442` `loadAll()` reload)? And on a 422, does the validation error surface visibly in
  `errorEl` (`studio.js:2459`)? Those two are precisely the deferred behavior test's value.
- **DD6 carries documentation debt at the code site.** The `collectFormData` branch
  (`studio.js:1930`) intentionally diverges from the sibling `max_iterations` `|| 20` idiom, but
  there is no inline comment — a future developer "normalizing" the two branches would silently
  reintroduce the falsy-`0`-coercion bug DD6 exists to prevent. The render template
  (`general-tab.js:122`, `cfg.chat_history_retention_days || 30`) uses the very idiom DD6 forbids in
  the collect path; harmless (the NOT NULL DEFAULT 30 column + Pydantic bound make a stored `0`
  impossible) but conceptually inconsistent and undocumented.

### Documentation

- **The `Field(ge=N, le=M)` → 422 bounded-int pattern is now a second clear precedent but is
  undocumented as a convention.** It is the first scalar-range field in `AgentConfig` (the existing
  `@field_validator`s all enforce nested-dict shapes). A short note in `the_one/agents.md`
  conventions would steer future scalar-range fields away from unnecessary custom-validator
  machinery, and would let the "atomic-leg / same-leg migration" rule (currently implicit from the
  F4 debrief) be made explicit now that v30 is a second example.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| v30 migration wraps the column work in an `agents` table-presence guard (`sqlite_master` check) beyond what DD4 specified | Partial-schema test fixtures reach the v30 block without an `agents` table, so `ALTER TABLE agents` would fail; mirrors v29's `pending_approvals` guard | **Yes** — already the house idiom; future migration blocks touching `agents`/`chat_sessions`/`pending_approvals` should include it by default, and flight specs should enumerate it rather than implying it via "mirror vN" |
| `TestSchemaV30` v29-fixture test builds a fresh minimal DB rather than rewinding a full-schema DB | SQLite < 3.35 in the container lacks `DROP COLUMN`, making rewind unreliable | **Yes** — reusable pattern for any future `agents`-table column migration test |
| Behavior-test acceptance deferred (not run) | Session lacked SendMessage continuation for the Witnessed crew; operator chose to land on automated + live evidence | No (deviation), but **the prerequisite check it exposes should be standardized** — see Recommendations |
| Frontend `collectFormData` uses `Number.isNaN(n) ? 30 : n` instead of `|| 30` (DD6) | `|| 30` would coerce a typed out-of-range `0` to a valid `30`, defeating criterion 2 | **Yes** — for any client-collected field that has a server-side bound, preserve the raw value so the server rejects out-of-range; document at the code site |

## Key Learnings

- **A flight's "verification" section can be technically complete on paper (apparatus audited,
  surfaces confirmed) yet undeliverable in the running session.** Live, multi-agent acceptance
  tests have a *tooling* dependency (here, SendMessage continuation) separate from their
  *environmental* dependencies. Treat the former as a hard prerequisite.
- **The migration-test trio (fresh-DB + on-fixture + idempotent) plus a live-DB backfill check is a
  strong, repeatable pattern** for any additive schema change — it caught nothing because nothing
  was wrong, which is the point.
- **Design reviews that the orchestrator independently re-verifies (rather than trusting) convert
  "approve with changes" into landed-correct in one cycle** — the same lesson the M12 F01 debrief
  drew, reconfirmed here on the browser-marker false-green catch.

## Recommendations

1. **Add a Pre-Flight Checklist item for live behavior-test execution prerequisites.** When a
   flight names a behavior test as an acceptance gate, the spec's prerequisites must include the
   Witnessed-crew execution requirements (SendMessage continuation available; Chrome MCP live;
   running rebuilt instance) — checked at planning, not discovered at the gate. *This is a
   mission-control `/flight` (and `/agentic-workflow`) methodology improvement candidate*, surfaced
   independently by both debrief agents.
2. **Run the deferred `agent-retention-setting-roundtrip` behavior test in a continuation-capable
   session before Mission 13 is called complete** — it is the only verification of the rendered
   reload-persistence and visible-error-on-reject paths. It is the natural entry gate for Flight 2.
3. **Add an inline DD6 comment at `studio.js:1930`** (e.g. `// preserve raw value — || 30 would
   coerce a typed 0→30 and mask the server-side ge=1 reject`) so the divergence from the
   `max_iterations` branch is self-explaining.
4. **Act on the standing `aiosqlite` event-loop-closed teardown warning** (`TestSchemaV17`) —
   recommended since F11/M12 and still open: either a scoped `filterwarnings` entry or a tracked
   maintenance ticket. Roll into the Mission 13 end-of-mission maintenance flight if not sooner.
5. **Document the `Field(ge/le)` bounded-int + same-leg-migration conventions in
   `the_one/agents.md`** now that v30 is a second concrete example.

## Action Items

- [ ] Run `agent-retention-setting-roundtrip` in a SendMessage-continuation-capable session (closes
  the rendered-UX coverage gap; gates Flight 2). *Tracked in mission Known Issues.*
- [ ] Add the inline DD6 comment at `studio.js:1930` (fold into Flight 2 or Flight 4 — same file
  neighborhood).
- [ ] Carry forward to Flight 2 (Purge Now) design: add `ChatSessionRepository.delete_all_for_agent`
  (`DELETE FROM chat_sessions WHERE agent_name = ?` — safe; FK dropped at v5); a sessions-scoped API
  endpoint distinct from `delete_agent` (`api.py:509`); reuse the `App.confirmDelete` arm-then-fire
  pattern (`general-tab.js`) for the "Purge now" control; an agent-scoped delete sweeps connector
  sessions too (keyed on `agent_name`, `connectors/_session.py:183`).
- [ ] Carry forward to Flight 3 (Daily Purge) design: decide `last_purge_at` storage (new metadata
  row vs. settings store) as a DD; reuse the additive-migration idiom + the fresh-file fixture-test
  pattern; mirror the M12 F05 web-session reaper lifespan shape (`app.py:512`/`:113`/`:232`) but
  due-based not interval-based; the purge DELETE keys on `updated_at < now('-N days')` with N from
  each agent's `chat_history_retention_days` (semantics confirmed at `repositories.py:1025`/`:1078`).
- [ ] Propose the "live behavior-test prerequisites in Pre-Flight Checklist" improvement to the
  mission-control `/flight` skill (methodology, not project — raise with the operator).
- [ ] (Carried, non-blocking) `system_prompt` textarea a11y label gap (WCAG 1.3.1/4.1.2) — fold into
  Flight 4 (Alignment) or a maintenance flight. *Tracked in mission Known Issues.*
- [ ] (Carried) Standing `aiosqlite` teardown warning — `filterwarnings` or maintenance ticket.
