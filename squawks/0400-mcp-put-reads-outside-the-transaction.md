# Squawk 0400: The MCP server PUT still reads the row outside its write transaction

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-23

## Report

The operator's MCP server save, `replace_mcp_source` (PUT `/api/mcp-sources/{id}`), reads the row
outside the transaction and writes it inside one. It then pins the OAuth-managed secret keys and
`_cache` from that earlier read.

An OAuth token refresh or a Test's `merge_cache` that lands between the read and the write is
overwritten with stale values. A rotated refresh token lost this way breaks sign-in.

This is the same race Mission 36 Flight 4 Leg 5a fixed for providers. The MCP proposal path
(`change_mcp_source`) already runs on `update_in_txn`. Only the operator PUT keeps the old
behaviour: Leg 4a moved the route code verbatim.

Found by the Flight 4 Batch B Reviewer.

## Evidence
- `the_one/mcp/service.py` `replace_mcp_source`: `existing = await repo.get(source_id)`, then
  `repo.update(...)`. The read and the write are separate transactions.
- `the_one/llm/provider_service.py` `replace_provider`, on `update_in_txn`: the fixed pattern.
- `tests/test_provider_service.py`: the deterministic race test recipe (hold `write_transaction`,
  then write the token raw) to copy.

## Corrective Action
`the_one/mcp/service.py::replace_mcp_source` now does its read and write inside one
`repo.update_in_txn(source_id, mutate)`. Everything that read the stored row (the surface-row
refusal, the per-key mask resolution, the OAuth-key pinning, the `_cache` preserve, the merge and
validation, the name checks and `_prune_cache_on_server_change`) moved into a sync `mutate`, which
works on copies so the caller's dicts are never changed. `KeyError` still becomes
`McpSourceNotFound`, and `_after_write` runs after the commit.

## Verification
`tests/test_mcp_service.py::test_a_refresh_written_while_a_replace_waits_for_the_lock_survives`
(Leg 1b). Falsified: with a stale pre-read row fed to `mutate`, it fails. The MCP route suites
pass with their assertion lines unedited. Original plan: a race test like the provider one shows that an OAuth refresh written while the PUT waits on the
write lock survives the PUT. It fails with the old read restored. The MCP route suites pass
unedited.

## Sign-Off
- **Fixed in:** Mission 36 Flight 5, Leg 1b.
- **Reviewed:** by the Flight 5 Batch A Reviewer (Sonnet, the security-sensitive tier):
  `[HANDOFF:confirmed]`, 2026-11-23. The Reviewer confirmed, from `git show` of the old code,
  that the race test fails on the pre-fix read-then-write.
- **Committed:** in the Flight 5 Batch A checkpoint commit (its ref is in the flight log).
