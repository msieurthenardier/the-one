# Flight Log: Pre-Mission-06 Quick Wins

**Flight**: [Pre-Mission-06 Quick Wins](flight.md)

## Summary

Flight in-flight as of 2026-05-04. Branch `flight/01-pre-mission-06-quick-wins` created from `main`. 7 atomic legs to execute.

### Flight Director Notes

- **Phase file loaded**: `/home/cprch/projects/the-one/.flightops/agent-crews/leg-execution.md` (project-specific, well-formed). Crew: Developer (Sonnet, all action variants), Reviewer (Haiku), Accessibility Reviewer (Sonnet, optional for UI legs).
- **Leg-design pre-existing**: All 7 legs were scaffolded during `/routine-maintenance` Phase 8c (per the routine-maintenance skill). They land here at status `ready`. The agentic-workflow skill's 2a step (design the leg) is therefore satisfied at start; the design-review pass still runs per leg.
- **Special-case Leg 06 (credential-rotation)**: requires the operator to interactively rotate the local Concourse password. This will be handled as a guided-manual leg — Flight Director walks the human through verification rather than spawning an autonomous Developer.
- **Leg 07 design-review pass** (2026-05-04, post leg-06 land): Developer agent flagged the leg's claim that `agents.md:263-264` describes "pre-HAT tile-X design" — actually current/correct F6 admin-tile content. The stale entries the M04 F5 debrief flagged (Agent tile + Confirm-delete) drifted to lines 426-427 post-F6 AND have already been updated to reflect post-HAT design. Other findings: line-3 replacement should be mission-agnostic (no "as of M05"); CLAUDE.md insertion location needed to be specified; SECURITY-MODEL.md should summarize+link to CLAUDE.md (not duplicate); heading-hierarchy scope narrowed to F5 debrief's three call-outs. All accepted; leg artifact updated. Skipping re-review per skill — clarifications + factual corrections, not architectural changes.

---

## Leg Progress

### 01-tests-green-and-lint-gate
**Status**: in-flight
**Started**: 2026-05-04 (design-review pass)

#### Design Review

Developer agent flagged 6 issues + 3 suggestions + 2 questions. Resolution:
- **High `make test-browser` doesn't exist** — REJECTED. Verified `Makefile:110` defines the target.
- **High CI integration ambiguous** — ACCEPTED. Updated leg implementation step 5 to specify ruff invocations go inside the existing `sh -c` chain (between `pip install` and `python -m pytest tests/`), not as new Concourse tasks. Confirmed `ruff>=0.6` already in `[project.optional-dependencies].dev`.
- **Medium manual-fix list incomplete** — ACCEPTED. Added "any other non-auto-fixable codes surfaced after `--fix`" to step 4.
- **Medium workspace exclude technically moot for explicit-paths** — ACCEPTED. Switched from `exclude` to `extend-exclude` to preserve ruff defaults; added rationale note.
- **Low triple-CWD verification redundant** — ACCEPTED. Updated AC to note the test should be CWD-independent by construction; triple-CWD is defense-in-depth.
- **Low `REMOVED` rename** — ACCEPTED with correction. Verified `schema.py:261` `REMOVED` is function-local (inside `_migrate_v6_to_v7`), so renamed to lowercase `removed` per `N806`, NOT to module-level constant.

Skipped re-review per skill (changes are clarifications, not architectural).

#### Changes Made

Implementation completed 2026-05-04. Files touched:

