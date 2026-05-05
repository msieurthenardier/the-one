# Flight Log: Debrief Follow-ups

**Flight**: [Debrief Follow-ups](flight.md)

## Summary

Flight scaffolded 2026-05-04 as Mission 06's second flight. Captures the 6 action items surfaced by Flight 01's debrief (`flights/01-pre-mission-06-quick-wins/flight-debrief.md`) as 5 atomic legs.

### Flight Director Notes

#### 2026-05-04 — Orchestration setup
- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project crew, not default fallback). Crew: Developer (Sonnet, design-review + implement + fix + commit), Reviewer (Haiku, code review), Accessibility Reviewer (Sonnet, optional — not relevant for this flight, all changes are docs/tests/middleware behavior, no UI).
- **Branch strategy**: User selected "Fresh branch off flight/01" — branched `flight/02-debrief-followups` from `flight/01-pre-mission-06-quick-wins` HEAD. Flight 1 wrap-up (mission.md checkoff, flight/01 flight.md checkoff, flight/01 flight-debrief.md) stashed as `flight-01-wrapup-deferred` (stash@{0}) to keep PR #25 untouched. Flight 2 artifacts (untracked dir) come along on new branch.
- **Starting state**: flight.md `ready` → `in-flight`. All 5 legs already drafted with status `ready`; design review still required per the methodology learning from Flight 1's debrief.
- **Crew model**: Developer = Sonnet, Reviewer = Haiku per phase file. Will not use Opus for any crew agent.

---

## Leg Progress

### 01-doc-patches
**Status**: landed

#### Design Review (round 1) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) cross-referenced leg cited line numbers and insertion points against actual `flight/02-debrief-followups` HEAD.

**Findings:**
- **[high]** `api.py:810` rationale comment ALREADY EXISTS as a 5-line block at L805-809 — shipped by Flight 01 Leg 05. Leg's premise (rationale lives only in flight log) is stale. **Resolution**: dropped the api.py change from this leg entirely; flight.md `api.py:810` checklist item marked `[x]` with annotation pointing to the existing block.
- **[medium]** No "existing FastAPI/SSRF section" or "provider/LLM-config section" in `agents.md`. **Resolution**: locked concrete insertion points — Origin allowlist subsection between L250 (end of Web tools (F5)) and L252 (SearchBackend Protocol (F5)); module-map row added at L93-98; Provider URL validation subsection at top of `## Provider type extension checklist` (after L1125 history note, before numbered list at L1127).
- **[medium]** Cited `_is_safe_provider_url` line numbers off by 1 (771→772, 810→811, 863→864). **Resolution**: corrected in leg.
- **[low]** CLAUDE.md "Security posture" at L318 (not L319); section spans L318-320 followed by `## Conventions` at L322. **Resolution**: pinned insertion location — append after L320 before L322.
- **[low]** Should cross-link `### __MASKED__ sentinel for API key updates` (L76 in agents.md). **Resolution**: cross-link added in the `_is_safe_provider_url` entry.
- **[suggestion → effectively medium]** Proposed `_is_safe_provider_url` entry overstated localhost exemption set (mentioned RFC1918 / link-local / 0.0.0.0). Actual code (api.py L662-665) only exempts `localhost` / `127.0.0.1` / `::1` / `*.localdomain`. **Resolution**: corrected leg entry to describe actual narrow exemption + added type-level skip layer (`_URL_VALIDATION_SKIPPED_TYPES = {"mock", "ollama"}`).

**Outcome**: leg revised. Round-2 review triggered (substantive changes — dropped output, locked insertion points, corrected docs-vs-code drift).

#### Design Review (round 2) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) re-verified all round-1 fixes and re-grepped insertion points.

