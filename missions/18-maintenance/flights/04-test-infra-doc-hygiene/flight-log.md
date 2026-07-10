# Flight Log: Test-infra & doc hygiene

**Flight**: [Test-infra & doc hygiene](flight.md)

## Summary
Both legs implemented and landed 2026-07-10. Test-infra fix durably removes the
aiosqlite `Event loop is closed` teardown artifact; doc/coverage hygiene closes
the F10 live-visibility action item, promotes two `agents.md` conventions,
verifies the two Mission-16 corrections were already applied (PR #153), and
authors the two recommended behavior-test specs (draft, not run).

---

## Leg Progress

### Leg 1 — `aiosqlite-teardown-durable-fix` (landed 2026-07-10)

Design review corrected the original T1 diagnosis: not a blanket "connections
aren't closed" problem — an AST sweep of all 85 `aiosqlite.connect` sites in
`tests/test_db_migration.py` found 83/85 closed 1:1 in-loop already. Fixed the
three real issues instead of a blanket rewrite:

- **Deterministic leak** — `TestSchemaV16.test_v16_legacy_v15_row_decodes_with_null_external_key_columns`
  (`tests/test_db_migration.py`, originally line 1798) opened a connection and
  never closed it; the function ended on a bare assert. This was the last test
  in `TestSchemaV16`, immediately followed by `class TestSchemaV17` — the
  origin of the warning being mis-attributed to `TestSchemaV17`. Converted to
  `async with aiosqlite.connect(str(db_path)) as conn:` wrapping the rest of
  the test body, so the close is guaranteed in-loop regardless of how the test
  exits.
- **Fragile shared fixture** — the `setup` fixture (consumed by 4 tests in
  `TestJSONToSQLiteMigration`) had its `await conn.close()` as a bare trailing
  statement after `yield`; any assertion failure in a consuming test would
  skip it and orphan the connection on a to-be-torn-down loop (the
  load-order-dependent nondeterminism F09 saw). Converted to wrap the fixture
  body (including the `yield`) in `async with aiosqlite.connect(...) as conn:`
  — close now fires in `__aexit__` even on a raised exception.
- **Duplicate close** — `TestSchemaV17.test_v17_legacy_v16_row_decodes_with_empty_connector_ids`
  had two consecutive `await conn.close()` calls (dead code, harmless per
  aiosqlite's idempotent close guard). Removed the redundant one.

`_daemonize_aiosqlite_worker_threads` (`tests/conftest.py:62-99`) was kept as
a backstop — not made redundant by this fix, and the leg didn't require
removing it.

**Verification** (design-review [3]: no `pytest-randomly`, out of scope):
- `tests/test_lifespan.py tests/test_db_migration.py` → 96 passed, warning absent.
- `tests/test_db_migration.py tests/test_lifespan.py` (reverse order) → 96 passed, warning absent.
- Full `make test-unit` → 3997 passed, 10 skipped, 664 deselected, 0 failed,
  20 warnings (337.95s / 5m38s) — none of the 20 warnings is
  `Event loop is closed` / `PytestUnhandledThreadExceptionWarning` (grepped
  the full log; zero matches).

`git diff` scope: `tests/test_db_migration.py` only (no `tests/conftest.py`
change — the daemonize backstop stayed; no `the_one/**` change; no
`pyproject.toml` change).

### Leg 2 — `doc-coverage-hygiene` (landed 2026-07-10)

- **DOC1** — the live thinking broadcast (`the_one/interfaces/web/app.py`,
  the `_thinking_text` block) now mirrors `codec.py`'s replay projection
  (`vis = {"visibility": msg.visibility} if msg.visibility is not None else {}`,
  `db/codec.py` ~332/383-388): emits `visibility` only when
  `msg.visibility is not None`, same key, same omit-not-null handling. Added
  a code comment at the broadcast site documenting the **timing caveat**
  (design-review [5]): `tag_post_step_visibility`
  (`connectors/post_step_metadata.py:57`) sets `msg.visibility` for
  connector-tagged sessions *after* this broadcast fires, so the connector
  case still emits no live `visibility` — full parity is reached only after
  persistence + rejoin. Still strictly better than before (correct for
  non-connector/operator-typed turns today). Two new tests in
  `tests/test_ws_storage_edge_shim_visibility.py`
  (`test_live_thinking_broadcast_carries_visibility_when_set`,
  `test_live_thinking_broadcast_omits_visibility_when_unset`) pin both sides
  of the contract; both pass (12/12 in that file, up from 10).
- **DOC2** — added a new `### Mission-specific (M16)` subsection to
  `the_one/agents.md`, placed right after `provider-request-param-config-surface
  (M16 F11)` and before `### Mission-specific (M10)`:
  - `rule-of-three OpenAI-compat duplication` (new convention): cites the two
    duplicated OpenAI-compat mapping pairs (F11 `_a4_request_kwargs` /
    `_v1_a4_kwargs` request-kwargs assembly; F12 `_content_block_to_api`
    content-block projection in `openai_provider.py` / `ollama_provider.py`)
    and the "lift at a genuine 3rd `/v1` provider; the conformance parity
    test (`tests/test_llm_provider_cross_provider_conformance.py`) is the
    drift net" rule.
  - `seed-before-overlay for partial-field UI saves` (extracted, not
    duplicated): the pattern was already fully described inside
    `provider-request-param-config-surface` at `agents.md:509-513`; added a
    named subsection that generalizes it and cross-referenced it from the
    original paragraph, rather than re-describing it.
- **M16 corrections** — verified both were already applied (PR #153), no
  change needed: `missions/16-llm-provider-hardening/mission.md`'s Windows
  seed-packaging Known Issue reads `[x]` resolved (commit `69512d2`) and the
  criterion-#8 footnote is corrected; `mission-debrief.md`'s Leg-09 line reads
  "conditionally-reachable, not dead ... retain."
- **T2/T3** — authored two behavior-test specs, both `status: draft`,
  `Last Run: never`, not run:
  - `tests/behavior/save-preserves-config.md` — modeled on
    `tests/behavior/system-provider-config.md`'s format. Creates a provider
    via API, sets `response_format`+`stop` via a PUT (out-of-band, no UI
    surface for those fields), edits `reasoning_effort` through the Admin
    editor UI, saves, and re-fetches to assert all three config keys survive
    — the regression net for the seed-before-overlay convention above.
  - `tests/behavior/vision-round-trip.md` — mined from the Flight 12 L08 HAT
    steps (`missions/16-llm-provider-hardening/flights/12-message-content-multimodal/legs/08-ingestion-and-vision-hat.md`):
    attach an image and assert the model's reply is grounded in its content
    (live Anthropic vision model required — the hermetic mock-provider
    browser suite can't falsify grounding), an image-only (no-text) send,
    and a session rejoin that doesn't crash the WS or corrupt replay.

`git diff` scope: `the_one/interfaces/web/app.py`, `tests/test_ws_storage_edge_shim_visibility.py`,
`the_one/agents.md`, `tests/behavior/save-preserves-config.md` (new),
`tests/behavior/vision-round-trip.md` (new), + flight artifacts. No M16
artifact edits needed (verified correct as-is).

`ruff check the_one/ tests/` and `ruff format --check the_one/ tests/` both
clean. Full `make test-unit` (run once, covering both legs' changes): 3997
passed, 10 skipped, 664 deselected, 0 failed.

---

## Decisions

- Leg 1 scoped the `async with` conversion to the deterministic leak + the one
  shared fixture (4 consuming tests) + the duplicate-close removal, per the
  design review's explicit "full conversion of all 85 sites is NOT required"
  guidance — the other 81 already-correct sites were left untouched to keep
  the diff minimal and reviewable.
- Leg 1 kept `_daemonize_aiosqlite_worker_threads` in place — the durable fix
  addresses the close-ordering root cause, but the daemonize backstop is
  still valid defense-in-depth for any future leak and removing it wasn't
  required by the acceptance criteria.

---

## Deviations

None — both legs implemented per spec.

---

## Anomalies

None.

---

## Session Notes

- Leg 1's `async with` conversion at the `test_v16_legacy_v15...` leak site
  pushed one pre-existing SQL string literal past the 100-char ruff line
  limit (extra 4-space indent from the new `with` block); reflowed the
  string concatenation to stay under the limit — no behavior change.
