# Flight: Pairing peers-axis decoupling (account-scope peers → DM-only)

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] Resolves the F15 L7 mission Known Issue — **"Pairing-approval collapses the open peers axis → connector locked to one peer"** — a defect in the already-closed pairing flow (#8). It is a hardening prerequisite for the **#19 daily-driver run** (F17): without it, approving one unknown DM-er during a working day silently locks the bot to that single peer everywhere.

> *(Numbering: this flight inserts as F16; the planned daily-driver gate shifts to F17 and the optional alignment to F18. Updated in mission.md's Flights list.)*

---

## Pre-Flight

### Objective

Make the **account-scope `allowlist.peers` axis gate DMs only** — remove it from guild-channel admission. Today `_admits_inbound_guild` consults the account-scope peers axis (`_acl.py`, the "# 1. Peers axis" block), so when pairing-approval appends the first peer to `peers`, every *other* peer's guild-channel message is denied (`no-eligible`). Per operator + the F9/F10 design intent, the account-scope peers axis was always meant for **DM admission**, never channel gating. This flight removes the leak, leaving the account-scope `channels`/`guilds`/`roles` axes and the **per-agent `connector_acls` overlay (L4's routing differentiation) untouched**. The deliberate two-step DM grant (approve adds the peer with `dm_allowed=False`; the operator flips the per-peer toggle to actually allow DMs) is **preserved** — this flight does NOT change the approve endpoint.

### Open Questions

- [x] **Is account-scope `peers` meant to gate guild channels, or DMs only?** → **DM-only** (operator-confirmed): per-channel/server *user* restrictions were intentionally excluded for simplicity ("it became weird and hard to comprehend when someone can DM the bot but can't talk to it in a channel"). The guild-gating is a pure leak.
- [x] **Should approving a peer grant DM access immediately?** → **No** — keep the two-step (approve = on the radar / DM-allowlisted with `dm_allowed=False`; the per-peer toggle = actually grant DMs). The under-grant is intended, not a bug. The approve endpoint is unchanged.
- [x] **Does removing account-scope peers-from-guild interact with the per-agent `connector_acls.peers` overlay?** → **No — resolved (Architect-verified).** They are genuinely separate code paths (`account.config["allowlist"]["peers"]` read by the deleted account-scope block vs `agent_acl["peers"]` read by the `agent_acl is not None` branch, `_acl.py:733-832`); the per-agent overlay's L4 guild-routing behavior is byte-unchanged. **The asymmetry is PERMANENT and intended:** account-scope `peers` = DM admission; per-agent `connector_acls.peers` = guild-channel *routing* narrowing (the L4 feature). The agents.md amendment (L2) words the distinction strongly.

### Design Decisions

**Account-scope `peers` axis becomes DM-only (remove from `_admits_inbound_guild`)**
- Choice: Delete the account-scope peers-axis check (the "# 1. Peers axis" block) from `_admits_inbound_guild` (`the_one/connectors/_acl.py`). The peers axis remains in `_admits_inbound_dm` (DM path) unchanged. Guild-channel admission is then gated by the account-scope `channels`/`guilds`/`roles` axes + the per-agent overlay only.
- Rationale: Operator-confirmed the account-scope peers axis is **DM-only by design**; the guild leak is the entire defect. F9 scoped the `resolve()`/`NeedsPairing` hook to DMs only (guild messages stay `Permit`); F10 added `dm_admission` as the DM-admission axis; F12 added per-peer `dm_allowed`. The peers axis was never intended as a channel-participant allowlist.
- Trade-off: loses the (accidental) ability to restrict guild-channel participants via the account-scope `peers` list — which the operator explicitly does NOT want.

**Keep the two-step DM grant — approve endpoint unchanged**
- Choice: `approve_peer_approval` (and the PAIR-prefix success path in `_inbound.py`) keep appending `{id, dm_allowed: False}`. The operator flips the per-peer DM toggle to grant DMs.
- Rationale: Operator-confirmed the two-step is intentional (approve = DM-allowlisted/on-radar; toggle = actually allow). Decoupling the over-restriction (this flight) makes the two-step coherent: after approval the peer can participate in channels immediately, and their DMs are gated until the toggle.
- Trade-off: an approved peer still can't DM until the toggle — by design.

**Preserve the per-agent `connector_acls.peers` overlay (L4)**
- Choice: Touch ONLY the account-scope peers block. The `agent_acl is not None` per-agent narrowing branch in `_admits_inbound_guild` is unchanged.
- Rationale: L4 verified live that the per-agent overlay routes same-channel peers to different agents (a routing feature, not account admission). Account-scope peers = "can this peer DM"; per-agent peers = "which agent serves this peer." The asymmetry is intentional.
- Trade-off: the two peers axes now have different semantics (account = DM admission; per-agent = routing) — documented as an agents.md convention so it doesn't read as inconsistency.

### Prerequisites

- [ ] F15's committed HAT driver (`tests/live/discord_hat/`) available for the optional end-to-end reproduce-gate (it can simulate the post-approval state via the connector PUT helper, then drive a non-listed bot's channel message).
- [ ] The `tests/test_connectors_acl.py` suite (incl. the F12 12-cell DM composition matrix) is the primary regression surface.

### Pre-Flight Checklist

- [x] Open questions resolved (the per-agent-overlay-coherence OQ confirmed at L1 + Architect review)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (unit ACL matrix is the primary gate; optional committed HAT reproduce-gate)
- [x] Legs defined

---

## In-Flight

### Technical Approach

A small, surgical ACL-semantics change with the test corpus as the gate. The fix is ~one block deletion in `_admits_inbound_guild`; the work is in the **test inversions** (tests that currently pin "account peers gates guild channels" must invert to "non-listed peer admitted in guild") + new admit assertions + re-verifying the DM-context matrix and the per-agent overlay are unchanged. Then docs + closing the Known Issue, with an optional end-to-end regression gate via the F15 driver.

