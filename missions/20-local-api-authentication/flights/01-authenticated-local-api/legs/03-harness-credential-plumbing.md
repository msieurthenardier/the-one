# Leg: harness-credential-plumbing

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Make every test-harness caller present the long-lived credential — browser
fixtures, browser seeders, and unit-test clients alike — **without registering
the gate**, so the entire migration is proven green before enforcement is
switched on.

## Context

This leg and `enforce-gate` are a split of what the flight spec planned as one
leg (`enforce-and-migrate-harness`). The split was made at design-review time,
on evidence: the review found the migration surface is materially larger and
differently shaped than the flight spec's reconnaissance recorded, and doing the
plumbing and the switch together would mean a long red window across ~50 files
with no way to tell a migration bug from an enforcement bug.

Splitting inverts that. Credentials are *plumbed but unused* here — every
harness caller starts sending an `Authorization` header at a server that does
not yet check it, so **the suite stays green through this entire leg**. The next
leg's switch is then a small, sharp change whose failures are unambiguous.

Design decisions implemented: **DD10** (centralize credential handling; do not
edit per call site), and **DD5** (the liveness exemption exists so readiness
probes work before a credential is presented).

### The verified migration surface

Counted directly against the working tree, not estimated:

| Surface | Count | Shape |
|---------|-------|-------|
| Browser app-spawn implementations | **10** files | `tests/browser/conftest.py` (`app_clean`/`_spawn_app`), `test_markdown.py` (`app_clean_module`), and `app_with_data_dir` **duplicated across 8 `test_flow_*.py` files**, each with its own `subprocess.Popen` and its own local `_wait_for_ready` polling `/api/info` |
| Browser seeder call sites | **252** | via 4 functions in `tests/browser/seeders.py` plus 2 inline `_seed_*` helpers in `conftest.py` |
| Unit-test client fixtures | **34** files | 28 defining a local `client` fixture on `httpx.AsyncClient(transport=ASGITransport(app=app))`, plus 6 using `TestClient(` |

Two of these were invisible to the flight spec's reconnaissance and must not be
skimmed past:

1. **There is no single "browser fixture layer."** The flight spec and this
   leg's first draft both assumed fixing `app_clean` would cover the browser
   suite. It covers one of ten. The other nine spawn their own subprocess and
   poll `/api/info` directly.
2. **`extra_http_headers` cannot reach the seeders.** `seed_mock_provider`,
   `seed_mock_agent`, `seed_connector` and `seed_tool_config` issue raw
   `httpx.post`/`httpx.put` **from the pytest process**, not from the browser.
   A Playwright context header covers browser-originated requests only.
3. **`ASGITransport`-based fixtures match neither name in DD10.** DD10 says
   "`TestClient` and direct-`httpx` call sites." 28 files use
   `httpx.AsyncClient(transport=ASGITransport(app=app))` — the async equivalent,
   going through the full ASGI stack and therefore fully gated, but found by
   grepping for neither term. An implementer working from DD10's wording alone
   will miss all 28.

### Prior-leg learnings

- **Leg 1**: `the_one/api_credential.py`. `_cache` is keyed by resolved
  credential path, so per-test isolated data directories do not bleed.
  `_sources` is module-level and mutated in place — isolate it in any new
  fixture, following `tests/test_api_credential.py::_isolated_credential_module`.
- **Leg 2**: the `Authorization: Bearer` channel is implemented and is a plain
  HTTP header. The liveness endpoint **`/api/live`** exists, is genuinely
  unauthenticated, and returns `{"status": "ok"}` — no version, no prompt.
- **Verified N/A**: this suite does **not** use `pytest-xdist`. No per-worker
  data-directory concern exists.

## Inputs

- `tests/browser/conftest.py` — `app_clean`, `_spawn_app`, `_wait_for_ready`,
  `page`, `_seed_openrouter_provider`, `_seed_ollama_provider`, and the layered
  `app_with_provider` / `app_with_agent` / `app_with_openrouter_models` /
  `app_with_two_providers` fixtures.
- `tests/browser/test_markdown.py` — `app_clean_module`, `page_with_app`.
- The 8 `test_flow_*.py` files defining `app_with_data_dir`:
  `test_flow_provider_plan_signin.py`, `test_flow_chat_visibility_distinction.py`,
  `test_flow_chat_operator_input_visibility.py`, `test_flow_chat_peer_attribution.py`,
  `test_flow_chat_routing_audit_panel.py`, `test_flow_chat_pending_approval.py`,
  `test_flow_chat_pending_badge.py`, `test_flow_chat_session_list_source_badge.py`.
- `tests/browser/seeders.py` — the 4 seeder functions.
- `tests/conftest.py` — shared unit fixtures.
- `the_one/api_credential.py` — Leg 1's writer and reader.

## Outputs

- One consolidated, credential-aware app-spawn path used by the whole browser
  suite.
