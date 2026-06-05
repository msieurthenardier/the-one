# Flight: Retention Setting

**Status**: in-flight
**Mission**: [Chat History Retention](../../mission.md)

## Contributing to Criteria
- [ ] Each agent exposes a chat-history retention setting (an integer number of days,
  constrained to 1–365, defaulting to 30) in the General tab's Behavior section,
  positioned above Max Iterations.
- [ ] The retention value persists across save and reload, and out-of-range values
  (below 1 or above 365) are rejected with a validation error rather than silently
  accepted or clamped.

---

## Pre-Flight

### Objective

Add a per-agent `chat_history_retention_days` setting (integer, 1–365, default 30) to
`AgentConfig`, persisted as a dedicated SQLite column via a v30 schema migration, and
surface it as a number input in the General tab's Behavior section above Max Iterations
with full save/load wiring. This flight delivers **only** the setting and its persistence
round-trip — no purge logic and no scheduler (those are Flights 2 and 3). Out-of-range
values are rejected with a validation error (surfaced as HTTP 422) rather than clamped.

### Open Questions

All three mission-level open questions bearing on this flight were resolved during mission
planning and re-validated against current `main` on 2026-06-05 (mission.md Open Questions):

- [x] **Storage shape** → dedicated SQLite column requiring a **v30 migration**; the
  Pydantic field, the migration, the `save()` column, and the `_row_to_config()` decode
  must all land in the **same leg** (atomic-leg pattern) to avoid an `IndexError` on load.
  See Design Decisions.
- [x] **Applying retention to pre-existing history** → the v30 migration backfills
  `chat_history_retention_days = 30` on existing agents; no special handling of existing
  chat data in this flight (purge enforcement is Flight 3).

No open questions remain for this flight.

### Design Decisions

