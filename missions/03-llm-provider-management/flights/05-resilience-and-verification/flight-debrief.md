# Flight Debrief: Resilience & Verification

**Date**: 2026-04-25
**Flight**: [Resilience & Verification](flight.md)
**Status**: landed
**Duration**: 2026-04-25 (single-day flight, ~5 hours wall-clock with HAT)
**Legs Completed**: 5 of 5 (4 autonomous + 1 HAT)

## Outcome Assessment

### Objectives Achieved

The flight delivered on all stated objectives plus surfaced and fixed three classes of bugs through the HAT process:

- **Crash-safe encryption-key rotation** via temp-file + `os.replace` ordering. New failure-injection test asserts the on-disk key, cached encryptor, and stored ciphertext are all unchanged when DB commit fails.
- **Session health classification** with three states (`agent_deleted`, `provider_missing`, `ok`) plus an implicit `not_found` for unknown session IDs. Surfaced through both the WebSocket `session_joined` payload and HTTP `/api/chat` errors. The silent default-agent fallback at `app.py:154-161` was removed.
- **Frontend session-health UX** — amber banner directly above the input area with disabled chat input, distinct from the existing global setup banner. `bannerEl`-as-state-flag refactored to a dedicated `setupIncomplete` boolean. Stale-join guard added for rapid session-switching.
- **Five cleanup items** — `OllamaProvider` model default removed; masked-API-key check switched to `__MASKED__` sentinel (test that was passing for the wrong reason caught and fixed); `test_provider` error taxonomy normalized (200 for upstream errors, 500 for unexpected); two test-collection errors fixed; one-shot ruff-format pass on `app.py`.

### Mission Criteria Advanced

This flight checked off the final 3 contributing criteria for Mission 03:

- ✓ API credentials are stored encrypted at rest [...] a rotate function re-encrypts all stored secrets with a new key
- ✓ The system degrades gracefully when a configured provider is unreachable or a requested model is unavailable, surfacing clear feedback to the user
- ✓ On first start with no provider configurations, the application guides the user to set up at least one provider before chat is functional

Mission 03 is now ready for debrief and close.

## What Went Well

- **Highest-risk-first leg ordering** (key rotation went first) gave the rotation design the most review scrutiny. The crash-safe ordering proved correct under failure-injection testing on first implementation.
- **Two design-review passes per leg** caught real correctness issues before implementation — most notably the `tests/test_provider_api.py::test_update_preserves_masked_key` bug (was passing by coincidence under the new sentinel) and the `chat.js` "+ new" stale-join regression.
- **Test renames over deletes** — `test_cascade_delete_agent` was renamed to `test_agent_delete_does_not_cascade_to_sessions` with the assertion inverted. The test name became documentation of the intent shift; the diff is reviewable; future contributors can git-blame their way to the migration.
- **HAT caught two cross-cutting bugs** that no unit test would have caught: the `chat_sessions.agent_name` FK CASCADE foreclosing the `agent_deleted` state, and the cached-Session snapshot pattern blocking system-prompt edits from propagating. Both became inline fixes within the leg's mandate.
- **Inline fix discipline** — when HAT surfaced bugs, the Flight Director spawned focused Developer agents with bounded scope rather than aborting the leg or expanding into ad-hoc surgery. Schema migration v5 and the C-lite reactivity change both shipped under this discipline.
- **Decision-as-record pattern** — the flight log's `## Decisions` section captured the *why* of choices that diverged from the leg specs (DB rollback addition, Concourse autopilot accepted breakage, orphan-temp-file policy). Future operators can find these without reading the entire log.

## What Could Be Improved

### Process

- **Prerequisite verification was stale.** The flight asserted "All 325 tests passing on current main" — actual baseline was 317 collected with 2 collection errors. The Flight Director correctly chose to proceed and recorded the deviation, but the `/flight` skill's prereq verification should run `pytest --co` against the named base commit, not trust a stale number.
- **HAT being optional was wrong for this flight.** The HAT caught two real bugs. Any flight that touches state-machine semantics with cross-layer dependencies (DB constraints, in-memory caches, WS protocol) should have a non-optional HAT.
- **Cross-cutting audit was missing from leg design.** Three of the bugs lived outside the leg specs' blast radius — schema, cache lifecycle, and deployment config. The leg-design template focuses on intra-module changes and under-audits cross-cutting infrastructure assumptions.

### Technical

