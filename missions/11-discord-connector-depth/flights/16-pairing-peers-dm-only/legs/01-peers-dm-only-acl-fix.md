# Leg: peers-dm-only-acl-fix

**Status**: completed
**Flight**: [Pairing peers-axis decoupling (account-scope peers → DM-only)](../flight.md)

## Objective

Make the account-scope `allowlist.peers` axis gate **DMs only** by removing its check from the guild-channel admission path (`_admits_inbound_guild`), leaving the DM path, the per-agent overlay, and the account-scope channels/guilds/roles axes untouched.

## Context

- **Defect source**: F15 L7 mission Known Issue — "Pairing-approval collapses the open peers axis → connector locked to one peer." `approve_peer_approval` appends the first approved peer to `account.config.allowlist.peers`; because `_admits_inbound_guild` consults that account-scope peers axis (the "# 1. Peers axis" block), every *other* peer's guild-channel message then routes `no-eligible`.
- **Design intent (operator-confirmed, flight Design Decisions)**: the account-scope peers axis was always meant for **DM admission**, never channel gating. F9 scoped the pairing/`NeedsPairing` hook to DMs only; F10 added `dm_admission` as the DM-admission axis; F12 added per-peer `dm_allowed`. The guild consult is a pure leak.
- **Two-step DM grant is preserved**: this leg does NOT touch the approve endpoint or `_inbound.py`'s PAIR-prefix path. Approve still appends `{id, dm_allowed: False}`; the operator flips the per-peer toggle to grant DMs. That is intended, not in scope here.
- **Asymmetry is permanent and intended**: account-scope `peers` = DM admission; per-agent `connector_acls.peers` = guild-channel *routing* narrowing (the F15 L4 feature). The per-agent branch is a separate code path and stays byte-unchanged.

## Inputs

- `the_one/connectors/_acl.py` with `_admits_inbound_guild` consulting the account-scope peers axis at lines 667–676 (the "# 1. Peers axis" block).
- `tests/test_connectors_acl.py` with the flat-shape `admits_inbound` test wrapper (defaults `guild_id=DEFAULT_TEST_GUILD_ID` for non-DM calls) and the guild-context peers tests that currently pin "account peers gates guild."
- `tests/test_connectors_commands.py` with `test_account_allowlist_denies_peer` (`:357`), a **guild-context** (`raw={}`, `plugin=None` → `is_dm=False`) test that asserts `_permitted_agents(ctx) == []` based on the account-scope peers axis — it WILL flip to failing after the fix. The file also provides `_StubPluginWithIsDm` (reads `envelope.raw["is_dm"]`) for building DM-context envelopes.
- `tests/_acl_shape_helpers.py` (`_to_v24_shape`, `_to_v24_agent_acl`, `DEFAULT_TEST_GUILD_ID`).

## Outputs

- `_admits_inbound_guild` no longer consults the account-scope peers axis; guild admission is gated by account-scope channels/guilds/roles + the per-agent overlay only.
- Docstrings in `_acl.py` updated so none implies account-scope peers gates guild channels.
- `tests/test_connectors_acl.py`: the guild-context peers tests inverted/re-commented; new guild-admit + DM-deny tests added; the DM-context + 12-cell `dm_admission` matrices and the per-agent overlay tests remain green and unchanged.
- Full backend suite green.

## Acceptance Criteria