**Round-1 resolution check** (reviewer's verdict): items 1, 2, 3, 4, 6 ✓; item 5 ✗ (cross-link target attributed to wrong file).

**New finding:**
- **[medium]** `### __MASKED__ sentinel for API key updates` heading lives in `CLAUDE.md:76`, NOT `agents.md`. Leg's Inputs and the new `Provider URL validation` entry both attributed it to `agents.md`. **Resolution (in-place, no round 3)**: corrected Inputs attribution; cross-link in the new entry now reads "in `CLAUDE.md`"; Acceptance Criteria bullet updated to name the file. Verified via `grep -rn "__MASKED__"` — only matches in `CLAUDE.md:76` (heading) and `api.py:634` / `api.py:806` (code).
- **[low cosmetic]** `_URL_VALIDATION_SKIPPED_TYPES` is `frozenset({"mock", "ollama"})` (api.py:640), not a plain set. **Resolution (in-place)**: rendered as `frozenset({"mock", "ollama"})` in the leg.

**Flight Director call**: applied both fixes in-place per reviewer's recommendation (small enough to skip round 3). Leg is implementation-ready. Within methodology max of 2 design-review cycles.

#### Implementation — 2026-05-04
**Implementer**: Developer agent (Sonnet) executed the leg per implementation guidance.

**Pre-edit re-grep verification (defense in depth):**
- `the_one/agents.md` module-map at L93-98 confirmed (`cli.py` L97, `web/app.py` L98).
- `### Web tools (F5)` at L239; transition to `### SearchBackend Protocol (F5)` at L252 confirmed.
- `## Provider type extension checklist` at L1121 with history note at L1125, numbered list at L1127 confirmed.
- `CLAUDE.md` `## Security posture` at L318, body at L320, `## Conventions` at L322 confirmed.
- `### __MASKED__ sentinel for API key updates` cross-link target at `CLAUDE.md:76` confirmed.

**Files touched:**
- `the_one/agents.md` — added `web/middleware.py` row to `the_one/interfaces/` module-map table (L99); inserted `### Origin allowlist (M06 F1 L5)` subsection between Web tools (F5) and SearchBackend Protocol (F5); inserted `### Provider URL validation (M06 F1 L5)` subsection at top of `## Provider type extension checklist` (after history note, before numbered list).
- `CLAUDE.md` — appended 2-line `**Origin allowlist override**` callout to `## Security posture` section (after L320, before `## Conventions` at L322).
- *(no `the_one/interfaces/web/api.py` change — rationale block at L805-809 already exists from F01 L05; retired during design review.)*

**Verification outcomes:**
- All 4 grep verifications pass: `OriginAllowlistMiddleware`/`Origin allowlist` (2 hits), `_is_safe_provider_url`/`Provider URL validation` (2 hits), `web/middleware.py` (2 hits), `THE_ONE_ORIGIN_ALLOWLIST` (1 hit in CLAUDE.md callout).
- `pytest -q --ignore=tests/browser --timeout=120` — 1076 passed, 1 skipped, 6 deselected in 64.58s. No regressions (purely markdown changes).
- `ruff check` + `ruff format --check` — clean (no Python files touched).

**Status**: ready → in-flight → landed.

---

### 02-edge-case-tests
**Status**: landed

#### Design Review (round 1) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) cross-referenced leg cited line numbers, fixtures, and test patterns against actual codebase.

**Findings:**
- **[high]** `test_provider` happy-path is ALREADY covered by `TestConnectionTest` (`tests/test_provider_api.py:653-768`): `test_openai_compatible_success` (L688), `test_openai_success` (L716), `test_anthropic_success` (L738) all exercise the validator-passes-through path with safe URLs. F01 debrief assessment was based on a grep that missed `TestConnectionTest`. **Resolution**: dropped the `test_provider` test from this leg; flight.md `test_provider happy-path` checklist marked `[x]` already-satisfied with annotation.
- **[high]** Wrong endpoint URL — leg cited `POST /api/providers/test`; actual is `POST /api/providers/{provider_id}/test` (`api.py:852`). **Resolution**: moot now that the test is dropped.
- **[high]** Wrong WS test client library — leg suggested `httpx_ws.aconnect_ws` / `websockets.connect`; actual file uses `starlette.testclient.TestClient` + `client.websocket_connect(...)` (no new dependency). **Resolution**: rewrote Implementation Guidance to specify `TestClient` + `_make_app(...)` helper.
- **[high]** WS test should use existing `_make_app(...)` helper (L36) with stub `/ws` echo route (L58-66), NOT the production app (`the_one/interfaces/web/app.py:740`). **Resolution**: explicit guidance added.
- **[medium]** Type-vs-URL trap — using type=`ollama` would bypass `_is_safe_provider_url` via `_URL_VALIDATION_SKIPPED_TYPES`. **Resolution**: moot now that the `test_provider` test is dropped.
- **[medium]** No `app_factory` / `provider_factory` fixtures exist — leg incorrectly cited them. **Resolution**: rewrote Inputs to reflect actual `_make_app(...)` in-file helper.
- **[medium]** WS-no-Origin test should mirror `test_websocket_with_allowed_origin_accepts` (L164-169) shape. **Resolution**: leg now includes verbatim copy-and-modify pattern.
- **[low]** Cite middleware lines 68-74 (WS branch) instead of bare L69. **Resolution**: corrected.
- **[low]** Verification grep regex pipe-escaping. **Resolution**: replaced with simpler line-number-based grep.

**Outcome**: leg revised. Round-2 review triggered (substantive changes — dropped the `test_provider` test entirely; rewrote WS test guidance from wrong library to correct pattern).

#### Design Review (round 2) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) re-verified all round-1 fixes against current source.

**Round-1 resolution check**: items 1, 3, 4, 5, 6, 7, 8 all ✓. No new findings.

**Verdict**: approve. Leg is implementation-ready.

---

### 04-host-env-dependency-clarity
**Status**: ready (post-design-review revision; rescoped from "fix gap" to "guardrail comment")

#### Design Review (round 1) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) cross-referenced cited dep-tier state against actual `pyproject.toml`.

**Findings:**
- **[high]** Premise was factually obsolete — `markdownify` and `readability-lxml` are ALREADY in base `[project.dependencies]` at `pyproject.toml:L8-9` (moved in commit `e65077e`, Flight 05 web expansion, 2026-04-30). The leg's path-(b) "deps shift" is already done.
- **[high]** `CLAUDE.md:13` already documents `pip install -e ".[all-llms,dev]"` — the leg's path-(a) "doc fix" is also already done.
- **[high]** Wrong consumer named — `WebSearchTool` (`web.py:331`) does NOT import these deps. The actual consumer is `FetchUrlTool` (`web.py:142-208`) with lazy imports at L202-203.
- **[medium]** Acceptance criterion (a)'s grep `"pip install.*\[dev\]"` already matches existing CLAUDE.md content — leg would be "complete" with zero changes. Criterion was too loose.
- **[medium]** No "if both gaps already closed" branch in Implementation Guidance.
- **[low]** `uv lock` guidance in path (b) was framing-incorrect — canonical install is `pip install` (Dockerfile L17, ci/pipeline.yml L24).

**Flight Director call**: rescoped leg from "fix the gap" to "guardrail comment in `pyproject.toml`". Path-(b) re-execution is no-op; path-(a) re-documentation is also no-op. The remaining valuable work is a 4-line `#` comment immediately above the `readability-lxml`/`markdownify` lines, explicitly attributing them to `FetchUrlTool` (with the gap-history reference) — guardrail against a future maintainer moving them back to `[dev]` and re-opening the original gap.

**Outcome**: leg revised from full-rewrite. Scope reduced from 10-15 lines of CLAUDE.md doc OR `pyproject.toml` dep movement to a single 4-line guardrail comment. Round-2 review triggered (substantive changes — entire leg purpose pivoted).

#### Design Review (round 2) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) re-verified rebased premise + scope against current source.

**Round-1 resolution check**: items 1, 2, 3, 4, 5, 6 all ✓. Two cosmetic low-severity nits (criterion bullet conflates check + remediation; example block uses `...` placeholder) — not worth a third cycle.

**Verdict**: approve. Leg is implementation-ready.

#### Implementation — 2026-05-04
**Implementer**: Developer agent (Sonnet) executed the leg per implementation guidance.

**Pre-edit re-grep verification (defense in depth):**
- `grep -nE '"(markdownify|readability)' pyproject.toml` confirmed both deps still in base `[project.dependencies]` at L8-9 (pre-edit). Concurrent flight branches did not shift them.
- `grep -nE '\bdev = ' pyproject.toml` confirmed `[dev]` at L26 still contains only test/lint tooling (pytest, pytest-asyncio, ruff, playwright, pytest-playwright, pillow, pixelmatch) — no markdownify/readability presence.
- Host env import check: `python3 -c "import markdownify, readability; print('OK')"` returned `OK` — host env is healthy, no re-bootstrap reminder needed.

**Files touched:**
- `pyproject.toml` — inserted 4-line `#` guardrail comment (L8-11) immediately above `"readability-lxml>=0.8"` (now L12; `"markdownify>=0.13"` at L13). Comment attributes both deps to `FetchUrlTool` (the_one/tools/web.py), pins them to base dependencies, and references commit `e65077e` as the gap-closer to prevent a future maintainer from moving them back to `[dev]` and re-opening the Flight 01 Leg 01 host-env gap.
- *(no `CLAUDE.md` change — install command at L13 already documents the canonical bootstrap.)*
- *(no `the_one/tools/web.py` change — `FetchUrlTool` consumer is correct as-is.)*

**Notable findings (carried forward from design review):**
- Original premise was obsolete: gap had **already been closed** by commit `e65077e` (Flight 05 web expansion, 2026-04-30) which moved both deps from `[dev]` into base `[project.dependencies]`.
- Leg pivoted to a **guardrail-comment-only scope** during design review — preserving the now-correct dep-tier state with an inline rationale to prevent regression.
- The actual consumer is **`FetchUrlTool`** (`the_one/tools/web.py:202-203`, lazy imports inside `_call`), not `WebSearchTool` as the original Flight 01 leg log incorrectly stated. `WebSearchTool` (`web.py:331`) does NOT import either dep.

**Verification outcomes:**
- `grep -B 3 -A 1 '"readability-lxml' pyproject.toml` shows the 4-line `#` comment block immediately above `readability-lxml>=0.8`, with `markdownify>=0.13` adjacent below.
- `python3 -c "import markdownify, readability; print('OK')"` — `OK` (host env healthy).
- `pytest -q --ignore=tests/browser --timeout=120` — **1077 passed, 1 skipped, 6 deselected in 56.75s**. Zero delta from Leg 03 baseline (1077) — comment-only TOML edit cannot affect test count.
- `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — clean (TOML untouched by Python tooling; no Python files modified).

**Status**: ready → in-flight → landed.

---

### 03-origin-allowlist-followups

#### Design Review (round 1) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) cross-referenced cited line numbers and structure against actual codebase.

**Findings:**
- **[medium]** `GATED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})` is a class attribute on `OriginAllowlistMiddleware` at L54 — leg's "tuple/set/frozenset at the top of the module" framing was imprecise. **Resolution**: leg now names the constant explicitly and identifies it as a class attribute.
- **[medium]** Existing `test_options_with_foreign_origin_passes` (`tests/test_origin_allowlist.py:89-96`) already asserts `OPTIONS` pass-through — locking in path (b). Leg didn't acknowledge this. **Resolution**: leg now references this test as evidence path-b is the no-op path; also notes that any future path-(a) implementer would need to update the test + class docstring.
- **[medium]** Existing rejection-path tests are 3 separate per-method tests (POST/PUT/DELETE; **PATCH coverage missing** — pre-existing gap). **Resolution**: noted in Inputs section as out-of-scope pre-existing issue; not addressed by this leg.
- **[low]** `SECURITY-MODEL.md` Future Work section heading is `## Future Work (NOT in scope today)` (L116, not bare "Future Work"). **Resolution**: leg now pins exact heading text.
- **[low]** `SECURITY-MODEL.md:30` already mentions reverse-proxy `THE_ONE_ORIGIN_ALLOWLIST` extension. **Resolution**: leg's new X-Forwarded-Host bullet now explicitly distinguishes the L30 mention ("proxy preserves Origin → use env var") from the new entry ("proxy strips Origin → see Future Work"). Edge Cases section calls this out explicitly to avoid contradiction.
- **[low]** Middleware class docstring at L34-35 lists `OPTIONS: never gated`. **Resolution**: path (b) preserves this; docstring stays. Edge Cases note added for any future path-(a) implementer.

