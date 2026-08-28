# Leg: ext-credential-trace

**Status**: completed
**Flight**: [Credential lifecycle integrity and observability](../flight.md)

## Objective
Every issuance and every disappearance of an `ext_` external credential leaves an operator-readable INFO log line — mint / revoke / rotate at the route layer (agent, identifier, label, principal; never the secret) and the two cascade points where rows vanish without an explicit revoke (surface disable, agent delete) — with the "no `revoked_at` tombstone" decision recorded in the docs.

## Context
- **Flight Design Decision Q2**: log lines including cascade points; no tombstone. The route layer owns the mint/revoke/rotate lines; `self_configuration/manage.py` owns the cascade lines (it is the only place that knows a surface teardown is happening). The format chosen here becomes the convention the Advisory logging sweep (maintenance report P8) inherits.
- **Why cascades matter**: `agent_external_credentials.source_id REFERENCES mcp_sources(id) ON DELETE CASCADE` — `manage.disable` and `manage.cascade_delete` both `mcp_repo.delete(row.id)` and then `external_credentials.unregister(row.id)`. The rows are gone before anything could read their labels; the in-memory registry is the only thing that still knows which identifiers died. So cascade lines carry identifiers (and count), not labels — the mint line already binds identifier → label.
- **Three entrypoints reach `disable`**: `DELETE /api/agents/{name}/self-configuration` (`api.py:1007`), the direct `DELETE /api/mcp-sources/{id}` path when the row is a surface row (`api.py:2174`), and `cascade_delete` from `DELETE /api/agents/{name}` (`api.py:835`). Logging inside `manage.py` covers all three with two lines of code.
- **Principal**: `/api/...` routes are behind `CredentialGateMiddleware`, which stamps `scope[CALLER_SCOPE_KEY]` with an `IdentifiedCaller(identifier, source)` (`middleware.py:194, :383`). `ext_`/`agt_` callers are confined to `/mcp/self-configuration`, so the principal on these routes is always the operator credential — still worth logging (`source:identifier`) because it is the mission's stated minimum and it is free. The only production reader of `CALLER_SCOPE_KEY` today is `self_configuration/surface.py:80`; the throwaway test apps mount no middleware, so the routes must tolerate an absent caller.
- **Logging pattern to mirror**: `self_configuration/pending.py:66, :98, :103` — `logger.info("self-configuration: ...", agent_name, ...)` with `%r` for names. `manage.py` already has a module `logger` (`manage.py:35`); `api.py` has one at `api.py:72`.
- **Prior-leg learnings**: Leg 1 landed (4550 passed / 0 failed) touching `api.py` only in its imports (+3 lines) and the rotation route at the bottom of the file; the line numbers below were re-verified against the landed tree on 2026-08-28. Leg 1's Developer noted the codebase's consumer-callsite-audit convention bites on any public-shape change — `unregister`'s new return value has exactly two in-repo consumers (both in `manage.py`), listed in AC4.

## Inputs
- `the_one/interfaces/web/api.py`: `mint_external_credential` (`@router.post("/agents/{name}/self-configuration/external-credentials")`, `api.py:1046-1047`), `revoke_external_credential` (`api.py:1114`), `rotate_external_credential` (`api.py:1128`), `delete_agent` (`api.py:825`), the self-configuration disable route (`api.py:~993-1009`), the mcp-source delete surface-row branch (`api.py:~2163-2179`). Routes that already take `request: Request` for reference: `api.py:439, :536, :712`.
- `the_one/self_configuration/external_credentials.py`: `register` (`:55`), `unregister(source_id)` (`:62`, returns `None`, computes `stale` list internally), `unregister_identifier` (`:73`).
- `the_one/self_configuration/manage.py`: `disable` (`:221-271`, `external_credentials.unregister(row.id)` at `:270`), `cascade_delete` (`:398-421`, `unregister` at `:421`).
- `the_one/interfaces/web/middleware.py:194` `CALLER_SCOPE_KEY`; `the_one/api_credential.py:136` `IdentifiedCaller(identifier, source)`.
- `tests/test_self_configuration_external.py` — `env` fixture (throwaway `FastAPI()` + router, no middleware, `auth_headers()`), `_isolated_registries` autouse fixture, `_create_agent` helper, existing tests for mint/revoke/rotate/disable/agent-delete (`:128-336`).
- Docs: `the_one/agents.md:821` "External-client credential (M21 F03)" (bullet 2 says "Hard-revoke is a row DELETE (no `revoked_at` tombstone); the audit ... lives in the revision log"); `SECURITY-MODEL.md:275` "External-client access to the self-configuration surface (M21 F03)".

