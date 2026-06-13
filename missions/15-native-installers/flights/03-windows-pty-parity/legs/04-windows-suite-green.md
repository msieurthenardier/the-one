# Leg: windows-suite-green

**Status**: landed
**Flight**: [Windows PTY Parity (ConPTY)](../flight.md)

## Objective

Narrow the `windows-2022` CI lane from the full default suite to the **curated
platform-relevant subset** (DD7 revised — CI-minutes pressure), make that subset
**green** on Windows by triaging its platform-divergent failures, and flip the
curated Windows job to **required**.

## Context

- **DD7 REVISED (2026-06-14, operator):** the Windows lane runs only the
  OS-divergent subset, not the full suite. Rationale (FD Note "DD7 narrowed"):
  ~86% of what ran on Windows was platform-agnostic (DB/connectors/web/LLM/
  MCP-protocol) — green on Linux ⇒ ~zero Windows signal — and the Windows lane
  (~25 min × 2× billing) is the dominant CI cost. Full suite stays the source of
  truth on **Linux**.
- **The curated subset** (the OS-divergent surface, non-bwrap): see the CI-job
  change below. ~427 tests vs ~3050 — est. Windows run ~25 min → ~5 min.
- **Backend parity is already proven** (Leg 2: test_pty_windows 7/7; Leg 3
  orphan-reap: see the flight-log Leg-3 CI entry — fold any failures in). This
  leg is the CI-curation + test-side Windows-awareness triage, NOT backend work.
- **3 of the 22 Windows failures drop out of scope** under curation (their files
  are agnostic, now Linux-only): `test_provider_repository` (timestamp),
  `test_token_definitions` (encoding), `test_mcp_stdio_sandbox` (one env test).
  They stay green on Linux. **Deferred, not lost** (see "Dropped" below).
- Operator action: the **branch-protection / required-checks flip** for the
  (curated) `windows` job needs repo admin — the FD coordinates.

## Inputs

- `.github/workflows/test.yml` — the non-required `windows` job runs
  `python -m pytest tests/ …` (full suite). To be narrowed.
- The 22 Windows failures (flight-log inventory); ~19 are in the curated subset.
- Leg-3 CI orphan-reap result (flight-log Leg-3 CI entry) — fold in if it failed.

## Outputs

- `.github/workflows/test.yml` — `windows` job runs the **curated subset** (not
  `tests/`), green; branch protection updated (operator) so it is required.
- Triaged subset test files (parametrized / POSIX-gated / Windows-aware env).
- Updated flight log: final triage dispositions + the dropped-tests deferral.

## CI-job change (the headline deliverable)

Replace the `windows` job's `python -m pytest tests/ …` with the curated subset.
**Recommended mechanism — explicit file list** (lowest friction, transparent,
no test-file churn for a "call it good for now" scope):

```yaml
      - name: Run platform-relevant subset (Windows — DD7 revised)
        run: |
          python -m pytest --timeout=300 --tb=short \
            tests/test_platform_paths.py tests/test_platform_shell.py \
            tests/test_platform_interpreter.py tests/test_platform_tempdirs.py \
            tests/test_pty_dispatch.py tests/test_pty_session.py tests/test_pty_windows.py \
            tests/test_filesystem_tools.py tests/test_filesystem_helpers.py \
            tests/test_filesystem_config.py \
            tests/test_config.py tests/test_config_data_dir.py \
            tests/test_execution_tools.py tests/test_execution_helpers.py \
            tests/test_execution_config.py \
            tests/test_encryption.py \
            tests/test_sandbox_factory.py tests/test_sandbox_contract.py \
            tests/test_logging_config.py
```
- The default `addopts -m '…'` deselects still apply, so any `requires_bwrap`/
  `browser` tests inside listed files are excluded automatically.
- **Add a loud comment** in the workflow: this list is the Windows-relevant
  surface; a NEW platform-divergent test file must be added here or it won't run
  on Windows. (Future refinement, noted not done: a `cross_platform` pytest
  marker — idiomatic with the project's marker convention — auto-includes new
  files; deferred to keep this leg's churn low. If adopted, the Windows job runs
  `-m "cross_platform and not requires_bwrap and not browser and not live and
  not pixel and not discord_hat"` — the full expression, since command-line `-m`
  replaces addopts `-m`.)

