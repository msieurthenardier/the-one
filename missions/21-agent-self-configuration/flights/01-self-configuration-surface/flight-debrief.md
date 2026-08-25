# Flight Debrief: Self-Configuration Surface

**Date**: 2026-08-25
**Flight**: [Self-Configuration Surface](flight.md)
**Status**: completed
**Duration**: 2026-08-24 – 2026-08-25
**Legs Completed**: 3 of 3

## Outcome Assessment

### Objectives Achieved

The flight delivered a loopback MCP surface through which an agent reads its own
configuration and revises its own description and system prompt, off by default
per agent, governed by the operator's existing per-source and per-tool controls.
All three legs landed and committed as `c7cf9cb`:

- **Leg 1** — `AgentConfig.tool_overrides`/`mcp_overrides` encrypted at rest,
  credential keys masked on every agent read path, preserve-on-PUT resolved
  server-side, and the agents columns joined to key rotation. Closed mission
  Known Issue 1 (plaintext secrets in agent override columns).
- **Leg 2** — the `the_one/self_configuration/` package; a per-agent
  `agt`-prefixed credential registered behind Mission 20's gate seam and
  **confined to the surface mount path**; a stateless FastMCP loopback endpoint;
  two read tools with a secret-free projection; the enable/disable API and Studio
  tab; admin-listing filter; ownership guards; and the desktop fallback-port fix.
- **Leg 3** — two write tools; `next_turn` applied at the turn-settle sites,
  `next_session` via persist-then-rebuild; the reserved constant row name
  (closing the 64-char tool-name ceiling, Anomaly A11); tool-cache reconcile.

### Mission Criteria Advanced

- **Criterion 1** (retrieve own config; no secret in any surface response) — met;
  verified by the projection tests and behavior-test steps 2/4/8.
- **Criterion 2** (agent config subject to the same secret handling as every
  other record) — met by Leg 1's encrypt-at-rest + mask-on-read + rotation.
- **Criterion 3** (revise description and system prompt; every other field
  refused by construction) — met; the two-field allowlist is the catalog's shape
  (no tool names a field).
- **Criterion 4** (a revision states next-turn vs next-conversation; observed
  behavior matches) — met for `next_turn` and for `next_session` into a new
  conversation; `next_session` into an already-open conversation is applied at
  the agent level but not reliably observable via reply sentinels (model
  history-anchoring; see A12).
- **Criterion 8** (surface appears among the agent's sources; per-capability
  operator control via existing controls) — met by DD1's real-source presentation.
- **Criterion 9** (off for every existing and new agent until enabled) — met.

Criteria 5–7 (approval mode, pending queue, revision log, restore) belong to
Flight 2; criterion 10 (external client access) to Flight 3.

## What Went Well

- **The re-entrancy probe earned its keep as a blocking prerequisite.** DD1's
  entire premise — the platform can call its own loopback MCP endpoint from
  inside a request handler without deadlock — was unverified until the probe ran.
  It passed cleanly (~45 ms round trip) and surfaced six concrete constraints
  (lifespan wrap, shutdown-drain ordering, `auth_posture`, operator-level gate
  identity, URL shape, cache-first build) that were threaded into Leg 2's design.
  A wrong answer would have collapsed DD1 and forced re-planning Flight 3.
- **Design review caught real bugs before code, twice.** Leg 2's confinement
  wording ("any source that is not `file`") would have 403'd the session cookie
  on every path and broken the entire web UI — caught and corrected to the
  `CONFINED_SOURCE_PATHS` map before implementation. Leg 3's resume-path hook
  needed `re_paused` gating and the default agent's `None` name normalized —
  both caught before code, both genuine AC violations avoided.
- **DD5's two factual errors were caught by design review, not production.** The
  flight-level DD text asserted `Encryptor.rotate_key` "has no production caller"
  (true but misleading — `POST /api/encryption/rotate` re-encrypts inline) and
  that `_decrypt_secrets_blob` "falls back to plaintext" (it returns `{}` on
  `InvalidToken`, which would have silently discarded real legacy operator data).
  Both surfaced as flight-log Decisions D1/D2 and were fixed before Leg 1 code.
