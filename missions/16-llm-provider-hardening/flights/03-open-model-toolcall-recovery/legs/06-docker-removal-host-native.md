# Leg: docker-removal-host-native

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **Added mid-flight as an operator-directed DIVERSION (2026-06-18).** Not part of the original
> #105 scope. Docker was retired for the Windows installer / host-native runtime a prior mission,
> but the deployment-Docker scaffold lingered in the repo and actively misled this flight's
> execution (the Flight Director mistook the operator's host-native Windows app on `:8484` for a
> container). The operator directed a full rip-out, folded into the flight/03 branch, done before
> the leg-05 behavior test. See flight-log Deviations.

## Objective

Remove **all deployment-Docker scaffolding** from the repo and replace each piece with its
host-native equivalent, so the dev/run workflow is correct and nothing implies the app runs in a
container. The app runs host-native via `the-one serve` (console script → `uvicorn.run(app, host,
port)`).

## Scope boundary (critical — read before touching anything)

**REMOVE (deployment Docker):**
- Files: `Dockerfile`, `docker-compose.yml`, `.dockerignore`.
- `Makefile` — the entire "Container lifecycle" section + every `docker`/`docker compose` invocation.
- `.flightops/agent-crews/leg-execution.md` — the **entire** "Run tests with…" paragraph in the
  Implement prompt, not just the `docker exec the-one pytest` token: it also carries a
  `(NOT docker compose exec — that defaults to a TTY and hangs…)` parenthetical that is irrelevant
  host-native. Rewrite the whole paragraph to the host-native run form already in use this flight.
- `README.md` — the "Docker (retired — M15 F1)" block (~:55-58) claiming `make rebuild`/`make logs`/
  `make down` "still work if you have the image." Once those targets are gone the sentence is false;
  rewrite to "Docker fully removed; the app runs host-native via `the-one serve` / `make up`" (or
  delete the block).
- Docs prose that describes the app as running in a container: `CLAUDE.md` (lines ~44–69 + the
  `make rebuild` references), `SECURITY-MODEL.md` (the `docker-compose.yml` `0.0.0.0`/bridge-network
  notes, ~:41–43, :262), `tests/HAT.md` (the `docker compose exec/ps/logs` runbook commands).
- `scripts/derive_brand_assets.py` (the `/app` default paths + `docker exec` docstring),
  `scripts/smoke_runtime_caches.sh` (the `docker compose exec`/`docker compose restart` framing +
  `/root/...` cache paths), `scripts/run-tests.sh:7` (the `docker exec` mention in the WHY comment).

**PRESERVE (do NOT touch):**
- **Tool-sandbox Docker** references — the tool-execution sandbox is a *different subsystem*. Any
  "docker" in `tests/test_platform_interpreter.py`, sandbox-isolation tests/specs
  (`tool-sandbox-*`), or `SECURITY-MODEL.md`'s sandbox section that refers to **sandboxing
  user/agent tool execution** (not app deployment) stays. When in doubt, a reference is
  deployment-Docker if it's about how *the-one itself* is served/built/run; it's sandbox-Docker if
  it's about confining *a tool the agent invokes*.