**DD1 — Field + migration + round-trip land in ONE atomic leg**: The Pydantic field, the
v30 migration, the `save()` INSERT/UPDATE column, and the `_row_to_config()` decode ship
together in the first leg.
- Rationale: `_row_to_config()` reads agent columns by name; `aiosqlite.Row[<missing>]`
  raises `IndexError` (in-code note at `db/repositories.py:239–242`). If the decode shipped
  before the migration, every agent load on an un-migrated DB would crash. Bundling
  guarantees the column exists before any code reads it. This mirrors the M10 F6 L1c
  precedent for `connector_acls` and the F4 debrief rule ("a Pydantic field intended to
  persist ships its migration in the SAME leg").
- Trade-off: a single leg touches four files (`config.py`, `schema.py`, `repositories.py`,
  plus tests) — larger than a one-file leg, but indivisible by construction.

**DD2 — Bound the field with Pydantic `Field(ge=1, le=365)`, default 30**: Validation is a
declarative `Field(ge=1, le=365, default=30)` constraint, not a hand-written
`@field_validator`.
- Rationale: the POST (`api.py:482`) and PUT (`api.py:502`) endpoints already call
  `AgentConfig.model_validate(data)` and map `ValidationError → 422`
  (`api.py:483–484`, `:503–504`). A `Field` bound surfaces out-of-range values as a 422 with
  **zero new endpoint code** and satisfies "rejected … rather than silently accepted or
  clamped" exactly. It is simpler and less error-prone than a custom validator.
- Trade-off: this is the first bounded-int field in `AgentConfig` (the existing custom
  `@field_validator`s all enforce nested-dict shapes that a type hint can't express; a scalar
  range does not need that machinery). The HTML input also carries `min="1" max="365"`, but
  the **authoritative** reject is server-side — the input attributes are a UX hint only and
  do not block pasted/scripted out-of-range values.

**DD3 — DDL `chat_history_retention_days INTEGER NOT NULL DEFAULT 30`**: The column is
NOT NULL with a constant default of 30.
- Rationale: every agent must have a concrete retention value; `DEFAULT 30` backfills all
  existing rows during the `ALTER TABLE ... ADD COLUMN`, satisfying the mission's resolved
  open question (existing agents become subject to the default 30-day policy). Because the
  validator rejects anything below 1, a stored `0` is impossible and the column is never
  NULL, so the decode reads `row["chat_history_retention_days"]` **directly** — no `or 30`
  truthiness defense is needed (contrast `max_iterations`' `or 20` at `repositories.py:236`,
  which guards a nullable legacy column). The typed-scalar-with-default shape mirrors
  `agents.max_iterations INTEGER DEFAULT 20` (`schema.py:55`).
- Trade-off: NOT NULL differs from the recently-added nullable JSON columns (`connector_acls`
  et al.), but those encode an absent/`{}`/populated tri-state this field does not have.

**DD4 — v30 migration follows the additive ADD COLUMN pattern, migration-only (no
SCHEMA_V1 edit)**: Append an `if version < 30:` block mirroring v29 (`schema.py:1794–1840`):
PRAGMA `table_info(agents)` guard so a re-run is idempotent, then
`ALTER TABLE agents ADD COLUMN chat_history_retention_days INTEGER NOT NULL DEFAULT 30`,
then `INSERT OR IGNORE INTO schema_version (version) VALUES (30)` **last** (partial-apply
safe), and bump `CURRENT_VERSION = 30` (`schema.py:15`).
- Rationale: a fresh DB runs `SCHEMA_V1` then every migration up to `CURRENT_VERSION`, so the
  v30 ALTER adds the column on both fresh and existing databases — exactly how
  `connector_acls` (v18) is handled without touching `SCHEMA_V1`. Editing `SCHEMA_V1`'s
  agents DDL is therefore unnecessary and would double-define the column.
- Trade-off: none — this is the house migration idiom.
- **Test-pin coupling (caught in design review)**: bumping `CURRENT_VERSION` to 30 breaks two
  *literal* `assert CURRENT_VERSION == 29` pins at `tests/test_db_migration.py:278` and `:5018`.
  Leg 1 MUST relax both to the house `>= 29` style (the pattern already used for v27/v28 at
  `:265`/`:272`), which is future-proof against later bumps. The numerous
  `assert max(versions) == CURRENT_VERSION` / `row[0] == CURRENT_VERSION` comparisons reference
  the variable, not a literal, and need no change.
- **E501 (caught in design review)**: the full ALTER statement is ~119 chars under the
  PRAGMA-guard indent, exceeding the M12 `ruff` `line-length = 100` (`pyproject.toml:89`,
  `select` includes `E`). `ruff format` will NOT split a string literal, so Leg 1 must hand-split
  the SQL across two lines (implicit string concatenation) for `ruff check` to pass.

**DD6 — Frontend preserves the raw retention value (no `|| default` coercion)**: The
`collectFormData` branch for `chat_history_retention_days` parses the input and only falls back
to 30 on NaN/empty — it does NOT use the `parseInt(...) || 30` idiom that `max_iterations` uses
(`studio.js:1929`).
- Rationale: the `max_iterations` branch uses `parseInt(f.value, 10) || 20` (`studio.js:1929`);
  applied to retention, `parseInt("0", 10) || 30` evaluates to `30` because `0` is falsy, which
  would silently coerce a typed out-of-range `0` into a valid `30` and save it successfully —
  exactly the "silently accepted or clamped" failure mode mission criterion 2 forbids. Preserving
  the raw
  value (`var n = parseInt(f.value, 10); data[key] = Number.isNaN(n) ? 30 : n;`) lets `0` and any
  >365 value reach the server, where the `Field` bound rejects them with a visible 422 — and makes
  the behavior test's lower-bound reject observable through the UI, not only via curl.
- Trade-off: a deliberate, documented divergence from the sibling `max_iterations` `|| 20`
  idiom (which has no server-side bound at all, so its client coercion is harmless). The two
  Behavior-section knobs therefore handle bad input differently; this is intended.

**DD5 — Behavior-test apparatus: browser (chrome-devtools), both axes verified**: The
set-persists-across-reload and out-of-range-reject flows are driven through the Studio web UI.
- **Act path**: the General-tab retention input (new `id="studio-retention-days"`,
  `data-field="chat_history_retention_days"`, adjacent to `general-tab.js:118–120`) and the
  editor Save button (`.save-btn` rendered at `studio.js:1908`, wired via `onSave` at `:1506` →
  `save()` at `:2351`; the PUT itself is at `:2429–2433`) — same surface class as `studio-smoke`.
- **Observe path (persist)**: after Save, the editor re-renders from `GET /api/agents`
  (`studio.js:2442` `loadAll()`), so the input reflects the stored value on reload; the value
  also appears in `model_dump()` JSON from `GET /api/agents/{name}`.
- **Observe path (reject)**: a 422 PUT throws on `!r.ok` (`studio.js:2436`) and the
  validation detail is written into the editor's `errorEl` (`studio.js:2459`) — observable in
  the DOM. The reject is independently confirmable at the HTTP layer (a `curl` PUT with an
  out-of-range value returns 422 from `api.py:503–504`).
- Both the act and observe premises rest on surfaces that exist in current code today; no
  test-only seam is introduced.

### Prerequisites
- [x] Project initialized for Flight Control (`.flightops/ARTIFACTS.md` present).
- [x] `CURRENT_VERSION == 29` on the branch base, so v30 is the correct next version
  (`db/schema.py:15`, verified 2026-06-05).
- [ ] the-one dev environment available: Docker + Makefile, Python 3.11+, SQLite.
- [ ] For behavior-test verification: a running instance on `http://localhost:8484` with at
  least one configured agent and the dev `mock` provider, plus a Chrome MCP browser session.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (schema version, codebase targets)
- [x] Validation approach defined (unit + API + behavior test)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Two legs.

**Leg 1 — `retention-field-and-persistence` (atomic backend)**: In a single leg,
add `chat_history_retention_days: int = Field(default=30, ge=1, le=365)` to `AgentConfig`
(`agent/config.py`, in the "# Behavior" group beside `max_iterations:265`); bump
`CURRENT_VERSION` to 30 and append the v30 ADD COLUMN migration (`db/schema.py`),
hand-splitting the ALTER SQL across two lines to stay under `ruff`'s 100-char limit (DD4); add
the column to the `save()` INSERT column list, the `VALUES` placeholders, and the
`ON CONFLICT ... DO UPDATE SET` clause (`db/repositories.py:121–173`); decode it directly in
`_row_to_config()` (`db/repositories.py:226+`); and **relax the two literal
`assert CURRENT_VERSION == 29` pins to `>= 29`** (`tests/test_db_migration.py:278`, `:5018`;
DD4). Cover with: a `test_config.py` case for the
1/365 boundaries and out-of-range rejection; a `test_db_migration.py` v30 case (column added,
backfill = 30, idempotent re-run); and a `test_db_api.py` save→load round-trip including a
non-default value. Run `make rebuild` then `make test-unit`; pass `ruff check` +
`ruff format --check`.

**Leg 2 — `retention-input-general-tab` (frontend)**: Render a number input
(`id="studio-retention-days"`, `data-field="chat_history_retention_days"`, `type="number"`,
`min="1" max="365"`, value `cfg.chat_history_retention_days || 30`) **above** Max Iterations
in the Behavior section (`general-tab.js:117–121`); add the field to the create-mode default
`cfg` object (`general-tab.js:24–31`); and add a `collectFormData` branch that **preserves the
raw value** per DD6 — `var n = parseInt(f.value, 10); data[key] = Number.isNaN(n) ? 30 : n;`
(NOT the `|| 30` idiom) so out-of-range values reach the server and are rejected, not coerced
(`studio.js:1928`). Before editing, confirm no existing browser test positionally asserts the
Behavior section (a quick grep of `tests/browser/` for `Behavior`/`max-iterations` came back
empty during planning, so inserting above Max Iterations should not break a snapshot/flow test
— re-verify at execution). Run `make rebuild`; verify save/load by hand and via the behavior test.

### Checkpoints
- [ ] `CURRENT_VERSION == 30`; v30 migration adds `chat_history_retention_days NOT NULL
  DEFAULT 30` and backfills existing agents; `make test-unit` green for migration + config +
  round-trip cases.
- [ ] Out-of-range value (0 or 366) rejected: `AgentConfig.model_validate` raises and the
  PUT/POST endpoint returns 422.
- [ ] Retention input renders above Max Iterations in the Behavior section and round-trips a
  non-default value across save and reload.
- [ ] `ruff check` + `ruff format --check` clean; full `make test` green.
- [ ] Behavior test `agent-retention-setting-roundtrip` passes (persist + reject).

### Adaptation Criteria

**Divert if**:
- The base branch's `CURRENT_VERSION` is no longer 29 when Leg 1 starts (an intervening
  flight claimed v30) — re-number the migration and re-verify, do not blindly target v30.
