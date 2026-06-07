# Leg: sandbox-backend-factory

**Status**: completed
**Flight**: [Sandbox Seam + Built-in Tool Retrofit](../flight.md)

## Objective

Build the shared seam's machinery: a `PassthroughSandbox` no-op backend, a
`get_sandbox_backend()` selection factory (bubblewrap on Linux+bwrap, passthrough
otherwise and under the test double-flag bypass, logged once), a new
`readonly_overlay_paths` field on `SandboxProfile` with the bubblewrap `--ro-bind`
overlay that implements it, and a profile-driven `HOME` in the bubblewrap backend —
all with unit tests. No spawn site is wired to the factory in this leg (that is
legs 3–4); this leg only lands and unit-tests the seam parts.

## Context

- **DD2 (flight):** backend selection via `get_sandbox_backend()` — returns
  `BubblewrapSandbox` on Linux when `bwrap` is on PATH; `PassthroughSandbox`
  otherwise (non-Linux, or `bwrap` missing), and when the test double-flag bypass
  (`THE_ONE_SANDBOX_DISABLED=1` + `THE_ONE_TEST_MODE=1`) is set. Logs the selected
  backend once. Centralizes the construct-time guard (today `BubblewrapSandbox()`
  is built directly at the MCP site and raises off-Linux) and the MCP-local
  `_sandbox_disabled_for_tests()` bypass.
