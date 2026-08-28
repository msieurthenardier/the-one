# Squawk 0013: `model_copy(update=raw_json)` on four PUT routes bypasses pydantic validation and can permanently 500 the read path

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
