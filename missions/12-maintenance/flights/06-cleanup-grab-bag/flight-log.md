# Flight Log: Cleanup Grab-Bag

**Flight**: [Cleanup Grab-Bag](flight.md)

## Summary
In progress (final mission flight). Four independent tidy legs: L1 P5 (`_StreamAccumulator` extraction, behavior-preserving), L2 Q4 (`App.api.fetchJson` helper), L3 DOC1–DOC5 (docs/env scrub), L4 G1+G2 (git/asset hygiene — G1 already done, G2 PNG re-export).

---

## Leg Progress

### L1 — streaming-accumulator-extraction (2026-06-04)

**Outcome**: landed. Pure behavior-preserving refactor. No tests modified.

**What changed**:
- `the_one/llm/_streaming.py` (new, ~165 LOC): `_StreamAccumulator` with `feed_tool_call_delta`, `finalize_tool_calls`, `maybe_emit_interim`. Imports only from `base` (acyclic).
- `openai_provider.py`: removed ~65-LOC hand-rolled accumulator + byte-emitter block; uses `_StreamAccumulator`. `INTERIM_USAGE_BYTE_THRESHOLD` constant removed (now in `_streaming.py`). `BYTES_PER_TOKEN_OPENAI` kept (still returned by `_bytes_per_token_for_interim()`).
- `ollama_provider.py`: removed ~75-LOC accumulator + emitter block; uses `_StreamAccumulator`. `INTERIM_USAGE_BYTE_THRESHOLD_OLLAMA` removed. `BYTES_PER_TOKEN_OLLAMA` kept (passed to accumulator).
- `anthropic_provider.py`: replaced ~20-LOC inline byte-emitter with `acc.maybe_emit_interim`. `INTERIM_USAGE_BYTE_THRESHOLD_ANTHROPIC` removed. `BYTES_PER_TOKEN_ANTHROPIC` kept.
- `the_one/agents.md`: added `_StreamAccumulator` subsection under Streaming protocol (DOC5 streaming anchor, Leg 1 scope).

**Per-provider `bytes_per_token` preserved**: OpenAI/OpenRouter 4.0, Ollama 3.5, Anthropic 3.7. OpenRouter override via `_bytes_per_token_for_interim()` still applies (accumulator instantiated inside `stream()` using `self._bytes_per_token_for_interim()`).

**Net LOC**: ~165 added in `_streaming.py`; ~140 removed across providers (3 duplicate bodies). Net delta roughly −0 (consolidation, not deletion). Duplication eliminated.

**Tests**: 491 targeted tests (stream/provider/llm/openai/ollama/anthropic/openrouter) passed. Full suite passed. Zero test files modified (confirmed via `git status`).

### L3 — docs-and-env-scrub (2026-06-04)

**Outcome**: landed. Documentation and env-config corrections only — no source code changed.

**What changed**:
- `the_one/agents.md` (DOC1): Rewrote the `F9 Discord-native peer-approval` subsection bullet to describe the real UI mechanism — optimistic DOM update (`msg-pending-approval-acting`) + on-200 status swap via `App.chat.applyApprovalStatus` in `chat.js:322-347`, list refresh on WS `session_list`. Removed the phantom `connector-peer-approval-resolved` studio-event-bus event. `grep -rn "connector-peer-approval-resolved" the_one/` → zero.
- `the_one/agents.md` (DOC5): Added `### Singleton aiosqlite connection model` anchor (in "Subsystem contracts" section, before "Web-session idle reaper") documenting `db/connection.py`'s module-level singleton, WAL + FK, lazy `get_connection()`, lifespan close. Streaming anchor (`_StreamAccumulator`) was already present from L1 — not duplicated.
- `the_one/connectors/README.md` (DOC2): Removed "Slack in F9" from `CommandHandler` description (line ~99), removed "the second connector — Flight 9" from structural-Protocol-satisfaction paragraph (line ~106), reframed the plugin skeleton section header to drop "Flight 8 (Discord) and Flight 9 (the second connector)" (line ~118), and updated §10 to remove "the second connector at F9" from scope list. Illustrative Slack/Discord mentions in `errors.py`, `_stub.py`, `_pool.py`, `base.py` left intact.
- `the_one/connectors/registry.py` (DOC2): Reframed module docstring (line ~13), `restore_to_baseline_for_test` docstring (line ~141), and `register_builtin_connectors` docstring (line ~156) to remove "flight 9 (second connector)" forward-references.
- `.env.example` (DOC3): Removed 3 dead `THE_ONE_LLM_PROVIDER`, `THE_ONE_LLM_MODEL`, `THE_ONE_LLM_BASE_URL` lines. Added `THE_ONE_LOG_LEVEL` (default INFO) and `THE_ONE_DATA_DIR` (default ~/.the-one).
- `.env.example` (DOC4): Added "Operational tunables" section documenting `THE_ONE_SESSION_CONTINUATION_SECONDS` (86400), `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` (1800), `THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS` (300), `MCP_POOL_IDLE_TTL_SECONDS` (300). Added separate "Dev / test seams — do NOT set in production" section for `THE_ONE_SANDBOX_DISABLED` and `THE_ONE_REGISTER_STUB_CONNECTOR`.