**Path decision (Flight Director call)**: locked path (b) — document, don't gate. The decisive argument is the reviewer's suggestion: gating `OPTIONS` without simultaneously emitting `Access-Control-Allow-Origin` headers would silently break any future CORS preflight (preflight 403s, real request never fires). Without a real CORS consumer to design against, path (a) is net-negative. Path (b) is YAGNI-aligned and reversible.

**Outcome**: leg revised. Round-2 review triggered (substantive changes — locked path-b explicitly, added existing-test acknowledgment, distinguished L30 mention from new Future Work bullet, pinned exact heading).

#### Design Review (round 2) — 2026-05-04
**Reviewer**: Developer agent (Sonnet) re-verified all round-1 fixes and re-grepped insertion points.

**Round-1 resolution check**: items 1, 2, 3, 4, 5, 6, 7 all ✓. No new findings (one cosmetic nit on "one-line" wording vs 3-line comment example, internally consistent with Implementation Guidance — not worth a third cycle).

**Verdict**: approve. Leg is implementation-ready.

#### Implementation — 2026-05-04
**Implementer**: Developer agent (Sonnet) executed the leg per implementation guidance.

**Pre-edit re-grep verification (defense in depth):**
- `TestWebSocketGating` class confirmed at L149.
- `test_websocket_with_allowed_origin_accepts` at L164-169 confirmed.
- `test_websocket_with_port_wildcard_origin_accepts` at L171 confirmed.
- `TestClient` already imported at L27; `_make_app(...)` helper at L36 confirmed.