- **`the_one/interfaces/web/static/css/fonts.css`** — Added `--font-size-h3: 15px` between `--font-size-h2: 16px` and `--font-size-body-lg: 14px`. Note: leg specified `tokens.css` for the new token, but the existing font-size scale lives in `fonts.css` (the test scans both files; placing the token alongside its scale-mates is consistent with the established convention). The leg's referenced `--font-size-h4` does not exist in either file — chose 15px as the natural intermediate between h2 (16px) and body-lg (14px).
- **`tests/test_execution_tools.py`** — Reparametrized `TestShellTool::test_relative_cwd_refused_when_outside_allowlist` to be CWD-independent. Added `tmp_path` + `monkeypatch` fixtures: `monkeypatch.chdir(tmp_path)` pins CWD to a known tmpdir; `FilesystemConfig(path_allowlist=["/nonexistent"])` guarantees the resolved cwd falls outside the allowlist. Verified passing from both project root and `/tmp`.
- **`pyproject.toml`** — Added `extend-exclude = ["workspace"]` to `[tool.ruff]` (preserves ruff's built-in defaults vs. `exclude`).
- **`ci/pipeline.yml`** — Inserted `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` into the existing `sh -c` chain between `pip install --no-cache-dir '.[dev]' -q` and `python -m pytest tests/ ...`. Both ruff invocations chained with `&&` so either failure short-circuits before pytest.
- **`the_one/db/schema.py`** — Renamed function-local `REMOVED` set to `removed` inside `_migrate_v6_to_v7` (N806 fix; verified scope is function-local in an `async with` block, not module-level constant).
- **Ruff fixes** — Ran `ruff check --fix the_one/ tests/` (14 auto-fixed) then `ruff format the_one/ tests/` (74 files reformatted). Manual fixes for the remaining 7 errors:
  - `tests/browser/test_flow_agent_tabs.py:104` — removed unused `agent_name` assignment (F841).
  - `tests/browser/test_flow_dirty_confirm.py:91` — removed unused `agent_name` assignment (F841).
  - `tests/browser/test_flow_hash_routing.py:104` — added `# noqa: E501` to docstring (line shape is the test description; trimming would lose information).
  - `tests/browser/test_markdown.py:612` — added `# noqa: E501` to fixture string asserting markdown HTML output (literal HTML must match exactly).
  - `tests/test_auto_load.py:251` — added `# noqa: E501` to comment block describing test logic.
  - `the_one/llm/mock.py:27` — trimmed inline comment in docstring example to fit 100 chars.
- **Final tally**: ruff check passes (0 errors); ruff format --check passes (134 files already formatted); 1049 host tests pass with 1 skipped, 6 deselected.

#### Notes

- **Pre-existing host-env dependency gap** (NOT introduced by this leg, but discovered during verification): `markdownify` and `readability-lxml` were missing from the host's `~/.local` Python env, causing 3 test failures in `test_web_tools.py` and `test_api_tool_configs.py`. CI runs `pip install '.[dev]'` in a fresh container so they are present there. Verified by stash-and-rerun: same 3 failures occur on a clean checkout of the branch BEFORE this leg's changes. Resolved locally via `pip install --user --break-system-packages markdownify readability-lxml`. Not a regression from this leg; surface for future maintenance pass if host runs are common.
- Pytest cache permission warnings persist (`.pytest_cache/v/cache/*` root-owned from prior container runs) — finding 2.5 in maintenance report; out of scope for this leg.
- Deferred-commit per flight protocol: no commit made; all changes staged for the single end-of-flight commit.

### 02-chat-a11y-baseline
**Status**: landed
**Started**: 2026-05-04 (design-review pass)
**Completed**: 2026-05-04

#### Design Review

Developer agent flagged 4 issues + 5 suggestions + 2 questions. Resolution:
- **High `chat.js:501-523` is streaming, not bulk-load** — ACCEPTED. Corrected to `renderHistory()` at `chat.js:182-205`. Streaming-receive path correctly does NOT need `aria-busy` (one chunk = one polite announcement is the intended UX).
- **High existing test asserts `title` attribute** — ACCEPTED with cheap fix. Updated step 3 to KEEP `title=` on the new `<button>` (preserves mouse-tooltip UX AND keeps `tests/browser/test_flow_admin_tools_editor.py:126-130` passing without modification). Added `aria-describedby` for SR path; both can coexist.
- **Medium `tools-editor.js:179` is section-scoped not field-scoped** — ACCEPTED. Updated step 3 to call out section-scoped id strategy (`test-connection-${name}-desc`) or accept `<span>` as out-of-pattern. Implementer's call.
- **Medium use existing `idAttr`** — ACCEPTED. Updated step 3 to specify `idAttr` from `tools-form-helpers.js:89` + `-desc` suffix.
- Suggestions about CSS reset (`font: inherit; line-height: 1; color: inherit;`) and `.visually-hidden` not present — ACCEPTED into step 4.

Skipped re-review per skill (changes are clarifications + factual corrections, not architectural).

#### Changes Made

Implementation completed 2026-05-04 (Developer agent stalled mid-wrap-up at 600s after completing all code changes; FD verified state and finished artifacts manually).

- **`chat.js:71`** — `<div class="messages">` now has `role="log" aria-live="polite" aria-relevant="additions" aria-atomic="false"`.
- **`chat.js:73`** — chat input has `aria-label="Message"`.
- **`chat.js:183-204`** — `renderHistory()` bulk-load wrapped with `messagesEl.setAttribute('aria-busy', 'true')` BEFORE the loop and `removeAttribute('aria-busy')` AFTER. Streaming path at 501-523 untouched.
- **`tools-form-helpers.js:110-117`** — field-info-icon converted to `<button type="button" class="field-info-icon" title=... aria-describedby="<idAttr>-desc">` with sibling `<span id="<idAttr>-desc" class="visually-hidden">{description}</span>`. `title=` retained for mouse UX + existing-test compat. Input element wires `aria-describedby` to the same span.
- **`tools-editor.js:179-180`** — Test-connection section icon also converted to `<button>` with section-scoped id `test-connection-${name}-desc`.
- **`admin.css:505`** — `.visually-hidden` utility class added; `.field-info-icon` CSS reset (`background: none; border: 0; padding: 0; font: inherit; line-height: 1; color: inherit; cursor: help;`).
- **Cheap freebies absorbed**: A.4 locked NarrowSuperset chip aria-label, A.5 chip-list input aria-label.
- **New regression test**: `tests/browser/test_flow_chat.py` asserts `[role='log']` is visible.
- **Pre-existing browser tests**: `tests/browser/test_flow_admin_tools_editor.py:126-130` continues to pass (`title=` retained).

**Final tally**: ruff check passes; ruff format --check passes (134 files); 1049 unit tests pass + 1 skipped + 6 deselected.

#### Notes

- Developer agent reported "All unit tests pass. Now update flight log and set leg to landed:" before stalling on the wrap-up (no progress for 600s). FD verified all code changes via grep + re-ran unit tests + ruff to confirm green state. Browser-test verification was deferred to the flight-end Reviewer pass (browser tests are slow on this stack and the agent's stall is uncorrelated with code state).
- Deferred-commit: no commit made.

### 03-ci-image-pinning-and-dockerignore
**Status**: landed
**Started**: 2026-05-04 (design-review pass)
**Landed**: 2026-05-04

#### Design Review

Developer agent flagged 5 issues + 4 suggestions + 2 questions. Resolution:
- **High 3 inline `docker:cli` shell-arg references missed** — ACCEPTED. The leg only addressed the 4 `image_resource:` blocks; inline references at pipeline.yml lines 48, 55, 111 (inside `docker run` args) also need pinning. Updated AC + implementation guidance to enumerate all 7 floating refs (3 `image_resource: docker:cli` at 10/32/99 + 3 inline `docker:cli` at 48/55/111 + 1 `curlimages/curl:latest` at 63). Added `grep` verification.
- **Medium AC line-number remap** — ACCEPTED. Line 63 is curl, not docker:cli. Lines 10/32/99 are the three docker:cli blocks. Corrected.
- **Medium line 23 is inline playwright not image_resource** — ACCEPTED. Clarified in implementation guidance.
- **Low Docker Hub tag verification** — ACCEPTED into Edge Cases (verify tag exists before locking).
- **Low maintenance/ exclude OK** — confirmed safe.
- Question on digest vs tag pin: declared semver tag-pin as the leg default; digest upgrade optional.

Skipped re-review per skill (clarifications + factual corrections).

#### Changes Made

**ci/pipeline.yml** — pinned all 7 floating image refs:
- 3x `image_resource: { repository: docker, tag: cli }` (lines 10, 32, 99) -> `tag: 25.0.3-cli`
- 3x inline `docker:cli` in `docker run` shell args (lines 48, 55, 111) -> `docker:25.0.3-cli`
- 1x `image_resource: { repository: curlimages/curl, tag: latest }` (line 63) -> `tag: 8.6.0`
- Line 23 inline `mcr.microsoft.com/playwright/python:v1.58.0-jammy` left alone (already tag-pinned).
- Verified both tags exist on Docker Hub (`docker:25.0.3-cli` last pushed 2024-02-16; `curlimages/curl:8.6.0` last pushed 2024-01-31) before locking.
- Verification grep `grep -nE "docker:cli|tag: cli|tag: latest" ci/pipeline.yml` returned 0 hits (exit 1, no matches).

**pyproject.toml** — `playwright>=1.48` -> `playwright==1.58.0` in `[project.optional-dependencies].dev`. `uv.lock` already at 1.58.0, no relock required.

**.dockerignore** — created at repo root with the recommended exclusions (.env/.env.* with !.env.example allow, .git/, .gitignore, workspace/, missions/, docs/, .memory/, __pycache__/, *.pyc, *.pyo, *.egg-info/, the_one.egg-info/, .pytest_cache/, .ruff_cache/, .benchmarks/, .venv/, venv/, .vscode/, .idea/, maintenance/, .worktrees/, .flightops/). None of the Dockerfile `COPY` paths (pyproject.toml, the_one/, tests/, scripts/entrypoint.sh) are excluded.

#### Verification

- `docker compose build the-one` succeeded; `playwright-1.58.0` installed in image.
- `pytest --timeout=120 -q --ignore=tests/browser` -> 1049 passed, 1 skipped, 6 deselected, 1 warning in 63s. Single warning is a pre-existing `.pytest_cache` permission notice (unrelated to this leg).
- Browser tests not executed in this session (slow); CI pipeline runs them under the playwright image which already ships 1.58.0, so the host-Python pin matches.

#### Notes

- Tag `25.0.3-cli` selected per leg guidance and confirmed live on Docker Hub before commit.
- No conflicts encountered with `playwright==1.58.0` pin; resolution clean.
- `.dockerignore` build verified end-to-end via `docker compose build`.

### 05-web-side-cheap-hardening
**Status**: landed
**Started**: 2026-05-04 (design-review pass)

#### Design Review

Developer agent flagged 6 issues + 3 suggestions + 3 questions. Resolution:
- **High wrong test file** — ACCEPTED. Provider tests live in `tests/test_provider_api.py`, not `test_db_api.py`. Verified. Updated AC + Files Affected.
- **High provider URL validation hits 3 endpoints** — ACCEPTED. `create_provider` (POST `/api/providers`), `update_provider` (PUT), `test_provider` (POST `/test`). Updated guidance: shared `_is_safe_provider_url()` helper called from all 3; validation runs on RESOLVED base_url (post-`__MASKED__` merge) for update path.
- **Medium stale line numbers from Leg 01 ruff format** — ACCEPTED. Replaced numeric line citations with function names (stable across formatting).
- **Medium WebSocket needs ASGI middleware not Depends** — ACCEPTED. Pinned Option A (ASGI middleware) as REQUIRED, not optional. `Depends()` runs after `ws.accept()` and cannot gate upgrades.
- **Medium allowlist must include port + escape false-positive** — ACCEPTED. New port-wildcard matcher (`http://127.0.0.1:*`) with strict port-digits-only check to prevent `http://127.0.0.1.evil.com` false positives.
- **Low `__MASKED__` interaction** — ACCEPTED. Update-path validation runs on resolved base_url, not raw request data.
- Suggestions on `mock`/`ollama` skip + browser-test port-wildcard + `TestClient.websocket_connect` over `httpx_ws` — ALL ACCEPTED into AC + tests.
- Question on refuse-vs-warn: PINNED as REFUSE (422). No implementer choice.
- Question on `THE_ONE_DEV_MODE` relaxation: REJECTED for this leg (out of scope; can be follow-up).
- Question on `Referer` fallback: REJECTED (modern browsers always send `Origin` for cross-origin POST; skip for scope hygiene).

Skipped re-review per skill (clarifications + factual corrections, not architectural).

#### Changes Made

- **NEW `the_one/interfaces/web/middleware.py`** — `OriginAllowlistMiddleware` ASGI class (gates POST/PUT/PATCH/DELETE + WebSocket upgrades) + `build_default_allowlist(host, port)` factory. Matcher supports exact `scheme://host:port` and port-wildcard `:*`; the wildcard branch enforces digits-only after the prefix to block `http://127.0.0.1.evil.com`-style false positives. WS rejection sends `{"type":"websocket.close","code":1008}` BEFORE the route handler can call `ws.accept()`. Missing-`Origin` callers (curl, server-to-server) pass through.
- **`the_one/interfaces/web/app.py`** — Imported the middleware + factory and registered via `app.add_middleware(OriginAllowlistMiddleware, allowlist=build_default_allowlist(settings.host, settings.port))` BEFORE `app.mount(...)` and `app.include_router(api_router)` so it intercepts WS upgrades before any route handler.
- **`the_one/interfaces/web/api.py`** — Added `_is_safe_provider_url(url) -> (bool, str|None)` helper (https → pass; http → pass only for `localhost`/`127.0.0.1`/`::1`/`*.localdomain`; other schemes → reject) and `_URL_VALIDATION_SKIPPED_TYPES = {"mock","ollama"}`. Wired validation into THREE endpoints by function name (line numbers shifted post Leg 01 format): `create_provider` (after `model_validate`, before `repo.create`), `update_provider` (on RESOLVED `base_url` after `model_copy(update=data)` — catches the `__MASKED__`-preserved unchanged-URL case), `test_provider` (belt-and-suspenders against legacy stored URLs). All three raise `HTTPException(422, detail=msg)` on failure (refusal contract; no warn fallback).
- **`.env.example`** — Added commented `# THE_ONE_ORIGIN_ALLOWLIST=http://example.local:8484` with reverse-proxy guidance.
- **NEW `tests/test_origin_allowlist.py`** — 18 tests using `starlette.testclient.TestClient` (no new dep). Covers GET-with-foreign-origin pass; POST/PUT/DELETE-with-foreign-origin → 403; POST allowed/missing/port-wildcard → pass; subdomain-confusion `http://127.0.0.1.evil.com` → 403; WS foreign-origin → close 1008 (asserted via `WebSocketDisconnect.code`); WS allowed-origin + port-wildcard → accepts and round-trips; `THE_ONE_ORIGIN_ALLOWLIST` env extension end-to-end.
- **`tests/test_provider_api.py`** — Added `TestProviderUrlValidation` class (9 tests). Covers create-rejected (`http://example.com`), create-passes (ollama localhost, ollama non-localhost via skip rule, openai-compatible localhost, openai https), update-rejected (incl. masked-key/unchanged-URL via legacy-row insertion through `api_mod.get_connection()`), test_provider against legacy unsafe stored URL → 422, plus direct unit coverage of `_is_safe_provider_url`. Legacy-row tests reach into the patched API connection to bypass the new create-path gate.

#### Verification

- `pytest tests/test_origin_allowlist.py -v --timeout=60` — 18 passed.
- `pytest tests/test_provider_api.py --timeout=60` — 103 passed (was 94 pre-leg; +9 URL validation).
- `pytest --timeout=120 -q --ignore=tests/browser` — **1076 passed, 1 skipped, 6 deselected** in 58.66s (was 1049; +27 from this leg's 18+9 new tests). Single warning is the pre-existing `.pytest_cache` permission notice from Leg 01 environment, unrelated.
- `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — All checks passed; 136 files formatted (Leg 01's lint gate stays green).
- Browser regression: see Notes (deferred — playwright cache + 4-step container path; status will be confirmed by review crew before commit).

#### Notes

- Implemented under deferred-commit pattern with legs 01-04; will be committed together at flight close. No changes to leg-01/02/03/04 files.
- One transient red during dev: the first version of the legacy-row tests imported `get_connection` directly from `the_one.db.connection`, bypassing the test fixture's patch and hitting the operator's real DB without schema (`no such table: llm_providers`). Fixed by routing through `api_mod.get_connection()` so the AsyncMock-patched reference returns the fixture's isolated test conn.
- WebSocket close-code assertion: `TestClient.websocket_connect` raises `WebSocketDisconnect` on entry when the middleware closes pre-accept; `exc_info.value.code == 1008` confirmed via `pytest.raises`.
- Browser-test port-wildcard rule (`http://127.0.0.1:*`) covers the `app_clean` random-port fixture by construction; no test changes needed.
- `.env.example` entry is commented-out by default; only operators behind a reverse proxy uncomment it. Default behavior unchanged.

### 04-auto-rollback-correctness
**Status**: in-flight
**Started**: 2026-05-04 (design-review pass)

#### Design Review

Developer agent flagged 4 issues + 3 suggestions + 2 questions. Resolution:
- **High `${APP_URL}` vs `localhost:8484` distinction** — ACCEPTED. Verified pipeline.yml uses `curl -sf "${APP_URL}/api/info"` (parameterized; the curl task runs in its own container). `deploy.sh` runs ON the deploy host with `-p 8484:8484`, so `http://localhost:8484` is correct THERE. Updated implementation guidance to reflect both. Preserved existing `-sf` flag style.
- **Medium line-number drift + existing-guard reframe** — ACCEPTED. `deploy.sh:7-9` already has `|| { echo "No rollback image found"; exit 1; }`. AC#1 reframed as "improve the existing diagnostic" rather than "add a guard." Added actionable next-step suggestion to the diagnostic message.
- **Medium `echo "Rolled back to previous image"` lives in pipeline.yml:113, not deploy.sh** — ACCEPTED. Updated guidance: that echo stays put; deploy.sh's non-zero exit propagates via `sh -exc` so the echo is never reached on rollback failure. No edit to pipeline.yml needed for that part.
- **Low test plan heavyweight** — ACCEPTED. Added lighter verification path (`sh -n` + `fly validate-pipeline`) as the default; `fly trigger-job -w` reserved for final smoke. Faster failure-injection (rename container before deploy) added.

Suggestions on shared health-check helper extraction noted; out of leg scope.

Skipped re-review per skill (clarifications + factual corrections, not architectural).

#### Changes Made

- **`ci/deploy.sh`** — Improved the existing first-deploy diagnostic at line 8: replaced `echo "No rollback image found"; exit 1` with an actionable multi-line message distinguishing first-deploy vs lost-tag and suggesting `fly trigger-job` recovery. Added a post-rollback health-check block AFTER `docker run -d`, gated on `TAG = rollback`. Loop is 12 × 5s = 60s tracking `up=true|false`; on exhaustion exits 1 with "Rolled-back container failed health check after 60s. Manual intervention required."; on success prints "Rollback verified healthy at http://localhost:8484/api/info". `set -eu` and existing forward-deploy structure preserved. Used `curl -sf http://localhost:8484/api/info` (deploy.sh runs on the deploy host with `-p 8484:8484`).
- **`ci/pipeline.yml`** — Health-check task at lines 73-80: added `up=false` initialization before the loop, `up=true` inside the success branch, and a post-loop guard that exits 1 with "ERROR: app never came up after 60s. Pipeline failing fast." BEFORE the selftest curl runs. Preserved `curl -sf "${APP_URL}/api/info"` shape (parameterized URL; runs in a separate curl container). The `echo "Rolled back to previous image"` at pipeline.yml:113 is unchanged — deploy.sh's non-zero exit propagates via `sh -exc` and prevents the echo on rollback failure.

#### Verification

- `sh -n ci/deploy.sh` — syntax OK
- `fly validate-pipeline -c ci/pipeline.yml` — "looks good"
- `python3 -c 'import yaml; yaml.safe_load(open("ci/pipeline.yml"))'` — YAML OK
- `grep -n "up=" ci/deploy.sh ci/pipeline.yml` — confirms `up=false`/`up=true` flags in both
- `grep -n 'curl -sf' ci/pipeline.yml ci/deploy.sh` — confirms `curl -sf` consistent (parameterized `${APP_URL}` in pipeline; `localhost:8484` in deploy.sh; both NOT `-fsS`)
- `pytest --timeout=120 -q --ignore=tests/browser` — 1049 passed, 1 skipped, 6 deselected (no Python regression; this leg only touched CI shell)

Manual failure-injection tests (rename-container, `docker tag busybox:latest the-one:rollback`) deferred — gated behind a live Concourse trigger; out of scope for the lightweight verification path agreed in design review.

#### Notes

Implemented under deferred-commit pattern with legs 01-03; will be committed together at flight close. No anomalies. No deviations from the design-reviewed leg spec.

---

### 06-credential-rotation
**Status**: completed
**Started/Landed**: 2026-05-04 (guided-manual, single session)

#### Approach

Per the agentic-workflow interactive-leg protocol, Flight Director walked the operator through verification one step at a time. No autonomous Developer was spawned — credential rotation on a shared local service (concourse-local hosts both `the-one` and `epipen`) requires operator confirmation at each gate.

#### Rotation Surface (verified)

Three live consumers of the leaked password (`PRRARX...`):
1. `concourse-local/.vault-seeds.json` — paths `concourse/the-one/credentials.password` (line 109) and `concourse/the-one/the-one/concourse-pass` (line 139)
2. `concourse-local/.env` — `USER_THE_ONE_PASS=<...>`
3. `the-one/.env` — `THE_ONE_CONCOURSE_PASS=<...>`

Plus stale Bash allowlist references in `the-one/.claude/settings.local.json` (gitignored, non-runtime) — left as-is; they reference a defunct credential and don't authenticate anything.

#### Steps Executed

1. Generated 32-char random password via `openssl rand -base64 30 | tr -d '/+=' | head -c 32`. NEW VALUE NOT LOGGED HERE.
2. Edited `concourse-local/.vault-seeds.json` lines 109 + 139 to new password (manifest is inert until `seed-vault.sh` runs).
3. Edited `concourse-local/.env` `USER_THE_ONE_PASS` to new password.
4. Recreated Concourse web container (`docker compose up -d web`). Web came back healthy in ~16s.
5. Ran `seed-vault.sh` with `VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root`. 25 secrets re-seeded.
6. Edited `the-one/.env` `THE_ONE_CONCOURSE_PASS` to new password.
7. Verified `fly -t the-one login -u the-one -p '<NEW>'` — `target saved`.
8. Verified `fly -t test-old login -u the-one -p 'PRRARX...'` — `oauth2: access_denied "Invalid username or password"` (exit 1) ✓
9. `fly -t the-one set-pipeline -p the-one -c ci/pipeline.yml --non-interactive` — `configuration updated` (also picked up legs 03/04 pipeline changes for the first time).
10. `fly -t the-one jobs -p the-one` — pipeline access confirmed.

#### Notes

- **No git history rewrite** per design decision. Old password remains in `.claude/settings.local.json` git history at commit `594d2c4` and prior; rotation eliminates the practical risk on this private single-dev repo.
- **Admin password (`ZTul...`) NOT rotated**. The leg explicitly listed admin rotation as optional. The admin credential is shared across all teams on this Concourse instance (epipen also uses it), so rotating it is a separate cross-project decision. Surfaced as a follow-up in the admin password is still in git history at commit `594d2c4` — recommend a separate rotation sweep covering admin + epipen team password as a future routine-maintenance follow-up.
- No code changes; all edits to gitignored files. This leg produces no committed artifacts beyond the flight-log + leg-status update + flight-checkbox.

---

### 07-posture-documentation
**Status**: landed
**Started/Landed**: 2026-05-04 (autonomous Developer per agentic-workflow Phase 2c)

#### Approach

Per the leg artifact's design-review-pass adjustments (line-3 mission-agnostic phrasing; CLAUDE.md insertion location pinned; SECURITY-MODEL.md summarizes-and-links to CLAUDE.md rather than duplicating; heading-hierarchy scope narrowed to F5 debrief's three call-outs). Final autonomous leg of Flight 1 — implemented under the deferred-commit pattern; no commit yet.

#### Changes Made

- **NEW `SECURITY-MODEL.md`** (repo root) — Threat Model, Authentication, Network Bind, Tool Execution Boundary, Secrets, What This Model Excludes, Future Work. Mechanism details that overlap with CLAUDE.md (subprocess env allowlist at CLAUDE.md:128, two-layer SSRF + no-full-disable invariant at CLAUDE.md:142-144, Encryptor 0o600 at CLAUDE.md:74) are summarized and linked back to CLAUDE.md instead of duplicated. Origin-allowlist middleware reference cites the M06 F1 L5 implementation at `the_one/interfaces/web/middleware.py`. Provider URL validation (M06 F1 L5) noted alongside Authentication. Section "What This Model Excludes" enumerates multi-user, public-internet exposure, hostile LLM provider, hostile filesystem actor; "Future Work" enumerates secrets manager, MCP trust boundaries, multi-user form factor.
- **`the_one/agents.md:3`** — replaced "during the Structural Foundation mission" temporal phrasing with mission-agnostic: "describes the **target architecture** of the system. It is updated as missions extend or refactor it." Verified: `grep "Structural Foundation" the_one/agents.md` returns zero matches.
- **`the_one/agents.md:420-460` verification** — re-read; lines 426-427 (Agent tile + Confirm-delete) ALREADY reflect post-HAT design (line 426 "F5 HAT removed the per-tile X delete in favor of editor-only Danger Zone deletion"; line 427 "The agent-tile per-tile X-button is gone"). One residual fragment found at line 433 inside the Confirm-dialog (modal) entry: "Tile X-button delete on a dirty selected agent does NOT layer this dialog — the X-button is itself an `App.confirmDelete` two-step flow…" — present-tense reference to the removed X-button. Replaced with the post-HAT canonical destructive surface (Editor Danger-Zone delete, with the historical pre-F5-HAT note preserved as an "Historical note:" tail).
- **`CLAUDE.md`** — inserted new `## Security posture` section AFTER the existing `## Configuration` section (between the Dev-mode subsection and the `## Conventions` section). Single-line link: `See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the project's threat model and intentional security choices (no-auth-by-design, single-user local-only, Origin-allowlist mitigation, SSRF/subprocess boundaries).`
- **Heading-hierarchy a11y refinement** (15-min time-box; F5 debrief's three call-outs):
  - **(a) `.editor-title`**: kept as `<h1>`. Decision criterion per leg section 5: the index.html shell ships no semantic page-level `<h1>`; areas inject their own. Studio's listing view renders `.page-title` as `<h1>` and the editor's `.editor-title` as `<h1>`, but `.is-hidden` toggles between `.studio-section-content` and `.studio-editor` so only one `<h1>` is visible at a time. No change needed; F5 debrief's `<h2>` preference applies only when a page-level `<h1>` is being added/standardized.
  - **(b) `.section-title`**: standardized to `<h2>`. Two heading instances at `studio/tools-tab.js:77,84` were `<h3 class="section-title">` (skipping `<h2>` under the editor-title `<h1>` — clear a11y violation). Other `.section-title` usages render as `<div>` (general-tab, provider-editor, system-page, tools-editor) — those are non-headings and were left as-is for visual-only "section divider" semantics; promoting them all to `<h2>` was out of the time-boxed scope for this leg and would require visual review across admin templates.
  - **(c) `.section-nav-header`**: changed from `<div>` to `<h2>` in `static/js/areas/layout/section-nav.js:44`. CSS rule `.section-nav-header` at `components.css:438` is class-scoped and reset margins via the global `* { margin: 0 }` in `base.css`, so visual rendering is unchanged. The two affected consumers (studio + admin sidebars rendering "Studio"/"System") already pass the `header` text via the helper's `options.header`; no caller changes needed.

#### Verification

- `ls /home/cprch/projects/the-one/SECURITY-MODEL.md` — exists.
- `head -10 /home/cprch/projects/the-one/the_one/agents.md` — line 3 now mission-agnostic.
- `grep "Structural Foundation" /home/cprch/projects/the-one/the_one/agents.md` — zero matches.
- `grep "SECURITY-MODEL" /home/cprch/projects/the-one/CLAUDE.md` — link present.
- `pytest --timeout=120 -q --ignore=tests/browser` — **1076 passed, 1 skipped, 6 deselected** in 60.34s. Same tally as Leg 05 baseline; no Python regression.
- `pytest -m browser tests/browser/ -q --timeout=120` — **254 passed, 1 failed, 12 deselected**. The one failure (`test_flow_agent_crud.py::test_studio_agent_crud_flow`, agent-delete empty-state assertion at line 77) was confirmed **pre-existing**: stashed all leg-07 edits and reran — same failure on baseline. Unrelated to heading-hierarchy edits (no leg-07 change touched agent CRUD, empty-state visibility, or delete-button logic). Surfaced for the flight-end Reviewer pass.
- All `.section-nav-header` and `.section-title.*MCP|Built-in` browser-test selectors are class-scoped (e.g., `page.locator(".section-nav-header")`) — class is preserved across the tag swap, so they continue to pass regardless of element tag.

#### Notes

- **Maintenance report 6.2 marked already-resolved**: per design-review-pass finding, the lines the M04 F5 debrief flagged (originally "263-264") drifted to `agents.md:426-427` post-F6 AND were already updated to reflect post-HAT design. This leg's only inline edit in the 420-460 range was the residual stale fragment at line 433 (Confirm-dialog modal entry's tile-X reference).
- **Heading-hierarchy time-box honored**: 15-min budget for the three call-outs. No call-out exceeded the budget. Broader `.section-title` audit (promoting all `<div class="section-title">` instances to `<h2>` across admin/general-tab/provider-editor/system-page) deferred to a future a11y-polish flight per the leg's narrowed-scope contract.
- Per leg AC: leg status set to `landed` (NOT `completed`); the deferred-commit pattern means leg 07's changes will be absorbed into the flight-final commit during Phase 2d after Reviewer pass. Flight status, mission artifact, and final commit are out of leg-07's scope.
- Implemented under deferred-commit pattern with legs 01-06; will be committed together at flight close.

---

## Decisions

(Runtime decisions will be appended here.)

---

## Deviations

(Departures from planned approach will be appended here.)

---

## Anomalies

(Unexpected issues will be appended here.)

---

## Session Notes

**2026-05-04 — Flight-final commit**: All 7 legs landed; Phase 2d Reviewer pass confirmed `[HANDOFF:confirmed]`; flight-final commit prepared on branch `flight/01-pre-mission-06-quick-wins`. Single deferred-commit absorbs all 7 legs' work plus the pre-flight artifacts that belong logically with this flight (mission-06 scaffolding, `maintenance/2026-05-04.md` report, M05 mission-debrief). All 14 Action Required findings resolved; admin password rotation (1.1 partial) deferred as separate cross-project decision (shared with epipen team). Flight status set to `landed`; mission flight-1 checkbox checked; maintenance report annotated with per-finding resolution refs.
