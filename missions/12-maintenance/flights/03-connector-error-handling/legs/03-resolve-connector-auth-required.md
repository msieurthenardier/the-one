# Leg: resolve-connector-auth-required

**Status**: completed
**Flight**: [Connector Error-Handling Correctness](../flight.md)

## Objective
**DELETE** the dead `ConnectorAuthRequired` exception — remove the type, its exports, its docstring promise, the prose in the operational manual, and its unit tests — leaving zero dangling references (resolves finding Q2).

## Context
- Maintenance report 2026-06-04, finding **Q2**: `ConnectorAuthRequired` is defined, exported, unit-tested, and documented — but never `raise`d anywhere. Auth failures funnel through generic `ConnectorConfigError`/`ConnectorConnectionError`.
- **Disposition: DELETE (operator-confirmed at flight start).** Investigation found no caller branches on connector error subtype and no surface consumes a "needs re-auth" distinction (the `app.py` `auth_required` machinery is the unrelated MCP tool-call OAuth pause). Wiring would leave the type dead-in-practice; deletion resolves it honestly.
- **Runtime safety confirmed (design review):** no `except ConnectorAuthRequired` or `isinstance(..., ConnectorAuthRequired)` exists anywhere — deletion breaks no catch site. Catch sites use `ConnectorClientError` (base) / `ConnectorRegistrationError`, both unaffected.
- This deletion also **moots the Flight 02 N818 concern** — the `# noqa: N818` is inline on the class line and vanishes with the class.

## Inputs (complete reference map, design-review verified — post-Flight-02 line numbers)
- `the_one/connectors/errors.py:34–50` — class definition (carries the `# noqa: N818`)
- `the_one/connectors/__init__.py:40` — import; `:86` — `__all__` entry
- `the_one/connectors/base.py:375–377` — docstring `:class:` mention (preceded by a `ConnectorConnectionError` clause ending in `;`)
- `the_one/agents.md:773` — prose: "defines **6** producer-side types: … `ConnectorAuthRequired`, …" (always-loaded operational manual — MUST update)
- `tests/test_connectors.py:12` (import), `:54` (class docstring "6-type"), `:61` (`test_subclassing_chain` tuple), `:79–83` & `:85–87` (two dedicated test methods)
- **No action**: `maintenance/2026-06-04.md` and all `missions/` artifacts are point-in-time/historical records — leave unmodified.

## Outputs
- `ConnectorAuthRequired` fully removed; `grep -rn ConnectorAuthRequired the_one/ tests/` → zero; ruff + suite green.

## Acceptance Criteria
- [x] Class removed from `errors.py` (the `# noqa: N818` went with it)
- [x] Removed from `__init__.py` import and `__all__`
- [x] `base.py` docstring: the `ConnectorAuthRequired` clause removed AND the preceding `ConnectorConnectionError` clause's trailing `;` changed to `.`
- [x] `the_one/agents.md` updated: count reads "5 producer-side types" and `ConnectorAuthRequired` absent from the list
- [x] `tests/test_connectors.py`: import removed; `test_subclassing_chain` tuple entry removed; class docstring "6-type" → "5-type"; both dedicated test methods deleted
- [x] `grep -rn "ConnectorAuthRequired" the_one/ tests/` → zero results
- [x] `docker exec the-one ruff check the_one/ tests/` → 0 (no dangling import)
- [x] Full suite green (2935 passed)

## Verification Steps
- `grep -rn "ConnectorAuthRequired" the_one/ tests/` → zero results
- `docker exec the-one ruff check the_one/ tests/` → 0
- `docker exec the-one pytest tests/test_connectors.py tests/test_connectors_discord.py -q` green (then full suite at flight-end)

## Implementation Guidance
Apply the complete checklist (5 files, 10 edits):
1. **`errors.py`** — delete the entire `class ConnectorAuthRequired(...)` block (34–50).
2. **`__init__.py`** — delete the `ConnectorAuthRequired,` import line (40) and the `"ConnectorAuthRequired",` `__all__` entry (86). (Leaving the import would trip ruff F401 — confirms removal.)
3. **`base.py`** — delete the `:class:`ConnectorAuthRequired`` sentence (375–377); change the preceding `ConnectorConnectionError` clause's trailing semicolon to a period. Do not disturb the `ConnectorConfigError`/`ConnectorConnectionError` `:class:` references.
4. **`agents.md`** — line 773: "6 producer-side types" → "5"; drop `ConnectorAuthRequired` from the inline list.
5. **`tests/test_connectors.py`** — remove the import (12); remove the tuple entry in `test_subclassing_chain` (61); update the `TestConnectorExceptions` docstring (54) "6-type" → "5-type"; delete `test_auth_required_carries_account_id` (79–83) and `test_auth_required_account_name_optional` (85–87).

## Edge Cases
- **Don't break shared tests** — `test_subclassing_chain` enumerates ALL error types; only remove the one tuple entry, keep the test and the other 4 types.
- **Don't break docstring prose** — the semicolon→period fix in `base.py` is required for grammatical flow.

## Files Affected
- `the_one/connectors/errors.py` - class removed
- `the_one/connectors/__init__.py` - import + `__all__` entry removed
- `the_one/connectors/base.py` - docstring clause removed + semicolon→period
- `the_one/agents.md` - count 6→5, symbol removed from list
- `tests/test_connectors.py` - import, tuple entry, docstring count, two test methods

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
