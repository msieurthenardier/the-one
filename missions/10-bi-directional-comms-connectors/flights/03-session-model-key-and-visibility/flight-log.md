# Flight Log: Session Model — Schema, Key Normalization, Visibility

**Flight**: [Session Model — Schema, Key Normalization, Visibility](flight.md)

## Summary

Status: in-flight. Flight created 2026-05-17. Planning + architect-design-review complete (committed `d2351c7` on main as `planning → ready`). Execution started 2026-05-17 on branch `flight/03-session-model-key-and-visibility`.

---

## Flight Director Notes

- **2026-05-17** — Phase 1 of /agentic-workflow: loaded `.flightops/agent-crews/leg-execution.md` (Developer/Sonnet for design-review + implement + fix-review-issues + commit; Reviewer/Haiku for review; optional Accessibility Reviewer/Sonnet for UI legs). Flight ready → in-flight; planning artifacts committed separately on main. Starting Phase 2 leg cycle.
- **Leg 5 will spawn Accessibility Reviewer in parallel** with the standard Reviewer (UI changes to the Studio editor's Lifecycle section). Legs 1-4 and 6 are non-UI; Accessibility Reviewer skipped.
- **Per-leg design review** spawns a Developer agent per `leg-execution.md` interaction protocol; substantive feedback triggers a second pass (max 2 cycles per leg).
- **Implementation legs do NOT commit individually** per /agentic-workflow's batched-review model: implement-only, then one Reviewer pass + one commit at flight end.

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

### Leg 01 — v16-schema-migration

- **Started**: 2026-05-17
- **Completed (landed, pending flight-end commit)**: 2026-05-17
- **Status**: landed

**Changes shipped**:

- `the_one/db/schema.py` — `CURRENT_VERSION` 15 → 16; added v16 migration block (7 ALTERs on `chat_sessions`, 1 ALTER on `connector_accounts`, 1 partial-expression CREATE INDEX); renumbered v15 block's downstream comment v16 → v17. (+69 lines)
- `the_one/db/models.py` — `ChatSession` gains 7 new fields (platform, connector_account_id, channel_id, thread_id, peer_id, session_metadata, last_inbound_at) all defaulting None; `ConnectorAccount` gains `session_continuation_seconds` + `_validate_session_continuation_seconds` validator (1 ≤ value ≤ 604800). (+56 lines)
- `the_one/db/repositories.py` — `ChatSessionRepository.create` extended (7 new INSERT columns); `update()` docstring documents identity-columns-not-mutated contract; `_row_to_model` reads all 7 new columns with defensive non-dict JSON normalization on `session_metadata`. `ConnectorAccountRepository` create/update/`_row_to_model` round-trip `session_continuation_seconds`. (+60 lines)
- `the_one/db/_connector_types.py` — docstring v16 → v17 renumber + v16 entry inserted for F3 L1.
- `the_one/agents.md` — connector-type checklist item 4 v16 → v17 renumber + v16 entry inserted.
- `tests/test_db_migration.py` — TestSchemaV8 head-version bumped to 16; TestSchemaV13 docstring v16 → v17 + column-set assertion extended with `session_continuation_seconds`; TestSchemaV14 docstring v16 → v17 + chat_sessions hand-built shape added to its v13-fixture (needed since v16 ALTERs `chat_sessions`, the prior test fixtures only seeded `connector_accounts`); TestSchemaV15 docstring updated to narrate v16/v17 renumber + chat_sessions hand-built shape added to its v14-fixture; NEW `TestSchemaV16` class with 3 tests (fresh-DB columns + index, idempotent re-run, legacy-v15-row-decodes). Also added chat_sessions hand-built shape to `TestMigrationV12::test_v12_real_v11_to_v12_upgrade` fixture for the same reason. (+290 lines)
- `tests/test_db_repositories.py` — 3 new ChatSession round-trip tests (connector identity round-trip, dict/None metadata, defensive non-dict JSON collapse) + 5 new `ConnectorAccount` `session_continuation_seconds` tests (round-trip real value, round-trip None, validator rejects 0, validator rejects 604801, validator accepts 1/86400/604800/None). (+183 lines)

**Test count delta**:

- `tests/test_db_migration.py + tests/test_db_repositories.py` scoped suite: 110 passing (3 new TestSchemaV16 + 3 new ChatSession round-trip + 5 new ConnectorAccount session-continuation = 11 new tests).
- Full non-browser suite: **1816 passed, 4 skipped, 12 deselected, 2 warnings in 118s** (the 2 warnings are the pre-existing `AsyncMock-never-awaited` on `test_provider_api.py::TestModelDiscovery::test_ollama_models` — F2 debrief carry-forward #10, not introduced by this leg).

**Deviations from leg spec**:

- **Three legacy migration tests required chat_sessions fixtures**: the leg spec listed `TestSchemaV13` column-set assertion as the canonical brittle site the two-pass planning grep was meant to catch. Test runs surfaced an additional class of breakage: three pre-existing tests that hand-build a partial pre-v11/v13/v14 schema (`TestMigrationV12::test_v12_real_v11_to_v12_upgrade`, `TestSchemaV14::test_v14_preserves_v13_seeded_row_with_empty_name`, `TestSchemaV15::test_v15_legacy_v14_row_decodes_with_none_idle_timeout`) omit the `chat_sessions` table. Up to v15, no migration touched `chat_sessions` since v5, so these fixtures never failed. v16 is the first migration since v5 to ALTER `chat_sessions`; running these tests after the v16 bump hits `OperationalError: no such table: chat_sessions`. Fix: extended each fixture's hand-built schema to include a post-v5-shape `chat_sessions` table (id, agent_name, title, messages, created_at, updated_at — no FK on agent_name post-v5). This pattern (extend legacy-fixture builders when a new migration ALTERs a previously-untouched table) is a useful addition to the two-pass-planning-grep convention; flagged for the F3 flight debrief.
- **`make lint` snag**: one line-too-long (>100 cols) on the new `ALTER TABLE connector_accounts ADD COLUMN session_continuation_seconds INTEGER NULL` literal in `schema.py`; resolved by breaking it into two adjacent string literals (same pattern v15's `INSERT INTO schema_version` uses elsewhere).

**Anomalies**: none.

**Verification**:

- v16 acceptance criteria walked individually and confirmed (column adds, index creation, idempotency, Pydantic round-trip including JSON metadata + non-dict-collapse, validator boundary cases for `session_continuation_seconds`, all renumber sites updated to v17).
- Scoped tests: 110 passed.
- Full suite (non-browser): 1816 passed, 4 skipped, 12 deselected (browser tests intentionally excluded — not in scope for this data-layer leg; the leg's verification rubric explicitly cites the scoped + full-non-browser suite).
- Lint: clean.

### Leg 02 — message-visibility-field

- **Started**: 2026-05-17T13:35-05:00
- **Completed (landed, pending flight-end commit)**: 2026-05-17T13:50-05:00
- **Status**: landed

**Changes shipped**:

- `the_one/llm/base.py` — `Message` dataclass gains 6th field `visibility: str | None = None` (last field, after `usage`). All four classmethod helpers (`system`, `user`, `assistant`, `tool`) accept `*, visibility: str | None = None` as a **keyword-only** kwarg and forward to `cls(...)`. Existing single-positional callers unchanged. Module-level docstring comment on the new field cross-references `OPERATOR_VISIBILITY` and the F3 L4 / F4 / F5 production set-sites. (+18 lines)
- `the_one/db/codec.py` — `message_to_dict` emits `d["visibility"] = msg.visibility` only when `msg.visibility is not None` (mirrors `_tool_result_to_dict`'s metadata-emit pattern). `message_from_dict` reads `visibility=d.get("visibility")` into the `Message(...)` constructor (None on legacy rows). `messages_to_ui_events` computes a per-iteration `vis = {"visibility": ...} if not None else {}` dict and spreads it via `**vis` into all four event-emission sites (user, assistant content, tool_call, tool_result) — pure addition; existing keys unchanged; absent key when source visibility is None. (+13 lines)
- `the_one/connectors/__init__.py` — module-level `OPERATOR_VISIBILITY = "operator"` constant (plain assignment, NOT `Final[str]` — design-review-confirmed: codebase has zero existing `typing.Final` usages). Added to `__all__` under a new `# Constants` group. (+12 lines)
- `tests/test_db_codec.py` — added `pytest` import + `message_to_dict` to the codec import line, plus three new test classes appended at end-of-file: `TestMessageVisibilityCodec` (6 tests: emit-non-none, omit-none, restore, back-compat-no-key, full round-trip tagged + untagged); `TestMessagesToUiEventsVisibility` (10 tests: projection on user/assistant-content/tool_call/tool_result, mixed-tag, plus 4 shape-unchanged-when-untagged regression checks across all 4 event types); `TestMessageVisibilityClassmethodKwargs` (12 tests: kwarg accepted + default None + positional rejected across all 4 classmethods). 28 new tests total. (+199 lines)
- `tests/test_connectors.py` — added `OPERATOR_VISIBILITY` to the imports + 1-test EoF section pinning the value and the export. (+15 lines)

**Test count delta**:

- `tests/test_db_codec.py + tests/test_connectors.py` scoped suite: 84 passed (29 new tests; per-file breakdown: test_db_codec 54 → 82 = 28 new; test_connectors 30 → 31 = 1 new).
- Full suite: **1845 passed, 4 skipped, 404 deselected, 2 warnings in 119s** — up exactly from leg 1's 1816 → 1845 (= +29 new tests; deselected count varies with marker-driven browser-test filtering but the passing count is the canonical delta). The 2 warnings remain the pre-existing `AsyncMock-never-awaited` on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (F2 debrief carry-forward #10, not introduced here).

**Deviations from leg spec**:

- **None of substance.** The leg artifact's "Implementation Guidance §7" left the classmethod-kwarg test home open (test_db_codec.py vs. a new test_llm_base.py); I placed all `Message`-construction-via-classmethods tests in test_db_codec.py alongside the codec round-trip tests, matching the leg artifact's "Outputs" note ("tests for `Message` shape currently live in `test_db_codec.py`"). One new file would have been ~12 imports and 200 lines for tests that semantically belong with the round-trip suite — the leg author's preferred shape.
- **Existing-shape-preservation regression checks added beyond the acceptance criteria's enumerated minimum.** The criteria list 12 new tests; the implementation adds 4 explicit "shape-unchanged-when-untagged" tests (user, assistant content, tool_call, tool_result) that pin the projected event dict's exact equality when source visibility is None. The leg artifact's Edge Cases section flagged "existing codec tests using `==` equality on whole dicts" as the back-compat anchor; these 4 tests make that contract explicit at the new-test layer instead of relying solely on the legacy test class. Net cost: 4 lines × 4 tests. Net benefit: a future contributor cannot accidentally project `"visibility": None` into the event dict without one of these 4 tests failing loudly.

**Anomalies**: none.

**Verification**:

- All acceptance criteria walked individually and confirmed:
  - `Message` has 6 fields with `visibility` last (`grep -n "visibility: str | None"` shows the dataclass field).
  - All 4 classmethods accept keyword-only `visibility`; positional rejected via `pytest.raises(TypeError)` in the dedicated test class.
  - `message_to_dict` emits-when-non-None / omits-when-None confirmed by paired tests.
  - `message_from_dict` restores via `d.get("visibility")`; back-compat test deserializes a pre-F3-shaped dict without the key and asserts `.visibility is None`.
  - `messages_to_ui_events` projects across all 4 branches (4 dedicated tests + mixed-tag test); 4 shape-unchanged tests pin absent-key on untagged.
  - `OPERATOR_VISIBILITY = "operator"` in `connectors/__init__.py` with `__all__` entry; import-and-value test in `test_connectors.py`.
- Scoped tests: 84 passed (0 failures, 0 errors).
- Full suite: 1845 passed, 4 skipped, 404 deselected (browser-test marker filtering — same baseline as leg 1).
- Lint: clean (`ruff check the_one/ tests/` → "All checks passed!").

### Leg 03 — session-key-resolver

- **Started**: 2026-05-17
- **Completed (landed, pending flight-end commit)**: 2026-05-17
- **Status**: landed

**Changes shipped**:

- `the_one/connectors/_session.py` — NEW module. `_DEFAULT_CONTINUATION_SECONDS = 86400` constant; `_utc_now_iso()` UTC-ISO write helper (inlined per the leg's NOTE — the resolver is NOT the first cross-package consumer of `db.models._now_iso`'s leading-underscore symbol); `_resolve_continuation_seconds(override)` mirroring `_pool._resolve_ttl_seconds` (override → env var read at call time → default; non-int env var falls back with a warning); `_derive_title(envelope, plugin)` consuming the optional `display_channel` hook via `getattr(plugin, "display_channel", None)` with sentinel-None + try/except + empty-result fallback to `envelope.channel_id`; `async resolve_session(envelope, account, repo, *, agent_name, plugin) -> ChatSession` orchestrating `plugin.normalize_session_key` → 4-tuple lookup → `datetime.fromisoformat`-parsed window check (with naive→UTC defensive normalization) → reuse-or-create with `uuid.uuid4().hex` primary key. (+196 lines)
- `the_one/db/repositories.py` — `ChatSessionRepository.find_most_recent_by_external_key(*, platform, connector_account_id, channel_id, thread_id)` added between `get` and `create`. SQL uses `COALESCE(thread_id, '') = COALESCE(?, '')` on both sides to mirror the v16 partial-index expression and handle NULL-distinct semantics. Reuses `_row_to_model` for shape consistency. (+32 lines)
- `the_one/connectors/_stub.py` — `StubPlugin.display_channel(envelope)` class method added after `normalize_session_key`. Returns `f"stub:{envelope.channel_id}"` — good-citizen reference implementation of the optional-hook convention. (+14 lines)
- `the_one/connectors/README.md` — NEW `## §4. Optional hooks (additive plugin extension)` section after §3 (Protocol decomposition). Documents the `getattr(plugin, "<hook>", None)` discovery pattern, names `display_channel` as the first instance, distinguishes Protocol method vs. optional-hook trade-offs, and forward-references F4's potential outbound-send optional extension. Renumbered §4-§8 → §5-§9. (+38 lines new, 4 lines renumbered)
- `tests/test_connectors_session.py` — NEW test file. 14 tests across two surfaces:
  - `_resolve_continuation_seconds` (5 tests): override-beats-env-and-default, env-beats-default, default-when-no-env, non-int-env-falls-back, env-read-at-call-time.
  - `resolve_session` (9 tests): first-contact creation (asserts all external-key columns populated, `last_inbound_at` ≈ now, title from `display_channel`, `uuid.uuid4().hex` 32-char id, persisted via repo); within-window reuse (no new row); outside-window supersession (new row created, old row preserved untouched); per-thread distinct; DM-shaped envelope (thread_id=None); `display_channel` missing → falls back to `envelope.channel_id` (uses local `_MinimalPlugin` without the hook); `display_channel` raises → resolver catches + falls back (uses local `_RaisingPlugin`); plugin authority over key shape (collapses threads — different envelope threads resolve to same row); `peer_id` stored-but-not-in-lookup (different peer_ids on same channel reuse the same row; first row's peer_id is preserved).
  - Fixtures `conn` / `chat_repo` / `agent_store` mirror `tests/test_db_repositories.py` shape; `_envelope` and `_account` are local kwargs-only constructor helpers. (+395 lines)
- `tests/test_db_repositories.py` — 3 new tests appended to `TestChatSessionRepository`: returns-none-on-no-match; returns-most-recent-by-updated_at (3-row seed, asserts ORDER BY DESC LIMIT 1); COALESCE-null-thread-id (query with `thread_id=None` matches NULL row, NOT `"A"` row; query with `thread_id="A"` matches `"A"` row, NOT NULL row). (+104 lines)

**Test count delta**:

- `tests/test_connectors_session.py + tests/test_db_repositories.py` scoped suite: 90 passed (14 new in test_connectors_session.py + 3 new in test_db_repositories.py = 17 new tests).
- Full suite: **1862 passed, 4 skipped, 404 deselected, 2 warnings in 118s** — up exactly from leg 2's 1845 → 1862 (= +17 new tests). The 2 warnings remain the pre-existing `AsyncMock-never-awaited` on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (F2 debrief carry-forward #10, not introduced here).

**Deviations from leg spec**: none of substance.

- The leg artifact's content sketch placed `logger = logging.getLogger(__name__)` between `_utc_now_iso` and `_DEFAULT_CONTINUATION_SECONDS`; the implementation moves `logger` above `_utc_now_iso` for the conventional module-level-imports-then-logger ordering (no functional difference; logger is only consumed by `_resolve_continuation_seconds` and `_derive_title`, both of which are defined later).
- README section numbering: leg spec allowed "leg-3 author chooses". Chose §4 (insert after §3 Protocol decomposition) with §5-§9 renumbered downstream. No §3.1 / §3.5 sub-numbering — the README uses flat `## §N` throughout.
- Ruff post-fix: one I001 import-sort finding on `tests/test_connectors_session.py` (blank line between two third-party imports); auto-fixed via `ruff check --fix`. Final `ruff check the_one/ tests/` clean.

**Anomalies**: none.

**Verification**:

- All acceptance criteria walked individually and confirmed:
  - Module exists (`the_one/connectors/_session.py`), constants + functions present (`_DEFAULT_CONTINUATION_SECONDS`, `_resolve_continuation_seconds`, `async def resolve_session`).
  - Resolver calls `plugin.normalize_session_key(envelope)`; lookup tuple is 4-tuple (peer_id NOT in lookup — exercised by `test_resolve_session_peer_id_stored_but_not_in_lookup`).
  - Reuse path: `(now - parsed(row.last_inbound_at)).total_seconds() < continuation` — exercised by within-window test.
  - Create path: `uuid.uuid4().hex` (full 32 chars — asserted by `assert len(session.id) == 32`); `agent_name` from parameter; `messages = "[]"` explicit; created_at/updated_at/last_inbound_at all set to same `now_iso`; all 5 external-key columns populated from SessionKey; `session_metadata=None`; calls `await repo.create(new_session)`.
  - Title derivation: `getattr(plugin, "display_channel", None)`; try/except Exception with `logger.warning(... exc_info=True)`; empty-string return falls back.
  - `datetime.fromisoformat(...)` used (NOT string compare). Naive datetimes treated as UTC.
  - `StubPlugin.display_channel` returns `f"stub:{envelope.channel_id}"`.
  - `find_most_recent_by_external_key` SQL matches spec (COALESCE on both sides, ORDER BY updated_at DESC LIMIT 1, `_row_to_model` reuse).
  - README has "Optional hooks" section with the three required points (no Protocol widening; plugins must tolerate exception-catching; future flights may use the same pattern).
- Scoped tests: 90 passed (0 failures, 0 errors).
- Full suite: 1862 passed, 4 skipped, 404 deselected (browser-test marker filtering — same baseline as legs 1+2).
- Lint: clean (`ruff check the_one/ tests/` → "All checks passed!").



### Leg 04 — inbound-dispatcher

- **Started**: 2026-05-17
- **Completed (landed, pending flight-end commit)**: 2026-05-17
- **Status**: landed

**Changes shipped**:

- `the_one/connectors/_inbound.py` — NEW module. Module-level `_session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)` for per-(chat_sessions.id) serialization. `_utc_now_iso()` UTC-ISO write helper (inlined per the same NOTE as leg 3 — not the first cross-package consumer of `db.models._now_iso`). `async def dispatch_inbound(agent_name, account_id, envelope, *, factory: AgentFactory) -> None` composing (1) `pool_acquire` for the F1 `last_activity` ratification, (2) function-local DB imports, (3) account load with graceful KeyError-on-deleted, (4) plugin resolve (deliberately redundant defensive coding kept), (5) `resolve_session` via leg 3, (6) per-session `async with _session_locks[session_row.id]`, (7) `chat_repo.update_last_inbound`, (8) `factory.create(agent_name)` (signature: `create(name)` — confirmed), (9) re-fetch of session row inside lock + history load mirroring `_restore_session:434`, (10) `current_chat_session_id.set(session_row.id)` token inside `try/finally`, (11) `async for _ in agent.step(envelope.text): pass` (no callbacks — F3 has no UI subscribers), (12) `repo.update(model_copy(update={title, messages}))` mirroring `_save_session_to_db`, (13) ContextVar reset in `finally`. `_clear_for_test()` helper for the autouse test fixture. (+219 lines)
- `the_one/db/repositories.py` — `ChatSessionRepository.update_last_inbound(session_id, when)` added after `purge_messages`. SQL: `UPDATE chat_sessions SET last_inbound_at = ?, updated_at = ? WHERE id = ?` (touches both — the resolver's most-recent-by-`updated_at` ordering depends on the dual-write). Raises `KeyError` on missing session (mirror of `update` / `delete` / `purge_messages` not-found-guard). **Amended `ChatSessionRepository.update`'s docstring** (added in leg 1) to drop the now-deprecated `append_messages` reference and replace with the `update_last_inbound` narrow primitive + the whole-history `repo.update` pattern citation (used by both `_save_session_to_db` and the new `dispatch_inbound`). (+34 lines net.)
- `the_one/agents.md` — Known Issues entry for `last_activity` rewritten from "ratification needed" → "Flight 3 ratified `last_activity` tracking via acquire-per-inbound (M10 F03 L04)". Cites the dispatcher's per-inbound `acquire(agent_name, account_id)` call as the contract anchor and names the warm-pool bypass invariant for future maintainers. Entry kept (not deleted) per the leg's "preserve the trail" guidance.
- `tests/test_connectors_inbound.py` — NEW test file with 15 tests. Fixtures: `_reset_stub_state` (autouse — `StubPlugin.reset_for_test`); `_clear_pool_locks_registry` (autouse — pool `_clear_for_test` + inbound `_clear_for_test` + registry `clear_for_test` + `restore_to_baseline_for_test`); `isolated_db` (per-test SQLite at `tmp_path` mirroring `tests/test_connectors_e2e.py::isolated_db` — required because the dispatcher uses module-level `get_connection()` singleton). Helpers `_seed_provider_and_agent` (mock-typed `LLMProviderConfig` + `AgentConfig`), `_seed_stub_account`, `_make_factory` (real `AgentFactory(store=SQLiteAgentStore(conn), mcp_provider=None)` — no MCP wiring), `_envelope`. Test-only `_BlockingProvider(LLMProvider)` that awaits an `asyncio.Event` inside `stream()` for event-coordinated concurrency tests (no wall-clock sleeps); `_make_blocking_factory` monkeypatches `the_one.agent.factory.get_provider` so the same event flows from the test body into the LLM resolver. Coverage:
  - `creates_session_on_first_contact` — all external-key columns populated; user + assistant turns persisted; title from `StubPlugin.display_channel`.
  - `persists_exactly_one_user_message_per_inbound` — the architect-revised "drop append_messages" regression net.
  - `reuses_session_within_window` — two inbounds in same continuation window → one session row with both turns.
  - `creates_new_session_after_window` — overrides `session_continuation_seconds=1` then bumps the first row's `last_inbound_at` two hours into the past via `update_last_inbound` → second dispatch creates a new row.
  - `touches_pool_last_activity` — snapshots `pool_mod._pool[(agent, account)].last_activity` across a second dispatch and asserts strict increase. F1 ratification anchor.
  - `serializes_concurrent_same_session` — warmup-then-block pattern: a non-blocking warmup dispatch materialises the session row, two concurrent blocking dispatches assert the per-session lock holds and queues the second until the event releases. Three user messages persisted in one row at end.
  - `parallelizes_different_sessions` — warmup-then-block on TWO different `channel_id`s; assert both per-session locks hold concurrently.
  - `sets_and_resets_context_var` — monkeypatches `factory.create` to wrap the produced `Agent.step` with a capturing wrapper; verifies `current_chat_session_id.get() == session.id` inside the step and `None` outside the dispatch.
  - `persists_inbound_with_visibility_none` + `persists_agent_reply_with_visibility_none` — F3 peer-visible defaults.
  - `account_not_found_returns_gracefully` — `pool.acquire` raises KeyError inside `_load_account`; dispatcher logs + returns; no session created.
  - `unknown_connector_type_returns_gracefully` — seeded account with `type="not-a-real-connector"`; pool `_resolve_plugin` raises `ConnectorRegistrationError`; dispatcher logs + returns; no session created.
  - `does_not_call_record_outbound` — `StubPlugin.outbound_records == []` after dispatch. F3 owns ZERO outbound (F4 is responsible).
  - `update_last_inbound_bumps_both_timestamps` — repo-unit test: stale `last_inbound_at` and `updated_at` both rewritten to `when`.
  - `update_last_inbound_raises_keyerror_on_missing_session` — repo-unit test.
  - (+555 lines)

**Test count delta**:

- `tests/test_connectors_inbound.py + tests/test_db_repositories.py` scoped suite: 91 passed (15 new in test_connectors_inbound.py + the 76 carry-forward from leg 3's TestChatSessionRepository).
- Full suite: **1877 passed, 4 skipped, 404 deselected, 2 warnings in 124.03s** — up exactly from leg 3's 1862 → 1877 (= +15 new tests). The 2 warnings remain the pre-existing `AsyncMock-never-awaited` on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (F2 debrief carry-forward #10, not introduced here).

**Deviations from leg spec**:

- The leg's two event-coordinated concurrency tests were tightened to a **warmup-then-block** pattern instead of "spawn two concurrent dispatches into a fresh DB and assert lock state from the first one". Reason: the resolver creates the session row OUTSIDE the per-session lock (the lock is keyed on `chat_sessions.id`, which doesn't exist until the resolver returns), so two concurrent first-contact dispatches race in `resolve_session` and create two distinct rows — the documented "concurrent first-contact race" from the leg's Edge Cases. The race is **intentional** (one row becomes historical-not-active; the next inbound's `find_most_recent_by_external_key` picks up the surviving row), but it muddles the lock-semantic assertion. The warmup-then-block pattern materialises the session row(s) first via a non-blocking `MockProvider`-driven dispatch, THEN spawns the concurrent blocking dispatches against the established session id. This isolates "does the per-session lock serialize same-key inbounds" from "what happens during the first-contact race" — they are separable invariants. Three user messages end up persisted in the same row (warmup + 2 blocking).
- The `unknown_connector_type` test exercises the pool's plugin-resolve raise (at `_pool.py:_resolve_plugin` via `_resolve_plugin = resolve as` import) rather than the dispatcher's defensive second-catch at step 3. Both paths are equivalent at the user-visible level (no session created; no exception raised); the comment in the dispatcher's body documents the deliberate redundancy so a future reader doesn't "simplify" by removing.

**Anomalies**:

- **Cross-test leak in the first full-suite run** — the initial `_make_blocking_factory` used bare module mutation (`factory_mod.get_provider = _resolver`) which is NOT reverted at test teardown, so the `_BlockingProvider` resolver leaked into `tests/test_factory_openrouter.py::test_factory_resolves_openrouter_provider`. Caught at full-suite stage (scoped tests passed because they don't exercise downstream factory tests). Fix: thread `monkeypatch: pytest.MonkeyPatch` through `_make_blocking_factory` and use `monkeypatch.setattr(factory_mod, "get_provider", _resolver)` so the override is auto-rolled-back. Methodology note: the M07 "monkeypatch the bare-mutation form leaks across tests" lesson re-surfaced; the existing tests/conftest.py and `_clear_pool_after_each_test` autouse fixtures cover plenty of shared state but bare attribute assignments still need explicit monkeypatch routing. Scoped-suite-only test discipline would NOT have caught this — full-suite-clean is the actual contract.

**Verification**:

- All acceptance criteria walked individually and confirmed:
  - Module exists (`the_one/connectors/_inbound.py`); `_session_locks` declared module-level via `defaultdict(asyncio.Lock)`; `dispatch_inbound(agent_name, account_id, envelope, *, factory: AgentFactory) -> None` signature exact.
  - Body executes in the 12-step order: pool_acquire → load account → resolve plugin → resolve session → per-session lock → update_last_inbound → factory.create → re-fetch session + decode → bind ContextVar (try/finally) → agent.step → encode + model_copy + repo.update → reset ContextVar.
  - `from the_one.agent.factory import AgentFactory` at module top is safe (design-review-verified — factory.py top-level imports are agent.config/core/store, config, db._provider_types, llm, tools.*; no transitive reach into connectors). `from the_one.connectors._pool import acquire as pool_acquire` aliased.
  - Function-local imports of `config.settings`, `db.connection.get_connection`, `db.repositories.{ChatSessionRepository, ConnectorAccountRepository}`, `encryption.get_encryptor` mirror the `_pool._load_account` pattern.
  - `ChatSessionRepository.update_last_inbound` exists with SQL that touches both `last_inbound_at` AND `updated_at`; KeyError on missing session.
  - `ChatSessionRepository.update` docstring amended to drop `append_messages` reference and reference the whole-history `repo.update` pattern + `update_last_inbound` narrow primitive.
  - `agents.md` Known Issues entry rewritten to mark ratified (entry preserved, not deleted).
  - 15 tests cover the full Outputs list; the `_BlockingProvider` fixture is the event-coordinated test seam for the two concurrency tests.
- Scoped tests: 15 passed (0 failures, 0 errors) in `tests/test_connectors_inbound.py`; 91 passed in scoped-suite (`test_connectors_inbound.py + test_db_repositories.py`).
- Full suite: in progress at landing time; results to be appended below.
- Lint: clean (`docker exec the-one ruff check the_one/ tests/` → "All checks passed!").



### Leg 05 — admin-editor-continuation-field

- **Started**: 2026-05-17
- **Completed (landed, pending flight-end commit)**: 2026-05-17
- **Status**: landed

**Changes shipped**:

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — Lifecycle section restructured: F2's single field-row + helper-text pair is now followed by a sibling field-row + helper-text pair for `session_continuation_seconds`. The new input carries `data-field="session_continuation_seconds"` + `data-testid="connector-account-continuation-input"`, `id="cf-continuation-window"`, `type="number"`, `placeholder="Use default (24 hours)"`, and pre-fills from `account.session_continuation_seconds` (null → blank). The new helper text carries `data-testid="connector-account-continuation-hint"` and reads: *"Inbounds on the same conversation continue an existing chat session within this window. After this many seconds of platform silence, the next inbound starts a fresh session. Leave empty to use the system default (24 hours). Distinct from the pool idle timeout above, which controls gateway warm-keep — not chat-session lifecycle."* F2's now-stale forward-reference sentence (*"Flight 3 will add a chat-session continuation window field next to this one."*) is **removed**; the F2 helper text now reads as a self-contained description of the pool-TTL field. `staticFields` array at the dirty-tracking site extended to include `'session_continuation_seconds'`. Form-data extraction at the snapshot site gains a parallel `contEl` / `contRaw` / `contValue` block mirroring `idleEl` / `idleRaw` / `idleValue` (parse as integer, fallback to raw string so backend 422 surfaces the inline error), and the returned payload dict now carries `session_continuation_seconds: contValue` alongside `idle_timeout_seconds: idleValue`. Header summary (`ttlSummary`) intentionally unchanged — option (a) from the leg's recommendation, header stays a glance-summary; operator who cares about the new field scrolls to the Lifecycle section. (+27 lines net.)

- `tests/test_db_api.py` — New `test_session_continuation_change_does_not_evict` inserted after `test_no_op_put_does_not_evict` (the structural template). Creates an account with secrets, warm-acquires its pool entry, PUTs `{"session_continuation_seconds": 3600}`, asserts (1) 200, (2) the `("test-agent", account_id)` pool entry survives (the new field is **NOT** in the eviction trigger — F3 design decision verified), and (3) the value round-tripped via subsequent GET. Cites the design-decision rationale in the docstring. (+44 lines.)

- `tests/browser/test_flow_studio_connector_account_editor.py` — New `test_edit_session_continuation_round_trip` browser test. Seeds a connector account, opens the editor, asserts both Lifecycle inputs are visible (`connector-account-idle-timeout-input` + `connector-account-continuation-input`), asserts the new helper text contains the disambiguating language (*"Distinct from the pool idle timeout"*), fills `3600`, saves, asserts backend persistence via `_get_account`, then closes the editor via Back → clicks the card to re-mount the editor (a same-URL `page.goto` is a no-op in this hash-router so we route through the grid), and asserts the input pre-fills with `"3600"`. (+39 lines.)

- **Validator boundary tests deliberately NOT added** at the REST layer per the leg's design-review note: leg 1 already covers `session_continuation_seconds` validator boundaries at `tests/test_db_repositories.py:925-963` (`_rejects_zero`, `_rejects_one_week_plus_one`, `_accepts_bounds`). REST-layer parametrized duplicates would inflate maintenance cost without new coverage.

**Test count delta**:

- New unit test: 1 (`test_session_continuation_change_does_not_evict`).
- New browser test: 1 (`test_edit_session_continuation_round_trip`).
- Full unit suite: **1878 passed, 4 skipped, 405 deselected, 2 warnings in 125.01s** — up exactly from leg 4's 1877 → 1878 (+1). The 2 warnings remain the pre-existing `AsyncMock-never-awaited` on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (F2 debrief carry-forward #10, not introduced here).
- Browser suite for the editor file: **13 passed in 16.60s** — up from leg 4's 12 → 13 (+1).

**Deviations from leg spec**:

- **Re-open-editor pattern in the browser test**: the leg sketched a `page.goto(f"{app_clean}#studio/connector-accounts/{account_id}")` re-navigate after save, but in this hash-router a same-URL `goto` is a no-op (the editor doesn't remount and the input keeps the in-memory value, defeating the "verify value pre-fills from backend" assertion). The test was tightened to route through the grid (Back → click card) so the editor genuinely re-mounts and the assertion exercises a fresh `GET /api/connector-accounts/{id}` → render path. Acceptance criterion ("round-trip verified end-to-end") is satisfied; the pattern matches the precedent in `test_create_and_test_creates_account_and_transitions_to_edit_mode`.

- **Header summary unchanged** — the leg explicitly recommended option (a) (leave `ttlSummary` alone) for minimal scope. Option (b) (add a second `continuationSummary` chip) is a cheap follow-up if user feedback says otherwise.

**Anomalies**:

- The first browser-test run after `make rebuild` failed with `playwright chromium` missing — Makefile's `_ensure-playwright` recovers this automatically (cache lives at `/root/.cache/ms-playwright` which doesn't persist across image rebuilds). One-shot recovery, not a regression.

**Verification**:

- All acceptance criteria walked individually and confirmed:
  - Lifecycle section renders TWO field-row + helper-text pairs in the same `editor-section` wrapper.
  - New input: `data-field`, `data-testid`, `type="number"`, placeholder all match the contract.
  - New helper text: `data-testid="connector-account-continuation-hint"`; text contains the disambiguating phrase (browser test asserts).
  - F2's forward-reference comment is removed (grep returns no matches).
  - `staticFields` includes `'session_continuation_seconds'`.
  - Form-data extraction parses parallel to `idle_timeout_seconds`; empty → null; non-empty integer → integer; non-integer string → pass-through (backend 422).
  - Payload dict includes the new field.
  - `test_session_continuation_change_does_not_evict` passes (scoped + full suite).
  - Browser round-trip test passes.
- Scoped REST test: `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountAPI::test_session_continuation_change_does_not_evict -xvs --timeout 30` → PASSED in 0.40s.
- Full unit suite: `docker exec the-one pytest -x --timeout 30` → 1878 passed in 125.01s.
- Browser suite (editor file): `docker exec the-one pytest -m browser tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -v` → 13 passed in 16.60s.
- Lint: clean (`docker exec the-one ruff check the_one/ tests/` → "All checks passed!").



### Leg 06 — e2e-integration-and-both-visibility-paths

- **Started**: 2026-05-17
- **Completed (landed, pending flight-end commit)**: 2026-05-17
- **Status**: landed

**Changes shipped**:

- `tests/test_connectors_e2e_session.py` — New test file (+374 lines). Three tests, NO production code changes (test-only leg per design). Fixture pattern mirrors leg 4's `tests/test_connectors_inbound.py` line-for-line: per-file `isolated_db` (tmp_path sqlite + module-singleton repoint via monkeypatch), inline `_seed_provider_and_agent` / `_seed_stub_account` / `_make_factory` / `_envelope` helpers (all module-local; no `conftest.py` extraction — design-review-recommended option (a) to keep leg 6 self-contained; the cross-file helper refactor stays a candidate for a future maintenance flight), and the critical autouse cleanup `_clear_pool_locks_registry` that calls `pool_mod._clear_for_test()` + `inbound_mod._clear_for_test()` + `_registry_clear_for_test()` + `restore_to_baseline_for_test()`. The `restore_to_baseline_for_test()` call is the one that would silently leak registry state across tests if omitted (leg 4's anomaly entry made this lesson explicit). `_seed_stub_account` gains a `session_continuation_seconds: int | None = None` kwarg (leg 4's helper doesn't take it; leg 6's continuation-window test needs the per-account override path).

- The three tests:
  1. **`test_e2e_both_visibility_paths_coexist_in_session`** (the headline) — drives `dispatch_inbound` once to create a peer session (peer user message + mock-provider assistant reply, both `visibility=None`), then directly appends two operator-tagged Messages (operator user + operator assistant) to the same session via `chat_repo.update(sess.model_copy(update={"messages": encode_messages(...)}))` — the exact `_save_session_to_db` shape leg 1's docstring at `the_one/db/repositories.py:750-769` describes as preserving connector-identity columns. Then asserts: (a) decoded `agent.messages` contains both kinds (`len(operator_msgs) == 2`, `len(peer_msgs) >= 2`); (b) encoded JSON shape — `sum(d.get("visibility") == "operator") == 2` and `sum("visibility" not in d) >= 2`, plus a regression guard `for d in parsed: if "visibility" in d: assert d["visibility"] == "operator"` that catches any future codec change emitting `"visibility": null`; (c) `messages_to_ui_events` projection — operator-derived events carry `event["visibility"] == "operator"`, peer-derived events have NO `visibility` key, with the same null-key regression guard at the projection layer. This is the F3 contract proof F5 inherits when implementing the Chat UI's visual distinction between operator and peer messages.

  2. **`test_e2e_session_metadata_column_round_trips_at_create_time`** — `ChatSessionRepository.create` writes a non-trivial dict (`{"routing": {"rule": "default", "agent": "test"}, "audit": ["v1"]}`) into `session_metadata` at row creation; `.get` reads it back; asserts equality. Plus a `session_metadata=None` round-trip case. Forward-compat for F7's routing-decision logs — F3 L1 added the column, this pins the round-trip BEFORE F7 needs it. F7 owns its update primitive; leg 6 only exercises the create-time write + read.

  3. **`test_e2e_continuation_window_real_time_supersede`** — two `dispatch_inbound` calls for the same external key with a real `asyncio.sleep(2)` between them, under a per-account `session_continuation_seconds=1` override (NOT the env var). Asserts `len(sessions) == 2` (both rows preserved with distinct ids but the same external-key 4-tuple). Distinct from leg 4's `test_dispatch_inbound_creates_new_session_after_window` which fakes elapsed time via a stale `last_inbound_at` write — leg 6's wall-clock variant exercises real `datetime.now()` comparison inside the resolver and catches a `datetime.now` vs. `utcnow` regression the faked test would miss. Includes a comment in the test body explaining the intentional 2-second sleep trade-off. Also asserts each row has exactly one user turn (confirms the second inbound did NOT land in the first session's history).

**Test count delta**:

- New unit tests: 3 (`test_e2e_both_visibility_paths_coexist_in_session`, `test_e2e_session_metadata_column_round_trips_at_create_time`, `test_e2e_continuation_window_real_time_supersede`).
- Full unit suite: **1881 passed, 4 skipped, 405 deselected, 2 warnings in 126.86s** — up exactly from leg 5's 1878 → 1881 (+3). The 2 warnings remain the pre-existing `AsyncMock-never-awaited` on `test_provider_api.py::TestModelDiscovery::test_ollama_models` (F2 debrief carry-forward #10, not introduced here).
- Scoped: `docker exec the-one pytest tests/test_connectors_e2e_session.py -x --timeout 30 -v` → 3 passed in 2.78s (the wall-clock test contributes ~2s of that).

**Deviations from leg spec**:

- **Three tests, not four** — the leg artifact's Acceptance Criteria header still references "at least four tests" in two places, and a "full-pipeline test (`test_e2e_first_contact_...`)" acceptance line. The Outputs section explicitly says **3 tests, NOT 4** with rationale: "first-contact smoke dropped per design review — it's covered by leg 4's `test_dispatch_inbound_creates_session_on_first_contact` and visibility=None pinning by leg 4's `test_dispatch_inbound_persists_inbound_with_visibility_none` and `_agent_reply_*` siblings". The Outputs section is the design-review-current contract; the residual "four tests" / "full-pipeline" lines in Acceptance Criteria are stale boilerplate from the earlier draft. Following Outputs — implementing 3 tests. Recording the discrepancy here so a future reader (or the flight-level Reviewer in Phase 2d) is not confused by the acceptance-criteria text. The both-visibility test does still exercise the full pipeline end-to-end (schema → dispatcher → resolver → codec → projection) — it's just doing double duty rather than being a separate test.

- **`_seed_stub_account` helper signature divergence from leg 4** — leg 4's helper is `_seed_stub_account(account_id: str = "acct-test")` with no continuation-window kwarg (leg 4's after-window test seeds the account directly via `ConnectorAccountRepository.create` inline). Leg 6 chose to extend the helper with `session_continuation_seconds: int | None = None` so the third test stays terse. Mechanically minor; the helper is module-local so this divergence does not affect leg 4's tests.

- **Regression guards beyond the minimum** — the both-visibility test adds two regression-guard loops the spec did not require: `for d in parsed: if "visibility" in d: assert d["visibility"] == "operator"` (catches `"visibility": null` regressions in the codec) and the same at the projection-events layer. Cheap; on-topic for the leg's "regression baseline F4+ inherit" framing.

**Anomalies**:

- None. Tests passed on first run (scoped + full suite); lint clean on first run. The leg's design work (notably the design-review pivot from 4 to 3 tests + the explicit "copy leg-4's helpers verbatim, including `restore_to_baseline_for_test()` in the autouse cleanup" guidance) absorbed enough of the failure modes upstream that implementation was mechanical.

**Verification**:

- All acceptance criteria walked individually and confirmed (treating Outputs as the authoritative contract per the deviation note above):
  - New test file exists at `tests/test_connectors_e2e_session.py` with 3 tests.
  - Both-visibility test asserts the persisted JSON contains exactly 2 messages with `"visibility": "operator"` and at least 2 messages without the visibility key; asserts `messages_to_ui_events` projects accordingly; includes regression guards against `"visibility": null` emission.
  - Session-metadata test writes a non-trivial dict (nested object + list), reads it back, asserts equality; includes a None round-trip case.
  - Continuation-window test uses per-account `session_continuation_seconds=1` override (NOT the env var); sleeps 2 seconds real wall-clock; asserts 2 distinct session rows survive (old row preserved); asserts external-key 4-tuple is identical across rows (only the most-recent-within-window query distinguishes them); asserts each row has exactly one user turn.
  - Fixture pattern mirrors leg 4 line-for-line — autouse cleanup includes `restore_to_baseline_for_test()`; `isolated_db` uses tmp_path + module-singleton repoint via monkeypatch; helpers are inline-module-local.
  - No code outside the test file (verified — only `tests/test_connectors_e2e_session.py` is new in working tree for this leg).
- Scoped: 3 passed in 2.78s. Full: 1881 passed, 4 skipped, 405 deselected in 126.86s. Lint: "All checks passed!".

**F3 readiness for Phase 2d (post-flight Reviewer pass + commit)**:

- All 6 leg statuses are `landed` (verified: L1-L6 all flipped).
- `flight.md` Legs list has all 6 entries ticked (`- [x]`).
- Flight log has Leg Progress entries for L1-L6.
- Working tree is dirty (uncommitted changes accumulated across all 6 legs per the agentic-workflow batched-review model).
- Branch: `flight/03-session-model-key-and-visibility` (verified).

Phase 2d's flight-level Reviewer should now consume the full diff against `main`, with all 6 leg progress entries above as the by-leg map.



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