## Triage map — the ~19 in-subset failures

**(A) `~`-expansion lands outside the allowlist on Windows (8) → patch `USERPROFILE` in setup**
`test_filesystem_tools.py` ×7 `test_tilde_expansion`,
`test_filesystem_helpers.py::test_tilde_path_canonicalizes_via_expanduser`.
**Actual CI failure** (not an assertion problem — corrected at design review via
the real log): `[error] [constraint] path 'C:\Users\runneradmin\y.txt'
outside allowlist`. Root cause: the tests monkeypatch `HOME=tmp_path` (which they
add to the filesystem allowlist), but on Windows `os.path.expanduser("~")`
resolves to the **real `USERPROFILE`** (`C:\Users\runneradmin`), NOT the
patched `HOME` — so the write target is the real home, outside the allowlisted
tmp_path. **Fix (setup-side):** in the test setup, also
`monkeypatch.setenv("USERPROFILE", str(tmp_path))` (and `HOMEDRIVE`/`HOMEPATH`
defensively) so `expanduser` resolves into the allowlisted dir on Windows. The
assertions (`"home content" in result`, `result.startswith("Wrote")`) are
correct as-is. *(Product-side note, OUT of scope: whether the real Windows user
home should be in the default FilesystemConfig allowlist is a Flight-5/follow-up
question — not this leg.)*

**(B) cmd.exe vs POSIX command strings → DD10 split**
`test_execution_tools.py`, `test_platform_shell.py`. From the real CI messages:
- `test_output_truncated_at_cap` uses `for i in $(seq 1 200); do…` → cmd.exe:
  *"i was unexpected at this time."* It targets the *output-cap wrapper*, so
  **parametrize** with a Windows output generator (`for /l %i in (1,1,200) do
  @echo line %i`, or a `python -c` loop) rather than POSIX-gating — keeps the
  cap behavior covered on Windows.
- `test_cwd_outside_allowlist_refused` (Shell+PythonExec): `/etc`→`D:\etc` on
  Windows → parametrize the outside path per-OS.
- `test_cwd_default_is_home`: same USERPROFILE/allowlist issue as Bucket A —
  the default cwd (home) isn't the allowlisted tmp_path on Windows; fix via the
  same `USERPROFILE` setup patch.
- `test_timeout_returns_promptly` / `test_platform_shell` timeout+env: parametrize
  the command with a cmd.exe equivalent (`timeout`/`set`) or POSIX-gate if it
  asserts POSIX shell semantics. Triage each against its real message.

**(C) POSIX file perms (1) → POSIX-gate**
`test_encryption.py::test_key_file_permissions` (0600) → `skipif(os.name != "posix")`.

**(D) DD5 env-allowlist (3 in-subset) → split: assertion-side union vs POSIX-gate**
- `test_execution_helpers.py::test_returns_only_allowlisted_keys` and
  `test_execution_tools.py::TestPythonExecTool::test_env_allowlist_invariant`:
  these read the env directly (no shell), so on Windows they see the
  POSIX+Windows union. **Fix (assertion-side):** assert membership in
  `set(_ENV_ALLOWLIST) | (set(_WINDOWS_ENV_ALLOWLIST) if os.name == "nt" else set())`.
  **`_WINDOWS_ENV_ALLOWLIST` is NOT re-exported from `the_one.tools.execution`**
  (design review) — import it as `from the_one.platform.env import
  _WINDOWS_ENV_ALLOWLIST`. Keep `test_execution_helpers.py:273`'s exact-tuple
  pin as-is.
- `test_execution_tools.py::TestShellTool::test_env_allowlist_invariant`:
  **POSIX-gate** (`skipif(os.name != "posix")`). It runs the env dump through
  cmd.exe, which **injects its own vars** (CI showed extras `PROMPT`, `!C:`,
  …) — so "subprocess env == only our allowlist" is unassertable on Windows.
  The function-level invariant is already covered by the helper test above.

## Dropped from Windows scope (deferred, not lost)

