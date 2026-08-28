# Flight Debrief: Credential lifecycle integrity and observability

**Date**: 2026-08-28
**Flight**: [Credential lifecycle integrity and observability](flight.md)
**Status**: completed
**Duration**: 2026-08-28 – 2026-08-28 (one session; three autonomous legs, no HAT)
**Legs Completed**: 3 of 3 autonomous (optional `uat-and-alignment` not run)

## Outcome Assessment

### Objectives Achieved
All three findings the flight was chartered for are closed, plus one it was not:

- **B8-rotate** — `POST /api/encryption/rotate` now stages the new key as an `encryption.key.next` sidecar *before* the DB commit, installs it in memory synchronously after the commit (no `await` between), then promotes the sidecar over the canonical file. A leftover `.next` is reconciled at startup by both entrypoints (`app.py:lifespan`, `cli.py:_run_cli`) by probing ciphertext under both keys. Every crash point is fault-injected in tests (staging failure → 500 with nothing changed; commit failure → rollback and sidecar discarded; promote failure → 200 `key_file: "staged"`, old key on disk, new key in `.next`, ERROR logged, reconcile promotes on next start).
- **B8-ext-credential-trace** — INFO lines at `ext_` mint/revoke/rotate (agent, identifier, label, principal; never the secret — asserted) and at both FK-cascade points (surface disable, agent delete). Q2 decided log lines over a `revoked_at` tombstone; recorded in `agents.md` and `SECURITY-MODEL.md` as the convention the Advisory logging sweep inherits.
- **S5 + S5b** — `GET /api/oauth/callback` is the second credential-gate exemption; the single-use `state` token is the credential. Proven **red-first**: the middleware-inclusive unit test and the cross-site browser test both hit the gate's 401 pre-fix (recorded verbatim in the flight log), green post-fix with same-site and cross-site controls proving the `Strict` cookie was withheld. The handler's inertness (no DB, mints nothing, sets no cookie, consumes `state` on first use) was re-confirmed from the code before the exemption was added.
- **Unplanned (Decision D1)** — rotation was missing two encrypted corpora added by later missions: `tool_configs.secrets` (M16 F08) and `agent_external_credentials.secret` (M21 F03). Post-rotation, tool API keys would have silently decoded to `{}` and the app would have failed at lifespan start with any `ext_` credential present. Both joined the single rotation transaction with round-trip and rollback tests. Rotation now covers seven corpora.

Committed as `b856ed0` (+ `0059625` log bookkeeping) on `flight/01-credential-lifecycle-integrity`; PR #179.

### Mission Criteria Advanced
All three Mission 22 success criteria are satisfied by this flight (rotation recovery path + fault-injection test; durable `ext_` trace + tombstone decision recorded; OAuth callback verified through the gate with a middleware-inclusive test). The mission's "return to Flight Ready" outcome is pending the next maintenance inspection, not this flight.

## What Went Well

- **Leg design against the code, not the report, found the biggest defect of the flight.** D1 (two un-rotated corpora) was invisible to the maintenance inspection and to the flight spec; it surfaced only because the leg designer read `rotate_encryption_key` and the repositories side by side while designing the reconcile sampler. The operator confirmed folding it in was the right call.
- **Design review earned its cost twice, both times on things a green test suite would never have caught.** Leg 1 round 1: the `promote_pending_key` primitive re-derived the key from `_pending_key`, which the route's own `install_key` had already cleared — every successful rotation would have crashed after the commit. Leg 3 round 1: the browser test's "unauthenticated" page would have inherited the fixture context's context-wide `Authorization` header and passed for the wrong reason — including its own negative control. Both were fixed on paper before a line of code.
- **Red-first with a recorded failing run.** Leg 3's flight-log entry quotes the pre-fix `assert 401 == 200` and the gate's 401 body for both tests. That is the live verification of finding S5 — no external IdP was configured, and the `localhost` → `127.0.0.1` cross-site navigation reproduces the IdP-redirect cookie behavior exactly (it is `SameSite=Strict`, not host difference alone, that withholds the cookie — confirmed by the reviewer).
- **Citation audits absorbed sequential `api.py` drift without rework.** Legs 2 and 3 were drafted while Leg 1 was in flight; each re-verified its line numbers after the prior leg landed (Leg 2: +3; Leg 3: +43). The re-verification became an explicit "step 0" in Leg 3 after the reviewer noticed the drift.
- **Prerequisite sequencing was load-bearing.** Squawk 0011's `_write_key_atomic` was reused unchanged for the sidecar write; squawk 0012 meant Leg 3's exemption was reviewed against an auth path that holds by construction.
- **Flight-end review passed first time** (488 targeted tests, ruff clean, load-bearing criteria spot-checked by reading code). Deferring review/commit to flight end cost nothing here — three legs, one commit, no per-leg overhead.

