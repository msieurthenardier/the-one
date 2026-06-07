# Leg: model-selection-guidance

**Status**: completed
**Flight**: [Agent-Selectable Execution Isolation (Boxed Mode)](../flight.md)

## Objective

Teach the model the box-by-default / `host_access`-to-escalate contract: refine the
`shell` / `python_exec` / `shell_session_start` tool descriptions + the `host_access`
parameter descriptions, and add one concise reinforcing principle to `BASE_PROMPT`, so the
agent escalates out of the box only when a task genuinely needs the user's real files or
network and otherwise stays isolated.

## Context

- **DD1 behavior shift**: box-by-default flipped the experienced default (legs 3–4). The
  agent now needs guidance on WHEN to set `host_access=true`, or it will either
  under-escalate (boxed when it needed host files → task fails) or over-escalate (always
  host_access=true → box never used). This leg supplies that guidance; leg 6's
  selection-decision behavior checkpoints verify it on unambiguous tasks.
- `BASE_PROMPT` (`agent/config.py:9-51`) explicitly tells the model: *"Tool descriptions
  tell you what each tool does and when it applies. Read them."* → the per-tool description
  is the canonical surface for the selection contract; a single BASE_PROMPT line reinforces
  the principle without always-on bloat.
- Legs 3–4 added `host_access` to the three tools' schemas with a minimal placeholder
  description — this leg writes the real guidance.
- This is a **prose/guidance leg — no enforcement code**. No `@requires_bwrap` needed.

## The selection contract (the guidance to encode)

- **Default is an isolated box**: a fresh disposable workspace with **no access to the
  user's files or network** and a working language/shell runtime. Safe for running or
  evaluating untrusted / self-generated / experimental code, computation, parsing, scratch
  work.
- **Set `host_access=true` ONLY when the task genuinely needs the user's real files or the
  network** — e.g. "read/edit files in my project", "fetch this URL", "use my installed
  data/tools". When in doubt, stay boxed; escalate only on a concrete need for host
  resources.
- **Boxed sessions persist** their scratch across `shell_session_send`s (install-then-use
  works); **boxed one-shot calls have no cross-call state** (each is a fresh box). If a
  multi-step boxed workflow needs continuity, use a `shell_session_*` session.

## Acceptance Criteria

- [x] `shell`, `python_exec`, and `shell_session_start` tool `description` strings convey the
      box-by-default default + the "escalate with `host_access=true` only for real
      files/network" contract (concise — a sentence or two each; don't bloat).
- [x] The `host_access` parameter `description` in all three schemas states: default false
      (isolated box, no host files/network); set true only when the task needs the user's
      actual files or network.
- [x] `BASE_PROMPT` gains **one** concise principle line (in the "Tool use" area) reinforcing
      least-privilege execution: default to the isolated box; escalate to host access only on
      a concrete need. (Keep it short — BASE_PROMPT is always present.)
- [x] Descriptions are accurate to the implemented behavior (boxed = no user FS/network +
      fresh scratch; one-shot ephemeral; session persistent) — no over-claim.
- [x] A lightweight test asserts the composed surfaces carry the contract: the three tool
      descriptions + `host_access` param text mention isolation/host_access; `compose_system_prompt`
      output contains the BASE_PROMPT principle. (Assert on substrings, not exact wording.)
- [x] **Update the exact-equality prompt test (design-review)**: `tests/test_factory.py`
      `TestConnectorSystemPrompt::test_non_connector_uses_base_prompt` (~`:603`) asserts
      `agent.system_prompt == BASE_PROMPT` (exact) — change it to
      `agent.system_prompt.startswith(BASE_PROMPT)` (resilient to future BASE_PROMPT
      additions). `test_config.py:221` (`compose_system_prompt(BASE_PROMPT, "") == BASE_PROMPT`)
      stays valid (binds BASE_PROMPT at call time) — confirm it still passes.
- [x] Full default suite + ruff green. No behavior/enforcement change.

## Verification Steps

- `docker exec the-one python -m pytest tests/test_agent_config.py tests/test_tools.py -k "prompt or description or host_access" --timeout 60 -q` (or the relevant test homes) — green.
- `docker exec the-one python -m pytest --timeout 60 -m "not requires_bwrap" -q` — no regressions.
- Eyeball: introspect the tool schemas (`GET /api/tools` or `BuiltinToolProvider().get_tools()`) — `host_access` present with the real description on all three tools.
- `docker exec the-one ruff check the_one/ tests/ && docker exec the-one ruff format --check the_one/tools/shell.py the_one/tools/python_exec.py the_one/tools/sessions.py the_one/agent/config.py`.

## Implementation Guidance

1. **Tool descriptions** (`shell.py:25`, `python_exec.py` desc, `sessions.py:84`): append the
   box-by-default contract. Keep each addition to ~1-2 sentences. Example shape for `shell`:
   *"Runs in an isolated box by default (no access to your files or the network; a fresh
   scratch workspace). Set `host_access=true` only when the command needs your real files or
   network access."* Tailor for `python_exec` (computation/untrusted code → stay boxed) and
   `shell_session_start` (note the boxed session's scratch persists across sends).
2. **`host_access` param description** in the three `parameters` dicts: **refine** the
   existing leg-3/4 description (legs 3-4 landed a real-but-sparse description, not a blank)
   to the full contract (default false = isolated box, no host files/network; true only for
   real files/network). Test homes for the substring assertions: `tests/test_config.py`
   (BASE_PROMPT/compose) + `tests/test_execution_tools.py` / `tests/test_session_tools.py`
   (tool descriptions) — do NOT create a new `test_agent_config.py`.
3. **BASE_PROMPT** (`agent/config.py`): add one line under "Tool use" (near the
   "Prefer the right tool" bullet), e.g. *"Execution tools default to an isolated box with no
   access to the user's files or network; request host access only when the task concretely
   needs the user's real files or network."* One sentence — do not expand into a paragraph.
4. Keep wording consistent across all four surfaces (same "isolated box" / "host access"
   vocabulary) so the model sees a coherent contract.

## Edge Cases

- **Over-claiming**: don't describe protections the implementation doesn't provide (e.g.
  don't claim "no network" if `ExecutionConfig.sandbox_network_allowed` could re-enable it in
  host mode — the box specifically is always network-off; host mode follows the config).
  Word the boxed claim precisely.
- **Don't make `host_access` sound dangerous/forbidden** — it's a legitimate, common choice
  (most "work on my project" tasks need it). The guidance is "escalate on real need," not
  "avoid escalating."
- **BASE_PROMPT length**: it's prepended to every agent; one sentence only.

## Files Affected

- `the_one/tools/shell.py` — description + `host_access` param description.
- `the_one/tools/python_exec.py` — description + `host_access` param description.
- `the_one/tools/sessions.py` — `shell_session_start` description + `host_access` param description.
- `the_one/agent/config.py` — one BASE_PROMPT principle line.
- A test (`tests/test_agent_config.py` / tool-schema test) asserting the contract surfaces.

---

## Post-Completion Checklist

> **Batched-commit flight**: implement, update the flight log, set leg status to `landed`,
> signal `[HANDOFF:review-needed]`. No commit here.

- [x] All acceptance criteria verified (contract on all four surfaces; accurate; lightweight test)
- [x] Full suite + ruff green; no enforcement/behavior change
- [x] Update flight-log.md with this leg's progress entry
- [x] Set this leg's status to `landed` (NOT `completed`)
- [x] Do NOT commit; do NOT check off the leg in flight.md
