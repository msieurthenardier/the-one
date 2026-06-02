# Flight Log: Pairing peers-axis decoupling (account-scope peers → DM-only)

**Flight**: [Pairing peers-axis decoupling](flight.md)

## Summary

Planning. Focused defect fix sourced from the F15 L7 mission Known Issue. Scope locked by the operator: make the account-scope `allowlist.peers` axis **DM-only** (remove from the guild path); **keep** the two-step DM grant (approve unchanged). Small flight (2 legs); unit ACL matrix is the binding gate.

---

## Reconnaissance Report

Source: the F15 L7 mission Known Issue ("Pairing-approval collapses the open peers axis → connector locked to one peer"). Walked against current code (F16 planning, via a codebase map).

| Item | Classification | Evidence | Recommendation |
|------|---------------|----------|----------------|
| Account-scope `peers` axis gates GUILD-channel messages (the over-restriction) | `confirmed-live` | `_admits_inbound_guild` ("# 1. Peers axis" block in `the_one/connectors/_acl.py`): `if allowed_peers and not any(p["id"]==peer_id ...): return (False, "peer_id not admitted")` — fires for `is_dm=False` | L1 — remove this block (peers → DM-only) |
| Approval appends `dm_allowed=False` (the under-grant) | `confirmed-live` (but **intended**, per operator) | `approve_peer_approval` (`api.py:~2716`) + PAIR-prefix path (`_inbound.py:~471-480`) append `{id, dm_allowed: False}`; `_admits_inbound_dm` (`_acl.py:~580`) denies DMs when `dm_allowed=False` under `admin-approved` | NO change — operator keeps the two-step |
| DM-context peers gating + 12-cell `dm_admission` matrix | `confirmed-live` (must stay unchanged) | `_admits_inbound_dm` (`_acl.py:~539-589`) + `tests/test_connectors_acl.py` DM-matrix tests | L1 — re-verify unchanged after the guild-path edit |
| Per-agent `connector_acls.peers` overlay gating guild routing (L4) | `confirmed-live` (must stay unchanged) | `_admits_inbound_guild` `agent_acl is not None` branch (`_acl.py:~276+`) — separate from the account-scope block | L1 — confirm byte-unchanged; flag the account-vs-per-agent asymmetry for the Architect |
| Tests pinning "account peers gates guild" | `confirmed-live` | `tests/test_connectors_acl.py` guild-context peers tests (`test_account_peers_subset_admits/denies_non_member`, the empty-vs-non-empty guild semantic test) | L1 — invert/rename per the rename-pattern |

**Operator-confirmed scope decisions:** (1) account-scope `peers` is DM-only by design (per-channel/server user restrictions deliberately excluded); (2) keep the two-step DM grant (approve stays `dm_allowed=False`).

---

## Flight Director Notes