- **Historical artifacts** — everything under `missions/**` and `tests/behavior/**/runs/**` are
  snapshots of past work; rewriting them falsifies the record. Leave them. (This flight's own
  artifacts under `missions/16-.../flights/03-.../` are the live exception — they're being written now.)
- **CI-infrastructure Docker (a third category)** — `ci/**` (`ci/the-one.pipeline.yml`,
  `ci/windows-installer.pipeline.yml`, `ci/README.md`) reference `docker compose`/`docker exec`
  against the **Concourse** local substrate (e.g. `concourse-local-minio-1`), NOT the-one's
  deployment. PRESERVE — and expect the final `grep -rn docker` to surface `ci/` hits; they are
  intentional. Do not touch.
- **`tests/test_platform_interpreter.py`** (asserts an error message does *not* mention docker —
  sandbox/frozen-runtime), **`tests/test_box_isolation.py`** (a `/root`-in-sandbox comment),
  **`tests/test_mcp_cache_cleanup.py`** (`"docker"` as an arbitrary unsupported-runtime string), and
  **`tests/behavior/pty-session-containment.md`** (sandbox `cap_add`) — all sandbox/test-infra, not
  deployment. PRESERVE.

**CONVERT (deployment-flavored, but live — not historical):**
- `tests/test_input_tokens_cross_provider_live.py` — convert the `docker exec`-based **operator
  run-examples in its docstring** to host-native; **keep** the `host.docker.internal` env-overridable
  default in the resolver (that's how the test reaches the **Ollama** service, not how the-one is
  deployed — and it's `LIVE_OLLAMA_BASE_URL`-overridable).
- `tests/behavior/connector-inference-provider-config-roundtrip.md` — a `docker exec the-one git grep`
  build-verification probe (~:19); convert that single probe to its host-native equivalent. Low
  priority; if non-trivial, flag in the flight log rather than forcing it.

## Inputs

- The full Makefile (read), `the_one/main.py` (`cli_entry` → `serve` runs `uvicorn.run(app,
  settings.host, settings.port)`), `the_one/config.py` (`Settings`: `env_prefix="THE_ONE_"`,
  `host=127.0.0.1`, `port=8484`, `dev_mode=False`, `data_dir` via `platformdirs` default factory).
- The console script `.venv/bin/the-one` (`the_one.main:cli_entry`) exists.

## Outputs

- `Dockerfile`, `docker-compose.yml`, `.dockerignore` deleted.
- `Makefile` rewritten host-native (see Implementation Guidance for each target).
- `leg-execution.md` crew Implement prompt corrected.
- `CLAUDE.md`, `SECURITY-MODEL.md`, `tests/HAT.md`, `scripts/*` updated to host-native.

## Acceptance Criteria

- [x] `Dockerfile`, `docker-compose.yml`, `.dockerignore` no longer exist (`git rm`).
- [x] **No deployment-Docker invocations remain in `Makefile`** — `grep -nE "docker( |$)|docker compose|docker exec" Makefile` returns nothing. Every former container target has a host-native replacement OR is removed (see guidance).
- [x] **`make up` starts the app host-native** (background) via `the-one serve`, writes a PID file + a log file, and returns. `make down` stops it (by PID). `make restart` = down+up. `make logs` tails the host log file. These work on a clean checkout with the repo `.venv`. (Pinned `$(PY) -m the_one.main serve`.)
- [x] **`make reset-db`** deletes the host data dir (resolved from `the_one.config.settings.data_dir`, NOT a hardcoded `/root/...`), keeps the `CONFIRM=1` destructive gate, and restarts. Verified: no-CONFIRM run refuses (non-zero) and leaves the data dir intact; path resolved dynamically via `$(PY) -c "from the_one.config import settings; print(settings.data_dir)"`.
- [x] **`make verify-serving`** keeps its host curl checks but its failure message no longer says "image may be stale, run 'make rebuild'" — it points at `make logs`/`make restart`.
- [x] **`make brand-assets`** runs `$(PY) scripts/derive_brand_assets.py` host-native; the script's default source/out paths resolve **repo-relative** (`Path(__file__).resolve().parents[1]`), not `/app/...`.
- [x] **`make smoke-runtimes`** runs `bash scripts/smoke_runtime_caches.sh` host-native; the script no longer wraps in `docker compose exec` and uses host cache dirs (`${XDG_CACHE_HOME:-$HOME/.cache}/uv`, `$HOME/.local/share/pipx`, `${npm_config_cache:-$HOME/.npm}`). Intent narrowed to cache-population + host-reuse (no container-restart persistence premise) — noted in flight log + script header.
- [x] **`make shell`/`make rebuild`/`make rebuild-browsers`/`make rebuild-clean` are removed**. `make help` + the Makefile header no longer mention `rebuild`/containers; the "common workflow" hint says `make restart` (since `the-one serve` has no `--reload`).
- [x] **The crew Implement prompt** (`leg-execution.md`) no longer says `docker exec the-one pytest`; it uses the host-native form (`PYTHON=.venv/bin/python bash scripts/run-tests.sh … -x --timeout 30` / `make test-unit`).
- [x] **CLAUDE.md / SECURITY-MODEL.md / tests/HAT.md** contain no prose describing the app as running in a container; deployment instructions are host-native. `tests/HAT.md`'s `docker compose exec the-one X` commands are host-native equivalents; windowed `docker compose logs --since/--tail` gates → line-count-marker `tail -n +$MARKER` against the host log.
- [x] **Sandbox-Docker and historical artifacts are untouched** — verified via `git status` (clean for `ci/**`, sandbox tests, `missions/**`, `maintenance/**`, `runs/**`). The only "docker" left in scoped files is intentional (the kept Ollama resolver default + the kept "test suite runs host-native — no Docker" note + the smoke-script's narration of the former premise). Out-of-leg-scope deployment-flavored refs (`the_one/agents.md`, `test_llm_provider_cross_provider_history.py` docstring, the Discord behavior specs + discord_hat runbook, the audit-log-inspector probe) PRESERVED and FLAGGED in the flight log.
- [x] **`make test-unit` stays green** — 3262 passed / 18 skipped (matches baseline). `make help` renders without error.
- [x] **`make up` → `verify-serving` → `make down` round-trips** — smoked host-native on alternate port 8585 (operator's Windows app holds `:8484`): served `/api/info` + `admin.js` (200), log captured, `make down` stopped by PID + removed pidfile, post-down `:8585` dead. Recorded in flight log.

## Verification Steps

- `grep -nE "docker( |$)|docker compose|docker exec" Makefile` → empty.
- `ls Dockerfile docker-compose.yml .dockerignore 2>&1` → all "No such file".
- `make up && make verify-serving && make logs` (briefly) `&& make down` → app serves host-native then stops cleanly.
- `make reset-db` (without CONFIRM) → refuses; (with `CONFIRM=1` on a throwaway) → resolves the real data dir.
- `make test-unit` → green.
- `grep -rn "docker" CLAUDE.md SECURITY-MODEL.md tests/HAT.md scripts/derive_brand_assets.py scripts/smoke_runtime_caches.sh` → only sandbox-context references (if any) remain; no app-deployment prose.

## Implementation Guidance

0. **Migrate dev env vars out of `docker-compose.yml` BEFORE deleting it.** The compose file's
   `environment:` block (~:50-58) is where the containerized dev app got its config — it carries
   `THE_ONE_DEV_MODE=true`, `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`, and LLM defaults
   (`THE_ONE_LLM_PROVIDER=ollama`, `THE_ONE_LLM_MODEL=qwen2.5:7b`,
   `THE_ONE_LLM_BASE_URL=http://host.docker.internal:11434/v1`, `THE_ONE_HOST=0.0.0.0`). The repo's
   `.env` currently holds only API keys, so these defaults would silently vanish. The compose file
   has **no uncommitted local edits** (checked), so nothing operator-private is at risk — but the
   *dev defaults* are. Action: append the still-relevant dev vars to `.env` (which is gitignored —
   local only), **translating container-isms to host**: `host.docker.internal` → `localhost` for the
   Ollama base URL; drop `THE_ONE_HOST=0.0.0.0` (host-native should bind the `127.0.0.1` default —
   `0.0.0.0` was only to expose the container). Keep `THE_ONE_DEV_MODE=true` and
   `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`. **Surface the final `.env` additions to the operator in
   the flight log** so they know what moved (do not print key *values*, only the dev-var names).

1. **Delete** `Dockerfile`, `docker-compose.yml`, `.dockerignore` via `git rm`.

2. **Makefile — host-native rewrite.** Suggested replacements (exact phrasing is the implementer's;
   keep `.PHONY`, the `## help` comments, and the `PY` variable):
   - **`up`**: `@$(PY) -m the_one.main serve …` — but the console entry is `the-one serve`; prefer
     `.venv/bin/the-one serve` when present (fall back to `$(PY) -c "from the_one.main import
     cli_entry; …"` is ugly — better: invoke the installed script). Launch backgrounded with a PID
     + log file, e.g.:
     ```make
     THE_ONE_PIDFILE ?= .the-one.pid
     THE_ONE_LOGFILE ?= .the-one.log
     up: ## Start the-one host-native in the background
     	@if [ -f $(THE_ONE_PIDFILE) ] && kill -0 $$(cat $(THE_ONE_PIDFILE)) 2>/dev/null; then \
     		echo "already running (pid $$(cat $(THE_ONE_PIDFILE)))"; exit 0; fi
     	@nohup $(PY) -m the_one.main serve >$(THE_ONE_LOGFILE) 2>&1 & echo $$! >$(THE_ONE_PIDFILE)
     	@$(MAKE) --no-print-directory verify-serving
     ```
     **Pin `$(PY) -m the_one.main serve`** as the launch form (verified at design review:
     `main.py` reads `sys.argv[1:]` and has an `if __name__ == "__main__": cli_entry()` guard, so
     `-m the_one.main serve` yields `args[0]=="serve"` → `uvicorn.run(...)`. The `-m` form is more
     robust than `.venv/bin/the-one serve` — it doesn't depend on the console script being
     installed.) Gitignore `.the-one.pid`/`.the-one.log` (add to `.gitignore`).
   - **`down`**: kill the PID from the pidfile (`kill $$(cat …)` guarded), remove the pidfile.
   - **`restart`**: `down` then `up` (host-native; picks up source edits — there is no `--reload` in
     `the-one serve`, so a restart is how edits take effect; say so in `help`).
   - **`logs`**: `tail -f $(THE_ONE_LOGFILE)`.
   - **`reset-db`**: keep the `CONFIRM=1` gate + the destructive warning, but resolve the data dir
     dynamically and `rm -rf` it host-side, then restart:
     ```make
     reset-db:
     	@… CONFIRM gate …
     	@$(MAKE) --no-print-directory down
     	@dd=$$($(PY) -c "from the_one.config import settings; print(settings.data_dir)"); \
     	  echo "wiping $$dd"; rm -rf "$$dd"
     	@$(MAKE) --no-print-directory up
     ```
     Update the warning text (it currently says "/root/.the-one inside the container").
   - **`verify-serving`**: keep the curl loop + the static-asset checks (they hit `localhost:8484`,
     which works host-native); change the failure hint from "image may be stale, run 'make
     rebuild'" → "not serving — check `make logs` / `make restart`".
   - **`brand-assets`**: `$(PY) scripts/derive_brand_assets.py`.
   - **`smoke-runtimes`**: `bash scripts/smoke_runtime_caches.sh` (no `docker compose exec`).
   - **Remove** `shell`, `rebuild`, `rebuild-browsers`, `rebuild-clean` (no container/image).
     `rebuild-browsers` was `rebuild + _ensure-playwright`; if a "prep browsers" target is still
     wanted, alias it to `_ensure-playwright` alone. Keep `_ensure-playwright`, all `test-*`, `lint`,
     `format*`, `doctor`, `audit*` (already host-native).
   - **Header comment + `help`**: rewrite the top-of-file rationale (no Dockerfile/COPY/bake story)
     and the `help` "common workflow" block (`make rebuild` → `make restart`).

3. **`scripts/derive_brand_assets.py`**: change `DEFAULT_SOURCE`/`DEFAULT_OUT_DIR` from `/app/...`
   to repo-relative paths resolved from `__file__` (e.g. `Path(__file__).resolve().parents[1] /
   "the_one/interfaces/web/static/brand/..."`). Update the module docstring (drop the `docker exec`
   usage examples → `python scripts/derive_brand_assets.py`).

4. **`scripts/smoke_runtime_caches.sh`**: drop the `docker compose exec`/`docker compose restart`
   framing in the header; use host cache dirs (`${XDG_CACHE_HOME:-$HOME/.cache}/uv`,
   `$HOME/.local/share/pipx`, `${npm_config_cache:-$HOME/.npm}`). The "persists across container
   restart" premise becomes "caches populate + are reused on the host" — narrow the intent and note
   it in the flight log. If the script can't be meaningfully host-native without deeper rework,
   record that and reduce it to the cache-population check it can do.

5. **`scripts/run-tests.sh:7`**: update the WHY comment (the `docker exec … pytest` orphan story) to
   reflect the host-native reality (it's still a valid self-bounding wrapper; just retell why).

6. **`leg-execution.md`** Implement prompt: replace the `docker exec the-one pytest …` paragraph
   with the host-native form this flight has used throughout (`PYTHON=.venv/bin/python bash
   scripts/run-tests.sh <files> -x --timeout 30`; `make test-unit` for the suite). Keep the
   `-x --timeout` rationale.

7. **CLAUDE.md**: rewrite the container section (heading "Local dev with Docker" ~:42 through :69).
   This includes a **`make`-command block (~:48-63)** that lists `make rebuild`/`rebuild-clean`/
   `shell`/`logs` — rewrite it **target-by-target** to match the new host-native Makefile (or it
   will reference removed targets). The app runs host-native (`the-one serve` / `make up`); edits
   take effect on `make restart` (no `--reload` in the console serve). Remove the "two ways the
   container runs" / "image-baked vs compose dev path" / "make rebuild required" content (:65-67)
   and the Pydantic-under-`--reload` gotcha (:69) (reload-specific; with restart-based dev it's
   moot — or reframe as "restart to pick up class-definition edits"). Keep line ~174's
   already-correct "test suite runs host-native — no Docker" note.

8. **SECURITY-MODEL.md**: reframe the `docker-compose.yml` `0.0.0.0`/bridge-network notes (~:41–43,
   :262) — host-native binds `127.0.0.1` by default (`Settings.host`); the operator owns host
   firewalling. Do NOT touch the document's tool-**sandbox** security content.

9. **tests/HAT.md**: ~13 `docker` hits (lines ~25-29, 70, 112, 139, 150, 158, 174, 195-215, 257,
   279). Enumerate and convert each to host-native: `docker compose exec the-one X` → run `X`
   directly against the host venv/app (`which bwrap`; `docker compose exec the-one pip install …`
   (:29) → `.venv/bin/pip install …`; `… python <<'PY'` → `.venv/bin/python <<'PY'`); `docker
   compose ps` health-check (:25, :257) → `make verify-serving` / curl. **The load-bearing gates
   need care:** the `docker compose logs --since="$HAT_START"` / `--tail=` verification steps
   (:195-215, :279 — the F5 L1 "transport close failed" count gate is one of these) have **no clean
   `tail -f` equivalent** — convert them to a timestamp-filtered `grep` against the **persistent
   host log file** (the `$(THE_ONE_LOGFILE)` written by `make up`), e.g. capture `HAT_START` as a
   line marker / timestamp and `grep` the log from there. If a windowed-log gate can't be made
   reliable host-native, flag it inline in HAT.md (per the Edge Case below) rather than dropping the
   check. Preserve the HAT's intent and step structure.

## Edge Cases

- **`$(PY) -m the_one.main serve` arg passing** — verify `serve` reaches `sys.argv[1]`. If `-m`
  semantics interfere, use `.venv/bin/the-one serve`. Pin whichever works.
- **A reference that's ambiguous deployment-vs-sandbox** — default to PRESERVE and flag it in the
  flight log for the operator, rather than risk removing sandbox-security content.
- **`tests/HAT.md` commands that genuinely required the container** (e.g. inspecting
  container-only paths) — if a step has no clean host-native equivalent, note it inline in the HAT
  rather than silently dropping the check.
- **Port 8484 already in use** by the operator's Windows app during `make up` smoke — the smoke
  test of the new workflow may need an alternate `THE_ONE_PORT`; note it, don't fight the running app.

## Files Affected

- Deleted: `Dockerfile`, `docker-compose.yml`, `.dockerignore`.
- `Makefile`, `.gitignore` (add pidfile/logfile), `.env` (append migrated dev vars — local/gitignored),
  `scripts/derive_brand_assets.py`, `scripts/smoke_runtime_caches.sh`, `scripts/run-tests.sh`,
  `.flightops/agent-crews/leg-execution.md`, `CLAUDE.md`, `README.md`, `SECURITY-MODEL.md`,
  `tests/HAT.md`, `tests/test_input_tokens_cross_provider_live.py` (docstring run-examples),
  `tests/behavior/connector-inference-provider-config-roundtrip.md` (one probe).
- PRESERVED (verify untouched): `ci/**`, sandbox/test-infra docker refs, all `missions/**` +
  `tests/behavior/**/runs/**` historical artifacts.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified; `make up/verify-serving/down` round-trip smoked (on alt port 8585)
- [x] `make test-unit` green (3262/18); `make help` renders
- [x] Sandbox-Docker + historical artifacts confirmed untouched
- [x] Update flight-log.md with the leg progress entry (incl. ambiguous refs preserved + the
      smoke-runtimes intent change + migrated .env var names)
- [x] Set this leg's status to `landed` (deferred-review model — NOT committed)
- [x] Check off this leg in flight.md
- [ ] (Diversion leg — after this, resume leg 05 behavior test against the host-native app)
