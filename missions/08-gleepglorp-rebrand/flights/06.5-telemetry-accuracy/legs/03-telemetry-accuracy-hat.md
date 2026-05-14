# Leg: telemetry-accuracy-hat

**Status**: completed
**Flight**: [Telemetry Accuracy](../flight.md)

## Objective

Operator HAT validating that L01's per-model `max_context_tokens` resolution and L02's `input_tokens` validation harness deliver accurate telemetry across the operator's real providers. Categorize the F6 KI #2 Ollama-undercount root cause (Ollama-side qwen-specific vs Ollama-wide vs ours).

This is a HAT leg — Flight Director walks operator through each scenario one at a time. Inline fixes happen during the cycle if defects surface.

## Context

L01 + L02 committed to flight branch at the HAT-cycle start; draft PR #53 open. Broad pytest 1669p/4s/374d and browser suite 315p/35s — both preserved at L02-landed state. L02 anomaly: Ollama test passed against the operator's default-selected model in the no-env-vars run — this HAT explicitly targets `qwen2.5:7b` via `LIVE_OLLAMA_MODEL` to reproduce the F6 bug-report scenario.

## HAT Scenarios

### Scenario 1: Ollama resolver against qwen model (real-vs-fake denominator)

1. Confirm an Ollama agent in Studio using `qwen2.5:7b` (or the operator's qwen model variant). Note the configured model name.
2. Open chat with that agent; send a short message; observe the telemetry overlay percent.
3. **Expected**: percent reflects context fill against the model's REAL window (e.g., 32k for qwen2.5:7b's 32768 actual context). Pre-F6.5, it would have been against 128k — so a turn that's truly 7k tokens would have shown ~5%; post-L01 it should show ~22%.
4. **Decision points**:
   - If percent matches expected proportions for the real window → L01 resolution is working for Ollama. Pass.
   - If percent still reflects 128k denominator → L01 resolver may have failed silently. Check container logs for "max_context_tokens resolution failed" debug message; verify `/api/show` is reachable from the container.

### Scenario 2: L02 harness against qwen2.5:7b (Ollama undercount categorization)

1. Confirm the operator's Ollama has `qwen2.5:7b` loaded: `docker exec the-one curl -s http://host.docker.internal:11434/api/tags | jq '.models[].name'`
2. Run the L02 harness specifically against qwen: `docker exec -e LIVE_OLLAMA_MODEL=qwen2.5:7b the-one pytest -m live tests/test_input_tokens_cross_provider_live.py::test_ollama_input_tokens_monotonic -v`
3. **Expected**: if F6 KI #2 reproduces, the test FAILS with the 3-turn token-count sequence showing flat or near-flat counts. If it PASSES (monotonic growth), the L02-default-model anomaly was the actual reading — qwen2.5:7b reports correctly too, and the F6 observation was perhaps a misread or a transient issue.
4. **Decision points**:
   - Test FAILS with flat counts → confirms F6 KI #2 is qwen-side (or our request shape). Run against a different Ollama model (e.g., `LIVE_OLLAMA_MODEL=llama3.2:3b` if available) to localize. If llama PASSES + qwen FAILS, it's qwen-specific tokenizer behavior. Document and close as external Ollama / qwen-side KI.
   - Test PASSES → F6 KI #2 was a transient or misread; close the KI with the L01 fix (denominator) doing the heavy lifting. Note for posterity in the flight log.

### Scenario 3: At least one non-Ollama provider validation

1. Run the L02 harness against whichever provider(s) the operator has credentials for:
   ```bash
   docker exec -e OPENAI_API_KEY=... the-one pytest -m live tests/test_input_tokens_cross_provider_live.py::test_openai_input_tokens_monotonic -v
   # or anthropic / openrouter equivalent
   ```
2. **Expected**: monotonic input_tokens growth across the 3 turns.
3. Cross-validates that the harness itself isn't broken — if non-Ollama providers all show growth, the harness is sound and any Ollama-side flat reading is the bug it's catching.

### Scenario 4: Telemetry warn/crit thresholds against real model

1. With the qwen agent from Scenario 1, send turns until context fill crosses 70%.
2. Verify the `.t-ctx-pct` percent text turns to `--status-warning` (orange).
3. Continue until 90%+ — verify it turns to `--status-danger` (red).
4. **Expected**: warn/crit fires at the REAL thresholds because L01 fixed the denominator. Pre-F6.5, you'd never hit these (128k denominator wouldn't fill in normal use).
5. **Decision point**: if warn/crit doesn't trigger even at perceived high fill, telemetry may still have an upstream bug (mid-stream emission, or per-step usage reporting). Log as F7 carry-forward.

### Scenario 5: Per-agent override (KI #9 re-evaluation)

1. Did Scenarios 1-3 reveal a model in the operator's setup that L01 doesn't cover? (i.e., resolver fell back to class default for a model the operator actually uses.)
2. **Decision point**:
   - YES → spawn an inline L04 to add a per-agent `max_context_tokens` override field in the Studio Agent editor.
   - NO → carry forward to F7 / future flight; close KI #9 as not needed now.

### Scenario 6: Broad + browser + pixel suite regression smoke

1. `docker exec the-one pytest -x --timeout 30` — exit 0, 1669p/4s/374d
2. `docker exec the-one pytest -m browser --timeout 60 --tb=line` — 315p/35s
3. `docker exec the-one pytest -m pixel --timeout 60` — 12/12 (no visual changes expected; no baseline regen needed)

## Acceptance Criteria

- [ ] Scenario 1: Ollama resolver verified against qwen — telemetry shows real-window-based percent
- [ ] Scenario 2: L02 harness against qwen2.5:7b run — Ollama undercount root cause categorized
- [ ] Scenario 3: At least one non-Ollama provider validated through the harness
- [ ] Scenario 4: warn/crit thresholds fire correctly at real-fill percentages
- [ ] Scenario 5: per-agent override decision (spawn L04 or carry forward)
- [ ] Scenario 6: broad/browser/pixel suites all preserved
- [ ] All HAT findings recorded in flight-log
- [ ] F6 KI #1 (max_context_tokens hardcoded) marked RESOLVED in mission.md
- [ ] F6 KI #2 (Ollama prompt_tokens undercount) categorized + dispositioned in mission.md

---

## Post-Completion Checklist

- [ ] All scenarios resolved
- [ ] flight-log.md updated with HAT findings + Ollama-undercount disposition
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg + flight in artifacts
- [ ] Mission KIs #1 and #2 closed (or carried forward with documented next step)
- [ ] Flight.md status → `landed`
- [ ] PR #53 → ready for review
- [ ] `[COMPLETE:flight]` signal

---

## Citation Audit

3 source-code citations verified against current code at leg design time (post-L01/L02 uncommitted state):
- `the_one/llm/base.py:_resolve_max_context_tokens_if_needed` — debug-log message ("max_context_tokens resolution failed") referenced in Scenario 1 — OK
- `tests/test_input_tokens_cross_provider_live.py` — operator-runnable harness — OK
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — warn/crit class application for `.t-ctx-pct` — OK (from F6 L04)
