# Leg: verify-integration

**Status**: completed
**Flight**: [Sandbox Seam + Built-in Tool Retrofit](../flight.md)

## Objective

Final verification + documentation for the flight: run the full default suite and the
complete `-m requires_bwrap` containment suite green, confirm the passthrough path
does not error when `bwrap` is absent, pass the ruff gate, and update the project's
canonical docs (`the_one/agents.md`, `CLAUDE.md`) to describe the now-platform-wide
seam, the host-workspace profile, the `sandbox_network_allowed` knob, and the
read-scoping deferral. No new product behavior — this leg proves and documents what
legs 1–4 built.

## Context

- This is the last autonomous leg. Legs 1–4 landed (uncommitted): the rename, the
  factory + passthrough + overlay + profile-driven HOME, the MCP retrofit, and the
  built-in tool seam.
- The flight's Verification section and Checkpoints define what "done" means; this
  leg executes that matrix and records the result.
- **Doc target:** `the_one/agents.md` already has an authoritative "MCP F3 Sandbox"
  section (around `agents.md:605` — `### MCP F3 Sandbox (authoritative for F4+)`),
  with point 6 (HOME policy) already updated by leg 2. The seam is no longer
  MCP-only, so the docs must describe the platform-wide shape.
- **DD4/DD5 resolution (carry forward):** the denylist overlay is **write-protection
  only** (read-scoping deferred). Docs and any verification wording must say
  "denylisted secrets are not *writable*", not "not readable". (See leg 4's flight-log
  entry.)

## Inputs

What exists before this leg runs (post-leg-4, landed):
- The full seam: `the_one/platform/sandbox/{base,bubblewrap,passthrough,factory}.py`;
  MCP via `get_sandbox_backend()` in `stdio.py`; built-in tools via
  `_build_tool_profile` + the optional `profile` seam path in
  `platform/{shell,interpreter}.py`.
- Tests: `tests/test_sandbox_factory.py`, `test_sandbox_bubblewrap.py`,
  `test_sandbox_contract.py`, `test_mcp_stdio_sandbox.py`,
  `test_mcp_sandbox_integration.py`, `test_builtin_tool_sandbox.py` (new in leg 4),
  `test_execution_tools.py` (passthrough-pinned), `test_platform_shell.py` /
  `test_platform_interpreter.py` (legacy path).
- `pyproject.toml` — `requires_bwrap` marker (count comment updated to 7 in leg 4),
  deselected by default `addopts`.
- `the_one/agents.md` — the "MCP F3 Sandbox" reference section.
- `CLAUDE.md` — testing notes incl. the `requires_bwrap`/`test_mcp_pool` run
  instructions (`CLAUDE.md:129`).
- **Environment note:** the canonical dev/test environment is the Docker container
  (`docker exec the-one …`), which has `bwrap` + the §10 privilege grants. A separate
  bwrap-less "host-native" Python environment is not assumed available; the bwrap-less
  behavior is proven by *simulation* (the factory's bwrap-missing/non-Linux unit tests
  + the passthrough-pinned `test_execution_tools.py`), not a second real environment.
  A genuine host-native CI run remains a Mission-15 concern (the flight prereqs note
  "no pytest CI yet").

## Outputs

After this leg:
- A recorded green run of: the full default suite; the complete `-m requires_bwrap`
  suite; `ruff check` + `ruff format --check`.
- A recorded confirmation that the passthrough path (simulated bwrap-missing) does not
  error end-to-end (built-in tool + MCP both route through passthrough cleanly).
- `the_one/agents.md` updated: the sandbox section describes the platform-wide seam
  (factory + passthrough + the four spawn paths, three wired this flight), the
  host-workspace profile, `sandbox_network_allowed`, and the write-only overlay /
  read-scoping deferral.
- `CLAUDE.md` updated: the testing note references the built-in-tool containment
  suite and how to run the full `requires_bwrap` set.
- Flight-log entry summarizing the verification matrix and its results.

## Acceptance Criteria

- [x] Full default suite green: `docker exec the-one pytest --timeout 60` — record
      the pass/skip/deselect counts. (The known pre-existing
      `test_connectors_e2e.py::test_e2e_full_lifecycle` failure, if present, is called
      out as not-a-regression; everything else passes.)
- [x] Complete containment suite green: `docker exec the-one pytest -m requires_bwrap
      --timeout 120` runs **all** `requires_bwrap` tests (built-in containment + MCP
      integration + pool) and they pass. Record the count (expected 7).
- [x] Passthrough no-error confirmed: with `bwrap` simulated-absent (or the test
      double-flag), a built-in tool **and** an MCP spawn both route through
      `PassthroughSandbox` and run without raising at construction/connect — recorded
      (the passthrough-pinned `test_execution_tools.py` + the factory/MCP passthrough
      tests already demonstrate this; cite them, or add a focused smoke if a gap
      exists).
- [x] Ruff gate green (canonical CI scope): `ruff check the_one/ tests/` and
      `ruff format --check the_one/ tests/` (matches `Makefile`/`lint.yml`; `.` would
      additionally lint `scripts/` and diverge from CI).
