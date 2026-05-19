# Leg: f6-carry-forward-bundle

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Close two small F6-debrief carry-forward items that share the F7 surface: (i) ship `tests/test_pairing_prefix.py` with ~6 cases pinning `_validate_pairing_prefix`'s whitespace + case-sensitivity claims (F6 debrief rec: "the pairing helper is integration-tested only; add a dedicated unit test"); (ii) add a `# F8: DM classification lands here` source-code marker at the DMs-only-sentinel branches in `the_one/connectors/_acl.py` (post-L2 the marker target moved from `tools/connector_send.py:202` — the ACL section is now in `_acl.py`). Genuinely orthogonal to L1-L7; no behavior change.

## Context

This is the eighth F7 leg per the flight spec. Per Design Decisions in `flight.md`:

- **"F6 carry-forward bundle as a single leg"** — F6 debrief flagged two small follow-ups (pairing-prefix unit tests + F8 marker); bundling them follows the "small items sharing a surface area" guidance.
- **Marker site moved post-L2**: the original target was `tools/connector_send.py:202` (where F6 had the inline DMs-only branch). After L2's extraction, the DMs-only sentinel handling lives in `_acl.py:97-99` (outbound) and `:170-173` (inbound). The F8 marker should sit adjacent to the `elif agent_channels == []:` branches in both places — that's where F8's DM-classification logic will replace the fail-closed deny with "permit if envelope is a DM."

Key learnings:

- L1: parser is mirror-shape for the pairing-prefix unit tests (both pure functions; both have whitespace + case-sensitivity claims).
- L2: ACL admission moved to `_acl.py`; DMs-only-sentinel site followed.

## Inputs

What exists before this leg runs:

- `the_one/connectors/_pairing.py:_validate_pairing_prefix` — pure function, byte-equality + case-sensitivity claims documented in the docstring at `:28-30`. Integration tests at `tests/test_connectors_inbound.py:1165-1380` exercise it indirectly via dispatcher; no dedicated unit test.
- `the_one/connectors/_acl.py:97-99` — outbound DMs-only fail-closed deny.
- `the_one/connectors/_acl.py:170-173` — inbound DMs-only fail-closed deny.
- F1–F7 (post-L7) test suite green: 543 tests pass.

## Outputs

What exists after this leg completes:

- `tests/test_pairing_prefix.py` (NEW) — ~6 unit tests pinning `_validate_pairing_prefix`'s claims.
- `the_one/connectors/_acl.py` — F8 marker comments adjacent to both DMs-only branches.
- F1–F7 regression suite unchanged; new tests added.

## Acceptance Criteria

- [ ] `tests/test_pairing_prefix.py` (NEW) ships with the following test cases:
  - `test_validates_correct_prefix_and_strips` — `_validate_pairing_prefix("PAIR abc hello", "abc")` → `(True, "hello")`.
  - `test_wrong_code_returns_false_and_unchanged_text` — `_validate_pairing_prefix("PAIR wrong hello", "abc")` → `(False, "PAIR wrong hello")`.
  - `test_empty_code_never_matches` — `_validate_pairing_prefix("PAIR abc hello", "")` → `(False, "PAIR abc hello")`.
  - `test_missing_prefix_returns_false` — `_validate_pairing_prefix("abc hello", "abc")` → `(False, "abc hello")`.
  - `test_case_sensitive_pair_keyword` — `_validate_pairing_prefix("pair abc hello", "abc")` → `(False, "pair abc hello")` (PAIR is case-sensitive; lowercase fails).
  - `test_case_sensitive_code_comparison` — `_validate_pairing_prefix("PAIR ABC hello", "abc")` → `(False, "PAIR ABC hello")` (byte-equality on code).
  - `test_leading_whitespace_fails` — `_validate_pairing_prefix(" PAIR abc hello", "abc")` → `(False, " PAIR abc hello")` (commands at column 0).
  - `test_code_with_internal_whitespace_fails` — `_validate_pairing_prefix("PAIR ab cd hello", "ab cd")` → `(False, "PAIR ab cd hello")` (single-space separator; codes with whitespace not permitted via the parser).
  - Style mirrors `tests/test_connectors_acl.py` — inline minimal usage; no heavyweight fixtures.
