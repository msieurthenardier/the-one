# Leg: verify-integration

**Status**: completed
**Flight**: [Telemetry Overlay Usage Persistence](../flight.md)

## Objective

Prove the full persist → restart → restore round-trip end-to-end: an in-process
integration test that drives a turn, drops the in-memory session, restores from the
DB through the real `_restore_session` path (covering both the ok and degraded join
payloads), and asserts the snapshot survives with its **exact** `context_tokens`;
plus a Playwright browser-flow test asserting the restored overlay DOM. This is the
last autonomous leg of the flight.

## Context

- L01 writes `last_usage`; L02 restores it in the overlay + asserts the join-payload
  builders carry it. L03 closes the loop with the **real restart path** and a
  **browser** assertion of the restored DOM.
- **Real restart path** — `_restore_session` (`app.py:856`). The genuine
  cross-restart case is exercised by **dropping the in-memory `_sessions` entry**
  (`_sessions.pop(session_id, None)`, the same pop the reaper/restore use at
  `app.py:879`/`:908`/`:918`/`:928`) so the join flows through the DB-reload branch
  (fresh `Session` at `app.py:970-986`, `_sessions[session_id] = session`) rather than
  the warm-cache branch (`app.py:949-968`, which refreshes `existing.session_metadata =
  db_session.session_metadata` at `:966`). Both branches converge on `RestoredSession`
  carrying `session_metadata` from the DB row.
- **Both join payloads** must carry `last_usage`: `_build_session_joined_ok`
  (`app.py:1088` → `session.session_metadata` at `:1108`) and
  `_build_session_joined_degraded` (`app.py:1112` → `db.session_metadata` at `:1137`).
  L02 added builder-level unit assertions; L03 asserts them **through the restore
  round-trip** (restore → build payload → value equals what was written).
