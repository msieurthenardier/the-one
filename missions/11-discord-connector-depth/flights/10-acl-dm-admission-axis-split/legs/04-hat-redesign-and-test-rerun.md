# Leg: hat-redesign-and-test-rerun

**Status**: completed
**Flight**: [ACL DM-admission + channels-axis UI split](../flight.md)

## Objective

Verify F10's UI surface changes (L2 + L3) did not introduce regressions in browser tests beyond what was absorbed inline, then re-design the L5 HAT spec to exercise the new DM-admission flow against a channels-restricted account configuration. L4 is the closing-out leg before the optional L5 operator-driven HAT.

## Context

**Why this leg is thinner than the flight spec anticipated.** The flight artifact's L4 description targeted "browser-test drift cleanup" assuming L2 + L3 would land without absorbing test changes themselves. In practice both legs did absorb inline:
- L2 grew two literal-list assertions in `test_flow_studio_connector_discord_vocabulary.py` by one element each (the new "DM admission" label between peers and channels).
- L3 added 4 new tests and broke no existing ones (186/186 connector + studio + always-listen browser tests passed post-L3).

What's left for L4: a confirmation pass + the HAT redesign for L5. The HAT redesign is the substantive deliverable.

**L5 HAT redesign — what changes from F9's L8 HAT.**

F9's L8 HAT (recorded `partial` at `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/legs/08-hat-pairing-and-detach.md`) exercised the dual-flow against an account with `channels=["1506831630923333722"]` + no `dm_admission` field — step 4 failed because the DM channel id wasn't in the account's channels list.

F10's L5 HAT must add a setup step verifying `dm_admission` is set explicitly, then exercise the same 8 scenarios against a channels-restricted account configuration that NOW works end-to-end. Plus an additional substep verifying the per-agent opt-out (L3).

**L5 leg-artifact authoring.** L4 writes the L5 leg artifact inline (status `ready`). The agentic-workflow's interactive-leg posture (per skill section "Interactive/HAT legs") means L5's "implementation" is the operator-driven walkthrough — the Flight Director guides them through the 8-step spec.

**Mission criterion #8 closure.** L5's successful run flips `mission.md` criterion #8 from `[~]` (partial) to `[x]` (closed). The flight's completion checklist at `flight.md:241-249` requires this.

## Inputs

- F9 L8 leg artifact (`missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/legs/08-hat-pairing-and-detach.md`) — the original 8-step spec to redesign.
- F10 L1, L2, L3 outputs (substrate + UI) — landed in working tree.
- `mission.md` — criterion #8 to update on L5 closure.
- `flight.md:241-249` — completion checklist.

## Outputs

- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/legs/05-hat-acl-split-verify.md` — NEW leg artifact (status `ready`) with the redesigned 8-step + 1-substep HAT spec.
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — append L4 progress entry noting confirmation outcomes + L5 spec authoring.

L4 does NOT touch: production code, browser tests (L2 + L3 absorbed drift inline; verification only), backend tests.

## Acceptance Criteria

- [ ] Verification grep confirms no browser-test slot/axis count assertions need updating beyond what L2 absorbed. Specifically: `grep -rn "data-allowlist-chiplist-slot\|chiplist'\]" tests/browser/` shows only legitimate uses (chiplist-mode tests in `test_flow_studio_connector_allowlist_dropdown.py` lines 173-197, 311-322, 367 — all count by axis name (peers/channels/guilds/roles), not by total slot count).
- [ ] Verification run: `docker exec the-one pytest tests/browser -k "connector or studio or always_listen" -x --timeout 120 -q` passes (excluding the chronic pre-existing `test_studio_section_round_trip_preserves_agent_selection` documented in F1/F4/F5/F6 debriefs).
- [ ] `legs/05-hat-acl-split-verify.md` exists, status `ready`, contains:
  - Prerequisites section listing: L1-L4 landed; app rebuilt; channels-restricted account configured with `dm_admission` set explicitly via L2's UI; 2 burner accounts.
  - 8 main steps mirroring F9 L8's structure but adapted for the new flow (DM-admission setup verification + the actual approval/detach scenarios).
  - 1 substep (5b) verifying the per-agent `admit_dms` opt-out: uncheck the toggle on one attached agent; verify subsequent DMs to that agent do not engage but other attached agents still do.
  - Operator-judged satisfaction gate (matches F9 L8's pattern).
- [ ] L4 flight-log entry documents: verification outcomes; L5 spec drafted and ready for operator-driven run.

## Verification Steps

```bash
# Confirm no outstanding browser-test drift
docker exec the-one bash -lc 'grep -rn "data-allowlist-chiplist-slot\|chiplist\\\"\\\]" tests/browser/ 2>/dev/null'