- [ ] `the_one/connectors/_acl.py` carries F8 marker comments at both DMs-only deny sites:
  - At `_acl.py:97-99` (outbound DMs-only branch — inside `admits_outbound`'s `elif agent_channels == []:`): add a one-line comment immediately above the `return` statement explicitly naming F8 as the consumer that will replace this fail-closed deny: `# F8: DM classification lands here — replace this fail-closed deny with "permit if envelope is a DM; else deny."`
  - At `_acl.py:170-173` (inbound DMs-only branch — inside `admits_inbound`'s `elif agent_channels == []:`): same comment shape.
- [ ] F1–F7 regression suite passes byte-identically:
  ```
  docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py tests/test_db_api.py tests/test_pairing*.py -x --timeout 30'
  ```
  Expected: prior 543 + 8 new pairing-prefix unit tests = ~551 passed. The `tests/test_pairing*.py` glob now resolves to the new file.

## Verification Steps

**Pairing-prefix unit tests** (in `tests/test_pairing_prefix.py`):
- Run `docker exec the-one pytest tests/test_pairing_prefix.py -v --timeout 30` — all 8 tests pass.

**F8 markers**:
- `grep -n "F8: DM classification lands here" the_one/connectors/_acl.py` — returns exactly 2 hits (one per branch).

**Regression**:
- Full suite green: ~551 tests pass.

## Implementation Guidance

### 1. New unit-test file `tests/test_pairing_prefix.py`

```python
"""Unit tests for ``the_one.connectors._pairing._validate_pairing_prefix``.

M10 F7 L8: closes F6 debrief carry-forward — the pairing helper is
integration-tested only via the dispatcher path
(``tests/test_connectors_inbound.py`` NeedsPairing-path tests). This
module pins the helper's byte-equality + case-sensitivity claims at
the unit level so a future refactor that drifts the prefix-parsing
semantic is caught here instead of cascading into dispatcher failures.

The helper's docstring at ``the_one/connectors/_pairing.py:18-31``
documents the contract this module verifies.
"""

from __future__ import annotations

from the_one.connectors._pairing import _validate_pairing_prefix


class TestValidatePairingPrefix:
    # ... 8 tests per Acceptance Criteria ...
```

### 2. F8 markers in `_acl.py`

Edit lines 97-99 and 170-173 to add a comment immediately above each `return` statement. The comment should be concise and explicit about what F8 will do.

### 3. Order of file edits

1. `tests/test_pairing_prefix.py` (new).
2. `the_one/connectors/_acl.py` (add 2 F8 marker comments).
3. Run regression.

### 4. Things NOT in scope

- The `connector-account-editor.js` Enable-toggle scan from F6 debrief — explicitly out of L7/L8 scope per the flight spec; stays in `/routine-maintenance`.
- Any other F6 follow-up not explicitly named here.

## Edge Cases

- **Empty text**: `_validate_pairing_prefix("", "abc")` — does not start with `"PAIR "` → returns `(False, "")`. Add a test if desired; the docstring covers it via the `startswith` semantic.
- **Code identical to a substring of a prefix-only-matched text**: `_validate_pairing_prefix("PAIR abcdef hello", "abc")` — expects code `"abc"` followed by space, the actual `"abcdef"` doesn't have a space after `abc` → returns `(False, "PAIR abcdef hello")`. Optional sharpening test.

## Files Affected

- `tests/test_pairing_prefix.py` (NEW) — unit tests.
- `the_one/connectors/_acl.py` — two F8 marker comments.

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

## Citation Audit

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/connectors/_pairing.py:18-31` (`_validate_pairing_prefix` docstring) | OK | Helper claims documented |
| `the_one/connectors/_acl.py:97-99` (outbound DMs-only deny) | OK | Post-L2 marker target |
| `the_one/connectors/_acl.py:170-173` (inbound DMs-only deny) | OK | Post-L2 marker target |
| `tests/test_connectors_inbound.py:1165-1380` (integration-only coverage to date) | OK | F6 debrief claim verified |