## What Could Be Improved

### Process
- **The design-review prompt should ask "what would make this test pass even if the fix were wrong?"** The Leg 3 catch was a test-apparatus error, not an implementation error, and only an independent reader asking that question finds it. Worth a checklist line in the crew's "Review Leg Design" prompt for any leg that introduces a negative-security-property test.
- **Maintenance-report scoping undersold Leg 3.** "May collapse to a one-line exemption" was true of the fix and false of the leg: the cost was proving the one line safe (two tests, a dev-mode seam, docs). Future reports should size gate/security-boundary findings by their verification burden, not their diff.
- **Flight Director artifact edits collided with Developer edits twice** (the flight-log Summary line was rewritten by each Developer, so scripted replacements missed). Minor, but the Flight Director should own the Summary line and Developers should append only.
- **Reviewer model rule.** The crew file says Haiku; the Flight Director used Sonnet for the second security-touching diff in a row and disclosed it. The operator chose to codify: Sonnet for security-touching reviews, Haiku otherwise — logged as squawk 0023.

### Technical
- **Seven encrypted corpora are hand-enumerated in two places** — `key_reconcile._ENCRYPTED_CORPORA` (data) and the seven inline SELECT/UPDATE blocks in `rotate_encryption_key` (code) — plus a de facto third in each repository's own encrypt call. Nothing enforces agreement; this is exactly the failure that produced D1, and it will recur on the next encrypted column. The cheapest guard is a test that cross-checks `_ENCRYPTED_CORPORA` against the literal `(table, column)` pairs the route touches (AST/regex over `api.py`, in the spirit of the codebase's consumer-callsite-audit convention). The full fix — a registry of `EncryptedColumn(table, column, strict)` descriptors that both the route and the sampler iterate — is flight-sized because the corpora have three genuinely different decrypt shapes.
- **Anomaly A1 is only half-closed.** The install/eviction half is fixed (no `await` between commit and `install_key`); the SELECT→UPDATE window (a concurrent insert between step 1 and step 4 lands under the old key) remains, with no red test. Needs either an app-level rotation lock or a `BEGIN IMMEDIATE` strategy that survives aiosqlite's auto-commit-on-non-DML — design work, so a recommendation for the next maintenance report's Known Issues rather than a squawk.
- **The reconcile's "nothing decidable → promote" branch is safe only because the sidecar is written before the commit** (so a `.next` with no decidable rows means nothing was ever encrypted under the old key that matters). That invariant is what makes the branch correct and it is not named at the branch. One comment, and ideally one test named for the failure mode it is *not* vulnerable to.
- **The CLI-window loss has observability but the log line doesn't say so.** The reconcile already WARNs when samples decrypt only under the canonical key — which is precisely the CLI-window symptom the flight documented — but the message doesn't name it. Make the message say "CLI-window" so an operator can connect the line to the doc.
- **`/_test/*` seams are always registered, gated per-handler.** Four now exist; each has its own 403 test but nothing asserts the set. One parametrized test walking `app.routes` for `/_test/` paths and asserting 403 with `dev_mode=False` closes the copy-paste-without-gate risk.
- **`EXEMPT_PATHS` is now a growing hand-maintained enumeration with bespoke safety arguments** — the same shape the corpora list had. A test asserting every exempt path resolves to a GET-only route, and lifting the four-part inertness checklist (no DB read/write, mints nothing, sets no cookie, single-use token) into `SECURITY-MODEL.md` as the named bar for any future exemption, keeps the third exemption honest.
- **Admin UI shows one success flash for `key_file: "staged"` and `"promoted"`.** The response now distinguishes a degraded-but-recoverable rotation; the UI should too.

