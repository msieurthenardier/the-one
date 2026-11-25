# Squawk 0417: A failed page-line item lookup is swallowed without a log line

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

GleepGlorp's page line resolves the open item's name. When that lookup raises, the code falls back to no name, which is correct because it must not fail the turn, but nothing is logged. A drawer that keeps saying "Looking at Agents" with no item name can't be diagnosed. The sibling handlers in `settings.py`, `status_rows.py` and `view_core.py` all log. Found by the 2026-11-24 routine maintenance (Python Inspector).

## Evidence
- `the_one/gleepglorp/page.py` (about line 312): `except Exception:  # noqa: BLE001 - a lookup failure must not fail the turn` then `name, item_id = None, None`, with no log call.
- Compare `view_core.py` (about line 628): `logger.debug("read_app_config: %s %r unreadable", ..., exc_info=True)`.

## Corrective Action
`the_one/gleepglorp/page.py` had no logger; added `import logging` and `logger = logging.getLogger(__name__)` (the sibling modules' style) and a `logger.debug("resolve_page: item lookup failed; line built without a name", exc_info=True)` in the broad `except` of `resolve_page`. Behaviour unchanged. Added `test_a_lookup_failure_is_logged_at_debug_and_the_line_has_no_name` to `tests/test_gleepglorp_page.py`.

## Verification
The test forces `MCPSourceRepository.get` to raise, asserts the line is still built (`Library › MCP servers › m-http`, the raw id as segment, no stored name) and that exactly one DEBUG record with `exc_info` is captured. Falsified: with the `logger.debug` line removed the test failed (`0 == 1` records); restored, `tests/test_gleepglorp_page.py` passes. Ruff check and format clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0411-0419
**Verdict**: confirmed. The message is a constant string. With `exc_info`, a database error's text can reach the debug log, but no descriptor or secret value can.
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
