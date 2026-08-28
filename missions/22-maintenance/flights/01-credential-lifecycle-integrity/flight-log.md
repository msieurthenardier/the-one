# Flight Log: Credential lifecycle integrity and observability

**Flight**: [Credential lifecycle integrity and observability](flight.md)

## Summary
Landed 2026-08-28. Started the same day on branch `flight/01-credential-lifecycle-integrity`; three autonomous legs completed (`rotation-handoff-safety`, `ext-credential-trace`, `oauth-callback-reachability`), flight-wide review confirmed on the first pass, committed as `b856ed0` — PR #179 (ready for review). Optional `uat-and-alignment` not run. Full suite at landing: 4571 passed / 10 skipped / 0 failed; browser cross-site test passed.

---

## Leg Progress

### rotation-handoff-safety
**Status**: completed
**Started**: 2026-08-28
**Completed**: 2026-08-28

#### Changes Made
- `the_one/encryption.py`: `Encryptor` now carries an optional `_pending_key`
  and decrypts via `MultiFernet([Fernet(canonical), Fernet(pending)])`
  (canonical first) whenever one is staged; `encrypt()` always uses the
  canonical key. New `next_key_path`, `pending_key` property, `key_for`,
  `stage_pending_key`, `promote_pending_key` (explicit-`key` argument per
  the design review's fix — the route's earlier `install_key` clears the
  in-memory pending key), `discard_pending_key`, module-level
  `resolve_pending_key` (the reconcile's effector — performs the
  promote/discard mutation, not just a classifier). `_write_key_atomic`
  hardened: the whole write/fsync/close/replace sequence is wrapped so a
  failure (including a failing final `os.replace`) unlinks the partial
  temp file before re-raising. `get_encryptor` loads a leftover `.next`
  as the pending key, logging a WARNING and falling back to canonical-only
  if the sidecar doesn't parse as a valid Fernet key. `rotate_key`
  re-implemented on the new primitives; its documented contract is
  unchanged.
- `the_one/db/key_reconcile.py` (new): `sample_ciphertexts(conn)` samples
  up to 50 rows per column across all seven encrypted corpora (skipping a
  missing table via `aiosqlite.OperationalError`), and
  `reconcile_pending_key(conn, encryptor)` short-circuits to `"absent"`
  with no query when there is no pending key, else delegates to
  `resolve_pending_key`.
- `the_one/interfaces/web/api.py:rotate_encryption_key`: added SELECT/decrypt
  blocks for `tool_configs.secrets` (tolerant, mirrors the `mcp_sources`
  pattern) and `agent_external_credentials.secret` (strict — no
  `InvalidToken` swallow, so a corrupt row aborts the rotation before any
  write); both re-encrypt loops added inside the existing single `try` /
  commit block. New step 3b stages the new key to `.next` before the
  commit (`OSError` → `logger.exception` + 500, DB and canonical key file
  untouched). On commit failure the `except` now also calls
  `encryptor.discard_pending_key()` before re-raising. Immediately after
  the commit — no `await` in between — `encryptor.install_key(new_key)`
  runs, then `encryptor.promote_pending_key(new_key)` is attempted
  (`OSError` → `logger.exception` + `key_file = "staged"`, else
  `"promoted"`); connector-pool eviction (former step 4b) now runs after
  the promote block and logs via the module `logger` instead of an inline
  `logging.getLogger(__name__)`. The old steps 5–7 (temp-file write +
  `os.replace` + `install_key`) are gone, replaced by the sidecar
  primitives. Added one INFO success log line with per-corpus row counts
  and `sha256(new_key).hexdigest()[:8]` — never key bytes. Response shape
  is now `{"status": "ok", "key_file": "promoted" | "staged"}`; docstring
  rewritten for the seven-corpus / two-phase-handoff contract.
- `the_one/interfaces/web/app.py:lifespan` and
  `the_one/interfaces/cli.py:_run_cli`: both call
  `reconcile_pending_key(conn, get_encryptor(settings.data_dir))` between
  `get_connection()` and the first encryptor-backed repository
  construction, logging at INFO when the outcome isn't `"absent"`.
