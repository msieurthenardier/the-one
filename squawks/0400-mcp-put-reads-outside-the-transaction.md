# Squawk 0400: The MCP server PUT still reads the row outside its write transaction

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

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
*(written at completion)*

## Verification
A race test like the provider one shows that an OAuth refresh written while the PUT waits on the
write lock survives the PUT. It fails with the old read restored. The MCP route suites pass
unedited.
