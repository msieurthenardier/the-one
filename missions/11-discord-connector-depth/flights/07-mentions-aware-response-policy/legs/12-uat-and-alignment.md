# Leg: uat-and-alignment

**Status**: ready
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Two-phase HAT for the F7 policy gate + LLM-side projection + channel-context tools, against a real Discord test guild: **Phase 1** is an agent-driven Chrome-MCP walk of the gate's decision tree (mechanical), producing a structured pass/fail report + screenshots; **Phase 2** is an operator-driven nuance pass with the agent's report in hand, catching response timing / conversational rhythm / inference judgment quality the mechanical pass can't evaluate. The output is the disposition of F7's behavioral change: shippable to daily-driver use, or remediation needed at a follow-up flight.

## Context

- **Flight DD §12** — two-phase HAT shape. Phase 1 is the methodology precedent that F10's durable HAT script generalizes; Phase 1 here is the seed pattern.
- **Eleven autonomous legs are committed** (`flight/07-mentions-aware-response-policy`, PR #76 draft). Tests: 2615 passed, 4 skipped, 0 regressions.
- **Interactive leg** — no autonomous Developer agent is spawned. The Flight Director (or the operator directly) drives the HAT by walking the steps below one at a time and recording results in the flight log.
- **Mission criteria covered** — #12 (policy gate behavior) + #13 (peer_name LLM-side projection, also covered by F6+F7 L4 combined) + criteria around `fetch_*_history` reachability + `list_visible_channels` enumeration + Studio toggle wiring.
- **Iterative round budget** (per F5 debrief's cumulative-debt-vs-single-feature heuristic) — F7 is single-feature; floor of band is 1-2 mechanical rounds. The multi-mode composition surface (5 gate paths × 2 toggle layers × 4 history tools) is wide enough to expect 2-3 nuance rounds, so total HAT round budget is **2-5**.

## Prerequisites

- [ ] PR #76 (or successor) is mergeable; F7 commit `05a21ce` (or descendant) on the branch.
- [ ] **Discord test guild fixture** — at least 3 distinct users (operator + 2 burners, OR 3 burners), 3+ text channels, 1 thread in one of the channels, ability for the operator's bot to DM at least one user.
- [ ] **the-one running** with the test bot's connector account configured, agent attached, `always_listen` toggle initially OFF (mentioned-only default).
- [ ] **Chrome MCP available** — the operator is logged into Discord in the browser session the agent will drive (or the operator drives the browser directly during Phase 2).
- [ ] **Inference provider configured** — `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` env vars set, OR confirm the fallback path (routed agent's LLM) is acceptable for the inference call.

## Phase 1 — Agent-Driven Mechanical HAT

The Flight Director (or operator) walks the agent through the gate's decision tree using Chrome MCP to drive the Discord web client + observe the operator-console side simultaneously. Each step posts a known input, observes the bot's response (or lack thereof), and captures a pass/fail entry with screenshot.

**Setup steps** (executed once at HAT start):

1. **Verify the bot is online** — open the connector account detail page in Studio; confirm the account is connected (pool warmed); confirm at least one agent is attached.
2. **Verify both toggles default state** — `always_listen` account-level toggle is OFF; per-agent toggles are disabled (greyed-out).
3. **Verify the agent's tool toolkit** — open the agent editor's Tools tab; confirm `fetch_channel_history`, `fetch_thread_history`, `fetch_dm_history`, `list_visible_channels` appear in the enabled tools list.

**Decision-tree walk** (each step: post → observe → record):

4. **DM engagement** — operator (via burner #1) DMs the bot a plain message `"Hello"`. **Expect**: bot replies. **Verify**: operator-console session shows USER + ASSISTANT messages; routing audit entry has `disposition="stepped"`; Chat UI renders peer attribution.

5. **DM + command-intercept** — operator (via burner #1) DMs `/help`. **Expect**: bot replies with help text (command-intercepted, NOT routed to agent). **Verify**: audit entry has `disposition="command-intercepted"` (NOT "stepped" and NOT "policy-silent"). Pins the DD §1-step-ordering invariant.

6. **Mention in channel** — operator posts `@<bot-name> what's the weather?` in a guild channel (account in mentioned-only mode, default). **Expect**: bot replies. **Verify**: audit `disposition="stepped"`; routing scope is whatever the routing rule resolves; the message's USER row has `peer_name` set; the LLM payload (verify via Chat UI showing the agent's reasoning or via API log inspection) carries the `[from {peer_name} in #{channel_name}]: ` prefix.

7. **Non-mention in channel (mentioned-only mode)** — burner #2 posts `"good morning everyone"` in the same channel. **Expect**: bot stays silent. **Verify**: routing audit entry has `disposition="policy-silent"`, `policy.outcome="always-listen-off"`; operator-console Chat UI does NOT show the inbound (silent turns don't broadcast per DD §13); session row's `last_inbound_at` is unchanged.

8. **`/talk_to` override** — burner #1 posts `/talk_to <agent-name> hello agent` in the channel (without mentioning). **Expect**: bot replies (override scope bypasses policy). **Verify**: audit `disposition="stepped"`, routing `scope="override"`.

9. **Toggle `always_listen` ON at account level** — operator clicks the "Always Listen" toggle in the connector account editor; saves. Confirm CustomEvent fires (per-agent toggles in the agent editor become enabled).

10. **Per-agent toggle still OFF** — verify per-agent toggle in the agent's Connectors tab is enabled but defaults unchecked. Non-mentioned messages in step 11 will still be silent.

11. **Non-mention with account ON + agent OFF** — burner #2 posts another plain message. **Expect**: bot stays silent. **Verify**: audit `policy.outcome="always-listen-off"`, `agent_always_listen=False`, `account_always_listen=True`.

12. **Enable per-agent toggle** — operator checks the per-agent "Always Listen on this connector account" toggle for the test agent; saves the agent.

13. **Non-mention with both toggles ON, clearly engaging message** — burner #2 posts `"can someone help me debug a python error?"` (clearly a question the agent can address). **Expect**: bot replies. **Verify**: audit `policy.outcome="inference-yes"`, `inference_provider_id` + `inference_model` recorded.

14. **Non-mention with both toggles ON, clearly skip-worthy message** — burner #2 posts `"lol nice"` (small-talk, not an agent target). **Expect**: bot stays silent (inference bias-toward-no). **Verify**: audit `policy.outcome="inference-no"`.

15. **Borderline messages** (≥3 each) — post a mix of ambiguous messages; observe the inference's call quality. Note any clear false-positives (engaged when shouldn't) or false-negatives (silent when should engage) for the Phase 2 nuance discussion.

16. **Operator-typed steering** — in the agent's Chat UI (operator-only side), type `"next time someone says 'foo', respond with 'bar'"`. Then have burner #2 post `"foo"` in the channel. **Expect**: bot replies with reference to "bar" (inference saw the operator-typed turn in its filtered history per L7's `[operator] ` prefix).

17. **`fetch_channel_history` tool reach** — when the agent engages on a later message, observe whether it calls `fetch_channel_history` to catch up on context it didn't see during silent turns. Verify the tool returns dicts with `peer_id`, `peer_name`, `content`, `ts`, `thread_id`.

18. **`list_visible_channels` tool reach** — manually prompt the agent (via mention) `"what channels do you have access to?"`. Verify the agent calls `list_visible_channels` and returns the expected `peers`/`channels`/`groups`/`roles` shape.

19. **Per-agent ACL gating on fetch** — set the agent's `connector_acls` to restrict to one channel; have the agent attempt to fetch from a non-permitted channel. Verify the tool returns `[{"error": "agent not permitted to read channel X..."}]`.

20. **Multi-channel routing** — with `always_listen` ON in two channels and the same agent attached, exercise the F7 routing rules to confirm the gate's per-channel decision is independent.

**Phase 1 output**:
- A structured pass/fail row per numbered step (table in flight-log.md).
- Screenshots saved locally (NOT committed per user-global "test snapshots not committed" rule); reference them as `evidence/M11-F7-L12-step-N.png` in the flight log for traceability.
- Any anomaly observed gets a row in the flight log's `## Anomalies` section.

## Phase 2 — Operator-Driven Nuance Pass

Operator walks through the same gate paths AND the borderline-message subset from Phase 1 step 15 with their own judgment + a real Discord client. Focus areas the mechanical pass cannot evaluate:

1. **Response timing** — does the bot reply within a conversational latency budget (≤5s for engaged turns)? If inference is slow, daily-driver use will feel sluggish.
2. **Conversational rhythm** — does engaging-the-mentioned-message + staying-silent-on-non-mentioned messages feel natural, or do operators / peers notice the silence?
3. **Inference judgment quality** — review the Phase-1 borderline-message set. Are the inference's yes/no decisions defensible? If many feel wrong, the inference prompt may need iteration (which is an in-leg debrief-time refinement per DD §9's "the leg author may iterate the wording at debrief time").
4. **System prompt clarity** — when the agent does engage, does it act like it understands the policy gate (e.g., naturally referencing recent context via the `fetch_*_history` tools)? Or does it ask the operator for permission anyway (regression of the F8 problem)?
5. **Tool ergonomics** — when the agent uses `fetch_channel_history`, does the dict shape feel useful (or are fields awkward)? Does `list_visible_channels` shape match what the agent reasons about?
6. **UI clarity** — when toggling `always_listen` ON/OFF in the connector editor + per-agent toggle in agent editor, are the controls + their disabled-state composition intuitive?
7. **No-regression check** — for any criteria from M11 mission Verification (cargo from F1-F6) that touch the F7-changed surfaces (auto-relay, post-step bindings, codec round-trip), confirm Phase 2 doesn't observe regressions.

**Phase 2 output**:
- Operator's "shippable for daily-driver use" or "needs remediation" disposition.
- A bulleted nuance-findings list in the flight log.
- If remediation is needed: scoped action items go into the flight log as TODO entries OR into a follow-up maintenance flight per the operator's judgment.

## Acceptance Criteria

- [ ] Setup steps 1-3 pass (bot online; default toggles; tools enabled).
- [ ] Decision-tree walk (steps 4-20) all pass OR pass-with-nuance-noted; any structural failure (e.g., silent branch acquiring the session lock) is logged as a blocking issue and remediated before Phase 2 starts.
- [ ] Phase 1 pass/fail report exists in `flight-log.md` under a `### L12 — uat-and-alignment / Phase 1` section.
- [ ] Phase 2 nuance findings exist in `flight-log.md` under `### L12 — uat-and-alignment / Phase 2`.
- [ ] Operator records a final disposition: **shippable** OR **remediation-scoped**.
- [ ] Mission criteria #12 + #13 marked closed (or partially-closed with caveats) in `missions/11-discord-connector-depth/criterion-coverage.md`.
- [ ] Flight status updated to `landed` in `flight.md`; flight checked off in `mission.md`.

## Verification Steps

(These ARE the implementation; see Phase 1 and Phase 2 above.)

## Implementation Guidance

This is an interactive HAT — no autonomous agent runs it. Flow:

1. **Pre-flight check** — operator confirms all Prerequisites are met (Discord guild + bot online + Chrome MCP available + inference provider configured).
2. **Flight Director (interactive)** walks the operator through Phase 1 setup steps 1-3.
3. **Drive Chrome MCP** to walk decision-tree steps 4-20 one at a time. After each step, record pass/fail + observations in the flight log. If a step reveals a structural issue:
   - Pause Phase 1.
   - Spawn a Developer agent to diagnose + fix the regression in the F7 code.
   - Re-run the failed step until it passes.
   - Resume Phase 1.
4. **Phase 2 handoff** — operator runs Phase 2 themselves with a real Discord client + the Phase 1 report. Records nuance findings.
5. **Disposition** — operator marks the F7 behavioral change as shippable OR remediation-scoped.
6. **Mark leg + flight landed** — set L12 status to `completed`; set flight status to `landed`; check off flight in mission.md.
7. **Commit the artifact updates** (flight log + leg + flight + mission updates).
8. **Mark PR ready for review** — `gh pr ready 76` (or PR-number-equivalent).

## Edge Cases

- **Inference provider not configured** — Phase 1 step 13's `outcome="inference-yes"` cannot fire. The fallback path uses the routed agent's LLM, so test with the agent's own provider; operator notes this in the Phase 1 report.
- **Chrome MCP unavailable** — fall back to operator-driven Phase 1 (slower but workable). Skip the screenshot capture; the operator records text observations.
- **Test guild lacks 3+ users** — single-user shortcuts are noted as caveats; the multi-user routing step 20 may be partially exercised. Operator decides whether to defer those criteria to a follow-up HAT with proper fixture.
- **Borderline messages return unexpected inference decisions** — if many false-positives or false-negatives, the prompt template at `_inference.py:_INFERENCE_PROMPT_TEMPLATE` may need iteration. Per DD §9, this is an acceptable in-leg refinement. The operator decides whether to ship-as-is OR iterate.
- **Discord rate-limits during HAT** — Phase 1's mechanical pace may trip rate limits if walked too fast. Add small delays between steps OR run Phase 1 in chunks.

## Files Affected

- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND Phase 1 + Phase 2 entries under `## Leg Progress`.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg; UPDATE status to `landed`.
- `missions/11-discord-connector-depth/mission.md` — CHECK OFF Flight 7.
- `missions/11-discord-connector-depth/criterion-coverage.md` — UPDATE criteria #12 + #13 closure status.

---

## Post-Completion Checklist

- [ ] Phase 1 walked end-to-end with pass/fail + observations recorded.
- [ ] Phase 2 walked with nuance findings recorded.
- [ ] Operator disposition recorded (shippable / remediation-scoped).
- [ ] Set this leg's status to `completed`.
- [ ] Set flight status to `landed`.
- [ ] Check off flight in mission.md.
- [ ] Update criterion-coverage.md.
- [ ] Commit artifacts.
- [ ] `gh pr ready` to mark PR #76 ready for review.

## Citation Audit

This is an interactive leg with no code citations to verify. References to autonomous-leg artifacts (DD §1, §9, §12, §13) are flight-level design decisions documented in `flight.md`. Operator-side fixture requirements are spelled out in Prerequisites.