- Docs: `the_one/agents.md` — both rotation sections now describe seven
  corpora, the stage/commit/install/promote handoff, the `MultiFernet`
  read mode, the startup reconcile, and the CLI-window trade-off; the
  stale `:718` "(three corpora)" cross-reference was corrected in the same
  edit. `SECURITY-MODEL.md`'s encryption bullet and `README.md:125`
  updated to the seven-corpus / sidecar contract.
- Tests: `tests/test_encryption.py` — new `TestPendingKey` (14 tests:
  stage/promote/discard, `get_encryptor` dual-key read + encrypt-canonical,
  all four `resolve_pending_key` branches including the WARNING-on-mixed
  case via `caplog`, `_write_key_atomic` temp-file cleanup on a mocked
  `os.write` failure, corrupt-sidecar-ignored-with-warning); all pre-leg
  `TestKeyRotation`/`TestGetEncryptor` tests pass unchanged. New
  `tests/test_key_reconcile.py` (4 tests: sampling across present corpora,
  skip-on-missing-table, absent-short-circuits, promote-on-pending-match).
  `tests/test_provider_api.py:TestEncryptionRotation` — updated the 8
  in-file `{"status": "ok"}` rotation-response assertions (plus
  `tests/test_db_api.py`'s 1) to the new `key_file` shape; extended the
  full `*_on_db_failure` family (5 tests, not just the one named in the
  leg) with a `.next`-discarded assertion; added staging-fault (AC1),
  promote-fault-then-reconcile (AC4), happy-path INFO/fingerprint log
  (AC5), tool-config and external-credential round-trip (AC9), and one
  rollback test per new corpus (AC9) — 9 new tests. `tests/test_lifespan.py`
  — added a module-level `pytestmark = pytest.mark.usefixtures
  ("reset_lifespan_singletons")` (the file drives the real lifespan to
  shutdown in every test but didn't have this yet) and one new test
  seeding a `.next` sidecar plus a provider row encrypted under it, then
  asserting `lifespan(app)` promotes it before any repository is built.

#### Notes
- Full-suite result: `make test-unit` — **4550 passed, 10 skipped, 700
  deselected, 20 warnings in 485.34s (~8m05s)**. All 10 skips are
  pre-existing Windows-only tests (`test_pty_dispatch.py`,
  `test_pty_windows.py`), unrelated to this leg. No new skips or xfails.
  `ruff check .` and `ruff format --check .` both clean.
- Verified during AC5 work: `tests/test_provider_api.py` has 12 exact-dict
  `{"status": "ok"}` assertions, not the 9 the leg's citation counted —
  the extra 3 belong to unrelated endpoints (`POST
  /api/providers/{id}/models/delete`, `DELETE /api/connectors/{id}` ×2)
  and were left untouched; only the 9 rotation-response sites were
  updated, matching AC5 exactly.
- No deviations from the leg spec. The `.next`-discarded-on-rollback
  assertion (AC2) was applied to all five tests in the
  `*_on_db_failure` family rather than only the one named — a coverage
  extension consistent with the spec's own "family" wording, not a scope
  change.
- The pre-existing SELECT/UPDATE interleaving window (Anomaly A1) is
  unchanged by this leg, as scoped — only the install/eviction half of
  A1 was closed (`install_key` now runs synchronously after commit, no
  `await` before eviction).

### ext-credential-trace
**Status**: completed
**Started**: 2026-08-28
**Completed**: 2026-08-28

#### Changes Made
- `the_one/self_configuration/external_credentials.py`: `unregister(source_id)`
  now returns `list[str]` — the identifiers it evicted (empty list on
  no-match), so surface-teardown callers can log them. Docstring updated;
  behavior otherwise unchanged.
- `the_one/self_configuration/manage.py`: `disable` and `cascade_delete`
  each capture `unregister`'s return value and, when non-empty, emit one
  `logger.info` line on the module's `the_one.self_configuration.manage`
  logger naming the surface row id, the agent, a cause ("disabled" for
  `disable`, "removed with the agent" for `cascade_delete`), the evicted
  count, and the identifiers. No line when nothing was evicted.
- `the_one/interfaces/web/api.py`: new `_caller_principal(request)` helper
  (renders `f"{caller.source}:{caller.identifier}"` from
  `request.scope[CALLER_SCOPE_KEY]`, or `"-"` when absent) beside the
  external-credential routes; new import of `CALLER_SCOPE_KEY` from
  `the_one.interfaces.web.middleware` (no import cycle — `middleware.py`
  imports nothing from `api.py`). `mint_external_credential`,
  `revoke_external_credential`, `rotate_external_credential` each gained a
  `request: Request` parameter and one `logger.info` line on the module
  logger (`the_one.interfaces.web.api`) after their mutation: mint logs the
  new identifier, label, agent, principal; revoke logs identifier, label
  (read before the delete), agent, principal, and only on the success path
  (the 404 guard short-circuits first, so an unknown identifier logs
  nothing); rotate logs old identifier -> new identifier, label, agent,
  principal. No log line ever receives a `credential`/`token`/`secret`
  object — only `.identifier` strings and the label.
- `the_one/agents.md` ("External-client credential (M21 F03)") and
  `SECURITY-MODEL.md` ("External-client access to the self-configuration
  surface (M21 F03)") each gained an "Operational trace" bullet recording
  the Q2 decision: log lines (with the field set) instead of a `revoked_at`
  tombstone, and why (FK cascade would make a tombstone a half-record; a
  queryable audit trail is a separate events-table initiative). This
  field set is named as the convention the Advisory logging sweep
  inherits.
- Tests: `tests/test_self_configuration_external.py` — new
  `TestLifecycleTrace` (11 tests): mint/revoke/rotate log content and
  secret-absence (AC1–AC3), revoke-on-404 emits nothing, `unregister`'s
  return value (AC4), cascade logging through all three entrypoints —
  the self-configuration DELETE route, the direct `DELETE
  /api/mcp-sources/{id}` surface-row branch, and `DELETE /api/agents/{name}`
  via `cascade_delete` — plus a disable-with-nothing-evicted no-log case
  (AC5), the `cascade_delete` "removed with the agent" cause (AC6), and
  principal rendering both with an ASGI shim stamping
  `scope[CALLER_SCOPE_KEY]` and without one (AC7).

#### Notes
- Full-suite result: `make test-unit` — **4561 passed, 10 skipped, 700
  deselected, 20 warnings in 458.90s (~7m39s)**. Delta from Leg 1's landed
  baseline (4550 passed) is exactly the 11 new tests; no other test
  count moved. The same 10 pre-existing Windows-only skips. `ruff check .`
  and `ruff format --check .` both clean.
- No deviations from the leg spec. The leg's own line numbers (re-verified
  against the Leg-1-landed tree on 2026-08-28) matched the working tree
  at implementation time.
- The leg's AC5 wording ("Three entrypoints reach `disable`... and
  `cascade_delete` from `DELETE /api/agents/{name}`") reads as one
  combined requirement across `disable`'s two call sites and
  `cascade_delete`'s one; Implementation Guidance #2 was unambiguous
  about the two actual call sites and their distinct cause strings, so
  that guidance was followed literally and all three entrypoints got
  their own test regardless of which manage.py function they reach.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_self_configuration_external.py
  tests/test_self_configuration_api.py -x --timeout 60` — 85 passed
  (targeted run, before the full-suite run above).

### oauth-callback-reachability
**Status**: completed
**Started**: 2026-08-28
**Completed**: 2026-08-28

#### Changes Made
- Guidance step 0 (citation audit): re-verified every `api.py` citation
  against the Leg-2-landed tree. Leg 2's `request: Request` additions
  shifted everything below `api.py:1046-1130` by +43 lines — `oauth_callback`
  moved from `:2999-3000` to `:3042-3043`, `oauth_start` from `:3153` to
  `:3196-3197`, and the three dev-mode-seam precedents
  (`seed_routing_audit`/`lookup_chat_session`/`trigger_purge_sweep`) from
  `:4560-4561`/`:4600`/`:4639` to `:4603-4604`/`:4642-4643`/`:4682-4683`.
  `middleware.py`, `_state.py`, and both `conftest.py`/test citations were
  unchanged (Leg 2 never touches those files). The leg artifact's Citation
  Audit paragraph was repaired in place.
- **Red tests first (AC1)**: wrote `tests/test_oauth_callback_gate.py`
  (middleware-inclusive: real `router` wrapped in
  `OriginAllowlistMiddleware` + `CredentialGateMiddleware`, no credential
  attached) and `tests/browser/test_flow_oauth_callback_cross_site.py`
  (genuine `localhost` → `127.0.0.1` cross-site navigation in a dedicated
  `browser.new_context()`, per the leg's AC6 apparatus). Built the
  dev-mode-gated seam (`POST /_test/oauth/pending`) first as scaffolding
  the browser test needs to seed a pending flow in a separate subprocess
  — the seam is not itself the fix under test, so building it ahead of
  the exemption does not compromise AC1's red-first requirement. Ran both
  before touching `middleware.py`'s `EXEMPT_PATHS`; both failed with 401
  from the gate — see **Pre-fix red-test evidence** below. Then added the
  exemption (`middleware.py`) and confirmed both tests green.
- `the_one/interfaces/web/middleware.py`: `OAUTH_CALLBACK_PATH =
  "/api/oauth/callback"`; `EXEMPT_PATHS = frozenset({LIVENESS_PATH,
  OAUTH_CALLBACK_PATH})` — the second exemption per flight Design Decision
  Q3. Extended the rationale comment above `EXEMPT_PATHS` with the Q3
  reasoning (cross-site `SameSite=Strict` cookie withholding, `state` as
  the credential, GET-only registration so other methods 405 at routing);
  updated the class docstring ("exactly one" → "exactly two
  unauthenticated exemptions") and the nearby comment that quoted the
  stale "exactly one exemption" phrase.
- `the_one/interfaces/web/api.py`: new dev-mode-gated test seam `POST
  /_test/oauth/pending` (next to the sibling `/_test/...` seams, after
  `trigger_purge_sweep`), gated on `settings.dev_mode` (403 when off,
  mirroring the sibling seams' exact detail string), with a typed
  `_PendingOAuthFlowBody` (`state`, `source_id`, `chat_session_id`,
  `tool_call_id: str | None = None`) — the docstring notes the typed body
  is a deliberate choice, not drift from the sibling seams' hand-parsed
  `request.json()`. Wraps `_state.register(...)` in `try/except
  RuntimeError` → 409 on a duplicate `state`; returns `{"state": ...}` on
  success. Its own docstring names the browser test as its only consumer.
  No other route in `api.py` was touched.
- `tests/test_credential_gate.py`: renamed
  `test_exempt_set_has_exactly_one_member` →
  `test_exempt_set_is_liveness_and_oauth_callback` in place (same
  position in the file, per AC2 — not deleted and re-added), asserting
  the two-member set; added the `OAUTH_CALLBACK_PATH` import.
- New `tests/test_oauth_callback_gate.py` (10 tests): `TestExemptionAllowsCallback`
  (the AC3 positive path — no cookie, no header, `state` seeded via
  `_state.register`, future resolves), `TestExemptionScope` (AC4 — replay
  → 401 "Unknown or expired state"; unknown `state` → same; missing
  `state` → 401 "Missing state parameter"; `POST` → 405; trailing-slash
  stays gated; an unrelated gated path still 401s from the gate, not the
  handler, proving the exemption opened exactly one path), `TestSeam`
  (AC5 — the seam's own 200/403/409, credentialed since the seam route
  itself is not gate-exempt).
- New `tests/browser/test_flow_oauth_callback_cross_site.py` (AC6): a
  dedicated `browser.new_context()` with no extra headers (never
  `set_extra_http_headers`, unlike `page`/`credentialed_context()`);
  `_establish_session_cookie` for the cookie, `ctx.request.post` with a
  per-call header to seed the seam; same-site positive control
  (`raw.goto(f"{app_clean}/api/info")` → 200); cross-site callback
  (`localhost` document → `window.location.assign` to the `127.0.0.1`
  callback URL, asserted via `expect_navigation` on the response body,
  not `page.content()`, since the success page auto-closes ~1.2s after
  paint); cross-site negative control (fresh `localhost` document →
  `/api/info` → 401), proving the positive result is attributable to the
  callback's exemption and not to the gate being generally inert in this
  harness.
- `SECURITY-MODEL.md`: the "Exactly one exemption" bullet (`:57`) became
  "Exactly two exemptions", with a new paragraph naming the OAuth callback
  and the single-use-`state`-as-credential reasoning (AC8); the Origin
  allowlist section's "the one exemption" / "`/api/live` is the only
  request" sentence (`:149`) updated to name both exempt paths. Grepped
  `the_one/agents.md` for any `EXEMPT_PATHS`/exemption-count mention —
  none exists (confirmed again on this landed tree, matching the leg's
  own citation note), so no edit there.
- No operator home path or username appears in any new test, code
  comment, or doc edit.

#### Pre-fix red-test evidence (AC1)
Both new tests were run against the working tree BEFORE `EXEMPT_PATHS`
gained `OAUTH_CALLBACK_PATH` (the seam existed already — see Changes
Made above for why building it first doesn't weaken this evidence).

**Middleware-inclusive unit test**
(`tests/test_oauth_callback_gate.py::TestExemptionAllowsCallback::test_callback_succeeds_through_gate_with_no_credential`),
`PYTHON=.venv/bin/python bash scripts/run-tests.sh
tests/test_oauth_callback_gate.py --timeout 60 -q`:
```
>       assert resp.status_code == 200
E       assert 401 == 200
E        +  where 401 = <Response [401 Unauthorized]>.status_code
```
The gate's own body for this class of 401 (`middleware.py::_send_401`) is
`{"detail":"Local API credential missing or invalid"}`. The full pre-fix
run showed 5 of the module's 10 tests red for the same reason (the
positive path above, the replay/unknown/missing-`state`-detail
assertions, and the `POST` → 405 expectation) — all 5 turned green after
the exemption was added; the module's other 5 tests (seam
register/403/409, trailing-slash-stays-gated, unrelated-gated-path) were
already green pre-fix, as expected (they exercise gate behavior the
exemption doesn't change, or the seam, which is unaffected by
`EXEMPT_PATHS`).

**Browser cross-site test**
(`tests/browser/test_flow_oauth_callback_cross_site.py`),
`THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh
-m browser tests/browser/test_flow_oauth_callback_cross_site.py -x
--timeout 120 -q`:
```
>           assert "Login successful" in nav_response.text()
E           assert 'Login successful' in '{"detail":"Local API credential missing or invalid"}'
E            +  where '{"detail":"Local API credential missing or invalid"}' = text()
E            +    where text = <Response url='http://127.0.0.1:<port>/api/oauth/callback?code=c&state=S-cross-site-1' ...>.text
```
The same-site positive control (`raw.goto(f"{app_clean}/api/info")` →
200) passed even pre-fix, confirming the harness's cookie/credential
mechanics were sound and the 401 above is specifically the
`SameSite=Strict` cookie being withheld on the cross-site hop — the live
verification of finding S5.

#### AC7 — inertness re-confirmation
Read directly off `the_one/interfaces/web/api.py:3042-3193`
(`oauth_callback`) and `the_one/mcp/oauth/_state.py`:
- **No DB read/write**: the handler calls no repository, no
  `get_connection`, no `get_encryptor` anywhere in its body.
- **Mints no credential, sets no cookie**: no `Set-Cookie` construction,
  no call into `the_one.api_credential` or the handoff store.
- **Consumes `state` on first use**: `oauth_state.resolve(state, code or
  "", state)` (`api.py:3117`) calls `_state.resolve`
  (`the_one/mcp/oauth/_state.py:106`), whose body pops the entry
  unconditionally — `entry = _pending.pop(state, None)` (`_state.py:118`)
  — before doing anything else. A second call with the same `state` finds
  `_pending.pop` returns `None`, so `peek(state)` in the route
  (`api.py:3081`) also returns `None` and the route 401s with "Unknown or
  expired state" — confirmed by
  `TestExemptionScope::test_replayed_state_is_401_with_handler_detail`
  above.
- No privileged action is reachable: on missing/unknown `state` → 401
  before touching `_state` further; on `error=` → `_state.fail` (pops,
  fails the future) + an `auth_failed` broadcast to the originating chat
  session (in-memory only) + an HTML page; on success → `_state.resolve`
  + an `auth_resolved` broadcast + scheduling a resume of a *paused
  agent's own already-in-flight tool call* (not a new privileged action —
  the pause/resume mechanism predates this leg).

No BLOCKED condition — the handler is confirmed inert; the exemption was
added as designed.

#### Notes
- No external IdP is configured in the operator's environment — the
  browser cross-site test above is the live verification of Q3's "if live
  verification confirms the `SameSite=Strict` cookie is withheld"
  condition; no live-IdP run was available to additionally record.
- Browser-lane result:
  `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh
  -m browser tests/browser/test_flow_oauth_callback_cross_site.py -x
  --timeout 120 -q` — **1 passed** (post-fix).
- Full-suite result: `make test-unit` (background, `tail --pid`) — **4571
  passed, 10 skipped, 701 deselected, 20 warnings in 463.33s (~7m43s)**.
  Delta from Leg 2's landed baseline (4561 passed) is exactly the 10 new
  tests in `tests/test_oauth_callback_gate.py`; the renamed test in
  `tests/test_credential_gate.py` nets zero. Same 10 pre-existing
  Windows-only skips. `ruff check .` and `ruff format --check .` both
  clean across the whole repo (452 files already formatted after
  reformatting the new browser test file once).
- No deviations from the leg spec beyond the one already recorded under
  Deviations below (cross-site navigation direction, planned before this
  leg's implementation began). Building the dev-mode seam ahead of the
  exemption (rather than strictly after, per the guidance's step
  numbering) is a sequencing choice, not a scope or acceptance-criteria
  deviation — see Changes Made above for why it doesn't weaken AC1.

---

## Decisions

### D1 — Fold the two un-rotated corpora into Leg 1
**Context**: While designing Leg 1, `rotate_encryption_key` was found to re-encrypt five columns but not `tool_configs.secrets` (schema v32, M16 F08 L03) or `agent_external_credentials.secret` (schema v36, M21 F03). Neither the flight spec nor the 2026-08-27 maintenance report noticed. Post-rotation, tool-config secrets silently decode to `{}` (tolerant decrypt) and `AgentExternalCredentialRepository.load_all` raises `InvalidToken` inside `lifespan` — the app would not start after a rotation with any `ext_` credential present.
**Decision**: Add both corpora to the rotation transaction in Leg 1 rather than squawking. Grounding-severity, directly in this leg's path, pattern-copy of the existing loops (no design decision), and the startup reconcile designed in this leg must enumerate every ciphertext corpus anyway.
**Impact**: Leg 1 grows by two SELECT/UPDATE loops and their tests; `agents.md` "five corpora" becomes seven; mission Known Issues records that two missions added encrypted columns without extending the rotation invariant (a debrief item — the invariant needs a guard, e.g. a test that enumerates encrypted columns from the schema).

---

## Deviations

### Leg 3 cross-site verification direction
**Planned**: flight Q3 — "sign in on `http://localhost:<port>`, navigate the popup to `http://127.0.0.1:<port>/api/oauth/callback…`".
**Actual**: session established on `http://127.0.0.1:<port>` (the only origin the test harness spawns the app at), cross-site navigation initiated from a `localhost` document to the `127.0.0.1` callback.
**Reason**: `_spawn_app` binds `127.0.0.1` and the credential registry is keyed by that base URL; the proof is identical (a `Strict` cookie withheld on a cross-site top-level navigation) with the sites swapped.

---

## Anomalies

### A1 — Pre-existing SELECT/UPDATE interleaving window in rotation
**Observed**: `rotate_encryption_key` reads every corpus with awaited SELECTs, then writes with awaited UPDATEs on the same connection. A concurrent request that inserts an encrypted row between the read and the write leaves that row under the old key after commit. Also, `install_key` today runs after the awaited pool eviction, so other coroutines can encrypt under the old key after the commit.
**Severity**: degraded (single-operator app; requires concurrent writes during a rotation)
**Resolution**: Leg 1 closes the second half (install immediately after commit, no `await` between). The first half is unresolved — needs either an app-level rotation lock or a `BEGIN IMMEDIATE` strategy that survives aiosqlite's auto-commit-on-non-DML; deferred to the flight debrief.

---

## Session Notes

### Flight Director Notes
- 2026-08-28 — Phase file `.flightops/agent-crews/leg-execution.md` loaded and validated (Crew / Interaction Protocol / Prompts present). Mission 22 transitioned `planning → active` and flight `ready → in-flight` at flight start (the mission was scaffolded `planning` by `/routine-maintenance`; the operator's go on this flight is the activation). Branch `flight/01-credential-lifecycle-integrity` created from `main` at `2f48a55`.
- 2026-08-28 — Leg 1 `rotation-handoff-safety` designed from the code, not the report: read `encryption.py`, `api.py:rotate_encryption_key`, `app.py:lifespan`, the repositories, and the existing rotation tests. Discovered the two un-rotated corpora → Decision D1. **Risk tier: high** — security-sensitive surface (key material handling), lifecycle change (startup reconcile mutates the shared encryptor before repositories are built), and a scope addition to the flight spec. Design review spawned (Developer, Sonnet per crew file).
- 2026-08-28 — Design review round 1: **needs rework**. Two high findings, both accepted: (1) the `promote_pending_key` primitive re-derived the key from `_pending_key`, which the route's earlier `install_key` clears — would have crashed every happy-path rotation; fixed by giving `promote_pending_key` an explicit `key` argument. (2) Nine existing tests assert the exact `{"status": "ok"}` response dict; added them to scope (`test_provider_api.py` ×8, `test_db_api.py` ×1). Mediums accepted: `_write_key_atomic` cleanup now also covers a failing final `os.replace`; the CLI entrypoint gets the same reconcile call (`cli.py:_run_cli`) rather than an edge-case note only. Lows fixed (citation `:584`, `agents.md:718` stale cross-reference). Non-blocking suggestion parked for the debrief: the admin UI shows the same success flash for `key_file: "staged"` as for `"promoted"` — a follow-up UI squawk once the field exists. Changes are substantive → second review pass spawned.
- 2026-08-28 — Design review round 2: **approve**, two lows applied (`resolve_pending_key` must perform the promote/discard mutation, not just classify; `key_for` must not raise when no pending key is set). Leg 1 marked `ready`. `[HANDOFF:review-needed]` — implementation Developer spawned (Sonnet).
- 2026-08-28 — Leg 1 landed (Developer report: 4550 passed / 10 skipped / 0 failed, 485s; ruff clean; no commit). `legs_completed = 1`. Two Developer notes accepted as in-scope: the `.next`-discarded assertion extended across the whole `*_on_db_failure` family; three non-rotation `{"status": "ok"}` sites correctly left alone.
- 2026-08-28 — Leg 2 `ext-credential-trace` designed (drafted during Leg 1, citations re-verified after it landed). **Risk tier: low** — additive INFO logging on an established pattern (`pending.py`), no schema, no lifecycle change; the one interface change (`external_credentials.unregister` gains a return value) has exactly two in-repo consumers, both enumerated, and is backward-compatible. The secret-leak risk is pinned by an explicit acceptance criterion (secret must not appear in `caplog.text`). Design review skipped; the flight-end Reviewer covers the code. Marked `ready`; implementation Developer spawned (Sonnet).
- 2026-08-28 — Leg 3 `oauth-callback-reachability` designed (drafted during Leg 1; run in parallel with Leg 2's implementation). **Risk tier: high** — a credential-gate exemption is a security-sensitive surface. Design review round 1: **approve with changes**. High finding accepted and fixed: the browser-lane test must not derive its "no credential" page from the `page` fixture's context — `set_extra_http_headers` is context-wide, so the raw page would have authenticated via the header channel and the cross-site test (and its 401 control) would have passed for the wrong reason; redesigned onto a dedicated `browser.new_context()` seeded only through `_establish_session_cookie` / per-call `ctx.request` headers, with a same-site positive control added. Lows: citation refresh promoted to an explicit guidance step 0 (Leg 2 shifts `api.py` ~+40 below its edits); trailing-slash case promoted to a real assertion; seam docstring note. Reviewer also confirmed (b) it is `SameSite=Strict`, not host difference alone, that withholds the cookie, and (c) `OriginAllowlistMiddleware` never gates GET. The flight's Q3 verification bullet describes the navigation in the opposite direction (sign in on `localhost`, navigate to `127.0.0.1`); the leg's direction is the correct one because the app binds only at `127.0.0.1` — recorded as a Deviation rather than rewriting the in-flight flight artifact. Second review pass spawned (contained but substantive test redesign).
- 2026-08-28 — Leg 3 design review round 2: **approve**, one low applied (explicit re-navigation to a `localhost` document before the negative control; exact `credential_for` import). Leg 3 marked `ready`; queued behind Leg 2's implementation — legs execute sequentially because both edit `api.py`.
- 2026-08-28 — Leg 2 landed (Developer report: 4561 passed / 10 skipped / 0 failed — exactly +11 from Leg 1; ruff clean; no commit; `CALLER_SCOPE_KEY` import into `api.py` verified cycle-free). `legs_completed = 2`. Developer's judgment call accepted: the AC5 wording said three entrypoints "reach `disable`" when one of them reaches `cascade_delete` — it tested all three regardless, which is what the criterion meant. `[HANDOFF:review-needed]` on Leg 3 — implementation Developer spawned (Sonnet).
- 2026-08-28 — Leg 3 landed (Developer report: red tests recorded pre-fix — unit `401 == 200` with the gate body, browser cross-site navigation returned the gate body while the same-site control passed; post-fix 98 targeted, browser 1 passed, full suite 4571 / 10 skipped / 0 failed — exactly +10; ruff clean; no commit). `legs_completed = 3` of 3 autonomous legs. Optional `uat-and-alignment` is a HAT leg — not run autonomously; offered to the operator after the commit. Phase 2d: flight-wide Reviewer spawned over all uncommitted changes. **Model deviation**: crew file prescribes Haiku for the Reviewer; using Sonnet because the diff carries key-rotation handoff logic and a credential-gate exemption — disclosed here and in the session summary.
- 2026-08-28 — Flight-wide review: `[HANDOFF:confirmed]` on the first pass (488 targeted tests green, ruff clean, load-bearing criteria spot-checked by reading code, no leak). Reviewer's one bookkeeping note (flight checkboxes untouched) is by design — ticked now at commit time. Legs 1–3 → `completed`, flight → `landed`, Flight 1 ticked in the mission. Committing code + artifacts in one commit; draft PR opened then marked ready for review since the flight has landed. `[COMPLETE:flight]`. Debrief is a separate `/flight-debrief` step; carry-forward items for it: Anomaly A1 (rotation SELECT/UPDATE interleaving), Decision D1's structural-guard follow-up (a test that enumerates encrypted columns from the schema), the admin UI showing one flash for `key_file: staged` vs `promoted`, and the optional UAT leg.
- 2026-08-28 — `/flight-debrief` run: Developer (isolated `--durations=0` suite: 4571 / 10 / 0 in 509.20s; per-file aggregate refutes the loopback-tail hypothesis) and Architect interviews, two-question human interview (D1 fold-in confirmed right; Reviewer model rule to be codified). Debrief written; six action items logged as squawks 0018–0023; flight `landed → completed` on operator confirmation; debrief committed onto the flight branch so it rides in PR #179.