**Verification**:
- `grep -rn "connector-peer-approval-resolved" the_one/` → 0 (DOC1)
- `grep -rni "flight 9\|second connector" the_one/connectors/` → only `_stub.py:23` (left intact per instruction)
- `grep -n "THE_ONE_LLM_" .env.example` → 0 (DOC3)
- `grep -n "THE_ONE_LOG_LEVEL\|THE_ONE_DATA_DIR" .env.example` → lines 11 and 15 (DOC3)
- `grep -c "THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS" .env.example` → 1, not duplicated (DOC4)
- 4 tunables present in .env.example (DOC4)
- `docker exec the-one ruff check the_one/ tests/` → All checks passed!

### L2 — fetch-json-helper (2026-06-04)

**Outcome**: landed. Behavior-preserving deduplication. No Python files changed; no tests modified.

**What changed**:
- `the_one/interfaces/web/static/js/api.js` (new, ~55 LOC): `App.api.fetchJson(url, opts)` exposed via cooperative `window.App = window.App || {}; window.App.api = window.App.api || {}` pattern. Reproduces the current fetch-error logic verbatim: ok-check → `r.text()` → try `JSON.parse` → `detail` string or flattened 422 `{loc, msg}` array (`loc.join('.') + ': ' + msg`, joined ` | `) → snippet fallback `'Server error ' + status + ' ' + statusText + ': ' + snippet` → `throw new Error(detail || 'Request failed')`. The per-call `'Save failed'`/`'Create failed'` fallbacks were unreachable dead code (the snippet branch always fills `detail`); collapsed to a single generic `'Request failed'`.
- `the_one/interfaces/web/static/index.html`: `<script src="/static/js/api.js">` added after `tabs.js`, before `section-nav.js` (well before `connector-editor.js`).
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js`: two duplicated ~22-line `fetch(…).then(r => { if(!r.ok){…}; return r.json() })` blocks in `handleSaveEdit` and `handleCreateAndTest` replaced with `App.api.fetchJson(url, opts)`. The other 11 `.ok` sites left intact (bespoke: silent swallows, inline-HTML rendering, `err.serverStatus` side-channel, custom formats).

**Verification**:
- `grep -c "\.ok" connector-editor.js` → 11 (was 13; dropped by 2 as expected)
- `make rebuild` → succeeded; all static assets served 200
- `docker exec the-one pytest -m browser tests/browser/test_flow_studio_connector_editor.py tests/browser/test_flow_studio_connector_create_and_test.py -q --timeout 120` → **27 passed** (422 error-path test green; error rendering unchanged)
- `docker exec the-one ruff check the_one/ tests/` → **0 errors**

### L4 — git-and-asset-hygiene (2026-06-04)

**Outcome**: landed. G1 verified-already-done (remote clean); G2 PNG re-export complete.

**G1 — remote branch verification (no writes performed)**:
- `git ls-remote --heads origin` → only `main` exists (`0078a37`). None of `docs/acl-recon-reason-string-convention`, `flight/16-pairing-peers-dm-only`, `flight/17-daily-driver-gate` present. Already satisfied at flight start.
- `git branch -a` → no dangling local tracking refs for those 3 branches. Clean.

**G2 — PNG re-export results**:

| File | Before | After | Dimensions |
|---|---|---|---|
| `gleepglorp_small.png` | 1712K | 264K | 1024×1024 RGBA → **512×512 RGBA** |
| `gleepglorp_med.png` | 1784K | 1708K | 1024×1024 RGBA → 1024×1024 RGBA (optimize only) |

- `gleepglorp_small.png`: Pillow `resize((512,512), Image.LANCZOS).save(optimize=True)` → **~85% reduction** (1712K → 264K). Now materially smaller than `_med`.
- `gleepglorp_med.png`: Pillow `save(optimize=True)` only → marginal reduction (1784K → 1708K, ~4%). No oxipng/pngquant available; accepted per operator decision.
- RGBA mode preserved on both. Filenames unchanged.
- `README.md` still references `gleepglorp_med.png` at `width="280"` — no broken src.
- `git status` confirms both PNGs modified in working tree.

**Verification**:
- `git ls-remote --heads origin` → `main` only (G1 already clean)
- `git branch -a` → no dangling tracking refs (G1 clean)
- Pillow `.size`: small=(512, 512), med=(1024, 1024) ✓
- `du -k`: small=264K, med=1708K (small materially < med) ✓
- `ruff check the_one/ tests/` → All checks passed! (no Python changed)

---

## Flight Director Notes

### 2026-06-04 — Flight start
- Invoked via `/agentic-workflow` for `the-one` mission 12, flight 06 (Cleanup Grab-Bag). Branched `flight/06-cleanup-grab-bag` off `main` (Flights 01–05 merged; main at 0078a37). Developer spawns pinned to `model: sonnet`.
- No open questions (N/A). Prerequisites resolved at flight start (below).
- **G1 already satisfied**: `git ls-remote --heads origin` shows NONE of the 3 target branches (`docs/acl-recon-reason-string-convention`, `flight/16-pairing-peers-dm-only`, `flight/17-daily-driver-gate`) exist on origin (only `main` remains); `fetch --prune` cleaned the stale local tracking refs. No remote-destructive push needed — Leg 4 = verify G1 + do G2.
- **G2 is real**: `gleepglorp_small.png` = 1712K vs `gleepglorp_med.png` = 1784K — "small" was never downscaled. Pillow 12.2 available in-container for re-export.
- **Cross-file coordination (Flight 05 already landed):**
  - `.env.example` already carries `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` (line 33) from Flight 05 — Leg 3 (DOC3/DOC4) must NOT re-add it; place the other tunables alongside it, and still remove the 3 dead `THE_ONE_LLM_*` (lines 3-5) + add LOG_LEVEL/DATA_DIR.
  - `agents.md` already has a "Web-session idle reaper" subsection (Flight 05). Both Leg 1 (P5 streaming anchor) and Leg 3 (DOC1 phantom-event fix + DOC5 anchors) touch `agents.md`. **Sequencing rule: Leg 1 adds the streaming-accumulator anchor (it creates the thing); Leg 3 does DOC1 + the singleton-connection anchor and does NOT re-add the streaming anchor.** Legs implement sequentially (1→2→3→4) so no file race.
- Flight `ready` → `in-flight`. Proceeding to design-review the 4 legs in parallel (read-only), then implement sequentially.

### 2026-06-04 — Leg design reviews (4× Developer agents, Sonnet, parallel) + revisions
All four approve-with-changes; corrections folded in (no new scope → no second cycles). Key deltas:
- **L1 (P5):** confirmed no test is coupled to provider internals → the no-test-change refactor IS achievable. [high] Ollama tool-call `arguments` may arrive as a **dict** (not str) — the provider edge must `json.dumps(args)` before handing a str increment to the accumulator (the accumulator is str-append-only). [med] OpenRouter overrides `_bytes_per_token_for_interim()` — instantiate the accumulator inside `stream()` with `bytes_per_token=self._bytes_per_token_for_interim()` so the override still applies. `bytes_per_token` differs per provider (OpenAI/OpenRouter 4.0, Ollama 3.5, Anthropic 3.7) → a required per-provider param, NOT a shared default; threshold 200 is shared. Helper → new `llm/_streaming.py` (acyclic: imports only from `base`). Current ranges: openai 191-261, ollama 174-250, anthropic 173-192.
- **L2 (Q4):** [high] the leg's test file `test_flow_studio_connector_account_editor.py` does NOT exist → use `test_flow_studio_connector_editor.py` + `test_flow_studio_connector_create_and_test.py` (the latter holds the 422 path). The two blocks (`handleSaveEdit` ~1523-1543, `handleCreateAndTest` ~1570-1591) differ ONLY in an **unreachable dead-code fallback** (`'Save failed'`/`'Create failed'` — `detail` is always set by the snippet branch) → helper uses a single generic `'Request failed'`. Only **2 of 13** `.ok` sites cleanly migrate; the other 11 are bespoke (silent swallows, inline-HTML errors, `err.serverStatus`) → leave them. Helper in new `static/js/api.js`, `<script>` before `connector-editor.js` in `index.html` (cooperative `window.App = window.App || {}` init). `make rebuild` before browser tests.
- **L3 (DOC):** [low] DOC1 "10s poll" is WRONG — the real mechanism is an optimistic DOM update (`msg-pending-approval-acting`) + on-200 status swap via `App.chat.applyApprovalStatus`, all in the POST handler `chat.js:322-347`; the approval list refreshes on WS `session_list`, not an interval. DOC2 actionable stale refs: `README.md:99,106,118` + `registry.py:13,141,156` (the `errors.py`/`_stub.py`/`_pool.py`/`base.py` Slack mentions are illustrative — leave). DOC4: `THE_ONE_SANDBOX_DISABLED` (needs `THE_ONE_TEST_MODE` too) and `THE_ONE_REGISTER_STUB_CONNECTOR` are test/dev-only → OMIT from operator tunables (or a clearly-marked dev seam); document the 4 real ones (session-continuation 86400, connector-pool-idle 1800, discoverable-refresh 300, mcp-pool-idle 300). DOC3 defaults: LOG_LEVEL=INFO, DATA_DIR=~/.the-one. DOC5: Leg 1 adds the streaming anchor; Leg 3 adds the **singleton aiosqlite-connection** anchor (`db/connection.py`) + DOC1 fix; don't dup. Keep the `THE_ONE_INFERENCE_*` deprecation shim (`app.py:196-207`).
- **L4 (G1/G2):** G1 already satisfied (verify only). G2: both PNGs are 1024×1024 RGBA, **unreferenced by the app** (only `README.md` shows `_med` at width=280). **Operator decision: `_small` → 512×512; `_med` → Pillow `optimize=True` (keep 1024).** Only Pillow available (no oxipng/pngquant). Verify by `du -k` + Pillow `.size`; `make rebuild` to bake.
- Proceeding to sequential implementation L1→L2→L3→L4 (`model: sonnet`).

### 2026-06-04 — Code review (Reviewer, Haiku) → confirmed
- **[HANDOFF:confirmed]** across all 4 legs. Verified: L1 zero test files modified + streaming/provider tests green (per-provider bytes_per_token preserved, OpenRouter override intact, Ollama dict-arg edge handled, acyclic `_streaming.py`); L2 helper reproduces error logic verbatim, 27 browser tests incl. the 422 path green, `.ok` 13→11, other sites untouched; L3 all DOC greps clean (phantom event gone, `.env.example` correct + session var not duplicated, deprecation shim intact); L4 G1 remote clean (no writes), G2 `_small` 512×512/264K & `_med` 1024 optimized, filenames intact. Scope clean, ruff 0. Single review cycle, no fixes.

---

## Decisions

### G2 PNG targets (operator)
**Context**: `gleepglorp_small.png`/`_med.png` are unreferenced 1024×1024 source assets; `_small` was never downscaled (the G2 bug); only Pillow available (no oxipng/pngquant).
**Decision**: `_small` → 512×512 (LANCZOS, optimize); `_med` → keep 1024×1024, `optimize=True` only (accept the marginal ~4%).
**Impact**: `_small` 1712K→264K (−85%); `_med` stays the full-res README hero. No app references change.

### G1 required no action
**Context**: The 3 stale branches the report flagged were already absent from `origin` at flight start.
**Decision**: Verify-only; no remote-destructive push. G1 criteria satisfied as-found.

---

## Deviations

### Q4 unreachable fallbacks collapsed
**Planned**: Port the two error blocks verbatim (incl. their `'Save failed'`/`'Create failed'` fallbacks).
**Actual**: Those `|| 'Save/Create failed'` fallbacks are dead code (the snippet branch always fills `detail`), so the shared helper uses one generic `'Request failed'`.
**Reason**: Behavior-equivalent (the fallbacks never fired); avoids a needless per-call parameter.

---

## Anomalies

### Full-suite `pytest tests/` wedged in the container (infra, not code)
**Observed**: At flight-end, full-suite runs (`pytest tests/`) hung indefinitely — 3 concurrent runs gridlocked ~4h on the shared SQLite DB (leftover orphans from leg work), then even a single run after a clean `docker compose restart` wedged past a 600s hard cap with no pass/fail summary (hang in collection/fixture/teardown, not caught by `--timeout` which only bounds in-test time). One orphaned run reached ~8.8h before being killed.
**Severity**: degraded (CI/verification friction) — NOT a code failure.
**Resolution**: The full-suite outcome for this flight is established WITHOUT a fresh full run: (a) the only Python change in Flight 06 is the P5 streaming refactor (Leg 1), and Leg 1's developer ran the **full suite → 2946 passed** immediately after it with zero test edits; (b) Legs 2–4 (Q4 JS, DOC docs, G2 PNG) touch no Python; (c) a clean, capped **targeted re-run of the P5 surface** (`-k "stream or provider or llm or openai or ollama or anthropic or openrouter"`) → **491 passed, 0 failed in 47.6s**; (d) Q4's 27 browser tests green; (e) ruff check 0 across the tree. Root cause is environmental (shared-SQLite container wedging under repeated SIGKILL'd/concurrent full-suite runs over a 13h+ container uptime), not the flight's changes. **Action item for debrief / routine-maintenance**: concurrent `pytest tests/` against one shared container does not isolate (shared DB/ports) and wedges for hours — needs a process fix (per-run DB isolation, a serialized test lock, or ephemeral test containers).

---

## Session Notes