- **String-match exception classification** in `_restore_session` (`app.py:198-224`) is fragile. If `factory.py:102` changes `"Unknown agent: ..."` or `db/repositories.py:401` changes `"Provider not found: ..."`, the classifier silently misclassifies. Mitigated by code comments listing source sites; properly fixed by typed exceptions in `factory.py` (out of scope, follow-up).
- **System-prompt merge invariant is implicit.** `agent.messages = agent.messages[:1] + non_system` in `_restore_session` assumes a single system message at index 0 and that all DB-stored non-SYSTEM messages are valid history. Any future feature with multi-system-message conversations or mid-conversation prompt overrides will break this.
- **`Encryptor.rotate_key` is dead code on the production path** but still tested. Test surface for unused code path will rot. Either remove (small follow-up) or annotate as deprecated.
- **`_get_or_restore_session` no longer matches its name.** After C-lite, the function always rebuilds via `_restore_session`. The name suggests caching semantics that no longer hold. Rename to `_rejoin_session` or `_load_session`.
- **C-lite mid-message limitation:** edits to agent config don't propagate to messages sent within an already-joined session — only at the next rejoin. Acceptable trade-off but a UX pothole. Document as a boundary contract.
- **No automated test for v_n → v_n+1 migration paths.** `test_schema.py` only tests fresh-DB migration. The HAT verified the v4 → v5 migration manually. A future regression to the v5 migration would not be caught.
- **`assert db is not None`** in `_build_session_joined_degraded`. Asserts are stripped under `python -O`; should be `if … raise`.

### Documentation

