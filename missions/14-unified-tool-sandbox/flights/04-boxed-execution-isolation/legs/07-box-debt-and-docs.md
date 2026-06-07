# Leg: box-debt-and-docs

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Land the boxed-mode documentation, the startup-prune of orphaned box scratch dirs (the one
real code item — surfaced by the leg-3 design review), and the Flight-3 carry-forward debt
that lives on the surfaces this flight already edits (the `_TOOL_CLASSES` cross-config note,
the ordering-is-policy assertion, the `pty.py` fork-safety convention). Plus update the
mission known-issue: read-scoping is now advanced for the boxed path.

## Context

Bundled-by-shared-surface (flight Source artifacts). Items:
1. **Startup-prune of orphan box scratch** (code — from leg-3/leg-4 design reviews): a
   SIGKILL/OOM mid-call/-session leaves a `settings.data_dir/"boxes"/<…>` orphan that
   accumulates across restarts (the per-call/per-session cleanup only runs on normal exit).
2. **`_TOOL_CLASSES` cross-config note** (Flight-3 carry-forward, docs): the shared
   `FilesystemConfig` resolves from the FIRST `_TOOL_CLASSES` tool whose `Config IS
   FilesystemConfig` (= `read_file`, not `shell`) — a real gotcha for tool-config tests.
3. **Ordering-is-policy assertion/comment** (`builtins.py`): make `_TOOL_CLASSES` ordering's
   policy consequence explicit so a future reorder doesn't silently change cross-config
   resolution.
4. **`pty.py` fork-safety + libc-preload convention** (Flight-3 carry-forward): promote the
   "compute spawn state / load libc in the parent, never in the post-fork child" rule from
   inline comments to a named module-docstring convention.
5. **Boxed-mode docs**: `SECURITY-MODEL.md` (true isolation / minimal rootfs / no user FS /
   network off / scratch lifecycle / read-scoping for the boxed path) + `CLAUDE.md`
   (box-by-default / `host_access`).
6. **Mission known-issue**: read-scoping ("cannot read outside scope") is now **advanced for
   the boxed path** (the box has no user FS); host-workspace read-scoping remains open.

## Inputs

- Legs 1-6 landed (boxed mode implemented + behavior spec authored).
- `settings.data_dir/"boxes"` is the scratch root (legs 3-4).
- Flight-3 debrief action items (cross-config note, fork-safety convention).

## Outputs

- A startup-prune of `settings.data_dir/"boxes"` orphans, called once at process startup.
- Docs: `the_one/agents.md`, `the_one/tools/builtins.py` (comment/assert), `the_one/platform/pty.py`
  (docstring), `SECURITY-MODEL.md`, `CLAUDE.md`.
- Mission known-issue update.

## Acceptance Criteria