**Files touched:**
- `tests/test_origin_allowlist.py` — inserted new `test_websocket_with_no_origin_passes` method (~15 lines including docstring) inside `TestWebSocketGating` class, between `test_websocket_with_allowed_origin_accepts` and `test_websocket_with_port_wildcard_origin_accepts`. Test mirrors the allowed-origin test shape but omits the `headers=` kwarg on `client.websocket_connect("/ws")` — the absence of `Origin` exercises the middleware's pass-through branch (`if origin and not self._is_allowed(origin)` short-circuits via `_extract_origin` returning `""`).

**Traceability — `test_provider` happy-path retired:**
- The 2nd debrief item from F01 ("test_provider happy-path test") was discovered during design review of this leg to **already be satisfied** by `TestConnectionTest` (`tests/test_provider_api.py:653-768`): `test_openai_compatible_success` (L688) hits the localhost-exempt branch via `http://localhost:1234/v1`; `test_openai_success` (L716) and `test_anthropic_success` (L738) hit the scheme-https branch. All three reach the upstream-mock invocation, demonstrating the URL validator passed through. F01's "rejection-only coverage" assessment was based on a grep that missed `TestConnectionTest`. No new provider test added in this leg.

**Verification outcomes:**
- `pytest tests/test_origin_allowlist.py::TestWebSocketGating -v --timeout=30` — 4 passed in 0.24s (existing 3 + new 1).
- `pytest -q --ignore=tests/browser --timeout=120` — 1077 passed, 1 skipped, 6 deselected in 62.90s. Delta from baseline 1076 is exactly +1, no regressions.
- `ruff check tests/` + `ruff format --check tests/` — clean.