- `_row_to_config()` or `save()` has been restructured such that the cited line anchors no
  longer hold — re-locate the round-trip sites before editing.

**Acceptable variations**:
- Exact wording of the field label/help text and input width class (cosmetic; Flight 4 owns
  UX polish).
- Splitting Leg 1's tests across additional test files if the project's test layout warrants.
- Choosing `@field_validator` over `Field(ge/le)` **only** if design review surfaces a
  concrete reason the declarative bound won't surface as a 422 (none currently expected).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created
> one at a time as the flight progresses.

- [x] `retention-field-and-persistence` - Atomic backend leg: `AgentConfig` field +
  `Field(ge=1, le=365, default=30)` validator + v30 migration (ALTER SQL split for E501) +
  `save()` column + `_row_to_config()` decode + relax the two literal `== 29` version pins +
  unit/migration/round-trip tests.
- [x] `retention-input-general-tab` - Render the retention number input above Max Iterations
  in the General-tab Behavior section; wire `collectFormData` (raw-value preserving, per DD6)
  and save/load.

---

## Post-Flight

### Completion Checklist
- [x] Both legs completed
- [ ] `CURRENT_VERSION == 30`; migration verified against a live SQLite DB (not only mocks)
- [ ] `make test` green (unit + browser)
- [ ] `ruff check` + `ruff format --check` clean
- [ ] Behavior test `agent-retention-setting-roundtrip` passes
- [ ] Code + artifacts committed together

### Verification

- **Unit/migration/round-trip**: `make test-unit` — `test_config.py` (boundary + reject),
  `test_db_migration.py` (v30 column + backfill + idempotent), `test_db_api.py`
  (save→load round-trip with a non-default value).
- **API reject**: `AgentConfig.model_validate` raises on out-of-range; PUT/POST
  `/api/agents` returns 422.
- **Behavior test**: `/behavior-test agent-retention-setting-roundtrip` — drives the General
  tab to confirm the input renders above Max Iterations, a non-default value persists across
  reload, and an out-of-range value is rejected with a visible validation error.
  Spec: [tests/behavior/agent-retention-setting-roundtrip.md](../../../../../tests/behavior/agent-retention-setting-roundtrip.md).
