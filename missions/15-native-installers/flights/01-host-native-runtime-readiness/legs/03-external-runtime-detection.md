# Leg: external-runtime-detection

**Status**: completed
**Flight**: [Host-Native Runtime Readiness](../flight.md)

## Objective

When an external MCP runtime (`node`/`npx`/`uv`/`uvx`/`python`) is missing, surface
actionable **host-native** install guidance naming the absent runtime — replacing the
Docker-flavored message that today tells users to edit the Dockerfile and `make rebuild`.

## Context

- **Mission criterion** — "When a required external runtime for MCP servers is absent,
  the app detects this and presents actionable, non-Docker guidance rather than failing
  silently." *(behavior-test-backed in a later flight; this leg lands the detection +
  message.)*
- **Detection already exists** — `the_one/mcp/transports/stdio.py` `_translate_inner_spawn_error()`
  Pattern 1 (lines 282-294) already catches `FileNotFoundError` on spawn and produces an
  `MCPConnectionError`. The problem is purely the **message**: it says *"not available in
  the container. Add it to the Dockerfile and run `make rebuild`, or install via
  `docker compose exec the-one …`"* (lines 288-293). That guidance is wrong once the app
  runs host-native.
- **Scope boundary** — this leg fixes the MCP-spawn runtime-absence path and adds a
  reusable, non-Docker install-hint mapping. Broader replacement of *other* remaining
  Docker-flavored runtime messages is Flight 7's "replace Docker-flavored runtime error
  messages" item — not duplicated here.
- The runtime-fetch shape suggestion (`command=uvx args=[<pkg>]` / `command=npx
  args=[-y,<pkg>]`) in the existing message is already non-Docker and stays.
- Independent of Legs 1/2 (touches a different surface).

## Inputs

- `the_one/mcp/transports/stdio.py` `_translate_inner_spawn_error()` with the
  Docker-flavored Pattern-1 message (lines 287-294); `command` arg carries the
  operator-configured command (e.g. `uvx`, `npx`, `python`).
- `tests/test_mcp_stdio_error_translation.py` — asserts the current Pattern-1 message
  (the Docker strings) and must be updated.
- The MCP-source connect error surface (web `interfaces/web/api.py`, CLI) that renders
  `MCPConnectionError.message` to the operator.

## Outputs

- Pattern-1 message rewritten to host-native guidance: names the missing runtime and
  gives a non-Docker install hint per known runtime, keeping the runtime-fetch shape tip.
- A small reusable hint mapping (e.g. `_RUNTIME_INSTALL_HINTS`) for the common runtimes
  (`node`, `npx`, `uv`, `uvx`, `python`/`python3`), with a generic fallback for unknown
  commands.
- No `docker`/`Dockerfile`/`make rebuild`/`container` strings anywhere in the
  runtime-absence message path.
- Updated tests asserting the message is Docker-free and names the missing runtime + a
  host-native install hint.

## Acceptance Criteria

- [x] On `FileNotFoundError` spawn failure, the `MCPConnectionError` message names the
      missing executable and gives a **host-native** install hint (no Docker references).
- [x] A reusable hint mapping covers `node`, `npx`, `uv`, `uvx`, `python`/`python3` with
      a sensible generic fallback for any other missing command.
