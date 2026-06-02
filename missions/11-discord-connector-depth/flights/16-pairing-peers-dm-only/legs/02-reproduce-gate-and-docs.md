# Leg: reproduce-gate-and-docs

**Status**: completed
**Flight**: [Pairing peers-axis decoupling (account-scope peers → DM-only)](../flight.md)

## Objective

Lock in the L1 ACL-semantics change with (a) an optional committed `discord_hat` live-regression scenario that reproduces the exact F15 L7 lock-out and (b) the load-bearing documentation: an `agents.md` convention establishing account-scope `peers` as DM-only, amendments to the three existing `agents.md` sites that encode the old peers-gates-guild invariant, and marking the mission Known Issue resolved with fix evidence.

## Context

- L1 removed the account-scope peers-axis block from `_admits_inbound_guild`; guild admission no longer consults `allowlist.peers`. This leg makes that change durable against future regressions (docs that a recon would otherwise re-derive wrongly) and optionally against substrate regressions (a live reproduce-gate).
- **Docs are load-bearing (Architect H1)**: without amending the existing `agents.md` invariant statements, a future ACL-touching leg's recon re-derives "account peers gates guild" from the stale convention text and could reintroduce the leak. This is the primary deliverable of L2.
- The mission Known Issue "Pairing-approval collapses the open peers axis → connector locked to one peer (F15 L7 HAT finding)" is the defect this whole flight closes; it gets marked resolved here with the L1 fix evidence and the F9/F10/F12 lineage note.
- The reproduce-gate is **optional** per the flight's Acceptable Variations — the L1 `test_connectors_acl.py` RED-before/GREEN-after is the binding gate. It ships as a committed, credentials-gated (`@pytest.mark.discord_hat` + `skip_if_unconfigured()`) scenario so it lives in the repo as a re-runnable regression artifact without requiring live execution during this autonomous flight.

## Inputs

- L1 landed: `_admits_inbound_guild` no longer consults account-scope `peers`; full backend suite green.
- `the_one/agents.md` with the sites encoding the old invariant (line numbers approximate — locate by intent, the file shifted during L1): the `per-axis-tri-state-override` convention **body** (~`:112`) **and its citation line** (~`:114`, which frames account-scope `peers` as a peer of channels/guilds/roles in the `admits_inbound` surface — the genuinely stale text); the five-parallel-axes statement **and its section header** (header ~`:791` "4-axis allowlist", body ~`:793`); the `dms-orthogonal-to-guild-restriction` convention (~`:407`, the natural anchor for the new convention). **NOT a target: the `two-symmetric-paths-in-acl` enumeration (~`:421`)** — its "peers axis + channels axis + guilds + roles" list is explicitly scoped to **the per-agent block**, where the peers axis is unchanged (still a guild-routing narrowing modifier). See the amendment guidance for the narrow exception.

**Stale phrasings to hunt for** (the invariant takes several textual forms across `agents.md`): (a) any "4-axis"/"five parallel axes" *count* applied to the account-scope allowlist; (b) any flat enumeration listing account-scope `peers` alongside `channels`/`guilds`/`roles` as guild-admission axes; (c) any citation framing `admits_inbound` account-scope admission as spanning `peers` + channels/guilds/roles together. Each form needs the carve-out; a negative grep alone will miss the header and citation forms.
- `missions/11-discord-connector-depth/mission.md` with the open Known Issue (the F15 L7 entry).
- `tests/live/discord_hat/` driver: `BotDriver`, `wait_for_session`, `latest_routing_entry`, `set_connector_routing`/`restore_connector_routing` (the `PUT /api/connectors/{id}` shallow-merge-config, preserve-secrets pattern), `config.skip_if_unconfigured`, the `@pytest.mark.discord_hat` marker.

## Outputs

- A new `agents.md` M11 convention `account-scope-peers-is-DM-only` (with the per-agent-peers-is-routing distinction), plus carve-out amendments at the three existing invariant sites.
- Mission Known Issue marked resolved with fix evidence (commit/test reference) and the F9/F10/F12 lineage note.
- *(Optional)* a committed `tests/live/discord_hat/` reproduce-gate scenario, credentials-gated (SKIPs without HAT env).

## Acceptance Criteria