- **The secret checks are response-text regression nets, not masking-function
  unit calls.** A seeded literal secret is asserted absent from the raw HTTP/tool
  response body across all six agent-config endpoints and both read tools —
  mirroring the existing `test_list_returns_masked_secrets` precedent.
- **The A12 investigation distinguished "mechanism wrong" from "oracle wrong."**
  A failing behavior test (6/8) that looked like a `next_session` propagation
  defect was, under server-side instrumentation, proven to be a
  test-observability confound — the propagation mechanism is correct. The fix was
  to the test spec, and the investigation was converted into a durable regression
  test rather than left as narrative.
- **Sequencing (secrets → read → write) was the right call.** The read projection
  was built over an already-safe store, not layered over a leaky one.

## What Could Be Improved

### Process

- **Flight-end review findings were under-documented in the first commit.** The
  flight-end review caught a real security bug (a route-prefix-boundary bypass in
  the confinement check) and two coverage gaps, but the flight log initially
  recorded only that a review ran — no itemized findings, unlike every leg-design
  review. Corrected retroactively (the findings are now itemized in the flight
  log). **Recommendation: itemize flight-end-review findings with severity in the
  flight log as standard**, since the flight-end review is the one point where
  cross-leg interactions get checked and it caught something no single leg review
  could have.
- **DDs that assert "X has no caller" or "Y already does Z" need a citation-audit
  pass before the leg is drafted.** DD5's two errors were exactly this shape. The
  flight adopted a per-leg "Citation Audit" section mid-stream — that should be
  standard from the first leg, not adopted after the first correction.

### Technical

- **Shutdown-drain WARNING mitigation is reasoned but unproven under load.** The
  pre-drain eviction of marked rows' pool entries (per the probe's Constraint 2)
  was implemented, but neither Leg 2 nor Leg 3's start/stop check exercised a
  surface-enabled agent with a live pool connection at shutdown. Small,
  self-disclosed gap.
- **Two-agent isolation (Leg 2 AC9) was ticked on enforcement + code inspection**,
  not a dedicated two-agent-simultaneous end-to-end test.
- **Import-order duplication in the new package.** `credentials.py:load_from_rows`
  duplicates `manage.is_surface_row`'s marker check inline, and `manage`/`surface`
  do function-local imports of each other, to route around a circular import —
  the same duplicate-shape-for-import-order pattern the Mission 20 debrief flagged
  (`auth_headers` ×3). A maintenance-cycle candidate if the package grows;
  factoring the marker check into `constants.py` would remove the duplication.

### Documentation

- Documentation was thorough (`SECURITY-MODEL.md` gained the surface, the second
  credential source and its path scoping, and an honest residual
  indirect-prompt-injection statement; `agents.md` and `CLAUDE.md` updated). No
  gaps beyond the flight-log process note above.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Credential minting moved from Flight 3 into Flight 1 | DD1 made a credential unavoidable on the agent's own loopback path | N/A — one-time scope shift, correctly re-classified |
| DD5 encrypt path used a purpose-built `_decrypt_overrides_column`, not the shared `_decrypt_secrets_blob` | The shared helper returns `{}` on `InvalidToken`, which would discard legacy plaintext agent overrides | Yes — a helper's `{}`-on-failure semantics must be re-checked before reuse on a column whose default is not `'{}'` |
| Surface row name became the constant `self-configuration` | The per-agent template hit the 64-char MCP tool-name ceiling (A11) | Yes — tool-name length budget must be checked when a source name is templated from user data |
| Gate confinement via a `CONFINED_SOURCE_PATHS` map | The `CredentialSource` protocol must not widen; per-route scope belongs at the middleware | Yes — template for any future non-operator credential source |
| Behavior-test observable changed to a fresh conversation | Sentinel-in-reply is confounded by model history-anchoring inside an established conversation | Yes — house rule for system-prompt-dependent behavior tests |

## Key Learnings