- [x] The live runtime-absence **message** carries no Docker guidance:
      `grep -in "not available in the container\|add it to the dockerfile\|make rebuild\|docker compose exec" the_one/mcp/transports/stdio.py`
      returns no hits. (Tightened to the exact Pattern-1 phrasing — a broad
      `"in the container"` token also matches the bwrap-discriminator *architectural*
      docstrings at `stdio.py:213/264` and `mcp/cache_cleanup.py:6`, which are not the
      runtime message and are out of this leg's scope.)
- [x] The stale Pattern-1 **catalog comment** that quotes the old Docker message
      (`stdio.py` ~206-218) and the test module docstring are updated to describe the new
      host-native message.
- [x] The runtime-fetch shape suggestion (`uvx`/`npx`) is preserved.
- [x] `tests/test_mcp_stdio_error_translation.py` updated and green: asserts the new
      host-native message shape (missing-runtime name present; Docker strings absent).
- [x] The message reaches the operator through the existing MCP-source connect error
      surface (web API response and/or CLI) — verified, no swallowing.
- [x] Full suite passes; `ruff check`/`ruff format` clean.

## Verification Steps

- `docker exec the-one pytest -x --timeout 30 tests/test_mcp_stdio_error_translation.py`
  → green with updated assertions.
- `grep -rin "dockerfile\|make rebuild\|docker compose exec" the_one/mcp/transports/stdio.py`
  → no hits.
- Manual/oneliner: construct a `FileNotFoundError(filename="uvx")`, call
  `_translate_inner_spawn_error(exc, "", "uvx")`, assert the message contains `uvx` and a
  non-Docker install hint and none of the Docker tokens.
- Confirm the surfacing path: trace `MCPConnectionError` from `_translate_inner_spawn_error`
  to where the web API / CLI renders it (no reformatting that drops the message).
- Full suite + `ruff` at leg-end.

## Implementation Guidance

1. **Add an install-hint mapping** near the translation helper in `stdio.py` (or a small
   sibling module): map known commands to a one-line, OS-neutral host-native hint, e.g.
   - `node`/`npx` → "install Node.js (e.g. from nodejs.org or your package manager) so
     `node`/`npx` are on PATH";
   - `uv`/`uvx` → "install uv (https://docs.astral.sh/uv/) so `uv`/`uvx` are on PATH";
   - `python`/`python3` → "ensure a Python 3.11+ interpreter is on PATH";
   - generic fallback → "install <missing> and ensure it is on this app's PATH".

2. **Rewrite the Pattern-1 message** (lines 287-294): keep the `missing = getattr(exc,
   "filename", None) or command` resolution; produce a message of the form: *"The command
   `<missing>` was not found on PATH. <install-hint>. For one-off Python/JS MCPs, prefer
   the runtime-fetch shape: command=uvx args=[<pkg>] (Python), command=npx args=[-y,<pkg>]
   (JS)."* No Docker tokens.

3. **Update the stale catalog comment** — the Pattern-1 catalog/comment block in
   `stdio.py` (~206-218) quotes the old Docker translation text; rewrite it to describe
   the new host-native message so the inline docs don't contradict the code. (Leave the
   bwrap-discriminator architectural docstrings at lines ~259-265 that mention
   "missing in container" as a *concept* — optionally reword for accuracy, not required.)

4. **Keep Patterns 2 & 3 as-is** — the `ModuleNotFoundError` and `can't open file`
   messages are already non-Docker (they reference `pip install`/`uvx`, which is fine).
   (If a later audit wants them tuned, that's Flight 7.)

5. **Verify the surface** — `MCPConnectionError.message` reaches the operator at two
   confirmed production surfaces (design review): the web MCP test/connect route
   (`interfaces/web/api.py:1590`, rendered verbatim by `mcp-server-editor.js:1942`) and
   the agent tool-call route (`mcp/_tool.py:166`, rendered by `cli.py:92`). Confirm the
   rewrite flows through both unchanged.

6. **Update tests** — `tests/test_mcp_stdio_error_translation.py`: rewrite the Pattern-1
   assertions in `test_translate_filenotfounderror_returns_actionable_connection_error`
   (the `"Dockerfile"` / `"make rebuild"` asserts at ~lines 37-38 break; the `"uvx"`
   assert at ~line 36 survives since the runtime-fetch tip is preserved). Assert the new
   shape (missing runtime named; host-native hint present; Docker tokens absent). Add a
   case per known runtime (`node`/`npx`/`uv`/`uvx`/`python`/`python3`) + the generic
   fallback. Update the module docstring (lines 5-6) describing the old Docker behavior.

6. **Run `ruff` + full suite**.

## Edge Cases

- **`FileNotFoundError.filename` is None** (possible on some Windows variants) — fall
  back to the configured `command` (existing behavior; keep it).
- **Unknown command** (operator-custom binary) — generic fallback hint, still names the
  missing command, still Docker-free.
- **bwrap-side "command not found"** — must NOT be mistranslated as a missing runtime;
  the existing discriminator ordering (Pattern 1 runs only after `_translate_bwrap_stderr`
  returns None and stderr has no `bwrap:` prefix — see the docstring at lines 259-265)
  is preserved. Do not reorder.

## Files Affected

- `the_one/mcp/transports/stdio.py` — install-hint mapping + Pattern-1 message rewrite.
- `tests/test_mcp_stdio_error_translation.py` — updated Pattern-1 assertions + per-runtime
  cases.

---