### Checkpoints

- [x] L1: account-scope peers removed from the guild path; DM-context + 12-cell `dm_admission` matrices still green; the per-agent overlay's guild behavior unchanged; the inverted/new guild tests green; full backend suite green (2835 passed).
- [x] L2: docs + Known Issue closed; optional committed HAT reproduce-gate shipped (credentials-gated, collects-and-skips clean; non-listed bot's channel message admitted while account `peers` is populated — to be exercised live in the F17 daily-driver run).

### Adaptation Criteria

**Divert if**:
- L1 finds the per-agent overlay shares code with the account-scope peers check such that removing one breaks the other (not expected — they're separate branches). Re-scope to a more careful extraction.
- The Architect review finds the DM-only semantic conflicts with an axis interaction not surfaced here (e.g. `admits_dm_peer` history-read, or the routing engine's `_agent_admits`).

**Acceptable variations**:
- The optional committed HAT reproduce-gate (L2) may be dropped to a unit-only gate if the live-driver setup proves heavy — the `test_connectors_acl.py` RED-before/GREEN-after is the binding gate.

### Legs

> **Note:** Tentative; planned one at a time.

- [x] `peers-dm-only-acl-fix` — **Code:** remove the account-scope peers-axis check (the "# 1. Peers axis" block, `_acl.py:667-676`) from `_admits_inbound_guild`; keep the peers check in `_admits_inbound_dm` unchanged. **Docstring sweep (Architect M2/M3):** update `_admits_inbound_guild`'s own docstring (`_acl.py:629-660`) from "4-axis (peers/channels/guilds/roles)" → **3-axis (channels/guilds/roles)** noting peers moved to the DM helper; update the module docstring's per-axis framing (`_acl.py:8-13,36-49`) + the `admits_dm_peer` docstring (`_acl.py:322-330`) so none implies account peers gates guild. **Tests (`tests/test_connectors_acl.py`):** invert `test_account_peers_subset_denies_non_member` (`:299-303`, guild-context) → admit P2 (the primary RED→GREEN pin); re-comment `test_account_peers_subset_admits_member` (`:293-297`) whose rationale is now wrong; **AND update `test_agent_acl_empty_dict_equivalent_to_none` (`:466-482`)** — its `:476-478` arm (account `peers:["P1"]`, guild, P2→deny) FLIPS to admit; preserve its empty-dict≡None invariant by moving the deny arm to a DM-context assertion (Architect M1). Leave the per-agent `test_both_axes_denied_short_circuits_on_peers` (`:486-498`) untouched (it's the per-agent branch). **Add** a guild-context test: account `peers` non-empty + a non-listed peer → **admitted** when the channels axis permits, **AND** paired with an assertion that a non-listed channel is still **denied** (channels axis still gates — guards the trade-off boundary). **Add** a symmetric DM-context test: a populated account `peers` + a DM from a non-listed peer is still **denied** (peers-DM-only is now account-peers' sole job). **Re-verify unchanged:** the F12 12-cell `dm_admission` matrix (`TestAdmitsInboundDmAdmissionAxis`, `:783+`, all `is_dm=True`); the per-agent overlay's guild-routing (L4). Full backend suite green. *(No tests in `test_connectors_routing.py`/`test_connectors_inbound.py` pin account-peers-gates-guild — Architect-verified.)*
- [x] `reproduce-gate-and-docs` — (a) *(optional, end-to-end regression gate)* a committed `discord_hat` scenario: PUT `allowlist.peers=[<one bot id>]` via the connector helper (simulating post-approval), drive a DIFFERENT bot's **`@mention`** into a channel (mention is REQUIRED so the test exercises the ACL path and isn't masked silent by the policy gate — Architect Q2), assert it is admitted/routed (not `no-eligible`) — RED against the pre-fix substrate, GREEN after. (b) **Docs (Architect H1 — load-bearing):** add an `agents.md` M11 convention (**account-scope-peers-is-DM-only**, with the per-agent-peers-is-routing distinction) AND **amend the existing agents.md sites that encode the old peers-gates-guild invariant** — the five-parallel-axes statement (`agents.md:793`), `per-axis-tri-state-override` (`:112`), and `two-parallel-admission-paths` (`:421`) — to carve out "account-scope peers = DM-admission axis only; guild gating uses channels/guilds/roles + the per-agent overlay." Otherwise a future ACL-touching leg's recon re-derives the now-wrong behavior. Mark the mission Known Issue **resolved** (with fix evidence); add the F9/F10/F12 lineage note.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged (draft PR open; merges after the F17 daily-driver gate / operator review)
- [x] Tests passing (ACL matrix RED-before/GREEN-after; full backend green — 2835 passed; optional HAT gate collects-and-skips clean)
- [x] Documentation updated (agents.md `account-scope-peers-is-DM-only` convention + carve-outs; mission Known Issue marked resolved)

### Verification

- **Primary gate (unit):** `tests/test_connectors_acl.py` — the guild-context peers tests inverted (non-listed peer admitted in guild), a new admit test, and the DM-context + 12-cell `dm_admission` matrices unchanged. RED against the pre-fix substrate, GREEN after. No real-environment observation needed — ACL admission is pure logic, fully unit-testable (no behavior test warranted).
- **Optional end-to-end gate:** a committed `discord_hat` scenario (extends `tests/live/discord_hat/`) that populates account `peers` and confirms a non-listed bot's channel message is admitted — a live regression gate against the exact F15 L7 lock-out.
- **Manual confirm:** the F15 L7 reproduction (approve a human DM, then a non-approved peer's channel message routes normally instead of `no-eligible`).
