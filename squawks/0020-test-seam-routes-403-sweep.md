# Squawk 0020: No single test asserts every `/_test/*` route 403s without dev mode

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

## Report

Four dev-mode test seams are always registered on the router and gated only inside each
handler by `settings.dev_mode`. Each has its own 403 test, but nothing asserts the set — a
fifth seam added by copy-paste without the gate would not be caught. Add one parametrized
test that walks `app.routes` for paths under `/_test/` and asserts each returns 403 with
`dev_mode=False`.

## Evidence

- `the_one/interfaces/web/api.py:4603` `/_test/chat/sessions/{session_id}/routing-audit`, `:4642` `/_test/chat/sessions/lookup`, `:4682` `/_test/purge-sweep`, `:4711` `/_test/oauth/pending`
- Gate detail string `"test-seam endpoint requires THE_ONE_DEV_MODE=true"` at `api.py:4625, :4670, …`
- `the_one/interfaces/web/app.py` — no conditional mounting by `dev_mode`

## Corrective Action

Added `tests/test_seam_routes_403_sweep.py`. It discovers every route mounted under
`/api/_test/` by walking `the_one.interfaces.web.api.router.routes` directly (an
`APIRoute` whose `.path` starts with `/api/_test/`, one entry per HTTP method the route
declares) rather than hardcoding a route list, so a future seam is picked up
automatically instead of relying on someone remembering to add a case.

Two tests:

- `test_discovered_seam_set_matches_expected` — asserts the discovered set is non-empty
  and equals exactly the four known seams (`routing-audit`, `chat/sessions/lookup`,
  `purge-sweep`, `oauth/pending`), with an assertion message that tells the next author
  to update the expected set deliberately rather than widen the check. This is the half
  of the squawk's report that catches an accidental un-registration or an un-gated
  fifth seam silently joining the set.
- `test_seam_route_403s_without_dev_mode` (parametrized over the discovered
  `(method, path)` pairs) — builds a client over a bare `FastAPI()` + the real `router`
  (no `CredentialGateMiddleware`; these handlers gate on `settings.dev_mode` as the
  first statement in the function body, so the credential gate is irrelevant to what
  this test proves — mirrors the existing bare-router pattern in
  `tests/test_db_api.py`/`tests/test_chat_history_purge.py`, not the
  middleware-inclusive `tests/test_oauth_callback_gate.py`). Explicitly monkeypatches
  `settings.dev_mode = False` (not relying on the default), fills `{param}` path
  segments with a placeholder value, sends an empty JSON body for POST/PUT/PATCH, and
  layers in the extra query params / body fields two of the four seams require to clear
  FastAPI's own request validation before the handler's gate can run (`connector_id`/
  `channel_id` for the `lookup` GET; `state`/`source_id`/`chat_session_id` for the typed
  `oauth/pending` body) — see `_EXTRA_REQUEST_KWARGS`. Asserts `== 403` explicitly (not
  `!= 200`), with a failure message distinguishing "422/404 means the test's
  minimal-request premise doesn't hold for this route" from "any other non-403 means the
  route isn't actually gated."

All four discovered seams returned exactly 403 — no gate gap found, so this squawk closes
test-only with no changes to `the_one/interfaces/web/api.py`.

## Verification

```
PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_seam_routes_403_sweep.py -x --timeout 60
# 5 passed (4 parametrized 403 checks + 1 seam-set comparison)

.venv/bin/ruff check .
# All checks passed!

.venv/bin/ruff format --check .
# 454 files already formatted
```

`git status` after the change shows only `tests/test_seam_routes_403_sweep.py` (new) and
this artifact's status/completion edits — squawks 0018/0019's uncommitted work
(`the_one/encryption.py`, `tests/test_encryption.py`, `the_one/agents.md`,
`tests/test_encrypted_corpora_guard.py`, their own squawk artifacts) is untouched.

## Sign-Off

Test-only change, scope held: no source file under `the_one/` was modified. All four
known seams passed the 403 assertion with `dev_mode` explicitly False, so no gate gap
was found and nothing was escalated beyond this squawk.
