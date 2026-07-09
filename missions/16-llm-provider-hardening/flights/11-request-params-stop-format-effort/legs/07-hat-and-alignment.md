# Leg: hat-and-alignment

**Status**: completed
**Flight**: [Request-Param Capabilities (A4)](../flight.md)

## Objective

Guided live HAT confirming the three A4 params behave on a real model, **scoped to
Anthropic this session** (operator has no live OpenAI reasoning key / local Ollama
right now) — plus a live check of the config-wipe fix (save-preserves-config), the
one behavior with no automated coverage.

## Scope & deferral

- **Live this session: Anthropic only.** Effort, structured outputs (json_schema),
  and stop are exercised against a live reasoning-capable Claude model; the L06
  admin `reasoning_effort` field and the save-preserves-config fix are exercised in
  the running Admin UI.
- **Deferred (recorded, not a gap): OpenAI + Ollama live verification.** Their wire
  paths are proven hermetically by the L05 cross-provider conformance matrix
  (config→wire) and per-provider unit tests; live-model confirmation is deferred to
  a future HAT when those environments are available. The two L04 HAT-confirm items
  (Ollama `/v1` effort→`think` translation; `/v1` json_schema-wrapper acceptance)
  remain open and carry to the flight debrief / a future Ollama HAT.

## Preconditions

- Backend running and **built from this branch** (`flight/11-request-params-stop-format-effort`, commit `d5a359d` or later) — the F10 HAT lesson: confirm the running backend's commit before driving.
- A live Anthropic API key and a configured Anthropic provider on a reasoning-capable model (Sonnet 4.6+, Sonnet 5, Opus 4.7/4.8, Fable 5).

## Verification Steps (guided, one at a time)

| # | Action | Expected |
|---|--------|----------|
| 1 | Confirm the running backend is built from this branch/commit. | Backend serves `d5a359d` (or later on this branch). |
| 2 | Open the Admin provider editor for the Anthropic provider. | The **Reasoning Effort** select is present (validates L06 render live); options Provider default / low / medium / high. |
| 3 | Set `response_format` (json_schema) and `stop` on the Anthropic provider via config/env (no UI field, DD6). Then in the Admin UI set Reasoning Effort = `high` and Save. Re-open / re-fetch the provider. | **Save-preserves-config**: `response_format` and `stop` still present after the UI save (the config-wipe fix). Reasoning Effort persisted = high. |
| 4 | With Reasoning Effort = `high`, send a chat message that invites reasoning; then set it to `low` (or default), Save, send a comparable message. | Observable difference — more/less thinking, latency, or thinking-token usage between high and low. |
| 5 | With a JSON `response_format` (json_schema) set, send a message asking for data matching the schema. | Model returns well-formed structured JSON consistent with the schema (provider-native structured output on the wire). |
| 6 | With a `stop` sequence set, send a message whose continuation would contain it. | Generation truncates at the stop sequence. |

_(Steps are performed by the operator and adjudicated live; issues are fixed inline
and the step re-run before proceeding. Empty/subjective observations are noted.)_

## Out of scope

- OpenAI + Ollama live verification (deferred — see Scope & deferral).
- Per-model exotic effort values (`xhigh`/`max`/`minimal`/`none`) — the UI offers
  low/medium/high only (DD6 minimal scope); config/env reach the rest.

---

## Post-Completion Checklist

- [ ] Steps 1–6 adjudicated (pass / issue-fixed / noted)
- [ ] Run outcome recorded in flight-log.md (incl. any inline fixes + the OpenAI/Ollama deferral)
- [ ] Set this leg's status to `completed` (or record disposition if HAT surfaces an accepted issue)
- [ ] Check off this leg in flight.md
- [ ] **Final leg** — after this lands: set flight.md → `landed`, check flight off in mission.md, mark PR ready
- [ ] Commit the HAT record (+ any inline fixes as separate commits — no amend)
