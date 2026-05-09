# Leg: 02-bwrap-error-translation

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## Objective

Translate bwrap-side post-setup errors (writable-path nonexistent, namespace creation refused, generic exit-code != 0) from F2's catch-all `MCPConnectionError` into `MCPSandboxError` with the F3 §6 catalog messages. Mechanism: pass a `tempfile.SpooledTemporaryFile(mode='w+')` as the SDK's `errlog=` parameter to `stdio_client(...)`; on transport-CM failure, seek-and-read the captured bwrap stderr, pattern-match, and re-raise as the appropriate catalog `MCPSandboxError`. Flip the L5a Test #6 expectation from `MCPConnectionError` to `MCPSandboxError`. Drop the "L4 enforces the boundary" language from CLAUDE.md F3 contracts §5 and `the_one/agents.md` (this leg IS L2, but the post-deviation L1a left transports unchanged, so the boundary enforcement is in this leg).

## Context

### Flight design decisions

- **§6 (A02 bwrap-stderr capture translation)**: capture bwrap stderr via the SDK's `stdio_client(server, errlog=...)` parameter (verified at `.venv/lib/python3.12/site-packages/mcp/client/stdio/__init__.py:106` — `errlog: TextIO = sys.stderr`). After the SDK's transport CM raises, `errlog.seek(0); stderr_text = errlog.read()`; inspect for known bwrap-error signatures and translate to the matching catalog message.
- **§6 (mechanism — locked at flight design)**: `tempfile.SpooledTemporaryFile(mode='w+')` is preferred over raw `os.pipe()` because it satisfies the SDK's `TextIO` type directly (no `os.fdopen` dance); no reader-side draining needed (the file accumulates in memory up to the spool limit; post-exit `seek(0); read()` retrieves everything); cleanup automatic via context-manager semantics.
- **§6 (signature matching — committed at L2 design via probe)**:
  - `"Can't find source path"` → catalog message #1 (writable_paths nonexistent)
  - bwrap stderr starts with `"bwrap:"` AND contains `"unshare"` (or `"user ns"`) AND `"Operation not permitted"` (in any order — bwrap's actual format is `bwrap: <context-with-unshare>: Operation not permitted`, NOT the reverse) → catalog message #3 (EPERM on unshare)
  - bwrap stderr starts with `"bwrap:"` and matches no other pattern → catalog message #2 (generic bwrap-failure fallback). The `bwrap:` prefix is bwrap's own error-line convention; using it as a discriminator distinguishes bwrap's own failures from inner-process failures.
  - **Critically**: if the captured stderr does NOT start with `"bwrap:"` and contains no recognised bwrap signature, `_translate_bwrap_stderr` MUST return None — letting F2's `MCPConnectionError` translation handle the (post-bwrap-success, child-process-failure) case. Cycle-1 reviewer caught a directionality bug in earlier drafts: any failing inner Python MCP server that writes to stderr and exits non-zero was being mistranslated as `MCPSandboxError("bubblewrap exited with code 1")` — that's a directionality regression and is explicitly forbidden by F3 §6's boundary contract.
- **§6 (L2 design authority)**: if the stderr-signature probe reveals patterns are not reliably emitted by `bwrap` 0.11.0 (locale-dependent, version-dependent), L2 has authority to adjust regex patterns inline OR drop signature (3) and emit message #2 for both bwrap-exit and EPERM cases. Major scope changes (dropping the entire translation) escalate per Adaptation Criteria.
- **§9 (L5a Test #6 expectation flip)**: `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` (lines 347-378) currently asserts `MCPConnectionError` and explicitly `not isinstance(exc_info.value, MCPSandboxError)` — flips to `MCPSandboxError` with substring match on catalog message #1.

### Carries forward

- F3 debrief Anomaly A02 + Action Item to land bwrap stderr translation in F4.
- Mission 07 known issue: `MCPSandboxError` exists in `the_one/mcp/errors.py` (verified at design 2026-05-07); `connect_stdio` does NOT inspect bwrap stderr/exit code. The F3 §6 boundary catalog of three messages is documented in CLAUDE.md F3 contracts §5 (line 332) but the boundary-enforcement-in-`connect_stdio` is currently deferred.
- L5a Test #6 currently has explicit defensive language ("locks the directionality... per L4 Anomaly A02") indicating the directionality flip is L4-scope.

### Why this leg lands third (after L1a, L1b)

L1a's AsyncExitStack refactor doesn't touch `connect_stdio`'s error path (post-deviation: `connect_stdio` is unchanged). L1b reorders argv unrelated to error translation. L2 is the first leg that actually modifies `connect_stdio`'s body — adding stderr capture and translation. This must precede L3 because L3's pool unit tests need the failure-mode catalog locked (some pool tests assert that connect-failures propagate as the correct exception class through the worker task).

## Inputs

What exists before this leg runs:

- `the_one/mcp/transports/stdio.py::connect_stdio` is `@asynccontextmanager`-decorated; uses nested `async with stdio_client(params) as (read, write): async with ClientSession(read, write) as session: yield session` (lines 166-190). No `errlog=` kwarg passed; bwrap stderr inherits the parent process's stderr.
- `the_one/mcp/transports/stdio.py` module docstring explicitly documents the gap (lines 49-54): "Per F3 §6's boundary, bwrap-side post-setup errors (`--bind` failures, `EPERM` on `unshare`) are not currently translated to `MCPSandboxError` inside this transport — see flight log Anomaly A02."
- `the_one/mcp/errors.py::MCPSandboxError` exists at lines 39-44 with docstring referencing F3 §6.
- `the_one/mcp/client.py::connect()` translates SDK transport errors into `MCPConnectionError` via the catch-all `except Exception` at lines 205-209 (post-L1a). When `connect_stdio` raises `MCPSandboxError`, that exception is a subclass of `MCPClientError`, which is matched by the `except (MCPClientError, NotImplementedError):` branch at lines 202-204 — re-raises unchanged. So `MCPSandboxError` propagates naturally; no `connect()` changes needed.
- `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` (lines 347-378) asserts:
  - `with pytest.raises(MCPConnectionError) as exc_info: async with MCPClient(source): pass`
  - `assert not isinstance(exc_info.value, MCPSandboxError)`
  - Module-list comment at line 28: "#6 Writable-path nonexistent — surfaces as MCPConnectionError"
- `tests/test_mcp_sandbox_integration.py` has 10 tests at the L2-start baseline. Test #6 flips, +2 new tests added → final count 12.
- Test counts at L2-start (post-L1b): `tests/test_mcp_client.py` 59, `tests/test_mcp_integration.py` 14, `tests/test_mcp_sandbox_integration.py` 10, `tests/test_mcp_stdio_sandbox.py` 9, `tests/test_sandbox_bubblewrap.py` 17, `tests/test_sandbox_contract.py` 14. Total: 123.
- `CLAUDE.md` F3 contracts §5 (line 332): "L2 adds the exception class; L4 enforces the boundary in `connect_stdio`." — the "L4 enforces" language is now stale (L2 — this leg — IS the enforcement).
- `the_one/agents.md` line 73: "L2 adds the exception class; L4 enforces." — same staleness.

## Outputs

What exists after this leg completes:

- `the_one/mcp/transports/stdio.py::connect_stdio` modified to:
  - Open a `tempfile.SpooledTemporaryFile(mode='w+', encoding='utf-8', errors='replace')` as the bwrap-stderr buffer (max_size default; in-memory until ~1KB, then spilled to disk).
  - Pass it as `errlog=...` to `stdio_client(params, errlog=...)`.
  - In the post-CM-failure path, seek and read the buffer; pattern-match against three known bwrap stderr signatures; raise the corresponding `MCPSandboxError` from F3 §6 catalog. If no pattern matches AND exit-code != 0, raise the generic-exit fallback (#2).
  - The `SpooledTemporaryFile`'s lifetime is bounded by a `try/finally` block — closed on success, closed on failure (after read), and never leaked.
- `the_one/mcp/transports/stdio.py` module docstring updated to drop the "currently not translated" language and replace with a one-line statement that A02 is resolved.
- `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` flipped:
  - `with pytest.raises(MCPSandboxError) as exc_info: ...`
  - Substring assertion: `"writable_paths entry" in str(exc_info.value) AND "does not exist" in str(exc_info.value)` (catches catalog message #1 verbatim).
  - The defensive `assert not isinstance(exc_info.value, MCPSandboxError)` is REMOVED (the assertion is now affirmative).
  - Test docstring rewritten to reflect the new directionality.
  - Module list at line 28 updated: "#6 Writable-path nonexistent — surfaces as MCPSandboxError (catalog #1)".
- THREE new tests in `tests/test_mcp_sandbox_integration.py`:
  - **#6b**: `test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2`: monkeypatches `BubblewrapSandbox.prepare_spawn` to inject `--no-such-flag-for-test-6b` into the args; bwrap rejects with `bwrap: Unknown option ...` which has the `bwrap:` prefix, no #1/#3 match, → catalog #2. Asserts `"bubblewrap exited non-zero"` and `"bwrap stderr:"` in the message.
  - **#6c**: `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3`: marker `@pytest.mark.skipif(_has_sys_admin(), reason=...)` — only meaningful in privilege-stripped envs; in the dev container (has SYS_ADMIN), this skips. Expects `MCPSandboxError` with catalog #3 substring (`"namespace creation refused"`).
  - **#6d (cycle-1 reviewer suggestion)**: `test_inner_process_failure_does_not_translate_to_sandbox_error`: locks the OTHER side of the directionality contract. Spawns a sandboxed source whose inner Python process fails post-bwrap-success with a stderr noise pattern that COULD superficially match catalog #2 if the prefix gate weren't there (e.g., the inner process prints `unshare failed` for unrelated reasons OR writes to its own stderr while exiting 1). Asserts `MCPConnectionError` (NOT `MCPSandboxError`) — i.e., F2's translation path still owns post-bwrap-success failures. Mechanism: monkeypatch the SpawnSpec's `command` to a path that exits 1 immediately while writing distinctive (but bwrap-prefix-LACKING) text to its stderr.
- `tests/test_mcp_sandbox_integration.py` count goes 10 → 13.
- The L2 design phase commits a STAKE-TEST PROBE that documents the actual stderr emitted by `bwrap 0.11.0` for each of the three failure modes — recorded as a comment block at the top of `connect_stdio`'s error-translation block, naming the regex patterns used. This satisfies F3 §6's "patterns committed at L2 design" mandate and provides forward-compat for bwrap minor-version upgrades.
- `CLAUDE.md` F3 contracts §5 (line 332) updated: drop "L4 enforces the boundary in `connect_stdio`"; replace with "**L2 adds the exception class; this leg (L2) enforces the boundary in `connect_stdio` via stderr-capture-and-translate.**" — accurately attributes the enforcement.
- `the_one/agents.md` line 73 updated: drop "L4 enforces"; replace with "L2 adds the exception class AND enforces the boundary in `connect_stdio`."
- Cumulative test count post-L2: 123 prior + 3 new (#6b, #6c, #6d) = **126** (Test #6 stays at one test post-flip; doesn't increase count). One test (#6c EPERM) is SKIPPED in the dev container — so collected = 126, passed = 125, skipped = 1.
- All other tests pass UNMODIFIED.

## Acceptance Criteria

- [ ] `the_one/mcp/transports/stdio.py::connect_stdio` opens a `tempfile.SpooledTemporaryFile(mode='w+', encoding='utf-8', errors='replace')` and passes it as `errlog=...` to `stdio_client(...)`.
- [ ] On post-CM-failure (the `try/except` path inside `connect_stdio` or its error-handling wrapper), `connect_stdio` reads the captured bwrap stderr (`buf.seek(0); stderr_text = buf.read()`), pattern-matches against the three known signatures, and raises the matching `MCPSandboxError` with catalog message text. If no pattern matches AND the underlying exception was a transport-failure that suggests bwrap exited (e.g., `BrokenResourceError`), raise the generic message #2 fallback.
- [ ] The three catalog messages are emitted from F3 §6 with the cycle-1-rework-amended #2 wording (drop synthetic exit-code; surface a snippet of the bwrap stderr instead):
  - **#1**: `"MCP sandbox setup failed: writable_paths entry {path!r} does not exist. Create the directory or remove from writable_paths."` (path interpolated from the `_BWRAP_NONEXISTENT_PATH_RE` capture group).
  - **#2 (revised — cycle 1)**: `"MCP sandbox setup failed: bubblewrap exited non-zero. Check that the dev/CI environment has cap_add: SYS_ADMIN AND security_opt: seccomp:unconfined per F3 design decision §10. bwrap stderr: {snippet!r}"` where snippet is the first ≤500 chars of stripped captured stderr. Drops the `{n}` exit-code interpolation that earlier revisions had — the SDK doesn't surface bwrap's exit code observably, and a synthetic `1` was misleading.
  - **#3**: `"MCP sandbox setup failed: namespace creation refused (EPERM on unshare). The container likely lacks the privilege grants required by §10."`
  - This is a deliberate rewording vs CLAUDE.md F3 contracts §5's pre-existing message #2 wording (which carried the `{n}` interpolation). The CLAUDE.md update in this leg also updates the catalog wording to match.
- [ ] If `_sandbox_disabled_for_tests()` returns True (the F3 §10 double-flag bypass is set), the new error-translation logic MUST NOT activate — the SDK's stderr passthrough behavior (`errlog=sys.stderr` default) is preserved. This means the new logic is conditional on the same code path that currently calls `BubblewrapSandbox.prepare_spawn`.
- [ ] `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` asserts `MCPSandboxError` with catalog message #1 substring. The previous "not isinstance MCPSandboxError" line is REMOVED.
- [ ] Three new tests exist in `tests/test_mcp_sandbox_integration.py`:
  - **#6b** `test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2` — exercises the generic bwrap-failure fallback via monkeypatched `prepare_spawn` injecting `--no-such-flag-for-test-6b`.
  - **#6c** `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` — exercises the EPERM-on-unshare path; SKIPPED in the dev container (has SYS_ADMIN), runnable only in privilege-stripped envs. Skip mechanism: `@pytest.mark.skipif(_has_sys_admin(), ...)` where `_has_sys_admin()` parses `/proc/self/status` CapEff bit 21.
  - **#6d** `test_inner_process_failure_does_not_translate_to_sandbox_error` — locks the OTHER side of F3 §6's directionality contract. An inner-process failure (post-bwrap-success) MUST surface as `MCPConnectionError`, NOT `MCPSandboxError` — gates against future regression of the bwrap-prefix discriminator.
- [ ] `tests/test_mcp_sandbox_integration.py` count goes 10 → 13.
- [ ] L2-start baseline (post-L1b) is **123 tests** across the six files: `{tests/test_mcp_client.py: 59, tests/test_mcp_integration.py: 14, tests/test_mcp_sandbox_integration.py: 10, tests/test_mcp_stdio_sandbox.py: 9, tests/test_sandbox_bubblewrap.py: 17, tests/test_sandbox_contract.py: 14}`. L2 flips Test #6 (count unchanged) and adds three new tests in `tests/test_mcp_sandbox_integration.py` (10 → 13: #6b generic-bwrap-failure, #6c EPERM-skipped-in-dev, #6d directionality-contract). **L2-end target: 126 tests across `{59, 14, 13, 9, 17, 14}`, with one of the 13 in `test_mcp_sandbox_integration.py` SKIPPED in the dev container** (Test #6c, the EPERM probe — dev container has SYS_ADMIN; only privilege-stripped envs run it).
- [ ] `CLAUDE.md` F3 contracts §5 (line 332) and `the_one/agents.md` (line 73) updated to drop "L4 enforces" language.
- [ ] `ruff check the_one/mcp/transports/ tests/test_mcp_sandbox_integration.py` clean (no NEW errors vs baseline).
- [ ] Flight log Leg Progress entry added with: (a) probe results — exact stderr captured for each of the three failure modes; (b) committed regex patterns (verbatim); (c) test count reconciliation; (d) confirmation that no other prior tests required modification.

## Verification Steps

How to confirm each criterion is met:

1. **`SpooledTemporaryFile` + `errlog=` wired**: `grep -n "SpooledTemporaryFile\|errlog=" the_one/mcp/transports/stdio.py` shows both forms.
2. **Three catalog messages emitted verbatim**: `grep -A 1 "MCP sandbox setup failed" the_one/mcp/transports/stdio.py` shows the three message bodies as documented in F3 §6.
3. **Test #6 flipped**: `grep -A 5 "test_sandbox_writable_paths_nonexistent_raises_at_connect" tests/test_mcp_sandbox_integration.py` shows `pytest.raises(MCPSandboxError)` and a substring assertion on `"writable_paths entry"`. The previous `assert not isinstance(... MCPSandboxError)` line is absent.
4. **Two new tests exist**: `grep -c "^async def test_sandbox_bwrap_unrecognised_exit_code\|^async def test_sandbox_eperm_on_unshare" tests/test_mcp_sandbox_integration.py` returns 2.
5. **Sandbox-integration count green**: `docker compose exec the-one pytest tests/test_mcp_sandbox_integration.py -q --timeout=60` returns 0 exit; collected = 13, passed = 12, skipped = 1 (the EPERM test #6c skips in dev container).
6. **Cumulative regression invariant**: `docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=60` returns 0 exit; collected = 126 (59+14+13+9+17+14), passed = 125, skipped = 1 (Test #6c). In a privilege-stripped CI without SYS_ADMIN, all 126 pass.
7. **CLAUDE.md and agents.md updated**: `grep -n "L4 enforces" CLAUDE.md the_one/agents.md` returns no matches.
8. **No prior test modifications**: `git diff <l2-start-sha> -- tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py | wc -l` returns 0 (no diff to those files). `git diff <l2-start-sha> -- tests/test_mcp_sandbox_integration.py` shows ONLY: (a) Test #6 expectation flip + docstring rewrite + module-list line 28 update, and (b) two new test methods added at the bottom or near the related-section block. No other test methods modified.
9. **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/transports/ tests/test_mcp_sandbox_integration.py` returns 0 exit.
10. **Probe results captured**: `grep -B 2 -A 10 "stderr-capture probe\|probe results 2026" the_one/mcp/transports/stdio.py` shows a comment block documenting the actual stderr observed for each failure mode.
11. **Flight log updated**: `grep -A 8 "02-bwrap-error-translation" missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` shows a Leg Progress entry with status `landed`, started/completed timestamps, probe results, regex patterns, and test-count reconciliation.

## Implementation Guidance

1. **Capture L2-start state**. `git rev-parse HEAD` returns the flight-design commit because L1a + L1b changes are uncommitted in the working tree (per agentic-workflow's flight-final-commit policy). For Verification Step #8's "no other test methods modified" check to be meaningful, capture a baseline diff of the current working tree before any L2 edits: `git diff > /tmp/l2-baseline.diff`. This baseline includes L1a + L1b changes; L2's verification is "the diff after L2 = the L2-baseline + L2's intended changes". For convenience, also capture per-file test counts before L2 edits — they should match the {59, 14, 10, 9, 17, 14} target above.

2. **Run the L2-affected test baseline**:
   ```bash
   docker compose exec the-one pytest tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py -q --timeout=60
   ```
   Expect: 10 + 9 = 19 passed.

3. **Run the STAKE-TEST PROBE** (per flight design §6 + F2 debrief KL #1). Inside the dev container, manually trigger each of the three bwrap failure modes and capture the actual stderr. Record results in a temporary scratch file or directly in a comment block you'll commit to `connect_stdio`'s error-translation block.

   Probe steps:

   a. **Writable-path nonexistent**:
      ```bash
      docker compose exec the-one bwrap --die-with-parent --unshare-user --unshare-net --clearenv \
          --setenv HOME /tmp --ro-bind / / --tmpfs /tmp \
          --bind /this/path/does/not/exist /this/path/does/not/exist \
          --proc /proc --dev /dev -- /bin/echo hello 2>&1; echo "exit=$?"
      ```
      Expected: exit code != 0; stderr containing `Can't find source path`.

   b. **Generic bwrap failure** (use a malformed flag):
      ```bash
      docker compose exec the-one bwrap --die-with-parent --unshare-user --unshare-net --clearenv \
          --setenv HOME /tmp --ro-bind / / --invalid-flag-xyz --tmpfs /tmp \
          --proc /proc --dev /dev -- /bin/echo hello 2>&1; echo "exit=$?"
      ```
      Expected: exit code != 0; stderr containing some bwrap-specific argument-parsing error.

   c. **EPERM on unshare** — only triggerable WITHOUT SYS_ADMIN. The dev container HAS SYS_ADMIN, so the probe must run elsewhere. **Recommended probe environment**: a separate `docker run --rm --user nobody mcr.microsoft.com/playwright/python:v1.58.0-jammy bash -c "apt-get update && apt-get install -y bubblewrap && bwrap --die-with-parent --unshare-user --unshare-net --clearenv --setenv HOME /tmp --ro-bind / / --tmpfs /tmp --proc /proc --dev /dev -- /bin/echo hi"`. Capture the resulting stderr. If this probe is not runnable from the agent's environment (e.g., docker-in-docker not allowed), do NOT silently waive — instead, attempt the probe at the host shell via `docker run` (the user can inspect output); if even that's not feasible, **escalate to the user** rather than committing an unverified regex (per F3 §6 "patterns committed at L2 design via probe" mandate). The bidirectional regex committed in step 4's `_BWRAP_EPERM_UNSHARE_RE` covers either ordering bwrap might emit, but empirical confirmation is mandatory.

   Capture the EXACT stderr text from each probe and decide on regex patterns. Commit the patterns to a comment block at the top of the new error-translation logic in `connect_stdio`. Format:

   ```python
   # Probe results captured 2026-05-07 against bwrap 0.11.0 in the dev
   # container (mcr.microsoft.com/playwright/python:v1.58.0-jammy + bwrap
   # apt install). See flight log L2 Leg Progress entry for full output.
   #
   # Pattern 1 (writable_paths nonexistent):
   #   regex: r"Can't find source path '?(?P<path>[^'\n]+)'?"
   #   exit-code: !=0 (typically 1)
   #
   # Pattern 2 (generic exit-code !=0 with no recognized signature):
   #   regex: (no match → fallback)
   #
   # Pattern 3 (EPERM on unshare):
   #   regex: r"(Operation not permitted|EPERM).*?(unshare|create user namespace)"
   #   exit-code: !=0 (typically 1)
   ```

4. **Modify `connect_stdio`** in `the_one/mcp/transports/stdio.py`. The function is currently `@asynccontextmanager`-decorated (post-L1a deviation; transport API unchanged). Modify the body to wrap `stdio_client(params)` with the stderr-capturing seam. Note the conditional: only activate translation when sandboxed (i.e., NOT when `_sandbox_disabled_for_tests()` is True).

   Sketch (the implementer adapts to the actual live source state):

   ```python
   import re
   import tempfile
   from typing import AsyncIterator

   from the_one.mcp.errors import MCPSandboxError

   # Compiled at module scope (CPython ~free since they're tiny).
   _BWRAP_NONEXISTENT_PATH_RE = re.compile(
       r"Can't find source path '?(?P<path>[^'\n]+?)'?\s*$",
       re.MULTILINE,
   )
   # bwrap's error-line convention is `<context>: <errno-strerror>`. The
   # context comes FIRST (e.g. `bwrap: setting up uid map: Operation not
   # permitted` or `bwrap: unshare user ns: Operation not permitted`). The
   # earlier-revisions regex had the order reversed and would have failed
   # to match real bwrap output. This pattern accepts either order to be
   # forgiving of bwrap minor-version drift.
   _BWRAP_EPERM_UNSHARE_RE = re.compile(
       r"(?:(?:unshare|user ns|create user namespace).*?(?:Operation not permitted|EPERM))"
       r"|(?:(?:Operation not permitted|EPERM).*?(?:unshare|user ns|create user namespace))",
       re.IGNORECASE | re.DOTALL,
   )
   # Discriminator: bwrap's own error lines start with "bwrap:". A captured
   # stderr that does NOT start with "bwrap:" indicates the bwrap setup
   # succeeded and the inner child wrote those bytes — F2's
   # MCPConnectionError must handle that case, not us.
   _BWRAP_OWN_PREFIX_RE = re.compile(r"^\s*bwrap:", re.MULTILINE)


   def _translate_bwrap_stderr(stderr_text: str) -> MCPSandboxError | None:
       """Pattern-match captured bwrap stderr → MCPSandboxError per F3 §6.

       Returns None if the capture indicates a non-bwrap failure (e.g., the
       child target spawned successfully under bwrap and itself failed
       mid-handshake — no translation needed; F2's MCPConnectionError
       handles it). The bwrap-prefix discriminator is the load-bearing
       check; if the captured stderr does NOT contain a `bwrap:` line at
       all, this helper returns None unconditionally.

       Returns an MCPSandboxError for any of the three §6 catalog signatures.
       """
       # Path-#1 check is exempt from the prefix gate because the
       # "Can't find source path" line is unambiguously a bwrap message
       # and is the most operator-actionable signature.
       m = _BWRAP_NONEXISTENT_PATH_RE.search(stderr_text)
       if m:
           path = m.group("path").strip()
           return MCPSandboxError(
               f"MCP sandbox setup failed: writable_paths entry "
               f"{path!r} does not exist. "
               f"Create the directory or remove from writable_paths."
           )
       # Path-#3 (EPERM) and path-#2 (generic) require the bwrap-prefix
       # gate to discriminate from inner-process failures.
       if not _BWRAP_OWN_PREFIX_RE.search(stderr_text):
           return None
       if _BWRAP_EPERM_UNSHARE_RE.search(stderr_text):
           return MCPSandboxError(
               "MCP sandbox setup failed: namespace creation refused "
               "(EPERM on unshare). The container likely lacks the "
               "privilege grants required by §10."
           )
       # bwrap printed something to stderr that we don't recognise → catalog #2.
       return MCPSandboxError(
           "MCP sandbox setup failed: bubblewrap exited non-zero. "
           "Check that the dev/CI environment has cap_add: SYS_ADMIN "
           "AND security_opt: seccomp:unconfined per F3 design decision §10. "
           f"bwrap stderr: {stderr_text.strip()[:500]!r}"
       )
   ```

   The `_translate_bwrap_stderr` signature drops the `exit_code` parameter that earlier revisions had — it was a synthetic proxy (always 1 or None) that the cycle-1 reviewer correctly identified as both useless (no real exit code) and dangerous (any inner-process failure with stderr → spurious "bubblewrap exited with code 1"). The bwrap-prefix discriminator replaces it.

   Then in `connect_stdio` itself, only when sandboxing is active (`not _sandbox_disabled_for_tests()`):

   ```python
   @asynccontextmanager
   async def connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]:
       """..."""  # docstring updated to drop "currently not translated" caveat
       params = _build_stdio_params(source)
       sandboxed = not _sandbox_disabled_for_tests()
       if sandboxed:
           # Sandboxed path: capture bwrap stderr for translation.
           with tempfile.SpooledTemporaryFile(
               mode="w+", encoding="utf-8", errors="replace"
           ) as errbuf:
               try:
                   async with stdio_client(params, errlog=errbuf) as (read, write):
                       async with ClientSession(read, write) as session:
                           yield session
               except BaseException as exc:
                   # Read whatever bwrap wrote to stderr before failing.
                   try:
                       errbuf.seek(0)
                       stderr_text = errbuf.read()
                   except Exception:
                       stderr_text = ""
                   sandbox_err = _translate_bwrap_stderr(stderr_text)
                   if sandbox_err is not None:
                       raise sandbox_err from exc
                   raise
       else:
           # Test bypass path: SDK's default errlog=sys.stderr passthrough.
           async with stdio_client(params) as (read, write):
               async with ClientSession(read, write) as session:
                   yield session
   ```

   The implementer may need to adapt the exit-code extraction. The SDK's `stdio_client` does NOT propagate the bwrap exit code directly; the captured stderr's presence-or-absence is the practical proxy. If the implementer can find a more precise mechanism (e.g., reading bwrap's exit code via `anyio.open_process`'s child-process attribute), they should — note in the flight log.

   **Important**: `stdio_client(params, errlog=errbuf)` requires the SDK 1.27.0 signature verified in §6. If the SDK was upgraded silently, the kwarg may have changed. Check `from inspect import signature; print(signature(stdio_client))` if needed.

5. **Update `connect_stdio`'s module docstring** in `transports/stdio.py` (lines 49-54): drop "Per F3 §6's boundary, bwrap-side post-setup errors... are not currently translated to `MCPSandboxError` inside this transport — see flight log Anomaly A02." Replace with: "Per F3 §6's boundary, bwrap-side post-setup errors (`writable_paths` nonexistent, `EPERM` on `unshare`, generic exit-code != 0) are translated to `MCPSandboxError` via the SDK's `errlog=` parameter — see leg `02-bwrap-error-translation`."

6. **Flip Test #6** in `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` (lines 347-378):
   - Change `pytest.raises(MCPConnectionError)` → `pytest.raises(MCPSandboxError)`.
   - Add substring assertion: `assert "writable_paths entry" in str(exc_info.value)` and `assert "does not exist" in str(exc_info.value)`.
   - REMOVE the line `assert not isinstance(exc_info.value, MCPSandboxError)` — that defensive line is no longer applicable.
   - Update the test docstring to reflect the new directionality (replace "L4 Anomaly A02" with "L2 catalog #1").
   - Update the section header comment block at line 342 from "Writable_paths nonexistent → MCPConnectionError per L4 Anomaly A02" to "Writable_paths nonexistent → MCPSandboxError catalog #1 per L2".
   - Update the module list at line 28 from `MCPConnectionError` to `MCPSandboxError catalog #1`.

7. **Add the two new tests** in `tests/test_mcp_sandbox_integration.py`. Place them in their own `# #N` section blocks AFTER Test #6, before Test #7 (the env-leakage section):

   ```python
   def _has_sys_admin() -> bool:
       """Return True if the current process has CAP_SYS_ADMIN in its
       effective capability set.

       Mechanism: parse /proc/self/status's CapEff line and check bit 21
       (CAP_SYS_ADMIN per <linux/capability.h>). No subprocess required;
       robust against locale changes; returns False on non-Linux hosts
       (where /proc doesn't exist) so the test gates correctly there too.
       """
       try:
           with open("/proc/self/status") as f:
               for line in f:
                   if line.startswith("CapEff:"):
                       cap_eff = int(line.split()[1], 16)
                       return bool(cap_eff & (1 << 21))  # CAP_SYS_ADMIN
       except (OSError, ValueError):
           return False
       return False


   # ---------------------------------------------------------------------------
   # #6b — Bwrap unrecognised failure (with bwrap: prefix) → MCPSandboxError catalog #2
   # ---------------------------------------------------------------------------


   @requires_bwrap
   async def test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2(
       monkeypatch: pytest.MonkeyPatch,
   ) -> None:
       """A bwrap failure with no F3 §6 #1/#3 signature but with the
       `bwrap:` prefix surfaces as catalog #2.

       Mechanism: monkeypatch BubblewrapSandbox.prepare_spawn to inject an
       unknown bwrap flag (e.g. `--no-such-flag-for-test-6b`) into the
       returned SpawnSpec.args. bwrap rejects unknown flags with
       `bwrap: Unknown option --no-such-flag-for-test-6b`, which has the
       bwrap-prefix discriminator, doesn't match patterns #1 or #3, and
       triggers catalog #2.
       """
       from the_one.platform.sandbox import BubblewrapSandbox, SpawnSpec

       _real_prepare_spawn = BubblewrapSandbox.prepare_spawn

       def _patched_prepare_spawn(self, profile, command, args, env, cwd=None):
           spec = _real_prepare_spawn(self, profile, command, args, env, cwd)
           # Inject a flag bwrap will reject. Place AFTER the namespace flags,
           # BEFORE the `--` separator (which is the last block before the
           # command). Find `--` and insert just before it.
           sep_idx = spec.args.index("--")
           new_args = (
               spec.args[:sep_idx]
               + ["--no-such-flag-for-test-6b"]
               + spec.args[sep_idx:]
           )
           return SpawnSpec(
               command=spec.command,
               args=new_args,
               env=spec.env,
               cwd=spec.cwd,
           )

       monkeypatch.setattr(
           BubblewrapSandbox, "prepare_spawn", _patched_prepare_spawn
       )

       source = _build_naughty_source(
           sandbox={"writable_paths": [], "network_allowed": False},
       )
       with pytest.raises(MCPSandboxError) as exc_info:
           async with MCPClient(source):
               pass
       assert "bubblewrap exited non-zero" in str(exc_info.value)
       # And the `bwrap stderr:` snippet preserves the underlying message
       # so an operator can debug.
       assert "bwrap stderr:" in str(exc_info.value)


   # ---------------------------------------------------------------------------
   # #6c — EPERM on unshare → MCPSandboxError catalog #3 (skip if SYS_ADMIN)
   # ---------------------------------------------------------------------------


   @requires_bwrap
   @pytest.mark.skipif(
       _has_sys_admin(),
       reason="Test exercises the no-privilege-grants path; dev container has SYS_ADMIN",
   )
   async def test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3() -> None:
       """EPERM on unshare surfaces as MCPSandboxError catalog #3.

       Only meaningful in environments WITHOUT cap_add: SYS_ADMIN +
       security_opt: seccomp:unconfined. The dev container has both;
       this test SKIPS there. CI without those grants exercises this
       path.
       """
       source = _build_naughty_source(
           sandbox={"writable_paths": [], "network_allowed": False},
       )
       with pytest.raises(MCPSandboxError) as exc_info:
           async with MCPClient(source):
               pass
       assert "namespace creation refused" in str(exc_info.value)
   ```

   The `_has_sys_admin()` mechanism is pinned to `/proc/self/status` CapEff bit-21 parsing — explicit, fast, no subprocess, no locale dependence. Earlier revisions of this leg left the choice open ("os.getuid() OR bwrap probe OR /proc parsing"); the cycle-1 reviewer correctly noted that `os.getuid() == 0` is wrong (root is not equivalent to SYS_ADMIN) and that the bwrap probe wastes a subprocess per session.

8. **Update CLAUDE.md F3 contracts §5** at line 332. Find: `**L2 adds the exception class; L4 enforces the boundary in connect_stdio.**`. Replace with: `**L2 adds the exception class AND enforces the boundary in connect_stdio via stderr-capture-and-translate (via SDK errlog= parameter); flight 04 leg 02 lands the enforcement.**`. ALSO: if §5 contains the exact text `"bubblewrap exited with code {n}"` for catalog message #2, update it to `"bubblewrap exited non-zero. Check that the dev/CI environment has cap_add: SYS_ADMIN AND security_opt: seccomp:unconfined per F3 design decision §10. bwrap stderr: {snippet!r}"` to match the cycle-1-rework-amended message #2 wording (drop the synthetic exit-code interpolation; embed a snippet of the bwrap stderr instead).

9. **Update `the_one/agents.md`** at line 73. Find: `**L2 adds the exception class; L4 enforces.**`. Replace with: `**L2 adds the exception class AND enforces the boundary in connect_stdio via stderr-capture-and-translate.**`.

10. **Run the L2 regression suite**:
    ```bash
    docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=60
    ```
    Expect 125 collected, 124 passed + 1 skipped (the EPERM test skips in dev container) — OR 125 passed if CI environment without SYS_ADMIN runs it.

11. **Lint**:
    ```bash
    docker compose exec the-one ruff check the_one/mcp/transports/ tests/test_mcp_sandbox_integration.py
    ```

12. **Update the flight log**: append a Leg Progress entry with status `landed`, ISO 8601 UTC timestamps, probe results section (the actual stderr captured for each failure mode), committed regex patterns, test-count reconciliation (10 → 12 in `test_mcp_sandbox_integration.py`; cumulative 125 across the L1a + L1b + L2 surface).

## Edge Cases

- **Stderr capture race**: `SpooledTemporaryFile` is in-memory until ~1KB then spilled. bwrap stderr is typically < 100 bytes for any of the three failure modes. No reader-side draining needed; `seek(0); read()` after the SDK's transport CM exits captures the full output.
- **Encoding-error tolerance**: `errors='replace'` on the buffer ensures that any non-UTF-8 byte sequences (unlikely from bwrap, but possible) don't crash the read.
- **Test-bypass path**: when `THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1`, the SDK uses its default `errlog=sys.stderr` passthrough — preserves the F2 behavior for unit tests that don't go through `BubblewrapSandbox.prepare_spawn` at all.
- **Locale dependence**: bwrap stderr message text may be locale-dependent on systems with non-`C` LANG. The dev container forces `LANG=C.UTF-8` (verified at F3 design). Document this assumption in the probe-results comment block; if a CI environment uses a different locale and the probe regex misses, the bwrap-prefix discriminator still triggers catalog #2 with a snippet of the actual stderr — operators see the raw bwrap message embedded in the `MCPSandboxError` and can act, even if the locale-specific catalog #1/#3 patterns missed.

- **Inner-process directionality**: F3 §6's contract is bidirectional. Failures BEFORE bwrap successfully wraps-and-execs → `MCPSandboxError`. Failures AFTER (target spawned, exits non-zero, handshake failed) → F2's `MCPConnectionError`. The bwrap-prefix discriminator (`_BWRAP_OWN_PREFIX_RE.search(stderr_text)`) is the load-bearing test. Test #6d locks this contract from the inner-process-failure side.
- **SDK signature drift**: `stdio_client(params, errlog=...)` is current at SDK 1.27.0. If the SDK is upgraded, re-verify the kwarg. If the kwarg is removed or renamed, escalate via Adaptation Criteria.
- **Concurrent-callers and shared file**: `SpooledTemporaryFile` is local to each `connect_stdio` invocation; concurrent calls (e.g., multiple agents spawning their MCPs in parallel under L3's pool) each get their own fresh buffer. No cross-contamination.
- **Generic exit-code message #2 false positives**: if bwrap exits with a non-zero code but the captured stderr is empty (highly unlikely), the message #2 fallback fires with `n=1` (a guess). The actual exit code is unobservable via the SDK's current `errlog=` mechanism. The flight log should note this limitation; the practical impact is minimal — operators see a clear error pointing at the F3 §10 privilege grants, even if the exact bwrap exit code is wrong.

## Files Affected

- `the_one/mcp/transports/stdio.py` — add `_translate_bwrap_stderr` helper at module scope; modify `connect_stdio` body to wrap `stdio_client` with the stderr-capturing seam (sandboxed path only); module docstring updated to drop the "currently not translated" caveat.
- `tests/test_mcp_sandbox_integration.py` — flip Test #6 expectation to `MCPSandboxError`; remove the defensive `not isinstance(... MCPSandboxError)` line; rewrite Test #6 docstring + module-list line 28 + section header at line 342; add two new tests `test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2` and `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3`; add `_has_sys_admin()` helper if needed.
- `CLAUDE.md` — F3 contracts §5 (line 332): drop "L4 enforces" language.
- `the_one/agents.md` — line 73: drop "L4 enforces" language.
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append Leg Progress entry with probe results.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [x] All acceptance criteria verified
- [x] STAKE-TEST PROBE results captured in `connect_stdio`'s comment block
- [x] `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=60` green; 126 collected (125 passed + 1 skipped in dev container — Test #6c skips per `_has_sys_admin()`)
- [x] `ruff check the_one/mcp/transports/ tests/test_mcp_sandbox_integration.py` clean (no NEW findings vs baseline)
- [x] CLAUDE.md F3 contracts §5 updated (drop "L4 enforces")
- [x] `the_one/agents.md` line 73 updated (drop "L4 enforces")
- [x] Flight log Leg Progress entry added (status `landed`, timestamps, probe results, regex patterns, test-count reconciliation)
- [x] Set this leg's status to `landed` (header at top of this file)
- [x] Check off this leg in flight.md (the `[ ] 02-bwrap-error-translation` line)
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

7 citations verified against current code at leg design time (2026-05-07).

- `the_one/mcp/transports/stdio.py:166-190` (`connect_stdio` `@asynccontextmanager` body — post-L1a still unchanged per scope-reduction deviation) — **OK**.
- `the_one/mcp/transports/stdio.py:49-54` (module docstring "Per F3 §6's boundary... not currently translated" caveat) — **OK**, will be removed in this leg.
- `the_one/mcp/errors.py:39-44` (`MCPSandboxError` class with F3 §6 docstring) — **OK**.
- `tests/test_mcp_sandbox_integration.py:347-378` (Test #6 currently asserts `MCPConnectionError` and `not isinstance(... MCPSandboxError)`) — **OK**, will flip in this leg.
- `tests/test_mcp_sandbox_integration.py:28` (module-list line "#6 Writable-path nonexistent — surfaces as MCPConnectionError") — **OK**, will update.
- `CLAUDE.md:332` (F3 contracts §5: "L2 adds the exception class; L4 enforces the boundary in `connect_stdio`") — **OK**, will update.
- `the_one/agents.md:73` ("L2 adds the exception class; L4 enforces") — **OK**, will update.
- `.venv/lib/python3.12/site-packages/mcp/client/stdio/__init__.py:106` (`stdio_client(server: StdioServerParameters, errlog: TextIO = sys.stderr)`) — **OK**, signature confirmed at flight design 2026-05-06; re-verify at L2 implementation start.