# Run the connector + studio + always-listen suite (regression net)
docker exec the-one pytest tests/browser -k "connector or studio or always_listen" -x --timeout 120 -q

# Full backend (post-L3 baseline: 2733)
docker exec the-one pytest --timeout 60 -q
```

Expected: tests pass; backend count unchanged.

## Implementation Guidance

### Sub-step A — Drift verification pass

Run the verification commands above. If any unexpected failure surfaces (beyond the pre-existing `test_studio_section_round_trip_preserves_agent_selection` flake noted across multiple flight debriefs), document in the flight-log and either fix inline (if <20 LOC) or escalate to the Flight Director.

Expected outcome (per L2 + L3 reports): green. No new fixes needed.

### Sub-step B — Author the L5 HAT leg artifact

Create `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/legs/05-hat-acl-split-verify.md`. Use this template:

```markdown
# Leg: hat-acl-split-verify

**Status**: ready
**Flight**: [ACL DM-admission + channels-axis UI split](../flight.md)

## Objective

Operator-driven HAT verifying F10's substrate + UI close the F9 L8 gaps end-to-end. Run against a channels-restricted account configured with `dm_admission` set explicitly via L2's selector. Closes mission criterion #8 on operator-judged satisfaction.

## Prerequisites

- F10 L1, L2, L3 landed and committed (or staged for Phase 2d batch — Flight Director's call).
- App rebuilt: `make rebuild`. Verify the app serves L2's new "DM admission" row by loading the connector account detail page and confirming the selector renders.
- One Discord connector account configured with:
  - `config.allowlist.channels = [<one specific guild channel id>]` — the restrictive setup that broke F9 L8 step 4.
  - `config.allowlist.dm_admission = "allowlisted-peers-only"` — the F10 flow's target state. Set via L2's UI selector OR via direct API.
  - At least 2 attached agents, both with default `admit_dms` (inherit; checkbox checked).
- Two unpaired burner Discord accounts (B1, B2) NOT in `account.config.allowlist.peers`.
- The bot is invited to the test guild; burners can DM the bot.

## Steps

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | From burner **B1**, open a DM to the bot. Send "hello bot". | The bot does NOT reply on Discord. In the operator Chat UI, a `pending-approval` banner appears (F9 L4 surface). |
| 2 | Inspect the banner: B1's display name, preview, timestamp, Approve button, Dismiss link. | All four present. |
| 3 | Click **Approve**. | Buttons replaced with `approved` badge. Navigate to Studio → Connectors → account detail → Allowlist: B1's id is in `peers`. **Crucially:** channels list is UNCHANGED (still the one guild channel from setup). |
| 4 | From B1, send another DM: "are you there now?". | **This is the F9 L8 regression-fix gate.** The agent engages this time — bot replies on Discord; operator Chat UI shows the exchange with peer-name attribution. F10's `dm_admission` gate consults the new axis (not the channels axis) for DMs. |
| 5 | Navigate to connector account detail → Attached Agents. Click **Detach** on one of the attached agents. | The row updates without page reload; the detached agent disappears from the list. The Connectors grid tile's agent-count badge decrements. |
| 5b | **NEW: per-agent `admit_dms` opt-out.** Navigate to a still-attached agent → Connectors tab → expand the account's ACL section. Uncheck "Admit DMs from this account". Save. From B1, send another DM. | The opted-out agent does NOT engage. Other still-attached agents on the same connector still do engage (verify by sending a follow-up DM and observing which agent replies). Verify via API: `GET /api/agents/{name}` shows `connector_acls[acct].admit_dms == false`. |
| 6 | From a user in a guild channel where the detached agent was previously responding, send a message mentioning the bot. | The detached agent does NOT respond. Other still-attached agents may. |
| 7 | From burner **B2** (different from B1), send a DM with `PAIR <code> hello` where `<code>` is the account's current pairing code (Studio Pairing section). | The bot accepts the pairing; B2 is added to the allowlist via the text-prefix path. The agent processes "hello" content (replies per agent logic). |
| 8 | Verify the chat session audit log shows the two pairing paths: B1 was paired via the Discord-native flow (`reason: "pending_approval"` then `permit`); B2 via the text-prefix flow (`reason: "paired"`). | Both flows are observable in the audit trail. The allowlist now contains B1, B2, and any pre-existing peers. **Channels list still unchanged from setup.** |

## Inline-Hotfix-During-HAT Discipline

If any step fails, fix inline if <80 LOC across <3 files (F7 L12 / F9 L8 precedent). Otherwise divert to a follow-on leg.

## Operator-Judged Satisfaction

L5 lands when all 8 steps + 5b pass AND the operator's judgment is "shippable" — the dual-flow + axis-split UX feels right end-to-end.

## Mission Criterion #8

On L5 land: update `mission.md` criterion #8 from `[~]` to `[x]` (full closure). The substrate + UI gap that F9 L8 partial-closed is now fully resolved.
```

### Sub-step C — Flight log

Append to `flight-log.md`:

```
### {date} — L4 hat-redesign-and-test-rerun (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- Verification pass confirmed no outstanding browser-test drift beyond what L2 absorbed inline. 186/186 connector + studio + always-listen tests pass (the single chronic `test_studio_section_round_trip_preserves_agent_selection` flake is pre-existing).
- L5 HAT leg artifact authored at `legs/05-hat-acl-split-verify.md` (status `ready`). 8 main steps + 1 substep (5b) covering the F9 L8 redesign + the new per-agent `admit_dms` verification.

**Test outcomes**: backend suite unchanged (2733 + 13 pre-existing errors); browser regression net green.

**Anomalies**: {document any}
```

## Edge Cases

- **Browser-test drift surface elsewhere** (e.g. a test counting axis labels by total): the grep + run combo at Sub-step A should surface it. If a failing test emerges that L4 should fix inline rather than leave for the operator's HAT to catch, do so.
- **L5 HAT spec word-smithing**: the operator may want different step wording / ordering. The L4-authored spec is `ready` for the operator's review at HAT-run time; tweaks land at L5 (not at L4 re-cycle).
- **Mission criterion #8 update timing**: the update lives in L5's land path, NOT in L4. L4 documents the intent in the L5 spec.

## Files Affected

- NEW: `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/legs/05-hat-acl-split-verify.md` (~150 LOC, the HAT step table + prerequisites + satisfaction gate).
- `missions/11-discord-connector-depth/flights/10-acl-dm-admission-axis-split/flight-log.md` — L4 entry.

Estimated total: ~150 LOC of documentation; no production code changes.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] Drift verification ran; outcome documented
- [ ] L5 leg artifact created at the right path with the redesigned HAT spec
- [ ] Update flight-log.md with L4 progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

3 citations verified against current code at leg design time:
- `tests/browser/test_flow_studio_connector_allowlist_dropdown.py:173-197, 311-322, 367` — chiplist slot assertions; verified count-by-axis-name not by total-count.
- F9 L8 leg artifact path — exists.
- F10 mission criterion #8 in `mission.md` — exists with `[~]` partial marker.