- [x] `the_one/agents.md` sandbox section updated to describe: (a) the seam is now
      platform-wide (built-in shell/python + MCP route through one
      `get_sandbox_backend()` boundary; PTY is Flight 2); (b) backend selection
      (bubblewrap on Linux+bwrap, passthrough otherwise — no construction-time error
      off-Linux); (c) the built-in-tool **host-workspace** profile (writable =
      `FilesystemConfig` allowlist; denylist via the read-only `--ro-bind-try`
      overlay; real `$HOME`; network deny-by-default); (d) the
      `ExecutionConfig.sandbox_network_allowed` knob; (e) the overlay is
      **write-protection only** and read-scoping is deferred.
- [x] **`the_one/agents.md` now-false claims CORRECTED** (not just augmented):
      - The "MCP F3 Sandbox" point that says bwrap-missing raises `SandboxError` /
        "NO unsandboxed fallback in production" (~`agents.md:613`) — corrected to:
        bwrap-missing now routes through `PassthroughSandbox` via the factory (a
        one-time WARNING on Linux, no construction error), per the mission criterion
        "runs through the seam via a passthrough and does not error … absence of
        enforcement is observable (logged), not silent." (Construction-time
        `SandboxError` is gone from the spawn sites; runtime bwrap-stderr translation
        on the MCP path still raises `SandboxError`.)
      - The "Subprocess environment invariant" section (~`agents.md:677`) — the call
        sites are stale: `_build_subprocess_env()` is now called from
        `the_one/tools/shell.py` and `the_one/tools/python_exec.py` (the platform
        layer receives the already-filtered env), not built in `platform/shell.py` /
        `platform/interpreter.py`. Correct the named call sites; the 8-key allowlist
        invariant itself still holds.
      - The "Constraint surface" table (~`agents.md:660`) — add a row for
        `ExecutionConfig.sandbox_network_allowed` (`Narrow`; applies to `shell`,
        `python_exec`).
- [x] **`the_one/mcp/README.md`** sandbox section updated where it describes the old
      direct `BubblewrapSandbox()` construction / bwrap-not-found-raises / double-flag
      bypass — these are now the factory's behavior (`get_sandbox_backend()`); correct
      the attribution (bwrap-missing → passthrough, not raise).
- [x] **`SECURITY-MODEL.md`** corrected where it (a) names stale env call sites
      (`shell.py::run_shell` / `interpreter.py::run_python`) and (b) understates the
      execution posture as denylist-trip-wire-only — note the new OS-level bwrap fence
      for built-in tools (host-workspace profile, network deny-by-default).
- [x] **`README.md`** — the MCP-is-sandboxed / built-in-tools-silent asymmetry
      (~`README.md:82`) corrected so built-in tools are described as sandboxed too
      (one sentence; README is high-churn — keep it minimal).
- [x] `CLAUDE.md` updated: the test-running note mentions `tests/test_builtin_tool_sandbox.py`
      and `pytest -m requires_bwrap` for the full containment set.
- [x] `pyproject.toml` — the `# Per-marker deselect math …` comment count
      (`requires_bwrap=N`, `total=N`) refreshed to the actual current counts (leg 4
      bumped `requires_bwrap` to 7; total shifted too). Comment-only; not a gate.
- [x] No source/behavior changes beyond docs (this is a verify+docs leg). If
      verification surfaces a real defect, fix it and record it as a deviation — do
      not paper over.

## Verification Steps

