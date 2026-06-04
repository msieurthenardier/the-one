# Leg: bring-tree-into-compliance

**Status**: completed
**Flight**: [Lint/Format Enforcement Gate](../flight.md)

## Objective
Bring the working tree to a zero ruff baseline (0 lint violations, 0 would-reformat) and remove the dead `# noqa: BLE001` vestiges — the one-time cleanup that the enforcement gate (Leg 2) will then hold.

## Context
- Maintenance report 2026-06-04, finding **Q1**: 78 ruff violations + 97 of 322 files would be reformatted; third recurrence of baseline drift.
- Breakdown: 33 I001 (unsorted-imports), 21 E501 (line-too-long), 10 F401 (unused-import), 6 N802 (invalid-function-name), 5 N818 (error-suffix-on-exception-name), 2 E402 (module-import-not-at-top), 1 N806 (non-lowercase-var). 43 of 78 are auto-fixable.
- Top offenders: `tests/test_connectors_discord.py` (14), `the_one/connectors/_inference.py` (4), `the_one/db/schema.py` (4), `tests/test_connectors_policy_gate.py` (4).
- The dead `# noqa: BLE001` comments suppress a rule not in the selected ruleset (`pyproject.toml` `select = ["E","F","I","N","W"]`) — dead no-ops. **Corrected count (design review): 12 in `.py` files, not 10** — `connector_history.py` (7), `api.py` (3), `test_connectors_discord.py` (1), `the_one/mcp/cache_cleanup.py` (1). (There is also 1 in `the_one/connectors/README.md` — a doc example, out of scope here; candidate for Flight 06's doc scrub.)

## Inputs
- Current tree with 78 violations + 97 unformatted files.
- `pyproject.toml` ruff config (`[tool.ruff]` line-length 100, `[tool.ruff.lint] select = ["E","F","I","N","W"]`).

## Outputs
- Tree at 0 lint violations and 0 would-reformat.
- Dead `noqa: BLE001` comments removed.

## Acceptance Criteria
- [x] `ruff check the_one/ tests/` → 0 errors
- [x] `ruff format --check the_one/ tests/` → all files already formatted (322 files)
- [x] N818 residuals (5 `_Stub*` classes in `test_connectors_discord.py`) resolved by a *targeted, justified* `# noqa: N818`; N802 residuals (6) resolved by a *targeted, justified* `# noqa: N802`; no blanket suppression
- [x] E402 (2) resolved by moving the import to the top block; N806 (1, `_FRONTEND_FIELDS`) resolved by lowercase rename
- [x] String-literal wrapping for E501 in `schema.py` (migration SQL) and `_inference.py` (prompt literals) preserves exact content — verified byte-identical via AST comparison (developer + independent reviewer)
- [x] No `# noqa: BLE001` comments remain in `.py` files (12 removed); ruleset left as-is
- [x] `api.py:2463`'s `except` clause left semantically untouched — only its dead noqa removed
- [x] Full test suite green — 2935 passed in-container

## Verification Steps
- `make lint` (or `ruff check the_one/ tests/`) → exits 0
- `ruff format --check the_one/ tests/` → "all files already formatted"
- `grep -rn "noqa: BLE001" the_one/ tests/` → no results (`.py` tree clean)
- `docker exec the-one pytest tests/ -q -x` → green

## Implementation Guidance

1. **Auto-fix the mechanical 43**
   - `ruff check --fix the_one/ tests/` clears I001 + F401. **Verified safe for this tree (design review):** all 10 F401s are in test files, none in an `__init__.py`, none near `__all__` — no re-export risk. Still eyeball the diff.

2. **Format**
   - `ruff format the_one/ tests/` clears the 97 would-reformat files. For the migration-SQL strings in `schema.py` and prompt literals in `_inference.py`, the E501 wrapping in step 3 must happen such that `ruff format` then leaves them stable — confirm content is byte-identical (see Acceptance Criteria).

3. **Resolve the 35 manual residuals** (full enumeration from design review):
   - **N818 (5)** — `_StubLoginFailure` (:111), `_StubPrivilegedIntentsRequired` (:115), `_StubGatewayNotFound` (:119), `_StubConnectionClosed` (:123), `_StubHTTPException` (:127), all in `tests/test_connectors_discord.py`. These deliberately mirror discord.py's own exception names (aliased into `_StubErrors`). **Add `# noqa: N818  # mirrors discord.py exception name` — do NOT rename.**
   - **N802 (6)** — test methods embedding external JS handler names / a step label: `test_connectors_inbound.py:2729` (`...after_L6`), `tests/browser/test_connector_form_registry.py:134`, `tests/browser/test_flow_studio_connector_allowlist_dropdown.py:218`, `tests/browser/test_flow_studio_connector_discoverable_dropdown.py:166` & `:190`, `tests/browser/test_flow_studio_connector_routing_dropdown.py:374`. **Add `# noqa: N802` with a one-line justification** ("test name mirrors JS handler `onChange`/`optionalFns`" etc.) to preserve the descriptive correspondence — these have no external callers, so rename is also safe if preferred, but noqa keeps the readable names.
   - **E402 (2)** — `tests/test_connectors_pool.py:596`, `tests/test_lifespan.py:319`. No load-order reason — **move both to the top import block** (no noqa).
   - **N806 (1)** — `the_one/interfaces/web/api.py:3007` `_FRONTEND_FIELDS` (function-local set). **Rename to `_frontend_fields`** (purely local, no external ref).
   - **E501 (21)** — `_acl.py:737`, `_inbound.py:860` (a 283-char `# NOTE` comment — wrap the comment), `_inference.py:73/76/77/79` (prompt strings — wrap via implicit string concatenation), `db/models.py:240`, `db/repositories.py:164`, `db/schema.py:826/827/1124/1125/1150/1151` (**migration SQL — wrap as concatenated strings, never alter SQL text/whitespace**), `tests/browser/test_connector_form_registry.py:186`, `tests/browser/test_flow_chat_peer_attribution.py:266`, `tests/browser/test_flow_studio_connector_inference_provider_row.py:122`, `tests/test_connectors_inference.py:258/314/333`, `tests/test_llm_provider_cross_provider_history.py:90`.

4. **Remove the dead BLE001 vestiges**
   - Delete the 12 `# noqa: BLE001` comments across `connector_history.py` (7), `api.py` (3), `test_connectors_discord.py` (1), `the_one/mcp/cache_cleanup.py` (1). Leave the ruleset as-is (do NOT add `BLE`/`B` to `select` — that is a separate ruleset decision).
   - **At `api.py:2463`**: remove only the noqa; leave the `except (ConnectorClientError, Exception)` clause exactly as written. Its redundant-`Exception`-tuple is a real issue but is Flight 03 T1/T2's to fix — do not touch it here.

5. **Re-run the suite** — renames and import reordering can break references; confirm green.

## Edge Cases
- **`ConnectorAuthRequired` is already noqa-suppressed and is NOT a current residual.** It carries `# noqa: N818` at `the_one/connectors/errors.py:36` (control-flow signal). The 5 N818 violations are the `_Stub*` test classes only. **Leave `ConnectorAuthRequired` and its noqa untouched** — Flight 03 Q2 may delete the symbol entirely; do not rename or churn it here.
- **Migration SQL string wrapping (`schema.py`)**: these strings are DDL/DML applied to live DBs. Wrap by Python string concatenation only; the resulting string must be byte-identical to the original. A dropped space inside an SQL keyword boundary would be a silent correctness bug the suite might not catch.

## Files Affected
- Many across `the_one/` and `tests/` (formatting, ~97 files); lint residuals concentrated in `tests/test_connectors_discord.py`, `the_one/connectors/_inference.py`, `the_one/db/schema.py`, `the_one/interfaces/web/api.py`, and the `tests/browser/*` files listed above; BLE001 removals in `connector_history.py`, `api.py`, `test_connectors_discord.py`, `the_one/mcp/cache_cleanup.py`. Ruleset (`pyproject.toml`) left unchanged.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight: (not final)
- [x] Commit all changes together (code + artifacts)
