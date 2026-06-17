# Leg: anthropic-thinking-repro

**Status**: landed
**Flight**: [Recon & Root-Cause Spike](../flight.md)

> **Outcome:** hole #1 **corrected, not reproduced** — the dropped-thinking-block
> replay was accepted by Sonnet 4.6 (no API error), and the_one never enables
> thinking in current code. `get_final_message()` does expose signed thinking
> blocks (replay-capture would be low-effort if needed). See flight-log Leg
> Progress + Findings. Flight 2 premise paused for operator re-plan.

## Objective

Reproduce the Anthropic extended-thinking + tool-use failure (hole #1) against the
operator's configured provider, capture the exact error, and determine whether
signed thinking blocks survive `get_final_message()` — settling Flight 2's
effort estimate.

## Context

- Interactive / operator-in-the-loop leg: it makes a **live, paid Anthropic API
  call** on the operator's key. Not run by autonomous agents.
- **Path chosen (operator decision, logged in flight log):** host repro with the
  key from the gitignored `.env`. The configured provider lives in the container's
  `the-one_the_one_data` volume (not host-reachable); since hole #1 is a bug in
  provider *code* (dropped thinking blocks), the credential *source* is immaterial
  to the reproduction. So we build `AnthropicProvider(model=<thinking model>,
  api_key=<from env>)` directly and call `.stream()` — bypassing the agent loop's
  confounds. This sidesteps the DB/encryptor construction entirely.
- **Run under `.venv/bin/python`** (anthropic 0.97.0). Host `python3` has anthropic
  0.79.0, where the thinking-block shapes this leg inspects may differ.
- Root-cause hypothesis (hole #1): the assistant turn's `thinking` blocks (with
  signatures) are dropped (`anthropic_provider.py:188-192`) and never replayed in
  `_to_api_message()` (`:236-244`), so the **follow-up turn** carrying the tool
  result is rejected by the API.

## Inputs

- `ANTHROPIC_API_KEY` in the project's gitignored `.env`, with access to an
  **extended-thinking-capable** model (Opus/Sonnet 4.x). Operator-supplied; never
  printed.
- An explicit thinking-capable model name confirmed by the operator (e.g.
  `claude-sonnet-4-6`).
- Project `.venv` (anthropic 0.97.0) — the repro runs under `.venv/bin/python`.
- Throwaway repro script (lives outside the repo tree — `/tmp`, not committed).

## Outputs

- Captured evidence in the flight log: the **turn-2 API error text** (or, if no
  error, the surprising success), plus a dump of `get_final_message()` block
  types / presence of `signature` / presence of `redacted_thinking` / block
  ordering relative to `tool_use`.
- A determination: is hole #1 confirmed as "dropped thinking blocks on replay,"
  or is the real trigger something else?
- A capture-point verdict: does `get_final_message()` already expose signed
  thinking blocks (→ Flight 2 replay-capture is low-effort additive) — separate
  from whether live-streaming thinking to the UI needs a raw-event refactor.
- No changes under `the_one/` (verify clean `git status`).

## Acceptance Criteria

- [ ] A throwaway repro builds `AnthropicProvider(model=<explicit thinking model>,
      api_key=<from `.env`>)` and runs under `.venv/bin/python` (anthropic 0.97.0).
- [ ] The request enables extended thinking **and removes `temperature`** (so the
      provider's temperature-strip retry at `:162-168` cannot mask the real error).
- [ ] A **two-turn** exchange is driven: turn 1 (offer a tool, model emits
      thinking + `tool_use`) then turn 2 (send tool_result back). The exact
      outcome of turn 2 is captured verbatim.
- [ ] `get_final_message()` from turn 1 is inspected and its block inventory
      recorded: which `block.type`s are present, whether `thinking` blocks carry a
      `signature`, whether any `redacted_thinking` appears, and the thinking↔
      `tool_use` ordering.
- [ ] The flight log records hole #1 as **confirmed** or **corrected**, with the
      capture-point (replay vs. live-display) verdict and a go/no-go for Flight 2.
- [ ] `git status` shows no modifications under `the_one/`.

## Verification Steps

- Inspect the repro script: confirms it takes the key from the env (no hard-coded
  key, never prints it), sets `thinking`, removes `temperature`, drives two turns.
- Run via `set -a; source .env; set +a; .venv/bin/python /tmp/.../repro.py`
  (operator-authorized live call) and read captured output.
- Confirm the flight-log Findings section contains the verbatim turn-2 result and
  the `get_final_message()` block inventory.
- `cd the-one && git status --porcelain the_one/` → empty.

## Implementation Guidance

1. **Build the provider directly from the env key**
   - `AnthropicProvider(model=<explicit thinking model>,
     api_key=os.environ["ANTHROPIC_API_KEY"])`. No DB/encryptor needed on this
     path. Importing `from the_one.llm.anthropic_provider import AnthropicProvider`
     directly is import-safe (avoids the `db.repositories` cold-import cycle).
2. **Enable thinking, drop temperature** in a throwaway way (direct SDK call or
   in-script monkeypatch of `_build_kwargs`) — never edit `the_one/llm/`.
   - `_build_kwargs` (`anthropic_provider.py:90-100`) always sets `temperature` and
     has no `thinking` passthrough, so the script must bypass it.
   - Anthropic thinking shape: `thinking={"type": "enabled", "budget_tokens": N}`
     (budget < max_tokens); omit `temperature` entirely.
3. **Drive two turns through `provider.stream()`**
   - Turn 1: system/user prompt that reliably triggers a tool call, offering one
     simple tool (e.g. a `get_weather`-style stub). Accumulate the streamed
     assistant message; call/inspect `get_final_message()`.
   - Turn 2: append the assistant turn + a `ToolResult` for the emitted call, send
     again. Capture whatever the API returns (success or the exact 400/error).
4. **Record findings** verbatim in the flight log (Findings section). Do not
   sanitize the error — the precise message is the evidence.

## Edge Cases

- **No error on turn 2** → hole #1 may be wrong, OR the configured model/SDK
  version already handles thinking replay. Capture and flag for synthesis; do not
  force a failure.
- **Turn 1 never emits a tool call** → adjust the prompt/tool; a turn with no
  `tool_use` cannot test the thinking+tool replay path.
- **Key can't access the chosen thinking model** (auth/permission error) → halt,
  surface to operator to pick an accessible thinking-capable model. Do not fall
  back to a non-thinking model — that wouldn't reproduce hole #1.
- **`.env` missing the key / empty** → halt with a clear message; do not proceed
  with an unset key.
- **`temperature`-rejection 400 on turn 1** → means temperature wasn't actually
  removed; fix the script, not the provider.

## Files Affected

- None under `the_one/` (throwaway script lives in `/tmp`, captured findings go to
  the flight log).

---

## Post-Completion Checklist

- [ ] Turn-2 outcome + `get_final_message()` block inventory captured in flight log
- [ ] Hole #1 confirmed or corrected; capture-point verdict recorded
- [ ] Go/no-go for Flight 2 noted
- [ ] Leg status set to `landed` (spike legs land; flight commits at the end)
- [ ] `git status` clean under `the_one/`
