# Squawk 0040: Discord group-DM (type=3) channel-name capture is untested

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-03

## Report

Flight 4's Discord channel-name directory capture (in `_resolve_channel_type`'s
cache-miss path) has tests for guild channels and threads but none for a group DM
(channel `type=3`), which has no `name` field in the same shape. Add one fixture test
pinning the behavior (whatever it is — capture with a fallback name, or skip) so the
edge is a decision, not an accident.

## Evidence

- `the_one/connectors/discord/plugin.py` — channel capture at the cache-miss site
- Flight 4 flight-end review, non-blocking note (2026-09-02)

## Corrective Action

Read `_upsert_channel_directory` in `the_one/connectors/discord/plugin.py`
before touching anything: the cache-miss capture path already does
`name = channel.get("name"); if not name: return` — a group DM (`type=3`)
falls through the same falsy-name check as a 1:1 DM (`type=1`), so it is
never written into the channel directory and never produces an
empty-string directory name (the outcome leg 1's rule forbids). The
existing behavior is reasonable and required no redesign — this squawk
pins it, per the qualification gate, rather than expanding scope.

What group DMs add that a 1:1 DM doesn't: Discord's `Get Channel` schema
gives a group DM a `"name"` key that is nullable (present, `null`, when
the group hasn't been custom-named) rather than simply absent the way a
1:1 DM's response is. `.get("name")` collapses both shapes to `None`, so
the code path is identical either way — but the prior test suite only
covered the "key absent" (1:1 DM) shape, not the "key present but null"
(group DM) shape, which is the actual gap the squawk's report named.

Changes:
- `the_one/connectors/discord/plugin.py` — added a comment at the
  `if not name: return` skip site in `_upsert_channel_directory`,
  explicitly naming the group-DM (`type=3`) nullable-`name` shape and
  stating that it's a deliberate, pinned decision (same skip as a 1:1
  DM), not an oversight. +5 lines; no behavior change.
- `tests/test_discord_plugin.py` — added a `"group-dm-channel-1":
  {"type": 3, "name": None}` fixture entry (explicit null, distinct from
  the 1:1 DM entry's absent key) and one new test,
  `test_group_dm_channel_carries_null_name_and_is_not_captured`, which
  sends a message through `_translate_message_create` on that channel
  and asserts `envelope.is_dm is True` and that
  `ConnectorDirectoryRepository.get(...)` returns `None` for it — pinning
  "group DM never gets a channel-directory row" as a tested decision.

No source behavior changed. Scope stayed within the leg-1 rule (skip on
falsy name / never an empty-string directory name); no design decision
was needed, so no escalation.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_discord_plugin.py -x --timeout 30`
  → `25 passed` (was 24; the new group-DM test is included and passes).
- `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`
  → both clean (`ruff format --check` initially flagged the new test
  block; ran `.venv/bin/ruff format tests/test_discord_plugin.py` to
  apply canonical formatting, then re-ran both checks clean).
- Discord subpackage line count: 854 total after this change (budget
  1,100) — well within budget; `plugin.py` grew by 5 lines (comment
  only), the rest of the diff is test-only.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet — security tier for 0037), squawk/turnaround-2026-09-03
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03 batch commit (PR follows)