**Status**: ready → in-flight → landed.

#### Implementation (Leg 03 actual work — middleware comment + SECURITY-MODEL.md bullets) — 2026-05-04
**Implementer**: Developer agent (Sonnet) executed the leg per implementation guidance.

**Path decision rationale**: locked **path (b) — document, don't gate**. Gating `OPTIONS` without simultaneously emitting `Access-Control-Allow-Origin` headers from a dedicated CORS middleware would silently break any future CORS preflight (preflight 403s, real request never fires). Without a real CORS consumer to design against today, path (a) is net-negative. Path (b) is YAGNI-aligned, reversible, and preserved by the existing `test_options_with_foreign_origin_passes` (`tests/test_origin_allowlist.py:89-96`) which already locks in the pass-through behavior.

**Pre-edit re-grep verification (defense in depth — methodology learning from Flight 1):**
- `GATED_METHODS = ` confirmed at `the_one/interfaces/web/middleware.py:54`.
- `## Future Work (NOT in scope today)` confirmed at `SECURITY-MODEL.md:116`.
- `Multi-user form factor` (last existing bullet — insertion anchor) confirmed at `SECURITY-MODEL.md:123`.

**Files touched:**
- `the_one/interfaces/web/middleware.py` — inserted 3-line `#` comment immediately above `GATED_METHODS = ` (now L57): `# OPTIONS intentionally NOT gated — see SECURITY-MODEL.md "Future Work"` / `# (CORS / OPTIONS preflight). Gating without Access-Control-Allow-Origin` / `# headers would silently break any future preflight.` No functional change.
- `SECURITY-MODEL.md` — appended two new bullets after the `Multi-user form factor` bullet, under the `## Future Work (NOT in scope today)` heading: `**CORS / OPTIONS preflight**` (current state + future-decision criteria, do-not-wildcard guidance) and `**X-Forwarded-Host / trusted proxy**` (explicitly distinguishes the L30 reverse-proxy mention "proxy preserves Origin → use env var" from the new bullet "proxy strips Origin → operator must forward or replace middleware after validating proxy trust").
- *(no test changes — `test_options_with_foreign_origin_passes` already locks in path-b behavior; per leg spec, this leg adds no test work.)*