- **A live model anchors on its conversation history more strongly than on a
  freshly-swapped system prompt.** This is the deepest finding of the flight: even
  asked outright to read its current instructions, a real agent reported the old
  sentinel while its live prompt held the new one. Any behavior test asserting a
  system-prompt-dependent property must use a fresh conversation as the oracle,
  never a reopen-and-ask pattern. A revision tool call's own arguments also echo
  the new prompt text into context, compounding the confound.
- **A failing acceptance test is a hypothesis, not a verdict.** The 6/8 run looked
  like a propagation bug; the disciplined response (instrument the mechanism,
  reproduce deterministically, rule out the alternative) found the test was wrong,
  not the product — and produced a permanent unit regression test as the residue.
- **Marker-driven enumeration satisfies "by construction" better than a list.**
  `MCP_OVERRIDE_CREDENTIAL_KEYS` (derived from `Substitute` field metadata) and
  the two-write-tool catalog shape both make the safe set impossible to drift by
  omission.

## Recommendations

1. **Flight 2 (operator oversight) must treat the live residual risk as its
   primary acceptance bar.** `SECURITY-MODEL.md` now states plainly that a
   prompt-injected agent can call the write tools with the same confinement as a
   legitimate self-revision; no approval gate, pending queue, or revision log
   exists yet. Flight 2's approval mode also needs a real `applied_to_store:
   false` / `"queued"` branch — Leg 3 always persists on write (LD2), the opposite
   of what approval mode requires; LD4 anticipated the result shape but not the
   branch. And the "operator edits the prompt in Studio between revision and
   settle" staleness case (Leg 3 Edge Cases, "recorded not solved") is Flight 2
   governance territory — name it as a criterion, don't rediscover it.
2. **Close the two small verification gaps in Flight 2**, since its approval-queue
   work touches the same pool/lifecycle code: the shutdown-drain-under-load check
   (a surface-enabled agent with a live pool connection at shutdown) and a
   two-agent-simultaneous isolation e2e test.
3. **Flight 3 (external client access) reuses `CONFINED_SOURCE_PATHS` and the
   in-memory-registry-loaded-from-rows pattern** rather than re-designing — both
   are now precedented and the confinement map already anticipates a second entry.
4. **Standardize three patterns** into the methodology/skills: the gate
   confinement map (minimal-blast-radius scoped credential source), the
   marker-driven secret-key set, and — into `behavior-test/AUTHORING.md` — the
   fresh-conversation observable rule for system-prompt-dependent assertions.
5. **Itemize flight-end-review findings in the flight log with severity**, as leg
   reviews already are.

## Action Items

- [ ] Flight 2: approval mode with a genuine non-persisting ("queued") write
      branch, revision log, restore, and the staleness-on-concurrent-edit case as
      a named acceptance criterion.
- [ ] Flight 2: shutdown-drain-under-load verification (surface-enabled agent,
      live pool connection at shutdown) and a two-agent-simultaneous isolation
      behavior/e2e test.
- [ ] Add the fresh-conversation observable rule to `behavior-test/AUTHORING.md`
      (mission-control side) so future self-revision-style specs inherit it.
- [ ] Maintenance-cycle candidate: factor the surface-row marker check into
      `constants.py` to remove the `credentials.py`/`manage.py` import-order
      duplication (watch-item, not urgent) — logged as **squawk 0004**.
- [ ] Squawk 0003 (pre-existing first-touch circular import) remains deferred;
      revisit if a standalone script needs to import `db.repositories` first.

## Notes

- **Human interview skipped** per the skill's guidance — the flight log is
  comprehensive (DD1–DD9, D1–D6, A10–A13, the full A12 investigation), and the
  Flight Director drove every decision first-hand, so a human Q&A would fill no
  gap.
- **Test metrics.** Full unit lane at flight end: **4381 passed, 10 skipped**
  (confirmed against commit `c7cf9cb` at the pre-commit gate). Leg-over-leg
  growth 4288 → 4344 → 4375 → 4381 passed, 10
  skipped throughout; per-leg full-lane wall-clock held in a stable ~6:10 band
  (~366s / ~372s / ~370s) despite four new test files and ~+130 net tests — no
  runaway growth. Baseline for comparison: Mission 20's debrief recorded ~4252
  unit tests. Browser lane green throughout (one pre-existing unrelated skip).
