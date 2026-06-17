# Leg: ollama-gemma-repro

**Status**: landed
**Flight**: [Recon & Root-Cause Spike](../flight.md)

> **Outcome:** hole #2 (#105) confirmed and characterized against live gemma3:4b.
> Capability gate is CORRECT — Ollama 400s if tools are offered ("does not support
> tools"), so the fix is text-form recovery, not offering tools. Captured the real
> loose format (a ` ```tool ` fenced block with Python-call syntax) to seed Flight
> 3's fixture. Full detail in flight-log Leg Progress + Findings.

## Objective

Reproduce issue #105 (gemma3:4b prints tool calls as text) against the live model,
determine whether the root cause is the capability gate or the parser, and capture
the real text-form tool-call shape for Flight 3.

## Context

- Interactive repro leg; local Ollama only (no credentials). gemma3:4b installed.
- Hypothesis (hole #2 / #105): the model emits tool calls as text that the
  Ollama provider's structured-only parser drops.

## Acceptance Criteria

- [x] `OllamaProvider("gemma3:4b").supports_tools()` evaluated → `False`.
- [x] Determined whether tools can be offered natively → **no**: Ollama 400s
      (`gemma3:4b does not support tools`), so the gate is correct and the fix
      cannot be "offer tools anyway."
- [x] Captured a real text-form tool call from the model (fixture seed for F3):
      ` ```tool\nget_weather(city='Paris')\n``` ` with `tool_calls: null`.
- [x] Root cause recorded: recovery parser is the only viable fix; format is a
      ` ```tool ` fenced block with Python-call syntax (model-specific).
- [x] `git status` clean under `the_one/`.

## Verification Steps

- `/tmp/the-one-spike/ollama_gemma_repro.py` (throwaway) ran the three probes
  (gate / tools-offered / text-form capture); results in flight log.

## Files Affected

- None under `the_one/` (throwaway script in `/tmp`; findings in flight log).

---

## Post-Completion Checklist

- [x] Findings captured in flight log (Leg Progress + Findings)
- [x] Hole #2 confirmed + characterized; Flight 3 direction refined
- [x] Leg status `landed`
- [x] `git status` clean under `the_one/`
