# Flight: Connector Error-Handling Correctness

**Status**: landed
**Mission**: [Maintenance (Post-M11)](../../mission.md)

## Contributing to Criteria
- [ ] `api.py:2463` broad-except narrowed to expected connector error types, programming errors propagate, the `# noqa: BLE001` crutch removed (T2)
- [ ] The ephemeral-followup non-401 path maps its `discord.errors.HTTPException` to a typed `ConnectorConnectionError` like the other send paths (T1)
- [ ] `ConnectorAuthRequired` is either raised from the Discord auth-failure path it documents, or removed along with its export and docstring promise (Q2)

---

## Pre-Flight

### Objective
Wire the connector error taxonomy through completely: stop the collapsed broad-except from swallowing programming errors as "connection errors" (T2), map the one send path that leaks a raw SDK exception (T1), and resolve the dead `ConnectorAuthRequired` type (Q2). All three are facets of "the error taxonomy exists but isn't fully wired."

### Open Questions
- [x] Q2 disposition — **RESOLVED at flight start: DELETE.** Investigation found no caller branches on connector error subtype and no operator surface consumes a "needs re-auth" distinction (the `app.py` `auth_required` machinery is the unrelated MCP tool-call OAuth pause). Wiring would leave the type dead-in-practice; deletion resolves the dead signal honestly (YAGNI for maintenance). Operator confirmed. This also moots the Flight 02 N818 concern (symbol + its noqa removed).

### Design Decisions

**T2 — narrow, don't suppress**: Replace `except (ConnectorClientError, Exception)` with a catch of the specific connector error types the save-warm path expects; let unexpected exceptions (programming errors like `AttributeError`) propagate rather than be recorded as connection failures. Remove the dead `# noqa: BLE001`.
- Rationale: a swallowed `AttributeError` masquerading as "Disconnected" is a debugging trap.
- Trade-off: an unexpected exception now surfaces louder — which is the point.

**Q2 — prefer wiring over deletion, but deletion is acceptable**: `ConnectorAuthRequired` is documented at `base.py:375` as the auth-failure signal but never raised; auth failures currently funnel through `ConnectorConfigError`/`ConnectorConnectionError`. Recommended: wire it at the Discord `LoginFailure` site (`_discord.py:~1300`) so callers can distinguish "needs re-auth" from generic failure. If the operator judges the distinction not worth a code path, delete the type + export + docstring promise instead. Either way the dead-signal is resolved.

**T1 — match the channel-ladder mapping**: The ephemeral-followup non-401 branch should `raise ConnectorConnectionError(...) from exc` like every other Discord send path, rather than bare-raising the SDK `HTTPException`.

### Prerequisites
- [ ] Q2 disposition confirmed (wire vs delete).
- [ ] Coordinate with Flight 02 Leg 1 if it renames `ConnectorAuthRequired` for N818 — deletion here makes that rename moot.

### Pre-Flight Checklist
- [ ] All open questions resolved (Q2 disposition)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach
Three small, independent fixes, each with a regression test. T2: narrow the except + remove noqa. T1: wrap the non-401 raise in the typed error. Q2: wire (or delete) `ConnectorAuthRequired`. Each leg adds a targeted test so the taxonomy contract is pinned going forward.

### Checkpoints
- [x] T2 fixed + test asserting a non-connector exception propagates (and isn't recorded)
- [x] T1 fixed + test asserting a typed error from the ephemeral path
- [x] Q2 resolved (deleted) + grep-zero confirmation; suite green after removal

### Adaptation Criteria

**Divert if**:
- Wiring `ConnectorAuthRequired` reveals the auth-failure path is more tangled than a single `LoginFailure` site — fall back to deletion and note it.

**Acceptable variations**:
- The exact connector error types caught in T2, based on what the save-warm path can actually raise.

### Legs
- [x] `01-narrow-broad-except` - Fix the collapsed `except (ConnectorClientError, Exception)` (T2)
- [x] `02-map-ephemeral-followup-error` - Map the non-401 `HTTPException` to a typed error (T1)
- [x] `03-resolve-connector-auth-required` - Delete dead `ConnectorAuthRequired` (Q2)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated (`base.py` docstring clause removed; `agents.md` error-taxonomy count 6→5)

### Verification
`docker exec the-one pytest tests/test_connectors_discord.py tests/test_connector_send_tool.py -q` green; the new regression tests assert: a programming error propagates past the save-warm handler (T2); the ephemeral-followup non-401 path raises a `ConnectorClientError` subtype (T1); `ConnectorAuthRequired` is either raised on auth failure or absent from the codebase (Q2).