- **DD3 (flight):** `PassthroughSandbox` satisfies the protocol; `prepare_spawn`
  returns `SpawnSpec(command, args, env, cwd)` unwrapped; namespace / network /
  writable / overlay fields accepted and ignored (forward-compat for the macOS
  backend's differing field set). Surfaces the unsandboxed state via a one-time
  WARNING, not per-spawn noise.
- **DD4 (flight, the overlay + HOME parts):** add a `readonly_overlay_paths` field
  to `SandboxProfile`; the bubblewrap backend emits `--ro-bind` for those paths so
  denylisted secrets under a writable root are re-protected (bind mounts are
  additive — without the overlay, mapping a home allowlist to writable would make
  secrets writable too). And make the backend's hardcoded `HOME=/tmp`
  profile-driven so MCP keeps `/tmp` and built-in tools (leg 4) can get the real
  home.
- **Constraint (mission):** profile fields a backend cannot honor must be silently
  ignored, never error — so `PassthroughSandbox` accepts the full profile and drops
  what it can't enforce.
- **Prior leg:** Leg 1 renamed the abstraction; this leg is authored against
  `ToolSandbox` / `SandboxError` and `BubblewrapSandbox` (unchanged name).

## Inputs

What exists before this leg runs (post-leg-1, landed):
- `the_one/platform/sandbox/base.py` — `SandboxProfile` (frozen dataclass, fields
  `writable_paths`, `network_allowed`, `pid_unshare`, `ipc_unshare`, `uts_unshare`;
  `from_dict` classmethod at `base.py:from_dict`), `SpawnSpec`, and the
  `ToolSandbox` Protocol (`base.py — "class ToolSandbox(Protocol)"`).
- `the_one/platform/sandbox/bubblewrap.py` — `BubblewrapSandbox`: raises
  `SandboxError` at construction when `bwrap` is absent
  (`bubblewrap.py — "if shutil.which(\"bwrap\") is None"`); hardcodes
  `assembled_env["HOME"] = "/tmp"` (`bubblewrap.py — "assembled_env[\"HOME\"] = \"/tmp\""`);
  argv order is `--ro-bind / /`, `--tmpfs /tmp`, writable `--bind` loop, `--proc`,
  `--dev`, `[--chdir]`, `--`, command, args.
- `the_one/platform/sandbox/__init__.py` — re-exports `BubblewrapSandbox`,
  `ToolSandbox`, `SandboxProfile`, `SpawnSpec`, `SandboxError`.
- `the_one/mcp/transports/stdio.py:_sandbox_disabled_for_tests` — the existing
  double-flag bypass (`THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1`),
  read from `os.environ` at call time. **Stays where it is this leg** — the factory
  implements its own copy of the check; leg 3 reconciles the MCP site to the factory.
- `pyproject.toml` — `requires_bwrap` marker registered; default `addopts`
  deselects it. (Not needed by this leg's tests — see Edge Cases.)
- `tests/test_sandbox_bubblewrap.py` — existing argv-shape tests, incl. HOME=/tmp
  assertions on the default profile (`tests/test_sandbox_bubblewrap.py` ~lines
  62–97, 207–216) and the A03 ordering test (~line 123).

## Outputs

What exists after this leg completes:
- `the_one/platform/sandbox/passthrough.py` — `PassthroughSandbox` (new).
- `the_one/platform/sandbox/factory.py` — `get_sandbox_backend()` + the double-flag
  bypass check + one-time selection log (new).
- `the_one/platform/sandbox/base.py` — `SandboxProfile` gains
  `readonly_overlay_paths: list[str] = field(default_factory=list)` and a
  programmatic-only `home: str | None = None`; `from_dict` parses
  `readonly_overlay_paths` (same coercion/validation as `writable_paths`) but does
  **not** parse `home` (preserves "operators cannot set HOME").
- `the_one/platform/sandbox/bubblewrap.py` — emits a `--ro-bind PATH PATH` per
  `readonly_overlay_paths` entry **after** the writable `--bind` loop; HOME is
  `profile.home if profile.home is not None else "/tmp"`.
- `the_one/platform/sandbox/__init__.py` — re-exports `PassthroughSandbox` and
  `get_sandbox_backend` (added to `__all__`).
- `tests/test_sandbox_factory.py` (new) — selection matrix + passthrough-never-raises
  + log-once behavior.
- `tests/test_sandbox_bubblewrap.py` — new tests for the overlay argv and
  profile-driven HOME; existing HOME=/tmp tests still pass (default `home=None`).
- Full default suite + ruff green.

## Acceptance Criteria

- [x] `PassthroughSandbox` exists in `the_one/platform/sandbox/passthrough.py`,
      structurally satisfies `ToolSandbox` (`isinstance(PassthroughSandbox(), ToolSandbox)`
      is `True`), exposes `name == "passthrough"`, and its `prepare_spawn(profile,
      command, args, env, cwd)` returns `SpawnSpec(command=command, args=args,
      env=env, cwd=cwd)` — env/args/command/cwd unchanged, all profile fields
      (writable, network, namespace, overlay, home) ignored without error.
- [x] `PassthroughSandbox()` constructs and `prepare_spawn` runs **without raising**
      regardless of platform or `bwrap` presence (the off-Linux no-error guarantee).
- [x] `get_sandbox_backend()` exists and returns:
      - `BubblewrapSandbox` when `sys.platform == "linux"` AND `bwrap` is on PATH
        AND the test double-flag is not set;
      - `PassthroughSandbox` when the double-flag bypass is set (highest priority),
        OR `sys.platform != "linux"`, OR `bwrap` is absent.
- [x] `get_sandbox_backend()` logs the selected backend **once per process** (not
      per call): INFO when bubblewrap or expected-passthrough (non-Linux /
      test-bypass) is selected; **WARNING** when passthrough is selected on Linux
      because `bwrap` is missing (enforcement was expected but is absent). Repeated
      calls do not re-log. *(See Implementation Guidance for the log-once mechanism
      and its test reset hook.)*
- [x] `SandboxProfile` has `readonly_overlay_paths` (defaults to `[]`) and `home`
      (defaults to `None`). `from_dict` accepts/validates `readonly_overlay_paths`
      exactly like `writable_paths` (list-of-str, `None`-entry rejected, non-list
      raises `ValueError`, unknown keys still debug-logged), and does **not** read
      `home` from the dict.
- [x] `BubblewrapSandbox.prepare_spawn` emits `--ro-bind PATH PATH` for each
      `readonly_overlay_paths` entry, positioned **after** the writable `--bind`
      loop and before `--proc`/`--dev`, so an overlay path under a writable root is
      re-mounted read-only on top.
- [x] `BubblewrapSandbox.prepare_spawn` sets `HOME` from `profile.home` when set,
      else `/tmp`. A profile with `home=None` (the default, and what MCP uses)
      still yields `HOME=/tmp` — existing HOME=/tmp tests pass unchanged. A profile
      with `home="/home/foo"` yields `HOME=/home/foo`.
- [x] `the_one/platform/sandbox/__init__.py` re-exports `PassthroughSandbox` and
      `get_sandbox_backend` (both in `__all__`).
- [x] New `tests/test_sandbox_factory.py` proves the selection matrix (via
      monkeypatching `sys.platform`, `shutil.which`, and the two env vars),
      passthrough-never-raises, and log-once. Full default suite passes
      (`docker exec the-one pytest -x --timeout 30`); `ruff check .` +
      `ruff format --check .` pass.

## Verification Steps

- `docker exec the-one pytest tests/test_sandbox_factory.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -x --timeout 30`
- `docker exec the-one python -c "from the_one.platform.sandbox import PassthroughSandbox, get_sandbox_backend, ToolSandbox; assert isinstance(PassthroughSandbox(), ToolSandbox)"`
- Selection smoke (in-container, bwrap present → bubblewrap):
  `docker exec the-one python -c "from the_one.platform.sandbox import get_sandbox_backend, BubblewrapSandbox; assert isinstance(get_sandbox_backend(), BubblewrapSandbox)"`
- Overlay argv check is a pure `prepare_spawn` assertion (no real bwrap needed) —
  covered by the new `test_sandbox_bubblewrap.py` cases.
- `docker exec the-one pytest -x --timeout 30` (full default suite) and
  `ruff check . && ruff format --check .`.

## Implementation Guidance

1. **`PassthroughSandbox`** (`the_one/platform/sandbox/passthrough.py`).
   - `name: str = "passthrough"`. No-arg `__init__` that never raises.
   - `prepare_spawn(self, profile, command, args, env, cwd=None) -> SpawnSpec`:
     `return SpawnSpec(command=command, args=list(args), env=dict(env), cwd=cwd)`.
     Copy `args`/`env` defensively (mirror bubblewrap's `dict(env)` no-mutation
     contract). Ignore every `profile` field — do not read them.
   - Docstring: state it is a no-op forward-compat backend; enforcement is absent;
     accepts and silently drops all policy fields (mission constraint).

2. **`get_sandbox_backend()`** (`the_one/platform/sandbox/factory.py`).
   - Selection order (first match wins): double-flag bypass → `PassthroughSandbox`;
     `sys.platform != "linux"` → `PassthroughSandbox`; `shutil.which("bwrap") is
     None` → `PassthroughSandbox`; else `BubblewrapSandbox()`.
   - Re-evaluate on **every** call (do **not** memoize the instance) — tests
     monkeypatch `sys.platform` / `shutil.which` / env between calls and must see
     fresh selection; the checks are cheap.
   - Double-flag check: implement the same predicate as
     `stdio.py:_sandbox_disabled_for_tests` (read `os.environ` at call time:
     `THE_ONE_SANDBOX_DISABLED == "1"` AND `THE_ONE_TEST_MODE == "1"`). The MCP
     site keeps its own copy this leg; leg 3 reconciles. (Acceptable variation per
     flight: a shared helper is fine if it reads cleaner — but do not delete the
     stdio copy here, leg 3 owns that.)
   - **Log-once mechanism:** a module-level guard — e.g. `_LOGGED: set[str]` keyed
     by `f"{backend_name}:{reason}"`, or a single module bool. Log on first
     selection only. Level: WARNING for the Linux-bwrap-missing case; INFO
     otherwise. Include the reason in the message (e.g. "sandbox backend:
     passthrough (non-linux) — tool spawns are NOT sandboxed"). Provide a
     module-level reset (e.g. `_reset_selection_log_state()`) so the new factory
     test can assert the log fires once then is suppressed; tests reset state in a
     fixture. Use a module logger `logging.getLogger(__name__)`.
   - **DD3 locus (accepted decision):** the one-time unsandboxed WARNING lives
     **here in the factory**, not inside `PassthroughSandbox.prepare_spawn` as DD3
     literally phrases it. The factory is the single selection locus, knows the
     *reason* (non-Linux vs bwrap-missing vs test-bypass) which sets the level, and
     this avoids per-instance global state on the backend. Observably equivalent to
     DD3 (one-time WARNING when unsandboxed). The implementing Developer must note
     this as a DD3 refinement in the flight-log leg entry so the design record
     stays honest.

3. **Extend `SandboxProfile`** (`the_one/platform/sandbox/base.py`).
   - Add fields: `readonly_overlay_paths: list[str] = field(default_factory=list)`
     and `home: str | None = None`. Keep the dataclass `frozen=True`.
   - In `from_dict`: add `"readonly_overlay_paths"` to the `known` set; parse it
     with the **same** logic as `writable_paths` (None → `[]`; list → coerce each
     entry to `str`, reject `None` entries with `ValueError`; non-list →
     `ValueError` naming the field). Pass it to `cls(...)`. Do **not** add `home`
     to `known` and do **not** read it from `data` — `home` is programmatic-only
     (preserves the §13 "operators cannot override HOME" contract; an operator
     `home` key falls through to the existing unknown-key debug log).
   - Update the dataclass docstring to mention the two new fields and that `home`
     is programmatic-only. Also add a one-line note in **`from_dict`'s** docstring
     explaining why `home` is intentionally absent from `known` (operator cannot
     set HOME) — so a future reader doesn't read the omission as an oversight.

4. **Bubblewrap overlay + profile-driven HOME** (`the_one/platform/sandbox/bubblewrap.py`).
   - HOME: replace `assembled_env["HOME"] = "/tmp"` with
     `assembled_env["HOME"] = profile.home if profile.home is not None else "/tmp"`.
   - Overlay: after the existing writable `--bind` loop and before
     `bwrap_args.extend(["--proc", "/proc"])`, add:
     `for path in profile.readonly_overlay_paths: bwrap_args.extend(["--ro-bind", path, path])`.
     Position matters — it must come *after* the writable binds so a secret path
     under a writable root is re-protected on top (bind order is last-wins for
     overlapping mounts).
   - Update the class/method docstrings' argv-order description to include the
     overlay step and the profile-driven HOME (the docstrings currently say "HOME
     unconditionally /tmp" — correct them to "HOME from profile, default /tmp").
   - **Update the stale test** `test_prepare_spawn_home_override_unconditional` in
     `tests/test_sandbox_bubblewrap.py`: it stays factually correct for the default
     profile, but its name/docstring imply a global invariant that no longer holds.
     Clarify the docstring (and optionally rename) to "with the default profile
     (`home=None`), HOME is still forced to `/tmp`".

5. **Re-export** (`the_one/platform/sandbox/__init__.py`): import and add
   `PassthroughSandbox` and `get_sandbox_backend` to `__all__` and the module
   docstring's public-API listing.

6. **Tests.**
   - `tests/test_sandbox_factory.py` (new): selection matrix. **Patch via the
     object form** (matches the established pattern in `test_sandbox_bubblewrap.py`
     / `test_mcp_stdio_sandbox.py`, which do `monkeypatch.setattr(module.shutil,
     "which", ...)`): `import the_one.platform.sandbox.factory as factory_module`
     then `monkeypatch.setattr(factory_module.sys, "platform", "darwin")` and
     `monkeypatch.setattr(factory_module.shutil, "which", lambda _: "/usr/bin/bwrap")`
     (or `lambda _: None`), plus `monkeypatch.setenv/delenv` for the double-flag.
     This requires `factory.py` to `import sys` and `import shutil` at module level
     (so the patched object is the one the factory reads). Assert the four branches.
     Assert `PassthroughSandbox` never raises off-Linux (simulate `sys.platform =
     "darwin"`). Assert log-once: call twice, assert one log record (use `caplog`,
     reset the module guard in a fixture).
   - `tests/test_sandbox_bubblewrap.py`: add (a) an overlay test — profile with
     `writable_paths=["/home/u"]`, `readonly_overlay_paths=["/home/u/.ssh"]`,
     assert the argv contains `--ro-bind /home/u/.ssh /home/u/.ssh` positioned
     after `--bind /home/u /home/u` and before `--proc`; (b) a profile-driven HOME
     test — `home="/home/u"` → `spec.env["HOME"] == "/home/u"` and argv `--setenv
     HOME /home/u`; confirm default profile still yields `/tmp`.
   - Extend `tests/test_sandbox_contract.py` so `PassthroughSandbox` is covered by
     the Protocol-conformance check alongside `BubblewrapSandbox` (the contract
     test is the natural home for this; promoted from optional to required so it
     doesn't conflict with the isinstance acceptance criterion). Match whatever
     conformance form that file already uses for `BubblewrapSandbox`.

7. **Run** the targeted files, then the full default suite, then ruff. Fix fallout.

## Edge Cases

- **No real bwrap needed for this leg's tests.** Selection tests monkeypatch
  `shutil.which`; the overlay/HOME tests inspect `prepare_spawn`'s returned argv
  (pure compilation, bwrap is never executed). So no `@requires_bwrap` markers are
  introduced here — the real-bwrap containment tests come in leg 4.
- **Frozen dataclass + new fields.** `SandboxProfile` is `frozen=True`; adding
  fields with defaults keeps all existing positional/keyword constructions valid.
  Confirm no existing call site constructs it positionally past `uts_unshare` (it
  doesn't — but the two new fields are appended last with defaults, so positional
  callers are unaffected).
- **`home` must not leak through `from_dict`.** If an operator puts `home` in
  `config["sandbox"]`, it must be ignored (debug-logged as unknown), not applied.
  Test this: `SandboxProfile.from_dict({"home": "/evil"}).home is None`.
- **Overlay path not under a writable root.** If a `readonly_overlay_paths` entry
  is *not* under any writable bind, `--ro-bind` still applies harmlessly (it just
  re-binds a path already read-only under `--ro-bind / /`). No special-casing
  needed; do not validate containment here (leg 4's `_build_tool_profile` decides
  which paths to overlay).
- **Selection must not cache.** A memoized factory would make the selection tests
  flaky/order-dependent (first test's platform wins forever). Re-evaluate per call;
  only the *log* is deduped. The per-call `shutil.which("bwrap")` PATH scan is
  negligible next to the cost of actually spawning a subprocess (the factory is
  called once per spawn, not in a tight loop), so no instance/type caching is
  warranted — keep it simple and test-isolated.
- **Log-once across tests.** The module-level log guard persists across tests in a
  process; without a reset fixture, a test asserting "logs once" could see zero
  records if an earlier test already logged. The reset hook + autouse-or-explicit
  fixture in `test_sandbox_factory.py` handles this.
- **Do not wire any spawn site here.** `stdio.py`, `tools/shell.py`,
  `tools/python_exec.py` are untouched this leg. Touching them is legs 3–4 and
  would muddy this leg's review.

## Files Affected

- `the_one/platform/sandbox/passthrough.py` — new `PassthroughSandbox`.
- `the_one/platform/sandbox/factory.py` — new `get_sandbox_backend()` + bypass +
  log-once.
- `the_one/platform/sandbox/base.py` — `SandboxProfile` gains
  `readonly_overlay_paths` + `home`; `from_dict` parses the former only.
- `the_one/platform/sandbox/bubblewrap.py` — `--ro-bind` overlay loop;
  profile-driven HOME; docstring corrections.
- `the_one/platform/sandbox/__init__.py` — re-export the two new symbols.
- `the_one/agents.md` — the HOME-policy description (currently "HOME is
  unconditionally set to `/tmp` … not configurable") goes stale once `profile.home`
  exists. Update it to: "HOME defaults to `/tmp`; callers with a real workspace pass
  `profile.home` to override — operators still cannot override HOME via the
  kv-table." (The second clause stays true: `from_dict` doesn't read `home`.)
- `tests/test_sandbox_factory.py` — new selection / passthrough / log-once tests.
- `tests/test_sandbox_bubblewrap.py` — overlay + profile-driven HOME tests; clarify
  the stale `..._home_override_unconditional` test docstring/name.
- `tests/test_sandbox_contract.py` — cover `PassthroughSandbox` (required).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (N/A — leg 2 of 5)
- [x] Commit all changes together (code + artifacts)

> **Note (batched flight):** Implementing Developer does **not** commit and does
> **not** signal `[COMPLETE:leg]` — set the leg to `landed`, update the flight log,
> signal `[HANDOFF:review-needed]`. Status → `completed` and the commit happen in
> the flight-level review/commit phase (2d).
