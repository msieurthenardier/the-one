# Leg: connector-observability-and-reaper

**Status**: landed
**Flight**: [Live-Traffic HAT Capability](../flight.md)

## Objective

Make `the_one.*` application logs (especially `the_one.connectors.*` connect/READY/`tree.sync`/ACL/dispatch lines) visible in `docker logs` by attaching a stdout handler to the `the_one` namespace logger at app startup, and add `tini` as PID 1 in the Dockerfile to reap orphaned test-runner zombies — the two diagnostic/container-startup fold-ins that must land before the live-traffic HAT legs.

## Context

- **Why now:** F14 named the absence of connector logging in `docker logs` "the single largest diagnostic impediment of the flight" — diagnosing Bug F required a standalone in-container `tree.sync` probe because the connect/READY/Forbidden lines were invisible. The live-traffic HAT legs (L4–L7) are expected to surface latent bugs (F14 precedent: 3); they must be diagnosable from logs.
- **Current state (verified at design time):** there is NO central logging configuration anywhere in `the_one/` or `scripts/` (no `basicConfig`/`dictConfig`/`StreamHandler`). The app relies on uvicorn's default root-logger threshold (WARNING), so `the_one.*` INFO logs are dropped. The codebase works around this by logging operational lines at WARNING purely for visibility — the "uvicorn-root-logger-threshold precedent" documented at `the_one/interfaces/web/api.py:55-60` and `the_one/mcp/cache_cleanup.py:294`. This leg removes the need for that abuse going forward (existing WARNING-abuse sites are NOT refactored here — out of scope).
- **Launch paths (both must be covered):** production runs `the-one serve` → `uvicorn.run(app, …)` (`the_one/main.py:21`); the dev container OVERRIDES the CMD with a direct `uvicorn the_one.interfaces.web.app:app --reload …` (`docker-compose.yml:16-21`). The only code that runs in BOTH paths is the FastAPI app's `lifespan` (`the_one/interfaces/web/app.py:82`). Logging setup must live there, not in `main.py`.
- **tini (verified):** `Dockerfile:37` `ENTRYPOINT ["/entrypoint.sh"]` → `scripts/entrypoint.sh` does `exec "$@"`, so the CMD process (`the-one serve` or the overridden uvicorn) becomes PID 1 — no init/reaper. F14 observed ~85 `<defunct>` zombie pairs after a browser-test run (the `scripts/run-tests.sh` group-kill reparents children to PID 1, which doesn't reap).

## Inputs

- `the_one/config.py` — `Settings(BaseSettings)` with `env_prefix="THE_ONE_"` (`config.py:8-9`); fields `host`, `port`, `dev_mode`, `data_dir`.
- `the_one/interfaces/web/app.py` — `lifespan` async context manager (`app.py:82-83`); its first statement today is `await init_db()` (`app.py:85`); module logger `logger = logging.getLogger(__name__)` (`app.py:74`); `import logging` already present (`app.py:6`); `from the_one.config import settings` already imported at module level (`app.py:39`) — reuse it, no new import. (A dev-mode-gated `logger.info(...)` StubPlugin-seam line also exists deeper in lifespan, `app.py:119-122`, gated by `settings.dev_mode AND THE_ONE_REGISTER_STUB_CONNECTOR==1` — it becomes visible too when that seam is active, but it is NOT an unconditional startup line; the deterministic startup line this leg adds is the reliable verification target.)
- `Dockerfile` — apt install block (`Dockerfile:6-14`), `ENTRYPOINT` (`Dockerfile:37`).
- `scripts/entrypoint.sh` — `exec "$@"` (unchanged by this leg).

## Outputs

- `the_one/config.py` — new `log_level: str = "INFO"` field (env `THE_ONE_LOG_LEVEL`).
- `the_one/logging_config.py` — NEW module with `configure_logging()`.
- `the_one/interfaces/web/app.py` — `lifespan` calls `configure_logging()` first; emits a deterministic INFO startup line.
- `Dockerfile` — `tini` in the apt install list; `ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]`.
- `tests/test_logging_config.py` — NEW unit test (handler attach, level, idempotency, namespace isolation).

## Acceptance Criteria

- [ ] `the_one/config.py` `Settings` gains `log_level: str = "INFO"` (read from `THE_ONE_LOG_LEVEL` via the existing `env_prefix`).
- [ ] `the_one/logging_config.py` defines `configure_logging() -> None` that: (a) resolves the `the_one` namespace logger (`logging.getLogger("the_one")`); (b) sets its level to `settings.log_level` (case-insensitive; invalid value falls back to `INFO` without raising); (c) attaches exactly ONE `logging.StreamHandler` writing to `sys.stdout` with a readable formatter (level + logger name + message, with timestamp); (d) LEAVES `propagate` at its default (`True`) — see Edge Cases; (e) is IDEMPOTENT — calling it more than once never attaches a second handler (guard via a sentinel attribute on the handler or logger).
- [ ] `the_one/interfaces/web/app.py` `lifespan` calls `configure_logging()` as its FIRST statement (before `await init_db()`), then emits one deterministic INFO line through the module logger (e.g. `logger.info("the-one starting; log_level=%s", settings.log_level)`).
- [ ] `configure_logging()` touches ONLY the `the_one` namespace logger — uvicorn's own loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`) and the root logger are left untouched.
- [ ] `tests/test_logging_config.py` passes and asserts: handler is attached at the configured level; a second `configure_logging()` call does not duplicate the handler; `the_one` logger `propagate` is left True (default); the root logger and `uvicorn` loggers are unmodified; AND a regression assertion that after `configure_logging()` runs, a `the_one.*` WARNING is STILL visible to pytest `caplog` (pins the propagation contract the `test_lifespan.py` deprecation-warning tests depend on).
- [ ] After `make rebuild` + container up: `docker exec the-one cat /proc/1/comm` returns `tini`.
- [ ] After container up: `docker logs the-one 2>&1` contains the deterministic `the-one starting; log_level=INFO` INFO line (proving `the_one.*` INFO now reaches `docker logs` without WARNING-abuse).
- [ ] Full backend suite green with `-x --timeout 30` (no regression; the `THE_ONE_REGISTER_STUB_CONNECTOR` dev-mode seam still registers and its lifespan `logger.info` line still fires).

## Verification Steps

- `docker exec the-one pytest tests/test_logging_config.py -x --timeout 30 -q` — new unit test passes.
- `grep -n "log_level" the_one/config.py` — field present.
- `grep -n "configure_logging" the_one/interfaces/web/app.py` — called in lifespan; confirm it's the first statement inside the `async with`/try body via reading `app.py:82-90`.
- `make rebuild` (rebuilds the image with tini) then bring the stack up.
- `docker exec the-one cat /proc/1/comm` → `tini`.
- `docker logs the-one 2>&1 | grep "the-one starting"` → shows the INFO startup line.
- `docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap' -x --timeout 30 -q` — full backend suite green.

## Implementation Guidance

1. **Add the `log_level` setting** (`the_one/config.py`)
   - After the `port: int = 8484` line, add a `# Logging` group with `log_level: str = "INFO"`. It rides the existing `env_prefix="THE_ONE_"`, so `THE_ONE_LOG_LEVEL` populates it. No validator needed (the resolver in step 2 tolerates bad values).

2. **Create `the_one/logging_config.py`**
   ```python
   from __future__ import annotations

   import logging
   import sys

   from the_one.config import settings

   _HANDLER_SENTINEL = "_the_one_stdout_handler"

   def configure_logging() -> None:
       """Attach a single stdout handler to the ``the_one`` namespace logger.

       Idempotent and namespace-scoped: only ``logging.getLogger("the_one")``
       is touched, so uvicorn's own loggers and the root logger are left as
       uvicorn configured them. Propagation is left at the default (True):
       uvicorn installs handlers only on the ``uvicorn*`` loggers, not root,
       so no standing root handler double-emits the_one records (lastResort
       is suppressed once our handler handles), while propagation keeps
       the_one.* records visible to pytest caplog. Call once at startup.
       """
       logger = logging.getLogger("the_one")
       level_name = str(settings.log_level).upper()
       logger.setLevel(getattr(logging, level_name, logging.INFO))
       # propagate is LEFT at its default (True) — see Edge Cases. Our
       # handler on ``the_one`` emits each record once (Python's lastResort
       # is suppressed once any handler handles), and propagation keeps
       # the_one.* records visible to pytest caplog (root-attached).
       if any(getattr(h, _HANDLER_SENTINEL, False) for h in logger.handlers):
           return  # already configured (re-import under --reload, repeated lifespan)
       handler = logging.StreamHandler(sys.stdout)
       setattr(handler, _HANDLER_SENTINEL, True)
       handler.setFormatter(
           logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
       )
       logger.addHandler(handler)
   ```
   - The sentinel-attribute guard (not a module-level bool) survives module re-import under `uvicorn --reload`.

3. **Call it from `lifespan`** (`the_one/interfaces/web/app.py:82`)
   - As the FIRST statement inside `lifespan`, before `await init_db()`:
     ```python
     from the_one.logging_config import configure_logging
     configure_logging()
     logger.info("the-one starting; log_level=%s", settings.log_level)
     ```
   - Import `settings` if not already in scope (it is referenced later in lifespan, so it's imported at module level — reuse it).

4. **Dockerfile: add tini + make it PID 1**
   - Add `tini \` to the `apt-get install -y --no-install-recommends` list (`Dockerfile:6-14`) — Debian's package installs the binary at `/usr/bin/tini`.
   - Change `ENTRYPOINT ["/entrypoint.sh"]` → `ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]`. `entrypoint.sh`'s `exec "$@"` is unchanged; tini stays PID 1 and reaps reparented zombies. The docker-compose `command:` override only replaces the CMD, so the dev container inherits tini-as-PID-1 too.

5. **Write `tests/test_logging_config.py`**
   - Test 1: call `configure_logging()`; assert `logging.getLogger("the_one")` has a handler with the sentinel attr, level == INFO (default), and `propagate is True` (unchanged default).
   - Test 2: capture `len(handlers)`, call `configure_logging()` again, assert count unchanged (idempotency).
   - Test 3: assert `logging.getLogger().handlers` (root) and `logging.getLogger("uvicorn").propagate` are not mutated by the call.
   - Test 4 (regression — pins the `test_lifespan.py` contract): after `configure_logging()`, emit a WARNING on a `the_one.*` child logger inside `caplog.at_level(logging.WARNING, logger="the_one...")` and assert the record IS captured (proves propagation to root/caplog survives).
   - Test 5 (optional): assert the level resolver handles a bogus value (`settings.log_level = "NOPE"` → falls back to INFO without raising). Keep tests hermetic — a fixture/teardown removes the sentinel handler after each test so it doesn't leak into other tests in the process.

## Edge Cases

- **Idempotency under `uvicorn --reload`:** module re-import + repeated lifespan must not stack handlers. The sentinel-attribute check handles this; the unit test pins it.
- **Propagation MUST stay True (pytest `caplog`):** an earlier draft of this leg set `propagate=False` to "prevent double emission" — that was wrong on both counts and is explicitly rejected. (1) It would BREAK existing tests: `tests/test_lifespan.py::test_lifespan_warns_on_deprecated_inference_env_vars` and `::test_lifespan_does_not_warn_when_inference_env_vars_unset` enter `async with lifespan(app):` (the exact call site of `configure_logging()`) and assert on `the_one.*` WARNING records via `caplog`, which captures through the ROOT logger and depends on propagation — `propagate=False` yields zero captured records and fails them. (2) The double-emission it aimed to prevent does not occur: uvicorn installs handlers only on the `uvicorn*` loggers, not root, so there is no standing root handler; once our handler on `the_one` handles a record, Python's `lastResort` is suppressed and nothing re-emits. So leaving `propagate=True` gives single-emission in production AND keeps caplog working. The new unit test pins this with a caplog-still-captures regression assertion. The test must still remove its handler in teardown (idempotency hygiene), but it does NOT need to touch `propagate`.
- **uvicorn's own config:** `uvicorn.run(app, …)` (`main.py:21`) passes no `log_config`, so uvicorn applies its default config (configures `uvicorn`/`uvicorn.access`/`uvicorn.error`, NOT root) at `uvicorn.run()` time — before lifespan. `configure_logging()` runs later (in lifespan) on a different namespace, so the two never clobber each other; under the docker-compose direct-`uvicorn` launch the same holds.
- **Invalid `THE_ONE_LOG_LEVEL`:** `getattr(logging, level_name, logging.INFO)` falls back to INFO without raising.
- **Namespace isolation:** only `logging.getLogger("the_one")` is touched; never the root or `uvicorn*` loggers (avoids double-emitting uvicorn access logs or clobbering its formatter).
- **Connector-specific lines (connect/READY/tree.sync/ACL):** these only emit when a real connector connects, which needs a configured token — not present in CI. This leg verifies the namespace plumbing via the deterministic startup line; the connector lines are validated implicitly at L4 when a real connector comes online.

## Files Affected

- `the_one/config.py` — add `log_level` field.
- `the_one/logging_config.py` — NEW: `configure_logging()`.
- `the_one/interfaces/web/app.py` — call `configure_logging()` + startup INFO line at top of `lifespan`.
- `Dockerfile` — add `tini` to apt install; `ENTRYPOINT` via tini.
- `tests/test_logging_config.py` — NEW unit test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (N/A — not the final leg)
- [ ] Commit handled at flight-level Phase 2d (deferred-commit model) — do NOT commit per-leg

## Citation Audit

7 citations verified against current code at leg design time: `config.py:8-9` (Settings/env_prefix) OK; `config.py:12-13` (host/port) OK; `app.py:82-83` (lifespan) OK; `app.py:74` (module logger) OK; `app.py:6` (import logging) OK; `main.py:21` (uvicorn.run) OK; `Dockerfile:6-14` (apt block) + `Dockerfile:37` (ENTRYPOINT) OK; `docker-compose.yml:16-21` (uvicorn command override) OK; `entrypoint.sh` (`exec "$@"`) OK; `api.py:55-60` + `cache_cleanup.py:294` (WARNING-abuse precedent) OK. All clean.
