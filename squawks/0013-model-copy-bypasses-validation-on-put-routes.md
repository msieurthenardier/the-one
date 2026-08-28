# Squawk 0013: `model_copy(update=raw_json)` on four PUT routes bypasses pydantic validation and can permanently 500 the read path

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-27

## Report

Four PUT handlers merge the raw request JSON into the stored model with
`existing.model_copy(update=data)`. In pydantic v2 `model_copy(update=)` does not
re-run field validators or coercion, so a malformed value (wrong type, out-of-range
number, unknown `type` literal) or an unknown key is persisted silently instead of
returning 422. On the next read the repository rebuilds the row through the real
constructor, which *does* validate — so the corrupted row raises, and because
`LLMProviderRepository.list` is a single comprehension over all rows, one bad
provider 500s `GET /providers` for every provider, with no UI path to repair it (the
edit form's own GET is what fails). `update_connector` hit this exact bug in Mission 10
and carries the fix (`model_dump() | data → Model.model_validate(...)`) with an inline
comment; it was never propagated to the sibling routes. Confirmed empirically during
the 2026-08-27 inspection (P4).

Fix: apply the same round-trip at all four sites; remove the dead
`except ValidationError` around `model_copy` in `update_mcp_source` (it can never
fire); one test per route asserting a malformed PUT returns 422 and leaves the row
untouched.

## Evidence

- `the_one/interfaces/web/api.py:1417` `update_knowledge_base` —
  `updated = existing.model_copy(update=data)`
- `the_one/interfaces/web/api.py:2087` `update_mcp_source` — same, wrapped in a
  `try/except ValidationError` that is dead code; `_validate_mcp_source_config`
  (`:1758-1766`) incidentally catches an unknown `type` but not `name`/`secrets`
- `the_one/interfaces/web/api.py:4495` `update_chat_session` — same
- `the_one/interfaces/web/api.py:4876` `update_provider` — same
- `the_one/interfaces/web/api.py:3466-3472` `update_connector` — the correct pattern:
  "`model_copy(update=...)` does NOT re-run field validators in Pydantic v2 … Round-trip
  through `model_dump() | data → model_validate(...)` … M10 F2 L6."
- `the_one/db/repositories.py:1742-1745` — `list()`/`get()` rebuild via `_row_to_model`
  → full constructor, uncaught.

## Corrective Action

Applied the `update_connector` round-trip pattern (`existing.model_dump() → merge
data → Model.model_validate(...)`, `ValidationError` mapped to
`HTTPException(422, detail=e.errors(include_context=False))`) at all four sites in
`the_one/interfaces/web/api.py`:

- `update_knowledge_base` (~:1409) — merge happens after `data["id"] = kb_id` is set,
  same as before; no other pre-merge key handling in this route.
- `update_mcp_source` (~:2005) — the merge now runs *after* the existing per-key
  `__MASKED__` secrets resolution, the OAuth-managed-keys preservation block, and the
  `_cache` config normalisation (unchanged ordering); the dead
  `try/except ValidationError` that used to wrap the bare `model_copy(update=data)`
  was removed and replaced with the real try/except around the round-trip, so the
  `except ValidationError` clause is now reachable. `_reject_reserved_surface_name`
  and `_validate_mcp_source_config` still run afterward, in the same order.
- `update_chat_session` (~:4487) — same pattern, no pre-merge key handling in this
  route.
- `update_provider` (~:4839) — merge happens after the mock/dev_mode gate, the
  masked-`api_key` resolution, and the OAuth-managed-secrets resolution (unchanged
  ordering); the `_is_safe_provider_url` check on `updated.base_url` still runs
  *after* the round-trip, preserving the "resolved base_url, post-merge" sequencing
  the existing comment calls out (comment wording updated to reference the new
  round-trip instead of `model_copy`).

All four models (`KnowledgeBase`, `MCPSource`, `ChatSession`, `LLMProviderConfig`)
have only plain JSON-serializable fields (`str`, `str | None`, `dict`, `Literal[str]`)
with no `datetime` objects, aliases, or computed fields — confirmed no
`model_dump()`/`model_validate()` round-trip pitfalls beyond what `update_connector`
already handles. No site required a model change or design decision; nothing was
escalated or reverted.

## Verification

Added one test per route (malformed PUT → 422 + row unchanged, valid PUT → success):

- `tests/test_db_api.py::TestKnowledgeBaseAPI::test_update_with_wrong_type_rejected`
- `tests/test_db_api.py::TestMCPSourceAPI::test_update_with_invalid_type_rejected`
- `tests/test_db_api.py::TestChatSessionAPI::test_update_with_wrong_type_rejected`
- `tests/test_provider_api.py::...::test_update_with_invalid_type_rejected`

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_api.py
tests/test_provider_api.py -x --timeout 60` → 307 passed.

`make lint` → all checks passed. `make format-check` → 441 files already formatted
(no `make format` needed).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `squawk/turnaround-2026-08-27` — PR pending (sha recorded on close)
