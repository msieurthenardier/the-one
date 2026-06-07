# Leg: boxed-profile-derivation

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Add the pure derivation glue between a scratch dir and the boxed seam: a sibling
`_build_boxed_profile(scratch)` that produces the isolated `SandboxProfile`, and a boxed
cwd-validation helper that validates against the box's writable set (the scratch) instead
of the operator allowlist. Legs 3–4 create the scratch dirs and call these; this leg
delivers + unit-tests the functions in isolation.

## Context

- **DD2a** (flight): a **sibling** `_build_boxed_profile(scratch)`, not a branch in
  `_build_tool_profile` (almost no shared inputs — no operator allowlist/denylist, no real
  home, empty `readonly_overlay_paths`). Keeps `tools/execution.py:424` (`_build_tool_profile`)
  clean.
- **cwd seam** (design-review finding): `_cwd_check` (`tools/execution.py:342`) →
  `_filesystem_check(cwd, fs_cfg, CheckMode.DIRECTORY)` validates cwd ⊆ the **operator**
  `FilesystemConfig._canonical_allowlist`. The scratch is never in the operator allowlist,
  so the host-mode check would self-refuse a boxed cwd. Boxed cwd must be validated against
  an ephemeral `FilesystemConfig(path_allowlist=[scratch], path_denylist=[])` through the
  same dispatcher (reuses canonicalization + `is_dir()`), OR cwd is forced to the scratch.
- Leg 1 already added `SandboxProfile.minimal_rootfs` + the backend path. This leg produces
  a profile with `minimal_rootfs=True`.
- `_build_tool_profile` shape (the host-mode sibling) for reference: returns
  `SandboxProfile(writable_paths=[canonical allowlist], readonly_overlay_paths=[canonical
  denylist], network_allowed=exec_cfg.sandbox_network_allowed, home=str(Path.home()))`
  (`execution.py:453-458`).

## Inputs

- Leg 1 landed (`SandboxProfile.minimal_rootfs`, backend minimal-rootfs path, seam WARNING).
- `FilesystemConfig` (`tools/filesystem.py`) — its constructor + `_canonical_allowlist`
  (the post-init expanduser+resolve) + `_filesystem_check` dispatcher.

## Outputs

- `_build_boxed_profile(scratch: str | Path) -> SandboxProfile` in `tools/execution.py`.
- A boxed cwd helper (e.g. `_boxed_cwd_check(cwd, scratch) -> Path`) that validates a
  requested cwd ⊆ scratch (or returns the scratch when cwd is None).
- Unit tests for both (no `@requires_bwrap` needed — these are pure functions).

## Acceptance Criteria

- [x] `_build_boxed_profile(scratch)` returns
      `SandboxProfile(minimal_rootfs=True, writable_paths=[str(scratch)], home=str(scratch),
      network_allowed=False, readonly_overlay_paths=[])`. Network is **always** off in box
      mode (not read from `ExecutionConfig` — the box has no network by definition). The
      scratch path is stringified consistently with how `_build_tool_profile` stringifies
      paths.
- [x] A boxed cwd helper (`_boxed_cwd_check`) validates a caller-supplied `cwd` is within
      the scratch (via an ephemeral `FilesystemConfig(path_allowlist=[scratch], path_denylist=[])`
      through `_filesystem_check(..., CheckMode.DIRECTORY)` — reusing canonicalization +
      `is_dir()`), and **defaults to the scratch** when `cwd` is None. A cwd outside the
      scratch raises `ConstraintError` (the same error type/wording family as host-mode
      `_cwd_check`).
- [x] Decision recorded (in the leg + flight log): **honor a supplied cwd if ⊆ scratch,
      else error** — symmetric with host mode. `_boxed_cwd_check` validates and accepts any
      path within scratch, defaults to scratch when cwd is None, and raises ConstraintError
      for anything outside.
- [x] Unit tests: profile shape correct (minimal_rootfs True, scratch as sole writable +
      home, network off, empty overlay); cwd helper accepts scratch + a subdir of scratch,
      defaults None→scratch, rejects a path outside scratch. 6 tests added, all green.
- [x] No `@requires_bwrap` needed; full default suite + ruff green. No tool wiring yet
      (legs 3–4) and no scratch creation here.

## Verification Steps

- `docker exec the-one python -m pytest tests/test_execution_tools.py -k "boxed_profile or boxed_cwd" --timeout 60 -q` (or wherever the unit tests land) — green.
- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — no regressions.
- `docker exec the-one ruff check the_one/tools/execution.py && docker exec the-one ruff format --check the_one/tools/execution.py`.

## Implementation Guidance

1. **`_build_boxed_profile`** — mirror `_build_tool_profile`'s structure (function-level
   `from the_one.platform.sandbox import SandboxProfile` import to avoid the cycle), but
   return the boxed shape: `minimal_rootfs=True`, `writable_paths=[str(scratch)]`,
   `home=str(scratch)`, `network_allowed=False`, `readonly_overlay_paths=[]`. Docstring:
   note network is unconditionally off and there is no host FS.
2. **Boxed cwd helper** — build an ephemeral `FilesystemConfig(path_allowlist=[str(scratch)],
   path_denylist=[])` and call `_filesystem_check(cwd or str(scratch), ephemeral_cfg,
   CheckMode.DIRECTORY)`. **`path_denylist=[]` is REQUIRED, not stylistic** (design-review):
   omitting it applies the default 19-entry `DEFAULT_PATH_DENYLIST` — pass the explicit empty
   list so no default denylist is in play. Import `CheckMode` function-locally, mirroring the
   existing `_cwd_check` pattern (`execution.py:353`); `FilesystemConfig` and `ConstraintError`
   are already module-level imports (`execution.py:40-41`). `model_post_init` canonicalizes
   the allowlist (a str scratch resolves correctly); the allowlist check's `canonical == r`
   branch covers the scratch-root itself (not just subdirs). Return the canonical Path.
3. Keep both functions adjacent to `_build_tool_profile` (`execution.py:424`) for locality.
   Do NOT wire them into `ShellTool`/`PythonExecTool`/sessions here — that's legs 3–4.

## Edge Cases

- **Scratch must exist before the cwd check** (`is_dir()` will fail otherwise) — but scratch
  CREATION is legs 3–4. The unit tests here create a real temp dir to stand in for the
  scratch. Document that the caller (legs 3–4) must create the scratch before calling.
- **`FilesystemConfig` post-init cost**: building an ephemeral config per call is cheap;
  fine for the per-call/per-send path.
- **Stringification**: match `_build_tool_profile`'s `str(p)` convention so the backend's
  `--bind` gets a real absolute path.

## Files Affected

- `the_one/tools/execution.py` — `_build_boxed_profile` + boxed cwd helper.
- `tests/test_execution_tools.py` (or the existing unit-test home for execution helpers)
  — unit tests for both.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to `landed`,
> signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified; cwd-honoring decision recorded
- [x] Unit tests green (6 new tests); full default suite + ruff green (no new regressions)
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