### Documentation
- `agents.md`, `SECURITY-MODEL.md`, `README.md` are consistent with the code (seven corpora, sidecar contract, two exemptions, operational trace). Gap: the exemption-safety checklist above is reasoning that currently has to be re-derived per exemption.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Two un-rotated corpora folded into Leg 1 (D1) instead of a squawk | Grounding, directly in the leg's path, pattern-copy; the reconcile sampler had to enumerate every corpus anyway | **Yes** — "grounding defect in the leg's path → complete it in the leg" is already the skill's rule; this is a confirming instance |
| Cross-site test direction reversed vs. flight Q3 text (session on `127.0.0.1`, navigate from `localhost`) | The harness only spawns the app at `127.0.0.1`; the proof is identical with sites swapped | No — harness detail; recorded in the flight log |
| Reviewer on Sonnet instead of crew-file Haiku | Diff carried key material and a gate exemption | **Yes** — operator chose to codify (squawk) |
| Dev-mode seam built before the exemption, not after (Leg 3 step order) | The browser test needs it to seed a pending flow in a subprocess; the seam is not the fix under test | No — sequencing detail; AC1 evidence unaffected |
| Legs 2 and 3 drafted while Leg 1 was in flight | Saves wall-clock; independent code regions | **Yes, with the citation re-verification step** — drafting ahead is safe only because each leg re-audited its citations after the prior leg landed |

## Key Learnings

- The two highest-value catches of the flight were both about *the apparatus that proves the fix*, not the fix: a primitive whose precondition the route itself violated, and a test that would have passed with the fix removed. Review effort on high-risk legs should be pointed at "how could this test lie?" as much as "is the code right?".
- A hand-maintained enumeration that must stay in sync across files is a defect waiting for its second author. This flight fixed one (corpora) and created a smaller one (exempt paths). The guard is a test, not a comment.
- Red-first with the failing output recorded in the log turns "we believe the callback was broken" into evidence a reader can check — and it cost one extra test run.

## Test Metrics

**Debrief capture (isolated, `make test-unit` invocation, `--durations=0`):** **4571 passed / 10 skipped / 0 failed / 701 deselected in 509.20s (8m29s)**, no flakes, `-x` never tripped; the 10 skips are the same Windows-only PTY tests as every prior cycle. Browser lane (`-m browser`): the new cross-site test 1/1.

**Trend:** M21 F3 isolated **4507 / 585.40s** → maintenance 2026-08-27 T2 **4511 / 508.26s** → this flight **4571 / 509.20s**. +60 tests at +0.94s. Against M21 F3 the suite is 13% faster with 64 more tests. The "growing uvicorn-loopback tail" hypothesis T2 left open is now **refuted with the per-file aggregate T2 asked for**: the five real-server files are nowhere near the top ten; the mass sits in three large, pre-existing, per-test-fixture-heavy files.

| File | Summed duration | Entries |
|---|---|---|
| `tests/test_provider_api.py` | 85.95s | 281 |
| `tests/test_db_repositories.py` | 63.47s | 279 |
| `tests/test_db_api.py` | 52.54s | 238 |
| `tests/test_db_migration.py` | 33.12s | 111 |
| `tests/test_connectors_inbound.py` | 23.77s | 121 |
| `tests/test_self_configuration_api.py` | 21.67s | 105 |
| `tests/test_pty_session.py` | 14.43s | 13 |
| `tests/test_mcp_pool.py` | 11.15s | 6 |
| `tests/test_self_configuration_external.py` | 10.69s | 55 |
| `tests/test_api_tool_configs.py` | 10.43s | 44 |