**Verification outcomes:**
- All 4 grep verifications pass: `GATED_METHODS = ` shows the 3-line comment immediately above; `## Future Work` still at L116; `CORS / OPTIONS preflight` bullet present with ≥2 sentences; `X-Forwarded-Host` bullet present with explicit L30 distinction.
- `pytest tests/test_origin_allowlist.py -v --timeout=60` — 19 passed in 0.31s (all baseline tests including `test_options_with_foreign_origin_passes` still green; path-b leaves behavior unchanged).
- `pytest -q --ignore=tests/browser --timeout=120` — 1077 passed, 1 skipped, 6 deselected in 59.50s. No delta from baseline (no test changes in this leg).
- `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/` — clean (3-line `#` comment block does not affect ruff).

**Status**: ready → in-flight → landed.

---

### 05-admin-pass-rotation
**Status**: landed (guided-manual leg — no autonomous Developer)

#### Execution — 2026-05-04
**Protocol**: Flight Director walked the operator through 8 steps one at a time, waiting for confirmation between each. Same protocol as Flight 01 Leg 06.

**Steps executed:**
1. Operator generated new admin password via `openssl rand -base64 30 | tr -d '/+=' | head -c 32`. Value never logged or transmitted to Flight Director. ✓
2. Operator updated `/home/cprch/projects/concourse-local/.env` `CONCOURSE_ADMIN_PASS` to new value (gitignored). ✓
3. Operator recreated `concourse-local-web` container via `docker compose up -d web`. ✓
4. Operator waited for ATC ready via `until curl -sf http://localhost:8080/api/v1/info ...`. ✓
5. Operator verified new pass authenticates via `fly -t local login -u admin -p '<NEW>'` — succeeded. ✓
6. Operator verified old pass rejected via `fly -t test-old-admin login -u admin -p 'ZTul...'` — failed with auth error as expected. ✓
7. Flight Director ran epipen audit: `grep -rE "ZTul|CONCOURSE_ADMIN_PASS|admin.*password|fly.*-u admin" /home/cprch/projects/epipen/` returned **zero matches**. epipen does not reference the admin credential in any tracked file — the admin pass is operator-direct (used only via interactive `fly login`), so no epipen-side update needed. ✓
8. Confirmed: NO git-history rewrite. Old password remains in `the-one`'s git history at `594d2c4`; rotation eliminates practical risk on this private single-dev repo with localhost-only Concourse. ✓

**Files touched:**
- `/home/cprch/projects/concourse-local/.env` — out-of-tree, gitignored, no commit possible from `the-one`'s working tree
- *(no `the-one` source files touched — this leg produces zero committed code changes)*

**Verification outcomes:**
- New admin password authenticates against local Concourse ✓
- Old admin password rejected with `oauth2: access_denied` ✓
- epipen-side audit clean (zero matches) ✓

**Notable**: this is the first leg in the flight that produces ZERO committed code changes — purely an out-of-tree credential rotation. The Flight 02 commit will not include any Leg 05-related diff; the leg's value lives entirely in the rotation outcome + this flight-log entry as the audit trail.

---

## Decisions

### mission.md checkoff deferred to post-merge
**Context**: `mission.md` does NOT have the "Flight 2: Debrief Follow-ups" entry on the `flight/02-debrief-followups` branch — that line lives in stash@{0} (`flight-01-wrapup-deferred`) along with Flight 1's checkoff and flight-debrief.md. Adding the line + checkoff in Flight 2's commit would create a merge conflict when the stash is popped on `flight/01-pre-mission-06-quick-wins`.
**Decision**: Flight 2's commit leaves `mission.md` untouched. When the operator pops the stash on flight/01 and commits Flight 1 wrap-up (adds Flight 2 line as `[ ]`), then Flight 1 merges, then Flight 2 rebases onto main, the operator can do a small follow-up commit to check off Flight 2. Or, if both PRs are squash-merged in order, the post-merge mission.md state can be cleaned up in the next maintenance pass.
**Impact**: Phase 3 step 5 ("check off flight in mission artifact") is deferred to post-merge cleanup; flight-log records the deferral as the audit trail.

---

## Deviations

(Departures from planned approach will be appended here.)

---

## Anomalies

(Unexpected issues will be appended here.)

---

## Session Notes

(Chronological notes from work sessions will be appended here.)
