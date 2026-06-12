# Flight Log: macOS Sandbox Backend (Seatbelt)

**Flight**: [flight.md](flight.md)
**Started**: — (planning)

## Summary

_Pending execution._

## Reconnaissance Report

Planning-time recon (2026-06-12) of carried-forward items sourced from the
F1 debrief and mission Carried Forward sections, verified against `main`
post-PR-#109:

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Re-mark ~12 `skipif(which("bwrap"))` integration tests as `@requires_bwrap` | confirmed-live | `tests/test_mcp_sandbox_integration.py:88` defines a `skipif`-based alias; `tests/test_mcp_stdio_sandbox.py:447` uses raw `skipif` | Leg 1 ride-along (same CI surface; F1 deadline "before the CI matrix expands") |
| Guard comments naming the `mcp/__init__` eager-load cycle at lazy `SandboxError` imports | confirmed-live | `the_one/mcp/_tool.py:157`, `the_one/mcp/_tool_provider.py:306` — lazy imports present, no hazard comment at either site | Leg 1 ride-along (tiny doc-comment debt) |
| `test.yml` bare-pytest-on-ephemeral-runners comment | already-satisfied | `.github/workflows/test.yml` header comment, added in F1 CI-red closeout (`625948f`) | Retired |
| Re-characterize `test_connectors_e2e` flake | already-satisfied | Root-caused as uptime-dependent `last_activity = 0.0` aging; fixed in `625948f`; debrief item ticked | Retired |
| `test-live` `test_aiat.py` `/app/...` path fixes | confirmed-live, out-of-scope | Needs a running host-native server; unrelated to the sandbox surface | Defer (future flight; tracked in F1 debrief) |
| Defer `mcp/__init__` eager `_tool`/`_tool_provider` imports (remove cycle class) | confirmed-live, out-of-scope | Structural maintenance beyond guard comments | Defer (maintenance; guard comments suffice this mission) |
| M14 optional forward-proofing: `network_allowed` param on `_build_boxed_profile`; `@requires_bwrap` reaper-path boxed-session cleanup test | needs-human-recheck (pick up only if touched) | Mission Carried Forward §3 — "do-if-touched, not blocking" | Leg 4 touches the boxed path; leg design decides whether the param falls out naturally |

Operator confirmations (2026-06-12): retirements accepted as listed; DD1
(direct `sandbox-exec`) locked after context discussion; DD8/DD9 scope answers
recorded in the flight spec.

## Design Review (Phase 5b)

Two Architect review cycles (2026-06-12), both "approve with changes"; all
findings incorporated:

- **Round 1** (8 issues): killed a factually false DD6 claim (pty.py:327-328
  already does `clear()`+`update` — no env leak exists); surfaced the third
  backend-name coupling (`stdio.py:479/:599` isinstance gates) → DD5 locked to
  capability attributes as the single mechanism; reframed the `_wrapped`
  predicate (bwrap-specific SIGTERM-not-forwarded semantic — rename, don't
  extend); corrected DD7's overstated premise (no `killpg` exists on the PTY
  teardown path — Leg 4 adds it for non-bwrap); added macOS path
  canonicalization (`/tmp`→`/private/tmp` SBPL matching), the Leg 3
  selection-flip audit, the Leg 1 SBPL-precedence + sandbox-exec-presence
  smokes, runner-image pinning (macos-15), narrow `/Library` allowlist,
  TMPDIR-to-scratch, DD7b minimal stderr translation, and prerequisite gaps
  (arm64 wheels).
- **Round 2** (3 issues, verified all round-1 fixes coherent): pinned the
  Leg 2→Leg 4 interim semantic for `minimal_rootfs=True` (graceful host-mode
  SBPL, seam warning truthfully fires); corrected DD4's tempdir-parity framing
  (bwrap's private `/tmp` is unconditional — the gap exists in host mode too);
  sequenced `wraps_stderr=False` at Leg 4 → True at Leg 5 with the translator.
  Plus: DD5 variation wording de-ambiguated, pre-existing `is_alive`/`close()`
  fd leak flagged as a Leg 4 decision point, stdio SDK default-env merge
  precision, factory log keys noted test-pinned.

## Decisions

_Pending execution — planning-time decisions live in flight.md Design Decisions._

## Deviations

_None yet._

## Anomalies

_None yet._

## Leg Progress

_Pending leg design._