- **★ Mock-usage blocker (discovered during L03 design — design decision DD-L03-1).**
  `MockProvider` hardcodes `TokenUsage(input_tokens=0, …)` (`mock.py:77` in
  `complete()`, `:124` in `stream()`). The overlay's derived `context_tokens` is
  `last_input` (= the last assistant step's `input_tokens`), and **L01's zero-usage
  guard is `if last_input:`** — so a turn driven by the default mock yields
  `last_input == 0` and the **entire `last_usage` write is suppressed**. With the
  stock mock there is nothing to restore, so the flight's "drive a turn → reopen →
  assert restored" plan cannot be exercised. **Resolution:** add a **backward-
  compatible test seam** to `MockProvider` — read an optional `input_tokens` from the
  provider `config` (default **0**, preserving every existing test's behavior) and
  emit it in both `complete()` and `stream()`. Tests that need a meaningful snapshot
  seed the mock with `config={"input_tokens": N}`. No L01 change is needed. This is
  recorded as a flight-log Deviation (the flight plan didn't anticipate the mock's
  zero input_tokens) and flagged to the operator.
- **★ Known limitation (design review, not fixed in this flight): the
  `if last_input:` guard also suppresses real Ollama turns that report
  `input_tokens=0`.** `OllamaProvider` derives `input_tokens` from
  `u.get("prompt_tokens", 0)`; some Ollama builds/endpoints omit `prompt_tokens` (or
  the whole usage block → `usage=None`), so a genuine Ollama turn can settle with
  `last_input == 0` and have its `last_usage` snapshot suppressed — the very
  reopen-shows-`0/max` symptom this flight fixes, for that provider. **Deliberately
  not addressed here:** (a) the fullness bar (`context_tokens`) is unrestorable for
  such a turn regardless of the guard, since `context_tokens` *is* the missing input
  count; (b) fixing it means reopening landed L01 + its zero-usage-guard tests for an
  edge-of-edge case. Recorded as a mission Known Issue / flight-log item and flagged
  to the operator as a candidate follow-up (e.g. guard on "saw any usage event" or
  `last_input or total_output` so the in/out counts still restore). L03 does **not**
  change the guard.

## Inputs

What exists before this leg runs (working tree, uncommitted L01+L02):
- L01: `_persist_last_usage` + writes at both settle points (`app.py`).
- L02: frontend restore + `setTelemetryMax` + `tests/test_session_joined_payload.py`.
- `_restore_session` (`app.py:856`), `_sessions` registry (`app.py:391`),
  `_build_session_joined_ok` (`app.py:1088`) / `_build_session_joined_degraded`
  (`app.py:1112`).
- Browser harness: `tests/browser/` with `seed_mock_provider` /
  `seed_mock_agent` (`tests/browser/seeders.py:34`/`:60`), `app_clean` /
  `app_with_provider` / `app_with_agent` fixtures (`tests/browser/conftest.py`),
  `@pytest.mark.browser`, Playwright `Page`/`expect`.
- `MockProvider` (`the_one/llm/mock.py`).
- Snapshot baselines are gitignored (`.gitignore:25` → `tests/browser/__snapshots__/`,
  confirmed untracked) — DOM-shape assertions only; **no committed visual snapshots**.

## Outputs

What exists after this leg completes:
- `MockProvider` honours `config["input_tokens"]` (default 0) in `complete()` and
  `stream()`.
- An in-process integration test: turn → `last_usage` persisted → `_sessions` dropped
  → `_restore_session` reload → both join payloads carry `last_usage` → restored value
  equals the written `context_tokens` (exact, not "non-zero").
- A Playwright browser-flow test: seed agent (mock `input_tokens` > 0), drive a turn,
  reopen the session, assert `.t-in` / `.t-ctx` / `.context-bar` reflect the restored
  values. DOM-shape assertions; no committed snapshots.
- Full unit suite green at/above the F5 baseline (`3422` passed); the browser suite's
  new flow passes.

## Acceptance Criteria
- [x] `MockProvider` emits `config.get("input_tokens", 0)` as the usage
      `input_tokens` in both `complete()` and `stream()`; **default 0 preserves
      existing behavior** (no currently-passing test changes its expectations).
- [x] Integration test: after a driven turn (mock `input_tokens` = N > 0),
      `session_metadata["last_usage"]` is in the DB; after
      `_sessions.pop(session_id)` and `_restore_session`, the restored session carries
      `last_usage`, and `_build_session_joined_ok` returns a payload whose
      `session_metadata["last_usage"]["context_tokens"]` **equals N** (the written
      value — not merely non-zero).
- [x] The degraded join path (`_build_session_joined_degraded`) also carries
      `last_usage` through the restore (assert the same exact value).
- [x] The integration test exercises the **DB-reload** branch (it drops the
      `_sessions` entry first), not the warm-cache branch — i.e. it is a genuine
      restart simulation.
- [x] Playwright browser flow: with a mock agent whose provider config sets
      `input_tokens > 0`, after driving a turn and **reopening** the session, the
      overlay's `.t-in` / `.t-ctx` show the restored non-zero values and the
      `.context-bar` width is > 0. Assertions are DOM-shape; **no committed visual
      snapshots** are added (the gitignored `__snapshots__/` rule holds).
- [x] Full unit suite passes at/above the F5 baseline; no new flakes; the new browser
      flow passes under `@pytest.mark.browser`.

## Verification Steps
- Mock seam: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_mock_provider*.py -x --timeout 30` (or the existing mock test module) —
  default still emits `input_tokens=0`; `config={"input_tokens": 7}` emits 7.
- Integration: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/<integration-test> -x --timeout 30` — round-trip asserts the exact restored
  `context_tokens` via both builders.
- Browser: run the browser suite per the repo's documented browser-test invocation
  (the `@pytest.mark.browser` marker; e.g. `make test-browser` if defined, else the
  pytest invocation the repo uses for `tests/browser/`). Confirm the new flow passes.
- Full regression: `make test-unit` — green at/above `3422` passed; report the
  pass/skip/deselect line.

## Implementation Guidance

1. **Add the `input_tokens` config seam to `MockProvider` (`the_one/llm/mock.py`).**
   - In `complete()` (`mock.py:74-78`), replace
     `TokenUsage(input_tokens=0, output_tokens=len(content.split()))` with
     `TokenUsage(input_tokens=self.config.get("input_tokens", 0),
     output_tokens=len(content.split()))`.
   - In `stream()` (`mock.py:124`), make the same change to the synthesized final
     `usage`.
   - Update the class docstring's `config` example (`mock.py:16-28`) to document the
     optional `"input_tokens": N` key (default 0).
   - Keep the default at **0** so existing usage-accounting tests are unaffected.

2. **Write the in-process integration round-trip test.**
   - New module (follow the repo's app-test layout — e.g.
     `tests/test_last_usage_round_trip.py`, sibling to L01's
     `tests/test_last_usage_persistence.py`).
   - **Drive a real `MockProvider` configured with `input_tokens = N` (N > 0)** so the
     step-1 seam is exercised in-process too (not only by the browser test). Wire a
     `MockProvider(config={"input_tokens": N})` through the agent and drive the turn
     through the real web settle path (`_process_and_broadcast`), reusing the in-process
     invocation harness from `test_last_usage_persistence.py` /
     `tests/test_process_and_broadcast_live_read.py`. (If wiring a real `MockProvider`
     through the agent factory in-process proves impractical, a stub agent that yields
     an assistant `Message` with `usage=TokenUsage(input_tokens=N, …)` is an acceptable
     fallback for the *round-trip* assertion — but then add an explicit note that the
     mock seam itself is covered only by the step-1 unit test + the browser test.)
   - **Use the non-streaming mock path** (do **not** set `config["stream_chunks"]`) so
     usage arrives once on the final settled `Message` — avoids interim
     `input_tokens=0` usage events racing the assertions.
   - Assert `session_metadata["last_usage"]` is in the **DB** with
     `context_tokens == N`.
   - Drop the warm session: `_sessions.pop(session_id, None)` (import the module-level
     registry at `app.py:391`). Then call `_restore_session(session_id)` and confirm it
     took the **DB-reload** branch — after the pop, `session_id in _sessions` is False
     (`app.py:949`) so it falls to the fresh-`Session` construction + re-insert
     (`app.py:970-986`). Assert the returned `Session` is a fresh object (identity
     differs from the pre-pop one) to prove the DB path ran.
   - **ok-path**: assert `_build_session_joined_ok(restored.session)
     ["session_metadata"]["last_usage"]["context_tokens"] == N`.
   - **degraded-path** (separate setup): `_restore_session` after a successful
     pop+reload returns `SESSION_STATUS_OK`, so it **cannot** also yield a degraded
     payload — construct a `RestoredSession` with a degraded status by hand (mirror
     L02's degraded-path test in `tests/test_session_joined_payload.py`, which patches
     `_merge_pending_approvals_into_history` to avoid a live DB dependency), with its
     `db.session_metadata` carrying the written `last_usage`, and assert
     `_build_session_joined_degraded(restored)["session_metadata"]["last_usage"]
     ["context_tokens"] == N`.
   - Assert the **exact** value N at every hop — the F5-HAT lesson: verify the real
     value survives, not merely "non-zero".

3. **Write the Playwright browser-flow test (`tests/browser/`).**
   - New flow (e.g. `tests/browser/test_flow_usage_restore.py`), `@pytest.mark.browser`.
   - Seed a mock provider with `config={"input_tokens": N}` (use `seed_mock_provider`'s
     `config=` param — signature at `seeders.py:34`, `config` forwarded into the POST
     payload at `seeders.py:52-53`) and a mock agent on it (`seed_mock_agent`). Do
     **not** set `stream_chunks` (non-streaming path → single final usage event, no
     interim zeros).
   - `page.goto(...)`, bootstrap into chrome by picking the agent from the welcome
     listbox (mirror `test_flow_new_chat.py`'s `.chat-welcome-item` click pattern),
     send a message (`[data-testid="chat-input"]` + `[data-testid="chat-send-btn"]`).
   - **Wait for the overlay to populate before reopening** — explicitly
     `wait_for_function` on `.t-ctx` (and/or `.t-in`) showing a non-zero value, **not
     merely the assistant message DOM** (the assistant bubble can land before the
     `usage` event settles + persists; reopening too early races an un-persisted
     turn). This confirms the live path first and gates the reopen.
   - **Reopen** the session so `session_joined` re-fires: `page.reload()` (simplest —
     re-joins the current session) or navigate to a new chat and back via the
     chat-history sidebar (`.session-group-list .list-item`). After the rejoin, assert
     the overlay restored: `.t-in` / `.t-ctx` show the restored non-zero values and
     `.context-bar` width is > 0 (read via `getComputedStyle(...).width` like
     `test_flow_new_chat.py`'s overlay test).
   - **No committed snapshots** — DOM-shape / computed-style assertions only.
   - **Reopen caveat (document in a test comment):** the subprocess stays up across
     `page.reload()`, so the rejoin hits the **warm-cache** branch
     (`app.py:949-968`) — but that branch still does `existing.session_metadata =
     db_session.session_metadata` (`app.py:966`), refreshing the snapshot from the DB
     row, so the *frontend restore* is genuinely exercised end-to-end (it is not a
     shortcut that skips the DB). The *genuine cross-restart DB-reload* path (fresh
     `Session` construction) is what the in-process integration test (step 2) covers by
     dropping `_sessions`. Together they cover both halves; neither alone is sufficient.

4. **Run the full suite** (`make test-unit`) and the browser flow; confirm green
   at/above the F5 baseline and record the numbers in the flight log.

## Edge Cases
- **Mock default unchanged**: any existing test asserting mock `input_tokens == 0`
  still passes (default is 0). Verify by running the mock's existing test module.
- **Warm-cache vs DB-reload divergence**: if the integration test forgets to drop
  `_sessions`, it silently tests the warm path and gives a false sense of restart
  coverage — the test must assert it hit the DB-reload branch (criterion above).
- **Browser timing**: wait for the `usage` event (overlay non-zero) before reopening,
  else the reopen races an un-persisted turn. Use Playwright `expect(...).to_have_text`
  / `wait_for_function` with a timeout, mirroring the existing flows.
- **`context_tokens` derivation**: with the mock, `last_input == input_tokens == N`,
  so `context_tokens == N`. The assertion pins N, catching any sum-vs-last-input
  regression at the restore layer too.

## Files Affected
- `the_one/llm/mock.py` — `config["input_tokens"]` seam (default 0) in `complete()`
  + `stream()`; docstring update.
- `tests/test_last_usage_round_trip.py` (new) — in-process restart round-trip.
- `tests/browser/test_flow_usage_restore.py` (new) — Playwright restore flow.
- The existing mock test module (`tests/test_mock_provider.py` or equivalent) —
  **required** companion: assert `config={"input_tokens": N}` yields
  `usage.input_tokens == N` in both `complete()` and `stream()`, and that the default
  (no config) still yields `input_tokens == 0`. Locks the seam contract.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (full suite ≥ F5 baseline; browser flow green)
- [x] Update flight-log.md with leg progress entry **and** the DD-L03-1 mock-seam
      Deviation
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)

> **Note (agentic-workflow):** This is the **last autonomous leg**. The Developer
> stops at `[HANDOFF:review-needed]` with leg status `landed` and the flight log
> updated. The Flight Director then runs the single flight-wide review + commit
> (Phase 2d) covering L01+L02+L03 together.

## Citation Audit

Citations verified against current (post-L01/L02) working tree at leg design time:
- `the_one/llm/mock.py:77` (`complete()` `TokenUsage(input_tokens=0, …)`) and `:124`
  (`stream()` synthesized usage) — **OK** (the hardcoded zeros this leg parameterizes).
- `mock.py:16-28` (config docstring), `mock.py:42-53` (`__init__` stores
  `self.config`) — **OK**.
- `app.py:856` (`_restore_session`), `:879`/`:908`/`:918`/`:928` (`_sessions.pop`),
  `:949-967` (warm-cache branch), `:986` (`_sessions[session_id] = session`,
  DB-reload branch) — **OK**.
- `app.py:391` (`_sessions: dict[str, Session] = {}`) — **OK**.
- `app.py:1088`/`:1108` (`_build_session_joined_ok`),
  `app.py:1112`/`:1137` (`_build_session_joined_degraded`) — **OK** (post-L01 lines).
- `tests/browser/seeders.py:34` (`seed_mock_provider`, `config=` param) / `:60`
  (`seed_mock_agent`) — **OK**.
- `tests/browser/test_flow_new_chat.py` (welcome-item click, telemetry overlay
  `getComputedStyle` patterns) — **OK** (browser-flow precedent).
- `tests/test_session_joined_payload.py` (L02; degraded-path test patches
  `_merge_pending_approvals_into_history`) — **OK** (round-trip degraded setup to
  mirror).
- `.gitignore:25` (`tests/browser/__snapshots__/` gitignored; confirmed untracked) —
  **OK** (no-committed-snapshots rule).