- `docker exec the-one pytest --timeout 60` — full default suite.
- `docker exec the-one pytest -m requires_bwrap --timeout 120` — full containment set.
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/ tests/`.
- Passthrough smoke (simulated bwrap-missing), e.g.:
  `docker exec the-one python -c "import the_one.platform.sandbox.factory as f; import shutil; orig=shutil.which; f.shutil.which=lambda _:None; from the_one.platform.sandbox import get_sandbox_backend, PassthroughSandbox; assert isinstance(get_sandbox_backend(), PassthroughSandbox)"`
  (or simply cite the passthrough-pinned `test_execution_tools.py` run as the
  end-to-end proof that built-in tools execute through passthrough without error).

## Implementation Guidance

1. **Run the verification matrix** (full suite, requires_bwrap set, ruff) and capture
   the exact counts/results for the flight log. If anything other than the known
   pre-existing failure fails, fix it (it's a regression introduced by this flight)
   and note it.

2. **Confirm passthrough no-error** end-to-end. The strongest existing evidence:
   `test_execution_tools.py` runs every built-in-tool unit test under passthrough
   (leg 4's autouse pin) and is green → built-in tools execute through the passthrough
   seam without error. For MCP, the leg-3 passthrough/bwrap-missing tests cover it.
   Cite these in the flight log; add a one-off smoke only if you find a genuine gap.

3. **Update `the_one/agents.md` — augment AND correct.** Extend the existing sandbox
   section (don't fork a competing one). Add bullets describing: the seam is now
   platform-wide (M14 F1); the `get_sandbox_backend()` factory + `PassthroughSandbox`
   (off-Linux/bwrap-missing → passthrough, one-time WARNING, no construction error);
   the built-in-tool host-workspace profile via `_build_tool_profile` (writable
   allowlist, `--ro-bind-try` denylist overlay, real `$HOME`, `sandbox_network_allowed`
   deny-by-default); and that the overlay is write-protection only with read-scoping
   deferred. **Then correct the now-stale/false claims** (see the AC for the exact
   list): point 4's "bwrap-missing → `SandboxError` / NO unsandboxed fallback"; the
   "Subprocess environment invariant" call sites; and the "Constraint surface" table
   (add `sandbox_network_allowed`). Keep the still-accurate MCP-specific points (HOME
   `/tmp` default for MCP, privilege model, the runtime bwrap-stderr→`SandboxError`
   translation). Frame the destination semantically; don't leak operator paths.

4. **Update the other doc surfaces (the verify leg owns doc-sync):**
   - `the_one/mcp/README.md` — fix the sandbox paragraphs that attribute bwrap-missing
     handling / the double-flag bypass to the old direct `BubblewrapSandbox()`
     construction; they're now the factory's behavior.
   - `SECURITY-MODEL.md` — fix the stale env call sites and note the new bwrap fence
     for built-in tools (don't overstate — read-scoping is deferred; the overlay is
     write-protection).
   - `README.md` — one sentence so built-in tools read as sandboxed too (fix the
     MCP-only-sandboxed asymmetry).
   - `CLAUDE.md` — near the existing `requires_bwrap`/`test_mcp_pool` note
     (`CLAUDE.md:129`), add that built-in-tool containment is proven by
     `tests/test_builtin_tool_sandbox.py` and the full set runs via
     `pytest -m requires_bwrap`.
   - `pyproject.toml` — refresh the `# Per-marker deselect math …` count comment.
   For each, prefer correcting the false/stale claim over leaving it beside the new
   text. If a surface turns out to need a larger rewrite than a verify leg should
   carry, make the minimal correction and flag the rest in the flight log for a
   maintenance cycle — do not leave a standing falsehood.

5. **Record** the verification results in the flight log (counts, ruff status,
   passthrough confirmation, the list of doc surfaces corrected, any deviation or
   flagged-for-later doc debt).

## Edge Cases

- **Write-only wording.** Per the DD4/DD5 resolution, never document or assert that
  denylisted secrets are unreadable — only that they are not writable. Read-scoping is
  a later flight.
- **No behavior changes.** If a doc update tempts a code tweak, stop — that belongs in
  a code leg, not the verify leg. The only code change permitted here is fixing a real
  regression the verification surfaces (recorded as a deviation).
- **Don't check off flight/mission here.** In this batched flight, the flight→`landed`
  transition, the flight.md checkpoint/criteria checkboxes, and the mission checkbox
  are handled in the flight-level commit/landing phase (after the single Reviewer
  pass), not by this leg.
- **"host-native" run.** Satisfied by simulation given the single available
  environment (see Inputs); record that the genuine bwrap-less host/CI run is a
  Mission-15 concern, consistent with the flight prereqs.
- **Pre-existing failure.** `test_connectors_e2e.py::test_e2e_full_lifecycle` — if it
  is the only failure, it is not a regression; note it and proceed.
- **`-x` omitted deliberately.** The verification commands omit `-x` so the **full
  failure surface** is recorded (this leg must enumerate every failure, not just the
  first). Trade-off: a wedged test can hang the run. If the suite produces no output /
  doesn't complete after ~5 min, kill it and re-run with `-x` to isolate the hang,
  then fix it.

## Files Affected

- `the_one/agents.md` — extend the sandbox section to the platform-wide seam,
  host-workspace profile, `sandbox_network_allowed`; **correct** the false
  bwrap-missing/`SandboxError`/no-fallback claim, the stale env call sites, and add
  the `sandbox_network_allowed` constraint-surface row.
- `the_one/mcp/README.md` — correct the factory-vs-direct-construction attribution.
- `SECURITY-MODEL.md` — correct stale env call sites; note the bwrap fence.
- `README.md` — built-in tools described as sandboxed (asymmetry fix).
- `CLAUDE.md` — testing note for the built-in containment suite + full
  `requires_bwrap` run.
- `pyproject.toml` — refresh the marker-count comment.
- (Only if a regression is found) the offending source file — fix + record as a
  deviation.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (full suite + full `requires_bwrap` set)
- [x] Update flight-log.md with leg progress entry (verification matrix results)
- [x] Set this leg's status to `completed` (in this file's header) — promoted at
      the flight-level commit phase (was `landed` during batched execution)
- [x] Check off this leg in flight.md — completed at flight-level commit phase
- [x] If final leg of flight: flight→landed / mission checkbox — completed at
      flight-level commit/landing phase
- [x] Commit all changes together (code + artifacts) — flight-level commit

> **Note (batched flight):** Implementing Developer does **not** commit and does
> **not** signal `[COMPLETE:leg]` — set the leg to `landed`, update the flight log,
> signal `[HANDOFF:review-needed]`. The flight-level review, commit, flight→landed,
> and checkbox updates happen in Phase 2d/3.