This flight's own additions are cheap: `test_encryption.py` +0.03s, `test_key_reconcile.py` +0.07s, `test_lifespan.py` +2.10s (real `lifespan()` in-process, no network), `test_oauth_callback_gate.py` +3.57s (real middleware stack in-process). The one real-browser test is correctly tiered into the browser lane. Slowest individual phases are deliberate timeouts (`test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` 10.01s; two execution-tool timeout clips ~2s) and `test_provider_api.py` fixture setups (1.3–2.7s) — a structural property of that file, not this flight. **If the unit lane needs to get faster, the lever is fixture cost in the three big files, not tiering loopback tests.**

## Skill Effectiveness

- **Mission** — the scaffolded mission carried the three Open Questions with the Architect's recommended defaults; resolving them before `/agentic-workflow` meant every leg started from a decided design. The "Known Issues: N/A" line proved wrong within an hour (D1) — maintenance missions should expect to surface issues, not only clear them.
- **Flight** — Design Decisions were specific enough to implement from; the Technical Approach's evidence citations were accurate. One text-level mismatch (Q3 verification direction) was harmless. The Adaptation Criteria were never triggered.
- **Leg / agentic-workflow** — risk-tiering out loud worked: two high-tier legs got two review rounds each and both needed them; the low-tier leg (2) skipped review and the flight-end Reviewer found nothing. Deferring review/commit to flight end removed per-leg overhead with no loss. Drafting later legs during earlier implementation is a wall-clock win *only* with the citation re-audit; recommend the skill name that explicitly.

## Recommendations

1. **Add the encrypted-corpora guard test now** (squawk 0018): cross-check `_ENCRYPTED_CORPORA` against the `(table, column)` pairs `rotate_encryption_key` touches. Then plan the `EncryptedColumn` registry refactor as a leg in the next maintenance flight.
2. **Carry Anomaly A1 into the next maintenance report's Known Issues** with the two candidate designs (rotation lock vs. `BEGIN IMMEDIATE`), so it is inspected rather than remembered.
3. **Lift the exemption inertness checklist into `SECURITY-MODEL.md`** and pin `EXEMPT_PATHS` members to GET-only routes with a test (squawk 0021) before a third exemption arrives.
4. **Add "how could this test pass with the fix removed?" to the leg design-review prompt** for negative-security-property tests (methodology change, mission-control side).
5. **Close the two `/_test/` and UI observability gaps** as squawks 0020 and 0022: a parametrized 403 sweep over `/_test/*`, and a distinct admin flash for `key_file: "staged"`.

## Action Items
- [ ] Squawk 0018 — test cross-checking `_ENCRYPTED_CORPORA` ↔ `rotate_encryption_key` touched columns
- [ ] Squawk 0019 — name the CLI-window in the reconcile WARNING and comment the "undecidable → promote" invariant
- [ ] Squawk 0020 — parametrized test: every `/_test/*` route 403s with `dev_mode=False`
- [ ] Squawk 0021 — test: every `EXEMPT_PATHS` member is a GET-only route; `SECURITY-MODEL.md` exemption checklist
- [ ] Squawk 0022 — admin UI: distinct warning flash for `key_file: "staged"`
- [ ] Squawk 0023 — crew file: Reviewer model Sonnet for security-touching reviews, Haiku otherwise
- [ ] Next maintenance report: Anomaly A1 as a Known Issue; plan the `EncryptedColumn` registry refactor as a leg
- [ ] Mission-control: design-review prompt checklist line for negative-security tests; agentic-workflow note on drafting legs ahead + citation re-audit
- [ ] Optional: run the `uat-and-alignment` HAT (rotate a key; mint/revoke an `ext_` credential on the real app) before the next `ext_` client is issued