- [x] A new convention `account-scope-peers-is-DM-only` is added to `the_one/agents.md`, stating: the account-scope `config["allowlist"]["peers"]` axis gates **DM admission only** (consulted in `_admits_inbound_dm`, never `_admits_inbound_guild`); the per-agent `connector_acls[account_id]["peers"]` axis is a **guild-channel routing-narrowing** modifier (the F15 L4 feature) and is unchanged. The asymmetry between the two same-named axes is **permanent and intended**. Cite `the_one/connectors/_acl.py` and the F9/F10/F12/F16 lineage.
- [x] The five-parallel-axes statement (~`agents.md:793`) **and its section header** (~`:791` "4-axis allowlist") are **restructured** (not merely caveated) so the lead framing no longer counts account-scope `peers` among the guild-admission axes — e.g. "four guild-context axes — `channels`/`guilds`/`roles`/`dm_admission` — plus the DM-only `peers` axis (consulted in `_admits_inbound_dm`)." An appended caveat that leaves the lead sentence asserting all five are parallel guild axes is **not** sufficient.
- [x] The `per-axis-tri-state-override` convention **body** (~`:112`) **and its citation line** (~`:114`) are amended: the citation currently frames `admits_inbound` account-scope admission as spanning `peers` + channels/guilds/roles — reword so account-scope `peers` is identified as the DM-admission axis, distinct from the guild axes. (This citation is the most-likely-to-be-missed stale site — it is an explicit acceptance target, not optional.)
- [x] The `two-symmetric-paths-in-acl` convention (~`:421`) is **left unchanged UNLESS** it conflates the account and per-agent scopes. Its enumeration is explicitly per-agent-scoped (where peers is unchanged), so do **not** rewrite it to say "account peers is DM-only." The only permitted edit is a one-line note that the *account-scope* path now diverges (peers DM-only) while the per-agent path retains peers-narrowing — and only if adding it improves clarity. Verify the scope of the surrounding text before any edit here.
- [x] The mission Known Issue "Pairing-approval collapses the open peers axis → connector locked to one peer (F15 L7 HAT finding)" in `mission.md` is marked **resolved** (`[x]`) with: the L1 fix summary (account-scope peers removed from `_admits_inbound_guild`), the test evidence (the inverted/new `test_connectors_acl.py` assertions + final backend suite count), the preserved two-step DM grant note, and the F9/F10/F12 lineage. The compounding `dm_allowed=False` wrinkle is noted as intentionally retained (out of scope, per the flight).
- [x] *(Optional — drop to unit-only if the live-driver wiring proves heavy)* A committed `tests/live/discord_hat/` scenario reproduces the lock-out: set the connector's `allowlist.peers` to a single bot's structured entry (`[{id: <bot0>, dm_allowed: ...}]`, simulating post-approval) via the connector-config helper; drive a **different** bot's `@mention` into a test channel (mention REQUIRED so the ACL path is exercised, not masked silent by the policy gate); assert the routing `disposition` is `stepped` (admitted/routed), **not** `no-eligible`. Restore the prior allowlist in teardown. The scenario is `@pytest.mark.discord_hat` + `skip_if_unconfigured()`-gated (SKIPs without HAT env) and is RED against the pre-fix substrate, GREEN after.
- [x] No source-tree behavior is changed by this leg (docs + tests only). Carve-out completeness is verified by a **positive enumeration** (not just a negative grep): the new convention is present; the five-axes statement + its header are restructured; the `per-axis-tri-state-override` body + citation are reworded; and `two-symmetric-paths-in-acl` was verified per-agent-scoped and left unchanged (or given only the narrow divergence note). A final `grep -n "peers" the_one/agents.md` read confirms no remaining statement implies account-scope `peers` gates guild channels.

## Verification Steps

- Docs: `grep -n "peers" the_one/agents.md` — every account-scope-peers mention now reads as DM-admission; the new convention is present; no stale "account peers gates guild" wording.
- Known Issue: the F15 L7 entry in `mission.md` is `[x]` with fix evidence.
- Optional reproduce-gate present and collectable-but-skipped: `docker exec the-one pytest tests/live/discord_hat/ -q` SKIPs cleanly (no error) without HAT env; the new scenario file imports the driver helpers correctly.
- Regression: `docker exec the-one pytest tests/test_connectors_acl.py -q` still green (no doc-leg drift).

## Implementation Guidance