- **`the_one/agents.md` should document the C-lite session reactivity invariant** — `_restore_session` rebuilds Agent in place from current config every join; mid-session edits do not propagate until next join.
- **`the_one/agents.md` should note the system-prompt-from-config invariant** — DB-stored system messages are intentionally discarded on restore. Future contributors will try to "fix" this without context; preempt them.
- **`the_one/agents.md` should be updated for schema v5** and explain that `chat_sessions.agent_name` is intentionally non-FK to support the `agent_deleted` health state.
- **`CLAUDE.md` (project-level) should mention the masked-API-key sentinel** — `__MASKED__` is a magic string any future developer touching the provider edit form needs to know about.
- **README/deployment doc should note the `the_one_data` named volume requirement** for docker-compose.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 01: DB rollback added beyond the leg snippet | Singleton aiosqlite connection would have masked the failure post-commit | Yes — design template should ask "if any I/O step in this transaction fails, does subsequent state on the same connection see uncommitted writes?" |
| Leg 01: `key_path is None` guard reordered to pre-DB | Caught at flight review; original order would leave a half-rotated DB if guard fired | Yes — ordering of precondition checks relative to side-effects is a design-time concern, not implementation-time |
| Leg 02: HAT discovered FK CASCADE foreclosing the `agent_deleted` state | Schema constraint contradicted the design intent; not audited at design time | **Yes — high priority.** Add "state-machine reachability audit" to leg-design template |
| Leg 02: Cache freshness was conflated with health-check semantics | Decision said "health is a join-time concept" but the cache held *config* state, not just health state | **Yes — high priority.** Add "cache freshness contract" requirement to design template |
| Leg 03: Backend protocol gap (only `_restore_session`'s caller used `_build_session_joined_ok`) had to be closed in Leg 03 instead of Leg 02 | Leg 02 audited only the `join` action, not all WS message emission sites | Yes — design must enumerate all emission sites for a protocol field |
| Leg 04: 4 pre-existing connection-failure tests had to be rewritten | The new error taxonomy required real exception classes; MagicMock attributes are not valid `except` targets | Partially — flag for "API-shape changes invalidate existing tests" |
| Banner placement moved at HAT (top → above input) | UX feedback came too late; no AC was specified for visual placement | Yes — design template should require explicit UX acceptance criteria for any new UI element |
| `the_one_data` named volume added during HAT | Container rebuilds were wiping data; no pre-flight check verified data persistence | Yes — `/preflight-check` should verify any project with persistent state has a bind-mount or named volume |

## Key Learnings

1. **Design must audit lower layers.** Three of this flight's HAT-caught bugs (FK CASCADE, snapshot pattern, container wipe) lived in layers below the leg's stated mandate. Application-layer designs that depend on storage, cache, or deployment behaviors must explicitly audit those layers — and the existing tests that pin them.

2. **Cache freshness ≠ cache validity.** The Leg 02 design conflated "the cached agent works" with "the cached agent reflects current config." A cache of derived state from a mutable source needs an explicit freshness contract (per-call rebuild / TTL / invalidation event / accepted staleness).

3. **Sentinel/display-string disambiguation requires test scrutiny.** A `startswith("***")` check that uses display-format strings as sentinels is silently bivalent — tests can pass for the wrong reason. Future flights touching display/sentinel boundaries should explicitly verify tests exercise the round-trip with realistic input, not the display format.

4. **HAT for state-machine flights is non-negotiable.** Two of this flight's three real bugs were unit-untestable — they required end-to-end interaction (delete agent in Studio → click session in chat) to surface. Any flight that touches state semantics across DB/cache/UI layers must include a HAT leg, not as optional but as required.

5. **Test renames as documentation of intent shifts.** The `test_cascade_delete_agent` → `test_agent_delete_does_not_cascade_to_sessions` rename made the contract change reviewable. This should be the standard pattern when a test's underlying intent reverses.

## Recommendations

### High priority

1. **Add "state-machine reachability audit" to the leg-design template.** When a design specifies a state, the design review must enumerate every infrastructure layer (DB constraints, FK cascades, indexes, cache TTLs, WS protocol versioning, application-layer fallbacks) that could foreclose that state. The Flight 05 FK CASCADE bug is the canonical case study.

2. **Add "cache freshness contract" to the leg-design template.** When a design introduces or relies on a cache of derived state, the design must state explicitly: *what is the source of truth, when is the cache rebuilt, what is the maximum staleness acceptable to the user?* The C-lite snapshot bug is the canonical case study.

3. **Fix the `/flight` skill's prerequisite verification** to actually run `pytest --co` against the named base commit, rather than trusting a stale number from earlier debriefs.

4. **Make HAT non-optional for any flight that touches state-machine semantics with cross-layer dependencies** (DB constraints, in-memory caches, WS protocol). Rename the leg slug from `hat-and-alignment` *(optional)* to `hat-and-alignment` *(required for state-machine flights)*.

### Medium priority

5. **Update `the_one/agents.md`** to document: (a) the C-lite session reactivity invariant, (b) the system-prompt-from-config invariant, (c) the schema v5 design note (intentional non-FK on `chat_sessions.agent_name`), (d) the masked-API-key sentinel.

6. **Refactor `factory.py` to typed exceptions** (`AgentNotFoundError`, `ProviderNotFoundError` extending `KeyError` for back-compat). Eliminates the message-substring matching in `_restore_session`. Small, mechanical, high-leverage.

7. **Concourse autopilot pipeline update** — the flight logged this as accepted external breakage. The pipeline now silently no-ops on degraded sessions. Either re-create the session with a valid agent, or surface `result.get("error")` and alert. 5-minute fix.

8. **Add `the_one_data` volume documentation** to README and ensure `/preflight-check` verifies data persistence for projects with persistent state.

### Lower priority / future flights

9. **Rename `_get_or_restore_session` → `_rejoin_session`.** Current name suggests caching semantics that no longer hold.

10. **WebSocket protocol tests** — assert payload-shape invariants (`session_joined` always carries `status`, etc.). Currently relies on `grep` and HAT.

11. **C-medium per-step rebuild — DEFER.** Not currently needed. The C-lite contract should be documented; a dedicated flight should be triggered only if a feature requires mid-conversation config swap (e.g., model auto-escalation per task complexity) or if operational reports show users confused by edit-doesn't-apply-to-current-message.

12. **Remove `Encryptor.rotate_key` dead code** in a small follow-up flight. Or annotate `@deprecated`.

13. **Schema migration tests for v_n → v_n+1 paths.** Today, `test_schema.py` only tests fresh-DB migration.

## Action Items

### Immediate (this PR / next commit)

- [x] Flight committed and pushed (PR #12, commits 062be7e + dcab2e6 + 1210dcf + 30599ca)
- [x] HAT verification complete (336 tests passing, 8 deselected, 0 collection errors)
- [x] Flight log records all decisions, deviations, anomalies
- [ ] Merge PR #12

### Mission close-out (next session)

- [ ] Run `/mission-debrief` for Mission 03 — record the system-prompt merge invariant and the exception-message classifier as mission-level "known issues at close" so they remain visible across future flights
- [ ] Decide disposition on the Concourse autopilot accepted breakage

### Methodology (mission-control updates)

- [ ] Add "state-machine reachability audit" to leg-design template
- [ ] Add "cache freshness contract" to leg-design template
- [ ] Fix `/flight` skill prerequisite verification (run `pytest --co` against named base commit)
- [ ] Update `/preflight-check` to verify data persistence for projects with persistent state
- [ ] Reconsider HAT optionality for state-machine flights

### Documentation (the-one)

- [ ] `the_one/agents.md`: document C-lite session reactivity invariant
- [ ] `the_one/agents.md`: document system-prompt-from-config invariant
- [ ] `the_one/agents.md`: update schema section for v5
- [ ] `CLAUDE.md`: mention `__MASKED__` sentinel
- [ ] README/deployment doc: note `the_one_data` named volume

### Follow-up flights (when prioritized)

- [ ] `factory.py` typed-exceptions refactor
- [ ] Concourse autopilot pipeline update
- [ ] Rename `_get_or_restore_session`
- [ ] WebSocket protocol tests
- [ ] Schema migration tests for v_n → v_n+1 paths
- [ ] Remove `Encryptor.rotate_key` dead code
- [ ] (Conditional) C-medium per-step rebuild — only if a concrete driver appears