- Credential-bearing seeders.
- A shared authenticated client helper adopted by the 34 unit-test fixtures.
- **No change to `the_one/interfaces/web/app.py`.** The gate stays unregistered.

## Acceptance Criteria

**Browser app-spawn**

- [ ] The 10 app-spawn implementations are **consolidated** onto the shared
      `_spawn_app` path rather than each being patched in place. Nine of the ten
      are copies of the same subprocess-spawn-plus-readiness-poll logic;
      credentialing them independently would permanently enshrine ten copies,
      each of which every future flight must remember. Consolidation is the
      larger diff and the smaller ongoing cost — take it. If a duplicate turns
      out to differ materially from `_spawn_app` (module scope, a distinct
      `data_dir` lifetime), say so in the flight log rather than forcing it.
- [ ] Every app-spawn path writes the credential into its isolated `data_dir`
      **before** `subprocess.Popen`. This resolves the flight's one deferred open
      question by removing the race rather than handling it: the fixture owns the
      directory and creates it before the server exists. Do **not** poll for
      server-side creation.
- [ ] Every readiness probe polls **`/api/live`**, not `/api/info`.
- [ ] The Playwright browser context carries the credential via
      `extra_http_headers`, sourced from the same app instance the test targets.
      Getting this wrong is silent: attaching `app_clean`'s credential to a test
      whose app is `app_with_data_dir` authenticates against the wrong instance's
      credential. A test must assert the context's credential matches the app it
      is driving.

**Seeders**

- [ ] The 4 `seeders.py` functions and the 2 inline `conftest.py` `_seed_*`
      helpers send the credential.
- [ ] **The 252 call sites are not edited.** Resolve the credential inside the
      seeders from the `base_url` they already receive — e.g. a small
      fixture-populated registry mapping base URL to credential. Changing the
      seeder signatures would touch every call site, which is precisely the
      per-call-site outcome DD10 exists to prevent.

**Unit-test clients**

- [ ] A shared authenticated client helper exists in `tests/conftest.py` (or a
      helper module), and all **34** fixtures adopt it — the 28 `ASGITransport`
      ones and the 6 `TestClient` ones.
- [ ] Adoption is a one-line-per-file mechanical change sourcing the header from
      the shared helper. A larger refactor consolidating the 28 local `client`
      fixtures into one shared fixture is **out of scope** for this leg — it is a
      worthwhile cleanup, but bundling it here would mix a mechanical migration
      with a structural one and make the enforcement flip harder to review.

**Green throughout**

- [ ] `make test-unit` green. The gate is not registered, so credentials are
      sent and ignored; nothing should change behaviourally.
- [ ] Browser lanes green.
- [ ] `the_one/interfaces/web/app.py` is unmodified by this leg, and
      `tests/test_credential_gate.py::test_gate_middleware_is_not_registered_on_the_real_app`
      still passes untouched.

## Verification Steps

- `make test-unit`
- Browser lanes per the Makefile's `test-browser` target. **Never `-m live`** —
  that lane targets the operator's production instance on the default port.
- `git diff --stat the_one/` must show no changes under `the_one/interfaces/web/`.

## Implementation Guidance

1. **Consolidate before credentialing.** Collapsing the ten spawn paths onto one
   first means the credential work happens once. Doing it in the other order
   means doing it ten times and then deleting nine.
2. **Start with the browser layer, then seeders, then unit clients.** Each is
   independently verifiable and the suite stays green after each.
3. **The credential registry for seeders should be scoped and explicit**, not a
   bare module global that survives between tests. Leg 1's cache finding and
   `_sources` are two live reminders in this same codebase.
4. **Do not touch `app.py`.** If you find yourself wanting to, the change belongs
   to the next leg.

## Edge Cases

- **`test_markdown.py`'s `app_clean_module` is module-scoped** while `app_clean`
  is function-scoped. Consolidation must preserve the scope difference or the
  module's tests will re-spawn per test and slow markedly.
- **Tests using `page` alongside `app_with_data_dir`** — the credential must come
  from *that* app, not from `app_clean`. Do not make `page` depend on `app_clean`
  unconditionally.
- **Which Leg 1 entry point writes the credential.** `get_credential()` reads the
  *ambient* `settings.data_dir` — the pytest process's own — which is not the
  fixture's isolated directory. Either use the path-taking writer directly or
  scope a `monkeypatch.setattr(settings, "data_dir", ...)` around the call. Pick
  one deliberately; the natural-looking `get_credential()` call is wrong here.

## Files Affected

- `tests/browser/conftest.py`, `tests/browser/seeders.py`,
  `tests/browser/test_markdown.py`, the 8 `test_flow_*.py` duplicates.
- `tests/conftest.py` and the 34 unit-test files adopting the helper.
- **Not** `the_one/` — no production code changes in this leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md

> Commit is deferred to the flight-end review gate. Do **not** commit and do
> **not** signal `[COMPLETE:leg]`.