1. **agents.md convention** — add `### account-scope-peers-is-DM-only` near the `dms-orthogonal-to-guild-restriction` convention (semantically adjacent). State the DM-only semantic, the per-agent routing-narrowing distinction, the permanence of the asymmetry, and the lineage. Word it strongly (per the flight's "the agents.md amendment words the distinction strongly").
2. **Amend the invariant sites** — locate each by intent (don't rely on exact line numbers — the file shifted during L1), hunting for the three stale phrasing forms enumerated in Inputs: (i) the five-axes statement **and its "4-axis allowlist" header** — restructure the lead framing (four guild-context axes + DM-only peers), not just append a caveat; (ii) the `per-axis-tri-state-override` **body AND its citation line** — the citation framing `admits_inbound` account-scope admission as `peers` + channels/guilds/roles is the highest-risk miss; reword it. **Do NOT amend the `two-symmetric-paths-in-acl` per-agent enumeration** unless it conflates scopes (verify first; the per-agent peers axis is unchanged by this flight). Keep all per-agent peers-narrowing language intact everywhere.
3. **Mission Known Issue** — find the F15 L7 entry by its title/intent (a project-owned artifact; locate it within whatever structure the mission uses), flip `[ ]` → `[x]`, append a `**— CLOSED by F16 L1**` clause mirroring the mission's existing closed-issue style, with fix summary + test evidence + lineage.
4. *(Optional)* **Reproduce-gate** — add `tests/live/discord_hat/test_pairing_peers_decoupling.py` (or extend an existing scenario file). Add a `set_connector_allowlist`/`restore_connector_allowlist` helper to `driver.py` mirroring `set_connector_routing` (GET full connector, record prior `config.get("allowlist")`, set `config["allowlist"]` to the post-approval shape, PUT `{"config": config}` with NO `secrets` key, return prior). The structured account-scope peers entry must satisfy the Pydantic validator (`{id, dm_allowed}`). Drive bot1's `@mention`, poll via `wait_for_session`, assert `latest_routing_entry(detail)["disposition"] == "stepped"`. Gate with `skip_if_unconfigured()`. Do NOT attempt live execution in this autonomous flight — the operator runs it with HAT creds; verify only that it collects-and-skips cleanly.

## Edge Cases

- **Skill–project boundary**: the mission Known Issue and `agents.md` are project-owned artifacts. Locate the target sections by intent, not by hardcoded heading/line; match the project's existing closed-issue annotation style rather than imposing a new one.
- **Structured-shape PUT**: the account-scope `allowlist.peers` PUT must use the v24 structured shape exactly — `{id, dm_allowed}` and no extra keys — else the connector-update Pydantic validator rejects it. The binding validator is in `the_one/db/models.py` (~`:354-390`: rejects bare-string peers AND rejects extra keys); the migration logic is in `the_one/db/schema.py` (~`:1251-1274`). Grep those for the authoritative shape rather than the test-only `_to_v24_shape` helper.
- **Reproduce-gate must use `@mention`**: a non-mention message could be silently dropped by the mentions-aware policy gate (`policy-silent`), masking the ACL behavior under test. The mention forces the ACL path (Architect Q2).
- **Don't re-run the live suite as a gate**: the reproduce-gate is a committed artifact, not an executed gate in this flight. The binding gate is L1's unit matrix.

## Files Affected

- `the_one/agents.md` — new `account-scope-peers-is-DM-only` convention; carve-out amendments at the three invariant sites.
- `missions/11-discord-connector-depth/mission.md` — mark the F15 L7 Known Issue resolved with fix evidence + lineage.
- *(Optional)* `tests/live/discord_hat/driver.py` — `set_connector_allowlist`/`restore_connector_allowlist` helper.
- *(Optional)* `tests/live/discord_hat/test_pairing_peers_decoupling.py` — the credentials-gated reproduce-gate scenario.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (ACL suite still green: 99 passed; reproduce-gate collects-and-skips cleanly: 5 skipped under `-m discord_hat`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header) — `completed` is set by the FD at flight-end acceptance per the batch model
- [ ] Check off this leg in flight.md — deferred to FD flight-end batch
- [ ] Final leg of flight: update flight.md status to `landed`, check off flight in mission.md — deferred to FD flight-end batch
- [ ] Commit deferred to flight-end review (per /agentic-workflow batch model)
