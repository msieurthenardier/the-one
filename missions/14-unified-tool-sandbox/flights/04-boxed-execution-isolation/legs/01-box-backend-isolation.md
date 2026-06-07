# Leg: box-backend-isolation

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Add the backend capability for true isolation: a programmatic-only `SandboxProfile`
isolation field and a minimal-read-only-system-rootfs path in the bubblewrap backend
(replacing the blanket `--ro-bind / /` for boxed spawns), plus the seam-level
no-enforcement WARNING for backends that can't honor it. This is the foundation leg —
its `@requires_bwrap` gate re-proves the empirically-verified DD2 in-flight before any
tool wiring depends on it.

## Context

- **DD2 / DD2a** (flight): boxed = no user FS. Instead of `--ro-bind / /`, bind only the
  system runtime RO + a host-bound scratch as the only writable path; `--unshare-net`.
  The Architect **empirically verified** this mount set works in the live container
  (`python:3.11-slim` / Debian bookworm / merged-usr / bwrap 0.11.0): boxed `python3` +
  `/bin/sh` run; `/root`,`/home` absent; planted canary unreadable.
- **DD3a**: scratch is a HOST-side dir bound writable via the existing `writable_paths`
  `--bind` (applied AFTER `--tmpfs /tmp`), NOT an in-box tmpfs. This leg does NOT create
  scratch dirs (that's legs 2–4); it only ensures the backend, given a profile with
  `minimal_rootfs=True` + `writable_paths=[scratch]` + `home=scratch`, produces a
  correctly-isolated spawn.
- **DD5**: backends that can't honor isolation (passthrough) ignore the field and the
  **seam** WARNING-logs (NOT the factory).
- **DD6**: the field is silently ignored by non-honoring backends — never errors.
- Current backend: the single unconditional base mount is `--ro-bind / /` at
  `the_one/platform/sandbox/bubblewrap.py:123`; `--tmpfs /tmp` at `:128`; writable
  `--bind` loop at `:129-130`; `readonly_overlay_paths` loop at `:138-139`; `--proc`/`--dev`
  at `:140-141`. `SandboxProfile` is a frozen dataclass at
  `the_one/platform/sandbox/base.py:91-117`; `home` is the precedent for a
  **programmatic-only** field (omitted from `from_dict`'s `known` set, `:142-149`).

## Inputs

- `bwrap` present (container 0.11.0, host 0.9.0; both support `--ro-bind` `--ro-bind-try`
  `--symlink`).
- The existing seam: `run_shell`/`run_python` (`platform/shell.py` / `platform/interpreter.py`)
  and `UnixPtySession.start` (`platform/pty.py`) all call `get_sandbox_backend().prepare_spawn(...)`.
- `tests/_sandbox_fixtures.py` helpers (`home_workspace`, `sleep_pids`) for the test harness.

## Outputs

- `SandboxProfile.minimal_rootfs: bool = False` (programmatic-only; `from_dict` ignores it).
- `bubblewrap.py` minimal-rootfs branch producing the verified mount set.
- Seam-level no-enforcement WARNING (in `run_shell`/`run_python`/`pty.start`).
- `@requires_bwrap` tests proving boxed isolation (the DD2 gate).

## Acceptance Criteria

- [x] `SandboxProfile` gains `minimal_rootfs: bool = False` (frozen dataclass field);
      **`from_dict` does NOT parse it** (programmatic-only, like `home` — operators can't
      set it via the kv-table). `from_dict`'s `known` set and unknown-key handling
      unchanged for it.
- [x] `BubblewrapSandbox.prepare_spawn`: when `profile.minimal_rootfs` is True, the base
      `--ro-bind / /` (`:123`) is **replaced** by the minimal RO system set —
      `--ro-bind /usr /usr` (always exists; covers `/usr/local`), `--symlink usr/bin /bin`,
      `--symlink usr/sbin /sbin`, `--symlink usr/lib /lib`, `--symlink usr/lib64 /lib64`,
      `--ro-bind-try /lib32 /lib32`, `--ro-bind-try /libx32 /libx32`, and a **narrowed
      `/etc`** set via `--ro-bind-try` (`/etc/ssl`, `/etc/passwd`, `/etc/group`,
      `/etc/nsswitch.conf`, `/etc/resolv.conf`, `/etc/alternatives`, `/etc/ld.so.cache`,
      `/etc/ld.so.conf`, `/etc/ld.so.conf.d`). The rest of the argv (`--tmpfs /tmp`, the
      writable `--bind` loop, `readonly_overlay_paths` loop, `--proc`/`--dev`, `--chdir`,
      `--`, command) is **unchanged**. When `minimal_rootfs` is False, argv is
      **byte-identical to today** (no host-mode regression).
- [x] **DD2 gate** (`@requires_bwrap`): given
      `SandboxProfile(minimal_rootfs=True, writable_paths=[scratch], home=scratch, network_allowed=False)`
      and a planted host home-file canary, a boxed spawn:
      - via **`run_python`** (NOT `run_shell`): `import sys, json, os, ssl, sqlite3; print('ok')`
        → `ok` (working runtime). **Critical**: use `run_python` because it passes
        `sys.executable` (`/usr/local/bin/python3`, inside `/usr` → bound) directly as the
        command. `run_shell("python3 …")` would fail "not found" — `--clearenv` leaves no
        PATH in the box and python3 isn't on a default search path.
      - via **`run_shell`**: `/bin/sh -c "echo hi"` → `hi` (sh exec'd by full path; `echo` is a builtin);
      - **cannot read** the planted canary (e.g. `cat <canary>` fails / file not present);
      - `ls /` contains **no** `home`, `app`, `var` (see deviation note below re `/root`);
      - **can write** to `scratch` (writable_path) and it's visible on the host fs;
      - `/proc/net/dev` shows **loopback only** (`--unshare-net`).
- [x] Seam no-enforcement WARNING: `run_shell`/`run_python`/`UnixPtySession.start` emit a
      single WARNING ("boxed execution requested but isolation is not enforced on this
      backend") when `profile.minimal_rootfs` is True AND the resolved backend is not the
      bubblewrap backend (e.g. `backend.name != "bubblewrap"`). bubblewrap path: no warning.
- [x] Passthrough backend **ignores** `minimal_rootfs` and does not error (DD6) — a boxed
      profile through passthrough runs (unisolated) without raising.
- [x] Existing `@requires_bwrap` suite + full default suite still green; `ruff check` +
      `ruff format --check` clean.

## Verification Steps

- `docker exec the-one python -m pytest -m requires_bwrap --timeout 120 -q` — all green incl. the new boxed tests.
- `docker exec the-one python -m pytest tests/test_sandbox_contract.py --timeout 60 -q` — host-mode argv unchanged (add/confirm a contract assertion that `minimal_rootfs=False` argv == today's).
- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — no regressions.
- Manual spot (in-container): build a boxed profile, prepare_spawn, run `bwrap <args> -- ls /` and confirm no `root`/`home`.
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/platform/sandbox/bubblewrap.py the_one/platform/sandbox/base.py`.

## Implementation Guidance

1. **Add the field** (`base.py:117`, after `home`): `minimal_rootfs: bool = False`. Update
   the dataclass docstring (note it's programmatic-only). Do NOT add it to `from_dict`'s
   `known` set or parse it — boxed mode is set by the tool layer (legs 2–4), never the
   operator kv-table.
2. **Branch the base mount** in `prepare_spawn`. Replace the single
   `bwrap_args.extend(["--ro-bind", "/", "/"])` (`:123`) with:
   ```python
   if profile.minimal_rootfs:
       bwrap_args.extend(["--ro-bind", "/usr", "/usr"])
       # bwrap: --symlink SRC DEST  → create symlink at DEST pointing to SRC
       # (merged-usr: /bin -> usr/bin, etc.)
       for src, dest in (("usr/bin","/bin"),("usr/sbin","/sbin"),
                         ("usr/lib","/lib"),("usr/lib64","/lib64")):
           bwrap_args.extend(["--symlink", src, dest])
       for opt in ("/lib32","/libx32"):
           bwrap_args.extend(["--ro-bind-try", opt, opt])
       for etc in ("/etc/ssl","/etc/passwd","/etc/group","/etc/nsswitch.conf",
                   "/etc/resolv.conf","/etc/alternatives","/etc/ld.so.cache",
                   "/etc/ld.so.conf","/etc/ld.so.conf.d"):
           bwrap_args.extend(["--ro-bind-try", etc, etc])
   else:
       bwrap_args.extend(["--ro-bind", "/", "/"])
   ```
   Keep everything after `:123` as-is (`--tmpfs /tmp`, writable `--bind`, overlay loop,
   `--proc`/`--dev`, `--chdir`, `--`, command). Update the **module-level docstring
   (`bubblewrap.py:8-20`, which states "`--ro-bind / /` … defines the FS scope" — now
   conditional)** AND the class + method argv docstrings to describe the boxed branch.
3. **Seam WARNING**: in `run_shell` (`platform/shell.py`), `run_python`
   (`platform/interpreter.py`), and `UnixPtySession.start` (`platform/pty.py`, where the
   spec is computed in the parent), after resolving the backend, add:
   `if getattr(profile, "minimal_rootfs", False) and backend.name != "bubblewrap": logger.warning(...)`.
   Use the module logger. (A small shared helper in `platform/sandbox/` is fine to avoid
   three copies — implementer's discretion.)
4. **Tests**: add a boxed section to `tests/test_builtin_tool_sandbox.py` (or a new
   `tests/test_box_isolation.py`) using `_sandbox_fixtures.home_workspace("box-scratch")`
   for the writable scratch + `home_workspace("box-canary")` for a planted host home-file
   (both under `~`/`/root`, outside `/tmp` so not tmpfs-shadowed; the canary is NOT in
   `writable_paths` and NOT in the minimal mount set → unreadable in the box). Construct
   the boxed profile directly. **Drive the python3 runtime check via `run_python`** (it
   passes `sys.executable` directly — `run_shell("python3 …")` would fail "not found"
   under `--clearenv`); drive the `/bin/sh` check via `run_shell`. Add a
   `test_sandbox_contract.py` assertion that `minimal_rootfs=False` argv is **byte-identical
   to today** AND `minimal_rootfs=True` argv contains the minimal set + **no** `--ro-bind / /`.

## Edge Cases

- **Merged-usr already symlinked**: `--symlink usr/bin /bin` recreates the link the host
  has; if a non-merged-usr host had a real `/bin`, `--symlink` would shadow it — acceptable
  (the deployment base is merged-usr; the test runs there). Note in a comment.
- **`/etc` partial**: `--ro-bind-try` skips any absent `/etc/*` entry — a missing
  `resolv.conf` (no network anyway) or `ld.so.conf.d` won't crash the spawn.
- **Host-mode regression**: the `else` branch must keep `--ro-bind / /` exactly; the
  contract test guards this.
- **WARNING noise**: fire at most once per spawn; only when isolation is requested AND
  unhonored. Do not warn on the bubblewrap path.
- **No scratch yet**: this leg's tests supply `writable_paths=[scratch]` directly; the
  per-call/per-session scratch *creation* is legs 3–4. Don't build scratch lifecycle here.

## Files Affected

- `the_one/platform/sandbox/base.py` — `minimal_rootfs` field (+ docstring).
- `the_one/platform/sandbox/bubblewrap.py` — minimal-rootfs branch (+ docstrings).
- `the_one/platform/shell.py`, `the_one/platform/interpreter.py`, `the_one/platform/pty.py` — seam WARNING.
- `tests/test_builtin_tool_sandbox.py` (or new `tests/test_box_isolation.py`),
  `tests/test_sandbox_contract.py` — boxed tests + argv contract.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to `landed`,
> signal `[HANDOFF:review-needed]`. No commit here (single review + commit after the last
> autonomous leg).

- [x] All acceptance criteria verified (DD2 gate green)
- [x] Host-mode argv unchanged (contract test); existing suites green; ruff clean
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
