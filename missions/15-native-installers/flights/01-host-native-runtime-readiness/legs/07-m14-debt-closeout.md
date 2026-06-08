# Leg: m14-debt-closeout

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

Close the surviving Mission-14 end-of-mission maintenance debt folded into this flight:
add the two genuinely-missing docs, record the already-satisfied items as
closed-with-evidence, and resolve the `test_connectors_e2e` flake (fix or quarantine
with rationale).

## Context

- **Source** — the M14 mission-debrief maintenance action items, reconnaissance-verified
  at flight planning (see the flight log's Reconnaissance Report). Of the cited items,
  only **2 doc notes** are genuinely missing and **1 flake** needs a live recheck;
  everything else is already satisfied (retire as closed-with-evidence, not silently
  dropped).
- **Independent** of Legs 1-6 (docs + one test). Runs last so any host-native changes
  from earlier legs are settled.
- Editing `agents.md` is known to work for agents (Leg 1 edited it); `CLAUDE.md` edits may
  be blocked by a self-modification guard — if so, the Flight Director updates `CLAUDE.md`
  in the flight's documentation phase, not this leg.

## Inputs

- `SECURITY-MODEL.md` — has the boxed-profile network-off note (`:154-158`) but **not** the
  non-merged-usr `--symlink` caveat.
- `agents.md` — mentions `pty.fork()` only in passing (`:751`); no fork-safety convention.
- `the_one/platform/sandbox/bubblewrap.py` — the boxed `minimal_rootfs` branch with the
  `--symlink` bind logic the caveat documents.
- `tests/test_connectors_e2e.py::test_e2e_full_lifecycle` (`:121-173`) — the suspected flake.

## Outputs

- `SECURITY-MODEL.md` gains a non-merged-usr `--symlink` portability caveat in its boxed
  execution section.
- `agents.md` gains a fork-safety convention near its PTY/fork discussion.
- The `test_connectors_e2e` flake is fixed at root cause (preferred) or, if not
  reproducible/unfixable in scope, quarantined with a documented rationale.
- The flight log's debt-closeout records the already-satisfied items as closed-with-evidence.

## Acceptance Criteria

- [x] `SECURITY-MODEL.md` documents, in its boxed-execution section, that the boxed
      `minimal_rootfs` `--symlink` binds assume a Debian/Ubuntu **merged-usr** layout, and
      states the portability caveat for non-merged-usr systems (referencing the
      `bubblewrap.py` boxed branch).
- [x] `agents.md` documents a **fork-safety convention** for the PTY spawn path: the parent
      must not be in a state that makes `fork()` unsafe (no work between `fork()` and
      `execvp()` beyond async-signal-safe operations; note the multi-threaded-parent
      hazard). Place it near the existing `pty.fork()` reference.
- [x] `test_connectors_e2e.py::test_e2e_full_lifecycle` is run under repeat/load
      (e.g. `pytest -p no:randomly tests/test_connectors_e2e.py::test_e2e_full_lifecycle
      --count=50` via `pytest-repeat` if available, else a shell loop) to characterize the
      flake; the root cause is fixed (preferred) or the test is quarantined with a
      `@pytest.mark.flaky`/`skip` + an inline rationale comment **and** a flight-log note.
      No silent papering. (Not reproducible — 30/30 passes. No code change needed.)
- [x] The already-satisfied M14 items are recorded as closed-with-evidence in the flight
      log debt-closeout entry (boxed network-off note, `_TOOL_CLASSES` note,
      `@requires_bwrap` $HOME constraint, PTY-echo sentinel, `network_allowed` hardcode,
      boxed-session reaper test — each with its citing location).
- [x] Full suite + `ruff` clean host-native (`.venv`).

## Verification Steps

- `grep -in "merged-usr\|symlink" SECURITY-MODEL.md` → shows the new caveat.
- `grep -in "fork-safe\|fork safety\|async-signal" agents.md` → shows the convention.
- Flake characterization: `.venv/bin/python -m pytest tests/test_connectors_e2e.py::test_e2e_full_lifecycle --timeout=60 -q` run repeatedly (or with `--count=N`) → record pass/fail ratio before and after the fix.
- `.venv/bin/python -m pytest tests/ --timeout=300 -q` full suite green; `.venv/bin/ruff check . && .venv/bin/ruff format --check .` clean.

## Implementation Guidance

1. **Non-merged-usr caveat** (`SECURITY-MODEL.md`, boxed-execution section) — read the
   boxed `minimal_rootfs` branch in `bubblewrap.py` (the `--symlink`/`--ro-bind` set for
   `/usr`, `/bin`, `/lib*`). Document that this mount set assumes merged-usr (where `/bin`,
   `/lib` are symlinks into `/usr`); on a non-merged-usr host the boxed rootfs may need
   explicit binds for the split directories. Keep it factual and brief; cite the code.

2. **Fork-safety convention** (`agents.md`, near `:751`) — add a short convention: the PTY
   child is created with `pty.fork()`; between `fork()` and `execvp()` only async-signal-safe
   operations are permitted (no Python-level allocation/logging/locks), and the parent should
   avoid spawning from a multi-threaded context where fork-without-exec is unsafe. Mirror the
   existing footgun-note style in that file.

3. **Flake** — characterize first. Read `test_e2e_full_lifecycle` (`:121-173`): it seeds a
   stub connector, acquires/ages a pool entry, triggers the reaper (`_reap_once`), and drains.
   Suspected cause (recon): an `aiosqlite` event-loop-teardown race or a lingering pool-reaper
   task across tests. Run it many times to reproduce. If a deterministic root cause appears
   (e.g. an unawaited task, a missing `await`, a fixture-ordering race), fix it. If it cannot
   be reproduced under load, record that (it may already be mitigated by earlier legs'
   changes) and leave it as-is with a flight-log note. Only quarantine (`@pytest.mark.flaky`
   or `skip` + rationale) if it reproduces and a root-cause fix is out of scope — and say so
   explicitly in the log.

4. **Record retirements** in the flight-log debt-closeout entry (the already-satisfied set,
   each with the location that satisfies it — from the Reconnaissance Report).

5. **Run `ruff` + full suite** host-native.

## Edge Cases

- **`CLAUDE.md` edit blocked** — if adding any note to `CLAUDE.md` is rejected by a
  self-modification guard, leave it and flag in the flight log for the Flight Director to
  apply in the documentation phase. (This leg's required doc edits are in `SECURITY-MODEL.md`
  and `agents.md`, both editable.)
- **Flake not reproducible** — absence of a reproduction is a valid outcome; document it
  rather than forcing a change. Do not quarantine a test that isn't actually flaking.
- **`pytest-repeat` absent** — use a shell `for` loop over the single test id instead of
  `--count`.

## Files Affected

- `SECURITY-MODEL.md` — non-merged-usr `--symlink` caveat (boxed section).
- `agents.md` — fork-safety convention.
- `tests/test_connectors_e2e.py` — only if the flake is fixed or quarantined (root-cause
  fix preferred; may also touch the relevant connector/pool source if the race is there).

---