## Outputs
- Three route-layer INFO lines (mint / revoke / rotate) and two cascade INFO lines (`disable`, `cascade_delete`), all through module loggers.
- `external_credentials.unregister` returns the list of evicted identifiers.
- Tests in `tests/test_self_configuration_external.py` asserting each line's content and the absence of the secret.
- `agents.md` and `SECURITY-MODEL.md` external-credential sections gain an "operational trace" bullet recording the Q2 decision.
- Flight log leg entry; leg status `landed`.

## Acceptance Criteria
- [x] AC1 — `POST .../external-credentials` (mint) emits one INFO record on the `the_one.interfaces.web.api` logger containing the agent name, the new `ext_` identifier, the label, and the principal; the record's message does **not** contain the secret component of the token (assert `credential.secret not in caplog.text`).
- [x] AC2 — `DELETE .../external-credentials/{identifier}` (revoke) emits one INFO record with agent name, identifier, label, principal. Emitted only on the success path (after the 404 guard).
- [x] AC3 — `POST .../external-credentials/{identifier}/rotate` emits one INFO record with agent name, old identifier, new identifier, label, principal; neither the old nor the new secret appears in `caplog.text`.
- [x] AC4 — `external_credentials.unregister(source_id)` returns `list[str]` of the identifiers it evicted (empty list on no-match); existing behavior otherwise unchanged; its docstring updated.
- [x] AC5 — `manage.disable` emits one INFO record on the `the_one.self_configuration.manage` logger when at least one external credential was cascade-revoked: agent name, surface row id, count, and the identifiers. No record when zero were evicted. Reached through all three entrypoints — the self-configuration DELETE route, the direct `DELETE /api/mcp-sources/{id}` surface-row branch, and (via `cascade_delete`) `DELETE /api/agents/{name}` — each covered by a test.
- [x] AC6 — `manage.cascade_delete` emits the equivalent record with the cause "agent deleted".
- [x] AC7 — Principal rendering: `"{caller.source}:{caller.identifier}"` when `request.scope[CALLER_SCOPE_KEY]` is present, `"-"` when absent. One test wraps the throwaway app in a two-line pure-ASGI shim that stamps `scope[CALLER_SCOPE_KEY] = IdentifiedCaller(identifier="loc_test", source="file")` and asserts `file:loc_test` appears in the mint record; the other tests accept `-`.
- [x] AC8 — `agents.md:821` section and `SECURITY-MODEL.md:275` section each gain a bullet: the mint/revoke/rotate/cascade trace is INFO log lines (fields listed), the tombstone was considered and rejected (FK cascade would bypass it; a queryable audit is an events table — separate initiative), and the log-line field set is the convention for future credential lifecycle logging.
- [x] AC9 — No secret, token, or operator home path appears in any new log line, test, or doc; `ruff check` / `ruff format --check` clean; `make test-unit` green.