- [x] **Startup-prune**: a `_prune_box_scratch()` (or similar) removes everything under
      `settings.data_dir/"boxes"/` and is called **once at process startup** — the FastAPI
      lifespan startup (`interfaces/web/app.py`) and, if cheap, the CLI startup
      (`interfaces/cli.py`). It runs only at startup (when THIS process has no live boxed
      sessions, so every box present is an orphan from a prior run). NOT in
      `settings.ensure_dirs()` (called per `AgentFactory.create()` — pruning there would
      delete a live session's scratch). Failures are non-fatal (logged). A unit test asserts
      a planted `boxes/<x>` is removed by the prune.
- [x] **`_TOOL_CLASSES` cross-config note** added to `the_one/agents.md` (the sandbox/tool
      testing area): the shared `FilesystemConfig` is resolved from the first
      `_TOOL_CLASSES`-ordered tool whose `Config IS FilesystemConfig` (`read_file`), so
      tool-config tests must key FS fields under `read_file`, and reordering `_TOOL_CLASSES`
      has policy consequences.
- [x] **Ordering-is-policy** comment (and an assertion if clean to express) at the
      `_TOOL_CLASSES` definition / the cross-config resolution loop in `tools/builtins.py`,
      noting the first-FilesystemConfig-tool-wins behavior is load-bearing.
- [x] **`pty.py` fork-safety convention**: the module docstring names the convention —
      compute the SpawnSpec AND load any libc/ctypes handle in the PARENT before
      `pty.fork()`; the post-fork child only uses already-loaded handles / never imports or
      dlopens. (Consolidates the SpawnSpec-in-parent + libc-preload precedents.)
- [x] **`SECURITY-MODEL.md`** gains a boxed-mode section: agent-selectable isolation;
      box-by-default + `host_access` escalation; true isolation via minimal RO system rootfs +
      host-bound tmpfs-free scratch (= `$HOME`, only writable), no user FS, network off;
      per-call-ephemeral (`boxes/<uuid>`) vs per-session-persistent (`boxes/{agent}-{sid}-{uuid}`)
      scratch — document BOTH name patterns + lifecycle; **read-scoping is satisfied for the
      boxed path** (host-workspace read-scoping still open); the passthrough degradation
      (logged, unenforced). State boxed network is **unconditionally** off (the boxed profile
      does NOT read `sandbox_network_allowed`), not "config-controlled".
- [x] **`CLAUDE.md`** gains a brief boxed-mode note (box-by-default; `host_access` escalation;
      pointer to SECURITY-MODEL for detail).
- [x] **Mission known-issue** (`missions/14-.../mission.md`): update the read-scoping entry —
      advanced for the boxed path (box has no user FS), host-workspace read-scoping remains a
      separate open concern.
- [x] Full default suite + ruff green; no behavior change beyond the startup-prune.

## Verification Steps

- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — green incl. the prune unit test.
- `docker exec the-one python -m pytest -m requires_bwrap --timeout 120 -q` — unaffected.
- Confirm prune is NOT wired into `settings.ensure_dirs()` (grep) — only startup.
- `grep -rn "read_file" the_one/agents.md` — the cross-config note present.
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/`.

## Implementation Guidance

1. **Startup-prune**: add a small function (e.g. in `tools/execution.py` next to
   `_ephemeral_box_scratch`, or a `platform`/lifecycle util):
   ```python
   def prune_box_scratch() -> None:
       from the_one.config import settings
       base = settings.data_dir / "boxes"
       if not base.exists():
           return
       for child in base.iterdir():
           shutil.rmtree(child, ignore_errors=True)
   ```
   Call it from the FastAPI lifespan **startup** (find the lifespan/`@asynccontextmanager` in
   `interfaces/web/app.py` — alongside `init_db()` / `set_factory()`), and from
   `interfaces/cli.py` startup if trivial. Log a debug/info line with the count pruned.
   **Single-process assumption** — word the comment precisely: *"At startup THIS process owns
   the data_dir exclusively and has no live boxed sessions (the session registry starts empty),
   so every `boxes/<…>` is an orphan from a prior run. A concurrent process sharing the same
   data_dir (e.g. web + CLI simultaneously) is unsupported and out of scope — a startup prune
   in one would remove the other's live boxes."* (Say "single PROCESS at a time", not just
   "single user".)
2. **Docs**: write the cross-config note in `agents.md` (sandbox/testing section added in
   Flight 3), the `pty.py` module-docstring convention, the `builtins.py` ordering comment,
   the `SECURITY-MODEL.md` boxed section, the `CLAUDE.md` note. Keep each tight + accurate to
   the implemented behavior (no over-claim — boxed network is unconditionally off; host mode
   follows config).
3. **Read-scoping records (design-review precision)**: the canonical "read-scoping is
   deferred" note lives in `the_one/agents.md:~629-630` — update it to "satisfied for the
   boxed path; host-workspace read-scoping still deferred." The mission `Known Issues` section
   currently has only the host-crash-orphan entry (no read-scoping entry) — **ADD** a new
   Known Issues entry recording the boxed-path advancement (don't assume one exists to edit).
4. **Ordering assertion (self-enforcing — adopt)**: add a module-level assert in
   `tools/builtins.py` near `_TOOL_CLASSES`:
   `assert next(n for n, c in _TOOL_CLASSES.items() if c.Config is FilesystemConfig) == "read_file"`
   with a comment that the first-FilesystemConfig-tool is the shared-cross-config source
   (currently `read_file`, `builtins.py:~49`; `shell` is first but its Config is
   `ExecutionConfig`) — reordering has policy consequences. This surfaces immediately on a
   reorder (preferable to a bare comment). (Confirm `FilesystemConfig` is importable at the
   assert site.)

## Edge Cases

- **Prune timing**: must be startup-only. Double-check `ensure_dirs()` (called per
  `create()`) does NOT call the prune — that would delete a live boxed session's scratch
  mid-operation. The prune unit test should also assert it leaves a non-boxes data_dir subdir
  (e.g. the agent DB) untouched.
- **Empty/absent boxes dir**: prune is a no-op (guard `if not base.exists()`).
- **Docs accuracy**: boxed network is ALWAYS off (`_build_boxed_profile` ignores
  `sandbox_network_allowed`); state that precisely. Read-scoping is advanced for the boxed
  path ONLY — don't claim the host path is fixed.

## Files Affected

- `the_one/tools/execution.py` (or a lifecycle util) — `prune_box_scratch()`.
- `the_one/interfaces/web/app.py` — call prune at lifespan startup; `the_one/interfaces/cli.py`
  — call at CLI startup (if trivial).
- `the_one/agents.md` — `_TOOL_CLASSES` cross-config note.
- `the_one/tools/builtins.py` — ordering-is-policy comment/assert.
- `the_one/platform/pty.py` — fork-safety convention in the module docstring.
- `SECURITY-MODEL.md` — boxed-mode section.
- `CLAUDE.md` — boxed-mode note.
- `missions/14-unified-tool-sandbox/mission.md` — read-scoping known-issue update.
- `tests/` — prune unit test.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to `landed`,
> signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified (prune startup-only + tested; all docs; mission known-issue)
- [x] Full suite + ruff green
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