### 2026-06-02 — F16 orchestration start
- Loaded `leg-execution.md` phase file (valid: Crew / Interaction Protocol / Prompts). Marked flight `ready` → `in-flight`. Branch `flight/16-pairing-peers-dm-only` created off `main`. Batch model: leg design reviewed per leg; single code review + commit at flight end.
- **L1 design** authored (`legs/01-peers-dm-only-acl-fix.md`) from the flight spec + live code read of `_acl.py` (`_admits_inbound_guild` account-scope peers block at `:667-676`; per-agent branch separate at `:735-751`; `_admits_inbound_dm` has its own peers check) and the `test_connectors_acl.py` flat-shape wrapper.
- **L1 design review (round 1 — Developer):** `needs rework`. Surfaced a **high** issue the flight's "Architect-verified none in routing/inbound" claim missed: `tests/test_connectors_commands.py::test_account_allowlist_denies_peer` (`:357`) is a guild-context test (`raw={}`, `plugin=None` → `is_dm=False`) pinning account-peers-gates-guild — it flips RED after the fix. Also a **medium**: the `admits_inbound` dispatcher docstring (`:402-403`) was missing from the sweep. FD independently verified the commands-test gap against source. **Incorporated:** added `test_connectors_commands.py` to scope (convert that test to DM context via `_StubPluginWithIsDm`), added the dispatcher docstring to the sweep, folded in an account-vs-per-agent asymmetry-interaction guild test, widened verification commands.
- **L1 design review (round 2 — Developer, focused):** `approve with changes`. Confirmed the high issue fully closed and the DM-conversion mechanically sound (`_permitted_agents` → `AdmissionContext.from_envelope` → `_admits_inbound_dm` under `is_dm=True`); full-tree re-grep confirmed those are the ONLY two account-peers-gates-guild sites. Two **low** precision fixes applied: pin the asymmetry test's deny origin to the per-agent reason substring (account allowlist carries only `peers`); note `_envelope()` needs a `raw=` param / inline construction. L1 set `ready`. **2 design-review cycles used (max).**
- **L1 implementation (Developer):** code change + docstring sweep + all prescribed test inversions/additions landed. The agent was truncated mid-run before emitting `[HANDOFF:review-needed]` / writing the flight-log. FD verified all 12 acceptance criteria against on-disk state (block removed; `_admits_inbound_dm` + per-agent branch unchanged; docstrings 4-axis→3-axis; every test present) and ran the suites green (targeted 161, regression-guard 98, full backend **2835 passed / 4 skipped / 528 deselected**, exit 0). The 3 warnings are the pre-existing `aiosqlite` teardown Known Issue, not introduced here. FD completed L1's leg bookkeeping (status `landed`, ACs checked, flight-log entry) — verification + artifact updates only, no FD-authored source.
- **L2 design** authored (`legs/02-reproduce-gate-and-docs.md`): docs (load-bearing `agents.md` carve-outs + new `account-scope-peers-is-DM-only` convention + mission Known Issue closure) and an optional credentials-gated `discord_hat` reproduce-gate.
- **L2 design review (round 1 — Developer):** `approve with changes`. Caught a **wrong-edit hazard**: the `two-symmetric-paths-in-acl` enumeration (~`agents.md:421`) is per-agent-scoped (peers unchanged there) — amending it to "account peers DM-only" would be incorrect. Also a **high**-value miss: the `per-axis-tri-state-override` citation line (~`:114`) frames account-scope peers among the guild axes and must be carved out. Plus restructure (not caveat) the five-axes statement + its "4-axis" header, and correct the validator reference (`models.py`/`schema.py`, not `_to_v24_shape`). **All incorporated**; FD independently confirmed the `:421` per-agent scoping and `:114` staleness from prior greps. No second design-review cycle for L2 (first verdict already `approve`; changes applied verbatim from the reviewer's own recommendations; flight-end Reviewer will also see the agents.md diff). L2 set `ready`.
- **L2 implementation (Developer):** `[HANDOFF:review-needed]`. agents.md carve-outs landed exactly to spec — the `two-symmetric-paths-in-acl` per-agent enumeration was left intact (scope note only), the wrong-edit hazard avoided. Known Issue closed; reproduce-gate committed (skip-gated, 5 skipped clean); ACL suite 99 passed. FD verified the agents.md diff (five-axes header+body restructured, citation reworded, per-agent enumeration untouched). L2 set `landed`.
- **Flight review (Reviewer — Sonnet, FD chose Sonnet over the crew's Haiku given correctness-critical ACL semantics; within the no-Opus envelope):** `[HANDOFF:confirmed]`. Reviewed ALL uncommitted changes against both legs' acceptance criteria + correctness + code quality + tests. Confirmed every L1/L2 criterion met, no other `admits_inbound` call site assumed account-scope peers gated guild, no axis weakened, DM peers gating intact, driver helpers mirror the routing-helper pattern (no `secrets` in PUT), reproduce-gate mechanically correct. **No issues — zero fix cycles.**
- **Commit + land (FD):** review independence already satisfied (no source to re-review), so FD performed the flight-control bookkeeping (both legs → `completed`; flight → `landed`; F16 checked off in mission.md; F15 L7 Known Issue resolved) and committed code + artifacts in one commit on `flight/16-pairing-peers-dm-only`. Documentation check (Phase 3.3): no new product commands/endpoints/config/public APIs introduced — the only new surface is the test-only `discord_hat` driver helper; `agents.md` (the substrate's doc surface) was updated by L2; no README/CLAUDE.md change warranted. Draft PR opened. `[COMPLETE:flight]`.

## Leg Progress

### L1 — peers-dm-only-acl-fix
**Status**: landed
**Completed**: 2026-06-02

#### Changes Made
- **`the_one/connectors/_acl.py`**: removed the account-scope "# 1. Peers axis" block from `_admits_inbound_guild` (the guild path no longer consults `allowlist.peers`). `_admits_inbound_dm`'s peers check and the per-agent peers branch are byte-unchanged. Docstring sweep: `_admits_inbound_guild` "4-axis → 3-axis (channels/guilds/roles)"; the public `admits_inbound` dispatcher docstring, the module per-axis framing, and `admits_dm_peer` reworded so none implies account-scope peers gates guild.
- **`tests/test_connectors_acl.py`**: inverted `test_account_peers_subset_denies_non_member` (guild context, P2 now admitted); re-commented `test_account_peers_subset_admits_member`; moved the deny arm of `test_agent_acl_empty_dict_equivalent_to_none` to DM context (`is_dm=True`); added three tests — guild-admit/channels-still-gate boundary, DM-context still-denies, and the account-vs-per-agent asymmetry pin (per-agent reason substring asserted + account-axis reason asserted absent).
- **`tests/test_connectors_commands.py`**: converted `test_account_allowlist_denies_peer` to DM context (`raw={"is_dm": True}` + `_StubPluginWithIsDm`) so the account-scope peers deny holds at its now-correct scope and `_permitted_agents(ctx) == []` stays green.

#### Tests
- Targeted: `test_connectors_acl.py` + `test_connectors_commands.py` → **161 passed**.
- Regression guard: `test_connectors_routing.py` + `test_connectors_inbound.py` → **98 passed**.
- Full backend suite: **2835 passed, 4 skipped, 528 deselected** (live `discord_hat` tests deselected/skipped), exit 0, 4:27. The 3 warnings are the pre-existing `aiosqlite` event-loop-closed teardown warnings (tracked mission Known Issue, NOT introduced here).

#### Notes
- The L1 design review (round 1) surfaced a guild-context test the flight's recon missed (`test_connectors_commands.py::test_account_allowlist_denies_peer`); incorporated before implementation, so no RED surprise during the implement leg.
- Implementing Developer agent was truncated mid-run (its final `[HANDOFF:review-needed]` signal + flight-log write didn't land); FD verified the on-disk changes against every acceptance criterion (code block removed, docstrings swept, all prescribed test inversions/additions present) and ran the full suite to green, then completed the L1 bookkeeping. No code was authored by the FD — verification + artifact updates only.
- Uncommitted per the batch model; review + commit deferred to flight end.

### L2 — reproduce-gate-and-docs
**Status**: landed
**Completed**: 2026-06-02

#### Changes Made
- **`the_one/agents.md`** — load-bearing docs carve-out (locate-by-intent, no hardcoded line numbers; the file shifted during L1). Sites amended:
  - **New convention `account-scope-peers-is-DM-only`** added next to `dms-orthogonal-to-guild-restriction`: states the account-scope `allowlist.peers` axis gates DM admission ONLY (`_admits_inbound_dm`, never `_admits_inbound_guild`); the per-agent `connector_acls[account_id].peers` axis remains a guild-routing narrowing modifier (F15 L4, unchanged); the asymmetry is permanent and intended; rationale + F9/F10/F12/F15-L7/F16 lineage; cites `_acl.py` + `tests/test_connectors_acl.py`.
  - **`per-axis-tri-state-override` BODY restructured** — the multi-axis list no longer counts account-scope `peers` among the composing guild axes (now "channels/guilds/roles/dm_admission, and — DM-only at account scope — peers"); added the M11 F16 L1 axis-scoping caveat.
  - **`per-axis-tri-state-override` CITATION line reworded** (the highest-risk miss) — the citation that framed `admits_inbound` account-scope admission as spanning `peers` + `channels` now identifies account-scope `peers` as the DM-admission axis (`_admits_inbound_dm`), distinct from the guild axes, NOT a peer of `channels` on the guild path.
  - **"4-axis allowlist" section header + five-parallel-axes body restructured** — header → "Allowlist axes + outbound fallback (M10 F8 L8; M11 F16 L1)"; lead framing now "four guild-context axes — `channels`/`guilds`/`roles`/`dm_admission` — plus the DM-only `peers` axis (`_admits_inbound_dm`)" with the account-vs-per-agent scope distinction spelled out. Not an appended caveat — the count was restructured.
  - **`two-symmetric-paths-in-acl` LEFT INTACT** (per-agent-scoped, peers unchanged) — verified its enumeration is the per-agent block before touching it. Added only the permitted one-line scope-divergence note (account-scope path now diverges: peers DM-only; per-agent path retains peers-narrowing) — the enumeration itself was NOT rewritten.
  - All per-agent peers-narrowing language kept intact everywhere. Final `grep -n "peers" the_one/agents.md` read confirms no remaining statement implies account-scope `peers` gates guild channels (residual "peers" hits are unrelated module-graph/visibility prose and the storage-shape REQUIRED-key statement).
- **`missions/11-discord-connector-depth/mission.md`** — the F15 L7 Known Issue flipped `[ ]` → `[x]` with a `**— CLOSED by F16 L1**` clause (mirroring the mission's existing closed-issue annotation style): L1 fix summary (account-scope peers removed from `_admits_inbound_guild`), test evidence (`test_connectors_acl.py` inverted/new assertions + final backend suite **2835 passed / 4 skipped / 528 deselected**), the preserved two-step DM grant noted as intentionally retained out of scope, and the F9/F10/F12→F16 lineage.
- **`tests/live/discord_hat/driver.py`** — added `set_connector_allowlist` / `restore_connector_allowlist` helpers mirroring `set_connector_routing` / `restore_connector_routing` exactly (GET connector, record prior `config.get("allowlist")`, set `config["allowlist"]`, PUT `{"config": config}` with NO `secrets` key, return prior).
- **`tests/live/discord_hat/test_pairing_peers_decoupling.py`** (NEW) — credentials-gated reproduce-gate: narrows account-scope `allowlist.peers` to one approved bot (`[{id: bot0, dm_allowed: False}]`, the v24 structured shape), drives a DIFFERENT bot's `@mention` (mention REQUIRED to exercise the ACL path, not policy-silence it) into a test channel via `post_and_wait_new_routing`, asserts routing `disposition == "stepped"` (admitted, not `no-eligible`). `@pytest.mark.discord_hat` + `skip_if_unconfigured()`; prior allowlist restored in `finally`. RED against pre-F16-L1 substrate, GREEN after.

#### Reproduce-gate disposition
- **Committed** (preferred per the leg) — the live-driver wiring was clean (the allowlist helper mirrors the existing routing helper 1:1), so it did NOT fall back to unit-only. NOT executed live (no operator-logged-in HAT session here); the binding gate remains L1's `test_connectors_acl.py` unit matrix.

#### Tests
- `docker exec the-one pytest -m discord_hat tests/live/discord_hat/ -q` → **5 skipped** (collect-and-skip clean, no errors — the new scenario is the 5th file; import/signature correct).
- `docker exec the-one pytest tests/test_connectors_acl.py -q` → **99 passed** (no doc-leg drift).
- New scenario `--collect-only` → 1 test collected (no import error).

#### Notes
- Docs-only on the source tree (no `_acl.py` behavior change); the reproduce-gate is a committed regression artifact, not an executed gate.
- Uncommitted per the batch model; review + commit + flight-landing deferred to flight end.

## Decisions

_None yet._

## Deviations

_None yet._

## Anomalies

_None yet._

## Session Notes

### 2026-06-02 — Planning
- Sourced from the F15 debrief flagship. Codebase map confirmed the over-restriction (`_admits_inbound_guild` account-scope peers block) and the (intended) under-grant.
- Operator locked the scope: Option A (peers DM-only) + keep the two-step. Per-agent overlay preserved.
