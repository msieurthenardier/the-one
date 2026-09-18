# Squawk 0081: `create_provider` and `create_chat_session` 500 on a malformed body instead of 422

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-18
**Completed**: —

## Report

`POST /api/providers` and `POST /api/chat/sessions` call
`Model.model_validate(data)` with no `try/except ValidationError`, so any
malformed request body raises out of the handler as an **unhandled 500** rather
than the 422 every sibling route returns.

Reproduced against a dev instance (port 8485, scratch data dir — never 8484):

| Body | Observed | Expected |
|---|---|---|
| `{"name":"x1","type":"mock","config":{}}` (omits required `base_url`) | **500** | 422 |
| `{"type":"mock","base_url":""}` (omits required `name`) | **500** | 422 |
| `{"name":"x3","type":"nonsense","base_url":""}` (invalid `type`) | **500** | 422 |
| `POST /api/knowledge-bases {"id":"../../evil"}` (sibling, for contrast) | 422 | 422 |

The project's own documentation already states the intended behaviour and is
wrong about the current behaviour: `tests/browser/seeders.py::seed_mock_provider`
explains it sends `base_url=""` because `LLMProviderConfig.base_url` "has no
default and **Pydantic 422s if the field is omitted**". It 500s.

Found incidentally while seeding a dev instance for Mission 24 Flight 6's
`kb-studio-round-trip` behavior test.

## Evidence

- `the_one/interfaces/web/api.py::create_provider` — `provider =
  LLMProviderConfig.model_validate(data)`, unguarded.
- `the_one/interfaces/web/api.py::create_chat_session` — same shape, unguarded.
- **Two of eighteen** `model_validate` call sites in that module lack the guard.
  The sixteen that have it include `create_agent`, `create_knowledge_base`,
  `create_kb_item`, `create_mcp_source`, `create_connector`,
  `update_chat_session` and — notably — **`update_provider`**, so the create and
  update halves of the same resource disagree.
- The established pattern, e.g. `create_knowledge_base`:
  `except ValidationError as e: raise HTTPException(status_code=422,
  detail=e.errors(include_context=False))`.
- `tests/browser/seeders.py::seed_mock_provider` docstring — asserts the 422 that
  does not happen.

## Disposition

**Deferred**: found mid-flight during Mission 24 Flight 6, entirely outside that
flight's surface (LLM providers and chat sessions, not knowledge bases). Not
`grounding` — it does not sit in the flight's path, and the flight works around
it simply by sending well-formed bodies.

**Revisit when**: the next turnaround batch. This qualifies cleanly as a squawk —
one coherent item (a guard applied at sixteen sites and missed at two), no design
decisions (the fix is the established pattern, copied), bounded blast radius (two
handlers, no schema or shared-interface change; no caller can depend on a 500),
and verifiable by unit tests asserting 422 for each malformed-body case. The
stale `seed_mock_provider` docstring is corrected in the same pass.
