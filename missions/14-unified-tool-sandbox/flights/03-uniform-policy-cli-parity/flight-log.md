# Flight Log: Uniform Policy, CLI Parity & Seam Hardening

**Flight**: [Uniform Policy, CLI Parity & Seam Hardening](flight.md)

## Summary

Flight in `planning`. Sources carry-forwards from the Flight 1 & 2 debriefs. The
Reconnaissance Report below classifies every cited item against current `main`
(`ddef8bb`, post-Flight-2 merge); operator scope decisions are folded into the
flight's Design Decisions.

---

## Reconnaissance Report

Walked each cited debt/follow-up from the Flight-2 debrief (top-5 recs + action
items) and the still-open Flight-1 action items against current `main`.

| Item | Classification | Evidence | Recommendation / disposition |
|---|---|---|---|
| `profile: object | None` typing | confirmed-live | `pty.py:170,558` (`# SandboxProfile | None (avoid import…)`) | **In scope** — `seam-hardening` leg (TYPE_CHECKING fix) |
| `SandboxError` relocation / import-cycle inversion | confirmed-live | `mcp/errors.py:37` (`class SandboxError(MCPClientError)`); `client.py:511 except MCPClientError` + the `:499` comment naming SandboxError; 4 function-level imports (`pty.py:212`, `interpreter.py:110`, `execution.py:451`, `shell.py:123`) | **Deferred** to end-of-mission maintenance (operator decision, DD1) — entangled dependency inversion, not a move |
| `factory.py` stale docstring | confirmed-live | `factory.py:61` ("until leg 3 reconciles both to this factory") | **In scope** — `debt-and-docs` |
| `bubblewrap.py` stale error message | confirmed-live | `bubblewrap.py:69` ("MCP sandbox setup failed…") — now platform-wide incl. PTY | **In scope** — `debt-and-docs` |
| `--ro-bind-try` doc in `SECURITY-MODEL.md` | **partially-satisfied** | `SECURITY-MODEL.md:81` documents the `--ro-bind-try` *mechanism* (read-only bind) but NOT the **silent-skip-of-absent-paths** caveat (the fixture footgun) | **Scope down** — add only the silent-skip caveat (`debt-and-docs`) |
| CLI sandboxed identically to web | confirmed-live (needs verification + test) | CLI `interfaces/cli.py:38` and web `interfaces/web/app.py:97` both `AgentFactory(store=store)` — shared path, no parity test exists | **In scope** — `cli-parity` leg |
| Host-crash PTY-orphan window | **already-mitigated** (revised at design review) | Architect empirically verified (bwrap 0.9.0): bwrap's own `--die-with-parent` calls `prctl(PR_SET_PDEATHSIG, SIGKILL)` tied to its parent = the Python process, so bwrap-outer dies ~300ms after an app crash. The F2-debrief premise ("bwrap-outer not tied to the app") was wrong. | **Reframed** (DD4): the window is a non-issue; `seam-hardening` adds a regression test locking the invariant + optional cheap pre-exec pdeathsig defense-in-depth. Mission known-issue → mitigated. |
| Footgun docs (teardown-dispatch, PTY-echo, workspace-under-$HOME) | confirmed-live | only in code/test comments (`pty.py` teardown comment; `test_pty_sandbox.py` docstring) | **In scope** — `debt-and-docs` |
| Agent-safe-observable rule → AUTHORING.md | confirmed-live (cross-repo) | mission-control `.claude/skills/behavior-test/AUTHORING.md` — not a the-one artifact | **Out of scope here** (cross-repo follow-up, DD6); the rule is *applied* on the the-one side via DD3 |
| Read-scoping ("cannot read outside scope") | confirmed-live (unmet mission criterion) | deferred since Flight 1 DD5; needs `ldd`/overlayfs | **Out of scope** — its own future flight; carried as mission known-issue |

**Operator scope decisions** (recorded in flight DD1/DD3/DD4): SandboxError relocation
deferred; host-crash hardening included; one unified containment behavior test. No
items were silently dropped — deferred items are retained with disposition above.

---

## Design Review (Phase 5b)

**Architect verdict**: *approve with changes* (1 cycle), with **empirical verification**
of the load-bearing DD4 claim. Changes incorporated:
- **[high] DD4 rationale was factually wrong** — the host-crash orphan window the F2
  debrief feared does not exist: bwrap's own `--die-with-parent` already
  `prctl(PR_SET_PDEATHSIG, SIGKILL)`-ties bwrap-outer to the Python parent (verified,
  ~300ms reap). DD4 reframed: `seam-hardening` now locks the invariant with a
  regression test + optional cheap pre-exec pdeathsig defense-in-depth (must probe
  `/bin/bwrap` is not setuid/setcap, else pdeathsig clears on `execve`). Mission
  known-issue → mitigated.
- **[medium] DD2 profile-equality was tautological** — CLI and web both use the same
  `AgentFactory(store=store)` → same `_build_tool_profile` inputs. Reframed: the
  CLI-parity test asserts (a) real containment under bwrap via the `AgentFactory` path
  and (b) the factory wires a non-empty `FilesystemConfig` — not profile-equality.
- **[medium] DD3 MCP consolidation overstated** — `test_mcp_sandbox_integration.py`
  uses `/var/tmp` + its own fixture + drives `MCPClient`; scoped the
  `_sandbox_fixtures.py` consolidation to `test_builtin_tool_sandbox.py` +
  `test_pty_sandbox.py`, assess-only for MCP.
- **Suggestions folded:** probe bwrap-not-setuid in the hardening test; behavior-spec
  step 6 captures the bwrap PID right after step 5 (avoids the close-vs-capture race);
  `factory.py:61` docstring → note the MCP copy is intentionally preserved (relocation
  deferred), not pending.

Second review cycle **skipped**: changes are faithful applications of the architect's
own findings (rationale corrections, assertion reframes, scope-downs), not new
architecture.

## Leg Progress

_None yet._

---

## Decisions

_Runtime decisions not in the original plan will be recorded here._

---

## Deviations

_Departures from the planned approach will be recorded here._

---

## Anomalies

_Unexpected issues will be recorded here._

---

## Session Notes

- **Planning (2026-06-07) — post-review**: After the DD4 finding (orphan window
  already mitigated by bwrap's `--die-with-parent`), operator folded the standalone
  `seam-hardening` leg into `debt-and-docs` — it shrank to a regression test + the
  typing fix + optional pdeathsig, not worth its own slot. Flight now 4 core legs
  (`cli-parity`, `containment-behavior-suite`, `debt-and-docs`, `verify-integration`)
  + optional HAT. Flight marked `ready`.
- **Planning (2026-06-07)**: Flight created from the Flight 1 & 2 debrief
  carry-forwards. Operator scope: defer SandboxError relocation (→ maintenance);
  include host-crash orphan hardening; one unified agent-safe containment behavior
  test + keep `@requires_bwrap` hermetic. Read-scoping flagged out of scope (its own
  flight). Recon run against `main@ddef8bb`.