## Verification Steps
- AC1–AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_external.py tests/test_self_configuration_api.py -x --timeout 60` — new tests use `caplog.at_level(logging.INFO, logger=...)` and assert on `record.getMessage()`.
- AC4: `grep -n "def unregister" -A12 the_one/self_configuration/external_credentials.py` shows the return; `grep -rn "external_credentials.unregister(" the_one tests` lists every consumer (expected: `manage.py` ×2 plus tests).
- AC8: `grep -n "operational trace\|revoked_at" the_one/agents.md SECURITY-MODEL.md`.
- AC9: `grep -rn "/home/" the_one/agents.md SECURITY-MODEL.md tests/test_self_configuration_external.py` empty; `.venv/bin/ruff check . && .venv/bin/ruff format --check .`; `make test-unit` in the background with `tail --pid`.

## Implementation Guidance
1. **`external_credentials.unregister`** — build `stale` as today, delete each, `return stale`. Update the docstring ("returns the evicted identifiers so surface-teardown callers can log them").
2. **`manage.py`** — in `disable` and `cascade_delete`, replace `external_credentials.unregister(row.id)` with `evicted = external_credentials.unregister(row.id)` followed by `if evicted: logger.info("external-credential: surface %s for agent %r %s; cascade-revoked %d external credential(s): %s", row.id, agent_name, "disabled" | "removed with the agent", len(evicted), evicted)`. Two call sites, same shape; keep the existing DD9 comments.
3. **`api.py` routes** — add a private helper next to the external-credential routes: `def _caller_principal(request: Request) -> str` returning `f"{caller.source}:{caller.identifier}"` or `"-"`, reading `request.scope.get(CALLER_SCOPE_KEY)`. Import `CALLER_SCOPE_KEY` from `the_one.interfaces.web.middleware` — check for an import cycle first (`middleware.py` must not import `api.py`; `surface.py` already imports the constant, so it is safe from the self-configuration side). Add `request: Request` to `mint_external_credential`, `revoke_external_credential`, `rotate_external_credential`. Log lines (INFO, module `logger`):
   - mint, after `register`: `"external-credential: minted %s (label=%r) for agent %r by %s"`
   - revoke, after `unregister_identifier`: `"external-credential: revoked %s (label=%r) for agent %r by %s"` — the label comes from the `cred` dict `_external_credential_of_agent_or_404` already returns.
   - rotate, after the new `register`: `"external-credential: rotated %s -> %s (label=%r) for agent %r by %s"`.
   - Never pass `credential`, `token`, or `secret` objects to the formatter — only `.identifier` strings and the label.
4. **Tests** (`tests/test_self_configuration_external.py`) — a `TestLifecycleTrace` class: one test per AC1–AC7 shape. Filter `caplog.records` by logger name and the `external-credential:` prefix so unrelated INFO lines don't matter. For the direct-mcp-source-delete entrypoint: mint, then `DELETE /api/mcp-sources/{source_id}` (find the id via `env.mcp_repo()` + `find_surface_row`), assert the cascade record. For the ASGI shim: `async def shim(scope, receive, send): scope[CALLER_SCOPE_KEY] = IdentifiedCaller("loc_test", "file"); await test_app(scope, receive, send)` and build the `AsyncClient` against `ASGITransport(app=shim)` — build this test's own app/client inline rather than changing the `env` fixture.
5. **Docs** — one bullet in each section (AC8). Keep to the facts; do not restate the FK design.
6. **Leg-end** — ruff, `make test-unit` in the background, flight-log entry, status `landed`. No commit.

## Edge Cases
- **Registry/DB skew at cascade time**: the cascade line reports what the registry evicted. In production the registry is rebuilt from the store at startup (`load_from_rows`) and mutated live, so it matches; a mismatch would mean rows the process never knew about — acceptable, note it in the docstring.
- **Revoke on an orphaned surface** (allowed today): the log line still carries the agent name and label — no change.
- **404 paths**: no log line (nothing changed). Do not log attempts.
- **Double-disable**: `disable` returns early on `row is None` before reaching the log — no line, correct.
- **`Request` on routes that had none**: FastAPI injects it by type annotation; the throwaway test app supplies a scope with no `CALLER_SCOPE_KEY` → `"-"`.

## Files Affected
- `the_one/self_configuration/external_credentials.py` — `unregister` returns evicted identifiers
- `the_one/self_configuration/manage.py` — cascade log lines in `disable` and `cascade_delete`
- `the_one/interfaces/web/api.py` — `_caller_principal`, `request: Request` on three routes, three log lines
- `tests/test_self_configuration_external.py` — `TestLifecycleTrace`
- `the_one/agents.md`, `SECURITY-MODEL.md` — trace + no-tombstone bullets
- `missions/22-maintenance/flights/01-credential-lifecycle-integrity/flight-log.md` — leg entry

## Citation Audit
Drafted 2026-08-28 against `2f48a55`; **re-verified 2026-08-28 after Leg 1 landed** (uncommitted tree; `api.py` shifted +3, `manage.py` −1): `api.py:825` `delete_agent`, `:835` `cascade_delete` call, `:1046-1047` mint route, `:1114` revoke, `:1128` rotate, `:1007` disable call, `:2174` second disable call, `:439/:536/:712` `request: Request` precedents, `:72` module logger; `external_credentials.py:55/:62/:73`; `manage.py:35` logger, `:221` `disable`, `:270` unregister, `:398` `cascade_delete`, `:421` unregister; `middleware.py:194`, `:383`; `api_credential.py:136` `IdentifiedCaller`; `surface.py:80`; `pending.py:66/:98/:103`; `tests/test_self_configuration_external.py:63` `env`, `:128-336` existing tests; `agents.md:821`; `SECURITY-MODEL.md:275`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT commit — review and commit happen at flight end