- [x] The account-scope peers-axis block (`_acl.py` "# 1. Peers axis", currently lines 667–676) is **removed** from `_admits_inbound_guild`. The peers check in `_admits_inbound_dm` is **unchanged**. The per-agent peers block in `_admits_inbound_guild` (`agent_acl is not None` branch, currently ~735–751) is **byte-unchanged**.
- [x] `_admits_inbound_guild`'s own docstring (currently ~629–660) is updated from "4-axis (peers/channels/guilds/roles)" → **3-axis (channels/guilds/roles)**, noting the peers axis moved to the DM helper. The public `admits_inbound` dispatcher docstring (currently ~376–451, specifically the "`is_dm=False` consults the peers / channels / guilds / roles axes per the established 4-axis ACL semantics" framing at ~402–403 and the surrounding 4-axis description ~423–441), the module-level per-axis framing (~8–13, 36–49), and the `admits_dm_peer` docstring (~322–330) are reworded so none implies the account-scope peers axis gates guild channels.
- [x] `test_account_peers_subset_denies_non_member` (`tests/test_connectors_acl.py:299`) is **inverted**: account `peers=["P1"]`, guild context, P2 → now **admitted** (`admits is True`, `reason == ""`). This is the primary RED-before/GREEN-after pin.
- [x] `test_account_peers_subset_admits_member` (`:293`) still passes; its comment/rationale is updated to reflect that admission no longer depends on the peers axis in the guild path (channels axis unrestricted).
- [x] `test_agent_acl_empty_dict_equivalent_to_none` (`:466`) keeps its empty-dict≡None invariant: the `:476` "non-member of peers → deny on both paths" arm is **moved to a DM-context assertion** (`is_dm=True`, where peers still gates) so a genuine deny-equivalence case is preserved; the guild-context arms still assert equivalence (now both admit).
- [x] A **new guild-context test** is added: account `peers` non-empty + a non-listed peer → **admitted** when the channels axis permits, **paired** with an assertion that a non-listed channel for that same peer is still **denied** (channels axis still gates — guards the trade-off boundary).
- [x] A **new DM-context test** is added: populated account `peers` + a DM from a non-listed peer → still **denied** (peers-DM-only is now the account peers axis's sole job).
- [x] A **new asymmetry-interaction test** is added (guild context, both axes populated): account allowlist carries **only** the `peers` key (`peers=["P1"]`, no channels/guilds/roles keys → those axes vacuously admit) + per-agent `peers=["P2"]` + a guild message from P3 → **denied by the per-agent axis, NOT by the account axis** (account peers is inert in the guild path even when populated; the per-agent overlay still narrows). The assertion must check the **per-agent** reason substring `"is not admitted for this agent"` (and, as a self-documenting negative, that the bare account-axis reason `"is not admitted on account"` is absent) so the test cannot pass on the wrong (account-axis or channels-axis) reason.
- [x] `test_account_allowlist_denies_peer` in `tests/test_connectors_commands.py` (`:357`) is **converted to DM context** so the account-scope peers deny still holds at its now-correct scope and `_permitted_agents(ctx) == []` stays green; its docstring is updated to note the deny is DM-scoped. Note: the existing `_envelope()` helper hard-codes `raw={}` and exposes no `raw=` kwarg — the conversion must either construct an inline `InboundEnvelope` with `raw={"is_dm": True}` or extend `_envelope()` with a `raw=` parameter, then pass `plugin=_StubPluginWithIsDm()` into `_build_context`.
- [x] `test_both_axes_denied_short_circuits_on_peers` (`:486`, per-agent branch) is **untouched** and still green.
- [x] The F12 12-cell `dm_admission` matrix (`TestAdmitsInboundDmAdmissionAxis` ~`:783`, `TestDmAdmissionCompositionMatrix` ~`:1106`) and the per-agent overlay guild-routing tests are **unchanged** and green.
- [x] The only source-tree tests that pin "account peers gates guild" are the ones enumerated here (`test_connectors_acl.py` + `test_connectors_commands.py::test_account_allowlist_denies_peer`); design review confirmed no others (the flight's original "Architect-verified none in routing/inbound" claim missed `test_connectors_commands.py` — corrected here). Full backend suite green.

## Verification Steps

- Removal + docstrings: `grep -n "# 1. Peers axis" the_one/connectors/_acl.py` returns no hit inside `_admits_inbound_guild`; the peers block still present in `_admits_inbound_dm`.
- RED-before check (optional, demonstrative): before the code edit, the inverted test asserts admit while the old block denies → fails; after the edit → passes.
- Targeted suite: `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_commands.py -x --timeout 30 -q`
- Full backend suite at leg end: `docker exec the-one pytest -x --timeout 60 -q`
- Regression guard for unrelated account-peers usage: `docker exec the-one pytest tests/test_connectors_routing.py tests/test_connectors_inbound.py -x --timeout 60 -q`

## Implementation Guidance

1. **Remove the account-scope peers block** in `_admits_inbound_guild` (`the_one/connectors/_acl.py`, currently lines 667–676 — the `allowed_peers = allowlist.get("peers", [])` check and its `return (False, …"is not admitted on account"…)`). Leave the surrounding `if allowlist is not None:` block and the channels/guilds/roles axes intact. Do not touch `_admits_inbound_dm`'s peers check.
2. **Docstring sweep**:
   - `_admits_inbound_guild` docstring: "Consults the 4-axis ACL semantics (peers / channels / guilds / roles)" → "3-axis (channels / guilds / roles)"; add a sentence that the account-scope peers axis is DM-only and lives in `_admits_inbound_dm`.
   - Module docstring per-axis framing (~36–49) and the F12 storage paragraph (~8–13): reword so the account-scope peers axis is described as the DM-admission axis, not a guild gate. Keep the channels-axis HAT-redesign framing accurate.
   - `admits_dm_peer` docstring (~322–330): confirm wording still reads correctly (this helper IS DM-scoped); adjust only if it implies guild gating.
3. **Invert / adjust tests** in `tests/test_connectors_acl.py` per the acceptance criteria. Use the existing flat-shape `admits_inbound` wrapper and `_account` builder. For DM-context assertions pass `is_dm=True` (suppresses the `DEFAULT_TEST_GUILD_ID` default so `guild_id` stays `None`). For the new admit/deny boundary test, set `allowlist={"peers": ["P1"], "channels": ["C1"]}` and assert P2/C1 admits while P2/C2 denies with the channels reason.
4. **Re-run** the targeted ACL suite, then the routing/inbound suites, then the full backend suite. If any unexpected failure surfaces outside the intentionally-inverted tests, stop and report — it may indicate a hidden account-peers-gates-guild dependency (the divert condition).

## Edge Cases

- **Per-agent overlay must not regress**: the `agent_acl is not None` peers branch in `_admits_inbound_guild` is a different read (`agent_acl["peers"]`) from the deleted account-scope read (`allowlist["peers"]`). Confirm it is byte-unchanged; its tests (`test_both_axes_denied_short_circuits_on_peers`, per-agent subset tests) stay green.
- **DM path untouched**: `_admits_inbound_dm` still denies a non-listed peer's DM under a populated account `peers` list (and under the `dm_admission`/`dm_allowed` composition). The new DM-context test guards this.
- **Channels axis still gates guild**: removing peers must not weaken the channels axis. The paired admit/deny boundary test pins that a non-listed channel still denies.
- **`test_account_scope_peers_empty_is_unrestricted_but_per_agent_peers_empty_is_deny` (`:440`)**: still passes (account arm uses `peers=[]` → vacuously admit; per-agent arm unchanged). Review its comment for lingering "account peers gates guild" implication; adjust wording only if misleading — no assertion change.

## Files Affected

- `the_one/connectors/_acl.py` — remove account-scope peers block from `_admits_inbound_guild`; docstring sweep (`_admits_inbound_guild`, the `admits_inbound` dispatcher, the module docstring, `admits_dm_peer`).
- `tests/test_connectors_acl.py` — invert `test_account_peers_subset_denies_non_member`; re-comment `test_account_peers_subset_admits_member`; move the deny arm of `test_agent_acl_empty_dict_equivalent_to_none` to DM context; add one guild-admit/deny-boundary test, one DM-deny test, and one account-vs-per-agent asymmetry-interaction test.
- `tests/test_connectors_commands.py` — convert `test_account_allowlist_denies_peer` to DM context (`raw={"is_dm": True}` + `_StubPluginWithIsDm`) so the account-peers deny holds at its now-correct scope.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (targeted ACL suite + full backend suite green — 2835 passed)
- [x] Update flight-log.md with leg progress entry
- [x] Leg status set to `landed` (→ `completed` at flight-end commit)
- [ ] Check off this leg in flight.md (deferred to flight-end commit)
- [ ] If final leg of flight: (not final — L2 follows)
- [ ] Commit deferred to flight-end review (per /agentic-workflow batch model)
