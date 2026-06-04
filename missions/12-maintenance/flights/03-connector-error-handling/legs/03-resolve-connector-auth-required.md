# Leg: resolve-connector-auth-required

**Status**: ready
**Flight**: [Connector Error-Handling Correctness](../flight.md)

## Objective
Resolve the dead `ConnectorAuthRequired` exception — either wire it into the Discord auth-failure path it documents, or remove the type, its export, and its docstring promise (resolves finding Q2).

## Context
- Maintenance report 2026-06-04, finding **Q2**: `ConnectorAuthRequired` is defined (`errors.py:36`), exported (`__init__.py:40,86`), unit-tested (`tests/test_connectors.py:80,86`), and documented (`base.py:375`) — but never `raise`d anywhere. Auth failures currently funnel through generic `ConnectorConfigError`/`ConnectorConnectionError`, so callers cannot distinguish "needs re-auth" from generic failure.
- Flight design recommends **wiring** (raise it at the Discord `LoginFailure` site, `_discord.py:~1300`) so the distinction exists, with **deletion** as the acceptable fallback if the operator judges the distinction not worth a code path. Confirm the disposition at flight start.

## Inputs
- `the_one/connectors/errors.py:36`, `the_one/connectors/__init__.py:40,86`, `the_one/connectors/base.py:375` (docstring), `tests/test_connectors.py:80,86`.
- The Discord auth-failure site at `_discord.py:~1300` (`LoginFailure`).

## Outputs
- Either: `ConnectorAuthRequired` raised on auth failure + a test asserting it; or: the type, export, docstring promise, and smoke-test removed.

## Acceptance Criteria
- [ ] **If wiring**: the Discord `LoginFailure` (and any equivalent token-rejection) path raises `ConnectorAuthRequired`; a regression test asserts it; callers that should distinguish re-auth handle it (at minimum it is no longer dead)
- [ ] **If deleting**: `ConnectorAuthRequired` is removed from `errors.py`, both export sites, the `base.py:375` docstring mention, and the smoke-test; `ruff check` stays green (no dangling import)
- [ ] No dead exported error type remains either way
- [ ] Full suite green

## Verification Steps
- `grep -rn "ConnectorAuthRequired" the_one/ tests/` — wiring: includes at least one `raise`; deletion: zero results
- `docker exec the-one pytest tests/test_connectors_discord.py tests/test_connectors.py -q` green
- `ruff check the_one/ tests/` → 0 (no unused-import left by deletion)

## Implementation Guidance

**Confirm disposition first**, then one of:

1. **Wire it** (recommended)
   - At the Discord `LoginFailure` handler (`_discord.py:~1300`), raise `ConnectorAuthRequired(...)` instead of (or mapped from) the generic error it currently produces.
   - Ensure the connect/save-warm caller treats it appropriately — at minimum it must not be misclassified; ideally `/status` or the operator surface can show "needs re-auth" distinctly. (Coordinate with the T2 narrowing in Leg 1 so the new type is among the caught connector errors where appropriate.)
   - Add a regression test that drives a `LoginFailure` and asserts `ConnectorAuthRequired`.

2. **Delete it** (fallback)
   - Remove the class (`errors.py:36`), both export lines (`__init__.py:40,86`), the `base.py:375` docstring reference, and the smoke-test (`tests/test_connectors.py:80,86`).
   - Run `ruff check` to confirm no dangling import; run the suite.

## Edge Cases
- **Flight 02 N818**: `ConnectorAuthRequired` lacks an `Error` suffix and may be an N818 candidate in Flight 02 Leg 1. If deleting here, that N818 concern evaporates — coordinate ordering so Flight 02 doesn't rename a symbol this leg removes.

## Files Affected
- `the_one/connectors/errors.py` - raise-site wiring OR class removal
- `the_one/connectors/__init__.py` - export (kept if wiring, removed if deleting)
- `the_one/connectors/_discord.py` - raise site (if wiring)
- `the_one/connectors/base.py` - docstring (corrected or removed)
- `tests/test_connectors.py`, `tests/test_connectors_discord.py` - tests

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
