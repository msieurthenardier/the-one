# Leg: hat-and-alignment

**Status**: completed
**Flight**: [Extended thinking follows the model](../flight.md)

## Objective
The operator confirms, on a dev instance with two real Claude models, that one provider serves a model that thinks and a model that does not, that a new provider starts with the switch on, and that the wording is right. It also walks sortie 16's unwalked step 8C (thinking inside the turn's work group).

## Context
- Interactive leg: the operator performs each step; the Flight Director presents one step at a time and records the result. No autonomous implementation.
- A look-and-feel fix found here is fixed inline by a Developer. A request that adds behaviour goes through the fix-vs-feature gate first.
- Contract a HAT change must not move without a deliberate re-author: the switch's id `pf-thinking-enabled`, the stored key `config.thinking_enabled`, and the help-text sentence pinned in `tests/browser/test_flow_provider_editor.py`.

## Inputs
- Branch `sortie/17-thinking-follows-the-model` at `fbb6198a` (draft PR #373).
- A dev instance on port 8485 with the scratch data directory `~/the-one-hat-sortie17/data`, started from `~/the-one-hat-sortie17/cwd` (never port 8484, never the default data directory).
- From the operator: credentials for one Claude provider that reaches a model from version 4.6 on and a model below it (confirmed at design; re-verified in step 1).

## Acceptance Criteria (the walk)

1. **[fresh instance] → [provider form open]**: Library › Add › Model provider, choose the Claude type you will use.
   - The "Extended thinking" switch is shown and already on.
   - The label reads "Extended thinking"; its info button reads: "When on, models that support adaptive thinking (Claude models from version 4.6 on) reason step by step before answering. Older models on this provider answer without it."
   - No error message.
2. **[provider form open] → [provider saved]**: enter the credentials and save without touching the switch.
   - The provider saves and opens; the switch is still on; the editor is not marked unsaved.
   - The model list offers both a 4.6-or-newer model and an older one (the re-verify of the design prerequisite).
3. **[provider saved] → [older-model chat]**: create an agent on the older model (for example Haiku 4.5), start a chat and send a short question.
   - The turn completes with a normal reply.
   - No agent error, no "adaptive thinking is not supported" text.
   - The turn shows no thinking item (a plain reply leaves no work group).
4. **[older-model chat] → [thinking-model chat]**: create an agent on the 4.6-or-newer model, same provider, and send a question that needs reasoning.
   - The turn completes with a reply.
   - The turn has a work group; opening it shows a thinking item with readable text (sortie 16 step 8C).
   - No error message.
5. **[thinking-model chat] → [tool turn]**: in the same chat, ask something that makes it call a tool (for example "what time is it right now?").
   - The work group shows the tool call and thinking; the turn completes (thinking replay across the tool step works).
   - Reload the page and reopen the chat: both turns still show their work groups, and the thinking item is still there.
6. **[switch on] → [switch off]**: open the provider, turn Extended thinking off, save. Start a new chat with the thinking-model agent and ask a reasoning question.
   - The turn completes; no thinking item.
   - Turn the switch back on and save: a new chat thinks again.
7. **[shared state]**: with the switch on, send one more message to the older-model agent's chat from step 3 (a chat that was open before the provider edits).
   - It still completes with no error.
8. **Flight Director check (no operator action)**: the instance's `serve.log` holds no `400` and no "not supported" line for the whole walk, and no "thinking unsupported" warning (the safety net should not have been needed for a model the rule knows).

## Verification Steps
- Steps 1-7: the operator's report at each step.
- Step 8: the Flight Director greps `~/the-one-hat-sortie17/cwd/serve.log`.

## Known limits of this walk
- The retry safety net is not walked with a real model: it only fires for a model id the rule cannot read that also cannot think, and no such real id is known. Its error text is pinned from the real API line recorded in squawk 0361.
- "A stored provider is unchanged" is not walked (a fresh instance has no older provider); it rests on the API and browser tests.

## Files Affected
- None planned. Any fix is recorded in the flight log.

## Citation Audit
- `tests/browser/test_flow_provider_editor.py` - pins the switch id and the help-text sentence - verified at `fbb6198a`
- `sorties/16-turn-work-group/flight-debrief.md` recommendation 4 - step 8C (thinking in the work group) was never walked with a real model - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Walk Results (2026-11-15)

Operator's provider: Claude Plan (OAuth). Through this app the plan answered only for Haiku 4.5; every other model was refused by the plan with a bare `429 rate_limit_error` ("Error").

| Step | Result |
|---|---|
| 1. New provider form: switch on, wording | **Pass** (operator) |
| 2. Save without touching the switch | **Pass** (saved; `POST /api/providers` 201). The model list is the static catalog fallback, so it showed every Claude model, not what the plan allows |
| 3. Older model (Haiku 4.5) with the switch on | **Pass**: normal reply, no error; the log has no 400 and no "not supported" line, so the rule kept the option off the request without the retry. This is squawk 0361's case |
| 4. Thinking model on the same provider | **Not walked**: the plan refused the model (429) |
| 5. Thinking with a tool call, reload | **Not walked**: depends on step 4 |
| 6. Switch off, then on (adapted) | **Pass**: with the switch off the refused model was still refused with the same 429 (so the refusal is the plan's, not a thinking request); Haiku still answered; the switch saved back on |
| 7. The chat open before the provider edits | **Pass** |
| 8. Log check (Flight Director) | **Pass**: no 400, no "not supported", no thinking warning in `serve.log`; three 429s, all on the refused model |

No fix was needed. Steps 4 and 5, and with them sortie 16's step 8C (thinking inside the work group with a real model), remain unwalked.
