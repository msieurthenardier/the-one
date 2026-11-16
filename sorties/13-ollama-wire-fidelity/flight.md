# Sortie: Ollama wire fidelity

**Status**: aborted

> **Aborted on 2026-11-16, before flight design.** The precondition run showed no gain: 199/240 as shipped against 198/240 with the corrected wire, on `qwen3:4b-thinking` at n=20. The charter below is kept as written. See the [flight log](flight-log.md), "2026-11-16, precondition run and abort".

## Charter

### Outcome
Reasoning models on Ollama keep their reasoning across the tool steps of a turn and sample with their own Modelfile settings instead of a forced temperature 0.

### Why Now
The 2026-11-05 local-LLM benchmark found three gaps in the Ollama native wire:
- **Reasoning is dropped.** `OllamaProvider._stream_native` and `_complete_native` never read `message.thinking`, and `_to_native_message` never sends it back. A reasoning model (`qwen3:4b-thinking`, `lfm3:1.7b`, `gpt-oss:20b`) therefore loses its reasoning on every tool step within a turn. Transcripts show 500 to 2000 reasoning tokens per step discarded.
- **Sampling is forced.** `temperature` defaults to `0.0` (`the_one/llm/ollama_provider.py`, the `complete`/`stream` signatures and `_native_options`), and the agent loop never overrides it. That overrides each model's own sampling (`qwen3` instruct 0.7, thinking 0.6, `lfm3` 0.1) against vendor guidance.
- **Tool results carry no `tool_name`.** This was a no-op for the three templates tested.

It was offered as a squawk and failed qualification (`sorties/11-tool-exposure-for-small-models/flight-log.md`, Decisions, "Ollama wire findings kept out of this sortie"):
- capturing reasoning fills `Message.thinking`, which `the_one/db/codec.py` persists and the web app broadcasts as a `thinking` event;
- the sampling change affects every Ollama agent;
- the benefit was unproven: neutral on `qwen3:4b-instruct` and `lfm3:1.7b` at n=20, and a small n=5 gain on `qwen3:4b-thinking`.

The sortie 11 debrief named it as recommendation 5.

### Precondition
An n=20 A-vs-B comparison on `qwen3:4b-thinking` (A as shipped, B with the corrected wire) shows a gain on the s11 scenario set. If it shows none, abort the sortie before flight design and record why.

### Success Criteria
- [ ] Within a turn, a reasoning model's reasoning from each tool step is passed back to Ollama on the next step.
- [ ] The operator has decided how captured reasoning is stored and shown (persisted and displayed like Anthropic thinking, or kept in memory for the turn only), and the implementation follows that decision.
- [ ] An Ollama agent's sampling follows the model's own settings unless something sets it explicitly. The evals keep a pinned, recorded sampling setting, so their comparisons stay reproducible.
- [ ] No gate failure on the s11 compare for `qwen3-4b`, `lfm3` and `haiku`, and the A-vs-B gain holds at n=20 on `qwen3:4b-thinking`.

### Constraints
- No change to the frozen `the_one/agent/core.py` without the owner's approval.
- Eval baselines are recorded before the change, so the comparison is same-prompt.
- Do not upgrade Ollama or re-pull eval models during the sortie.
- Out of scope: the claimed-action work (sortie 12) and Anthropic prompt caching (sortie 14).

---

## Pre-Flight

*(Flight design never started. The precondition was not met and the sortie was aborted.)*

### Evidence
The benchmark arms, all gitignored: `evals/runs/bench-layer`, `bench-confirm` and `bench-arms`. The bench driver is in the sortie 11 session scratchpad and is not in the repo. Bring it in or rebuild it as part of the precondition run.
