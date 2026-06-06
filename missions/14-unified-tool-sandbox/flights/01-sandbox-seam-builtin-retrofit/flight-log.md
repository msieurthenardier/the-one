# Flight Log: Sandbox Seam + Built-in Tool Retrofit

**Flight**: [Sandbox Seam + Built-in Tool Retrofit](flight.md)

## Summary
Flight planned. Awaiting execution.

---

## Leg Progress

_No legs executed yet._

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
- Flight spec created from Mission 14 (Unified Tool-Execution Sandbox), Flight 1.
- Architect design review (Phase 5b): **approve with changes** — all incorporated.
- Key decisions (final): built-in tools default to a **host-workspace** profile
  (capable assistant, not a cage) = writable from `FilesystemConfig` allowlist,
  denylist OS-enforced via a new `readonly_overlay_paths` field, **real `$HOME`**,
  network deny-by-default (opt-in via `ExecutionConfig.sandbox_network_allowed`).
  Read-scoping deferred. Rename **in place** (`ToolSandbox`/`SandboxError`,
  keeping the `MCPClientError` hierarchy + `client.py:511` catch) as its own first
  leg. Existing `test_execution_tools.py` pinned to passthrough; containment via
  `@requires_bwrap` integration tests. Profile derivation built as one clean
  `_build_tool_profile()` function = the hook for Flight 4 (agent-selectable boxed
  mode), which was added to the mission as a separate flight.
- Architectural framing confirmed with operator: bwrap ≠ Docker — the seam is a
  per-execution *policy dial*, not an outer cage; the native trajectory (M15)
  makes the app the capable assistant on the host with the sandbox as the opt-in box.