- `test_provider_repository.py::test_update_changes_fields` — `updated_at`
  collides under fast update on Windows' coarse clock (F1-`last_activity`
  flavored). Real test fragility but agnostic file → Linux-only now. **Deferred**
  to a maintenance follow-up (or fix opportunistically if touched).
- `test_token_definitions.py::test_every_var_reference_is_defined` — cp1252
  `UnicodeDecodeError` from unencoded `read_text()`. Agnostic file → Linux-only.
  **The product-code unencoded-open audit it flagged moves to Flight 5** (frozen
  Windows app) — recorded in the FD Note so it isn't silently lost.
- `test_mcp_stdio_sandbox.py::test_connect_stdio_sdk_default_env_preserved` —
  env test in a bwrap-heavy file → Linux-covered.

## Acceptance Criteria

- [ ] `.github/workflows/test.yml` `windows` job runs the curated file list (not
      `tests/`), with the loud maintenance comment.
- [ ] The ~19 in-subset failures are triaged (A–D above): parametrized,
      POSIX-gated, or Windows-aware — and the curated Windows lane is **GREEN**
      (0 failures; skips/xfails acceptable with reasons).
- [ ] **Leg-3 orphan-reap test fix (folded in):** `test_close_reaps_grandchild`
      failed on its precondition (grandchild never wrote its PID — quoting of the
      inline `start /b "" python -c "…"` through cmd.exe-through-PTY mangled the
      Windows backslash path). Re-mechanism it to launch the grandchild from a
      **temp `.py` file** (write the script to a NamedTemporaryFile, then
      `start /b "" "{sys.executable}" "{script_path}"` — **quote both paths**
      (design review: spaces/backslashes in `%TEMP%` paths)) so there's no
      quoting-through-PTY; the script writes its own PID + sleeps. Then the
      existing Job-Object reap assertion runs. If still unreliable on CI after
      this, `xfail(reason=…)` and defer the definitive proof to the operator's
      Windows box (do NOT silently drop). The Job Object *code* is unchanged
      (Leg 3) — this is a test-harness fix only. **Do NOT touch the existing
      `test_parent_death_reaps_grandchild` xfail** (it has the same inline-`-c`
      quoting shape — leave it xfailed; "fixing" it risks a wrong-reason
      pass/fail).
- [ ] Linux (`test`/`bwrap`/`browser`) + lint remain green — the triage edits
      must not change POSIX behavior; the full suite still runs on Linux.
- [ ] The curated `windows` job is wired into branch protection as **required**
      (operator action — FD coordinates; record completion).
- [ ] The 3 dropped tests are recorded as deferred in the flight log (the
      encoding-audit explicitly handed to Flight 5).

## Verification Steps

POSIX-side (implementing agent, locally):
- `.venv/bin/python -m pytest <the curated file list> --timeout=60 -q` — all green on Linux (triage edits must not break POSIX).
- Full default suite `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green.
- `ruff check` / `format --check` — clean.

Windows-side (Flight Director, post-push, `windows-2022` lane):
- The curated subset runs **green** (0 failed) and noticeably faster (~5 min).
- Then: operator flips branch protection → FD marks the curated job required.

## Implementation Guidance

1. Edit the `windows` job in `test.yml` to the curated file list + comment.
2. Triage A–D in the listed files only. Prefer `@pytest.mark.parametrize` over
   duplicate tests; `skipif(os.name != "posix", reason=…)` at test level for
   semantics/perms. For (D), import the real allowlist constants — don't hardcode.
3. Do NOT touch the PTY backend / Job Object code (Legs 2-3). Do NOT fix the 3
   dropped tests here (they're Linux-green and out of the curated subset).
4. The branch-protection flip is the LAST step, an operator action — the FD
   coordinates after the curated lane is green; the agent does not touch repo
   settings.

## Notes for the Flight Director (post-implementation)

- Push → confirm the curated `windows` lane is green AND faster (record the new
  wall-clock + test count vs the ~25 min / ~3050 baseline — quantify the saving).
- Reconcile against the Leg-3 CI result before finalizing scope.
- THEN coordinate the operator's branch-protection flip; record completion.
- Confirm the dropped-tests deferral (esp. the Flight-5 encoding audit) is in the
  flight log.
