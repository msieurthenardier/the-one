# HAT — Human Acceptance Test (Tier 1 + Tier 2)

This document specifies the two-tier acceptance test for F6's per-agent
MCP attach + tool-routing feature. Tier 1 is automated (CI-runnable);
Tier 2 is manual (operator-runnable, quarterly).

## Tier 1 (CI / always-run)

`tests/test_mcp_attach_hat.py` exercises the 5-step verification
sequence inside the dev container against a real bwrap-spawned
`mcp-server-fetch` subprocess.

**Run command** (inside the dev container):

```bash
docker compose exec the-one pytest tests/test_mcp_attach_hat.py -v
```

**Expected output**: 7 tests pass. (5 step tests + 1 caplog gate + 1
bonus per-(agent, source) keying test.)

If skipped, ensure `mcp-server-fetch` is installed:

```bash
docker compose exec the-one pip install mcp-server-fetch
```

Then re-run. Outside the dev container, every test in the file is
expected to SKIP (the module-level `pytest.mark.skipif` probes for
`bwrap` and `mcp-server-fetch` availability — both must be present).

## Tier 2 (Manual / quarterly) — GitHub MCP via manual-entry path

Operator-runnable end-to-end check against a real OAuth-protected MCP
server. Verifies the F5 manual-entry OAuth path + F6 per-agent attach
work together against a production-grade server. Not blocking; not part
of CI.

**Setup**:

1. Register an OAuth app at <https://github.com/settings/developers> —
   "OAuth Apps" → "New OAuth App". Set the homepage URL to
   `http://localhost:8000`; set the callback URL to
   `http://localhost:8000/oauth/callback`.
2. Copy the resulting `client_id` (and `client_secret` if the app is
   confidential).
3. Start the the-one server: `docker compose up`.

**Procedure**:

1. Navigate to the chat UI in a browser (`http://localhost:8000`).
2. In the agent settings, attach a new MCP source pointing at GitHub
   MCP: `https://api.githubcopilot.com/mcp/`. Choose "manual entry"
   for the OAuth credentials.
3. Trigger a tool call that requires the GitHub MCP tools (e.g., ask
   the agent to "list my repos"). The agent will detect the
   unauthenticated state and surface a "Login required" prompt in the
   chat UI.
4. Click "Login required". The chat UI presents the manual-entry form
   (per F5 L4 — operator-driven entry of `client_id`, `client_secret`,
   `authorization_endpoint`, `token_endpoint`, optional `scope`).
5. Paste the GitHub OAuth app's `client_id` + `client_secret`; the
   discovery endpoints autofill from `https://github.com/login/oauth`.
6. Click "Connect". A new tab opens at `https://github.com/login/oauth/
   authorize?...`; consent on the GitHub page; the tab closes after
   the callback round-trip.
7. Re-trigger the original tool call. The agent now has GitHub MCP
   credentials and the call succeeds; verify a meaningful response in
   the chat UI.

**Acceptance**: The tool call returns a coherent response (e.g., the
list of the operator's repos). No error envelope, no auth-required
loop.

## F2-known-issue retirement gate

The Tier-1 caplog assertion (in
`tests/test_mcp_attach_hat.py::test_caplog_no_transport_close_failed_warnings`)
is the binary go/no-go gate for retiring the F2-known-issue from
`missions/07-mcp-integration/mission.md`'s "Known Issues" section.

The gate's assertion:

```python
assert not any(
    "MCPClient transport close failed" in r.message
    for r in caplog.records
)
```

The substring matches the verbatim message emitted at
`the_one/mcp/client.py:328` when the cross-task `__aexit__` guard
fires during disconnect. F5 L1 added `_open_*_transport_stack` helpers
to retire this WARNING under F4-pool-routed paths; F5 shipped the
mechanism speculatively because the warning surfaces only during real
subprocess teardown (not unit-mockable). The Tier-1 HAT exercises real
bwrap subprocess + real MCP session + real teardown; zero matches in
the caplog confirms the F5 L1 mechanism works end-to-end.

**On PASS**: edit `missions/07-mcp-integration/mission.md`'s "Known
Issues" section to remove the `MCPClient.disconnect teardown noise`
entry (line 104 at the time of writing; line numbers may drift). This
edit happens AT FLIGHT-END, after the Tier-1 docker run has actually
PASSED — NOT during L5 implementation. L5 lands the test scaffold; the
flight-end docker run is the gate.

## On FAIL

If the Tier-1 caplog assertion FAILS — i.e., one or more
`MCPClient transport close failed` WARNINGs surface during the run —
file a follow-up flight with the following pre-written scope:

1. **Revert F5 L1's `_open_*_transport_stack` helpers** in
   `the_one/mcp/transports/streamable_http.py` and
   `the_one/mcp/transports/stdio.py`. These helpers were the
   speculative F5 mechanism for retiring the WARNING; if they don't
   actually retire it, they add complexity without value.
2. **Revert `the_one/mcp/client.py::_transport_connect` dispatcher's
   consumption of these helpers** — restore the pre-F5-L1 inline
   `async with stdio_client(...)` / `async with streamablehttp_client(...)`
   pattern.
3. **Revert the `the_one/mcp/README.md §3` scoping update** that
   documented the F5 L1 helpers as the F2-known-issue retirement
   mechanism.
4. The F2-known-issue line in `missions/07-mcp-integration/mission.md`
   stays OPEN with a real diagnosis plan: investigate whether the
   anyio cross-task `CancelScope.__aexit__` guard is still firing
   despite F4's same-task disconnect pattern. Possible causes: (a) a
   subscope inside the SDK's `ClientSession` constructor binds to a
   different task, (b) `AsyncExitStack` re-entrancy semantics shift
   between SDK versions, (c) the F4 worker-task pattern itself has a
   bug masked by the speculative helper. Each cause has a different
   fix; the diagnosis must precede the next attempt.

The follow-up flight is a separate work item (its own flight artifact
under `missions/07-mcp-integration/flights/`). DO NOT auto-revert in
this leg — the Flight Director escalates with this scope to the user
for explicit go-ahead.

The mission-level F2-known-issue line stays open until the follow-up
flight lands a fix that produces a green caplog gate on a re-run of
this Tier-1 HAT.
