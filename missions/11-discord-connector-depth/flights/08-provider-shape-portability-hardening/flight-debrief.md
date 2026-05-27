# Flight Debrief: Provider-Shape-Portability Hardening

**Date**: 2026-05-26
**Flight**: [Provider-Shape-Portability Hardening](flight.md)
**Status**: landed
**Duration**: 2026-05-26 (single-session planning + execution + commit + merge)
**Legs Completed**: 3 of 3 autonomous (L1, L2, L3); L4 (conditional HAT) retired during execution per L1's no-gap outcome.

## Outcome Assessment

### Objectives Achieved

F8 closed F7 debrief Recommendation #1 in its entirety. The surgical hotfixes (12.l Anthropic coercion, 12.m telemetry projection) and the partially-audited invariants (Message.content ASSISTANT/SYSTEM branches, mask-shape constant duplication) became structurally enforced guarantees:

- **`ToolResult.content`** now widened to `str | dict | list[Any]` with `__post_init__` JSON-normalization at construction (`the_one/llm/base.py:28-55`). The agent loop at `the_one/agent/core.py:336` wraps tool returns into `ToolResult(content=output)` where `output` may be `list[dict]` from L10 channel-context tools; normalization at construction means every downstream consumer (4 providers, codec, telemetry, CLI) reads `str` uniformly. The F7 12.l Anthropic coercion at `anthropic_provider.py:219-249` was deleted (~25 LOC removed); `import json` removed from that file.
- **`Message.content`** now has `__post_init__` `assert isinstance(self.content, str)` (`the_one/llm/base.py:121-137`). Asymmetric semantic (assert vs normalize) by deliberate design — a non-str on a Message means a provider-parser defect we want surfaced.
- **Cross-provider canonical-format portability** pinned by `tests/test_llm_provider_cross_provider_history.py` (~620 LOC, 9 pure-encoder tests + 5 live-marked tests for Anthropic↔Ollama qwen + Anthropic↔OpenRouter `google/gemma-4-26b-a4b-it:free`). **L1 surfaced no gap** — the canonical Message shape was already portable; F7-debrief's "task #25" concern was overstated at the encoder level.
- **Mask-shape duplication** in `the_one/interfaces/web/api.py` unified via shared constants (`_MASK_PREFIX`, `_MASK_TAIL_SEPARATOR`, `_MASK_TAIL_LEN`) plus `_emit_mask` helper. Regex rebuilt from `re.escape(constants)` — rendered pattern byte-identical to pre-L3 literal (pinned by regression test `test_rendered_regex_matches_pre_l3_literal`).
- **Two new conventions** codified in `the_one/agents.md`: `provider-shape-portability` (L2, line 134) and `single-source-of-truth-for-paired-helpers` (L3, line 153). Mutually cross-referenced; aligned with existing convention style.

### Mission Criteria Advanced

- **#19** (full working-day daily-driver run) — indirectly supported. Provider-shape invariants reduce the probability of a latent shape-loss surfacing during long-running sessions that swap models or accumulate tool calls across many turns. The encoder-level cross-provider invariant is now structurally enforced rather than convention-only; the operational benefit accrues to any future daily-driver run.
- F8 does not close any criterion directly (substrate hardening flight); F7 action item *"Open a M11 follow-up flight artifact for provider-shape-portability hardening"* is closed.

## What Went Well

**The asymmetric `__post_init__` pattern (normalize vs assert) paid off by surfacing dead code via type-system invariants.** `tests/test_connectors_inference.py::test_run_engagement_inference_returns_false_on_none_content` deliberately constructed `Message(role=Role.ASSISTANT, content=None)` to pin a defensive branch in `run_engagement_inference`. Under L2's assert, that construction crashes at `__init__`. The test was deleted; the defensive branch in `run_engagement_inference` becomes dead code (noted for a future maintenance-flight cleanup). A *normalize* semantic would have silently coerced `None` to `"None"` and hidden the dead branch indefinitely. The architect framing — "ToolResult normalizes because structured returns are legitimate; Message asserts because non-str is a parser defect" — was the right asymmetry.

**Test-first atomic L1 with bounded divert threshold was the right shape for substrate verification.** Without the test, the "task #25 concern" framing from F7 debrief Rec #1(d) would have stayed a vague worry. With the test, L1 ships clean (no gap) and the canonical Message shape is now empirically confirmed portable. Even though the ~80 LOC divert threshold wasn't exercised, having it pre-committed at Phase 5b meant the operator didn't have to make a "expand vs split" call mid-leg. The substrate flight's null-result is also a result — "test passed from the start" earns the same regression-net value as "test caught a gap and fix landed."

**The L2+L3 collapse held at the production-code level even when the test-rewrite scope stretched.** Predicted ~30 LOC production + ~20 LOC of test; shipped ~30 LOC production + ~280 LOC of test rewrites (collapse from 8 deleted + 17 new tests). The production-code budget was accurate; the test surface was wider because Message and ToolResult share a thematic anchor and each invariant boundary earned its own regression net. One commit, one review pass, two related invariants — the collapse rationale held.

**L3's separation from L2 paid off for review-surface cleanliness.** L3's diff is reviewable independently from L2 at the file level (`api.py` vs `base.py`); `single-source-of-truth-for-paired-helpers` lands as its own convention citation rather than sharing a paragraph with `provider-shape-portability`. The leg-level discipline cost ~0 — one extra Phase 2 cycle, no extra commit because the agentic-workflow batched.

**The HAT conditional planning shape was correct.** L4 retirement at execution time was clean: "L1 surfaced no gap, no fix shipped, L4 retired per F8 conditional plan." Pre-committing HAT would have been waste (no fix to verify); pre-dropping HAT would have been over-confident given the recon's "real concern, needs test" framing. The conditional shape is the right answer for any substrate-hardening flight where the test outcome determines whether end-to-end verification has anything to verify.

**The cycle-1 design-review caught real high-severity issues in both L1 and L2.** L1 cycle-1 caught three high-severity issues (wrong Ollama host inside container, wrong skip-marker, wrong test command). L2 cycle-1 caught one high-severity issue (the `Message(content=None)` test in `test_connectors_inference.py`). All four catches were recoverable with mechanical fixes applied in the same cycle; without the review, all four would have surfaced at first `make test-unit` run and would have caused re-spin loops. The review system paid for itself.

**The new agents.md conventions are well-scoped, cross-referenced, and aligned with existing style.** Both new conventions (`provider-shape-portability` at line 134, `single-source-of-truth-for-paired-helpers` at line 153) use the established bolded-section headers (Convention / Mechanism / Source / When this matters / Anti-pattern), include concrete file:line citations to pinning tests, and explicitly cross-reference each other plus the existing `cross-subsystem-pattern-premise-revalidation` (line 122). The anti-pattern paragraphs are unusually load-bearing — they name the precise way to bypass each invariant (post-construction direct field assignment for the dataclass shape; copy-pasted hardcoded literals for the paired-helpers).

## What Could Be Improved

### Process

- **L1 design-review's three high-severity catches all shared a single root shape**: importing patterns from outside the codebase without checking the project's installed conventions. The Ollama host (container `localhost` vs `host.docker.internal:11434`), the unregistered `@pytest.mark.integration` marker, and the wrong test command (`pytest tests/` vs `make test-unit`) are all instances of the same mistake. The fix at design time was mechanical (read `tests/test_input_tokens_cross_provider_live.py:143-260` as the canonical live-test reference), but the root cause is a leg-design blind spot. A line in the `/leg` template like "Before writing live/integration tests, identify the project's existing live-test convention file and mirror its skip-marker, host-discovery, and cleanup patterns" would pre-empt this. The convention `cross-subsystem-pattern-premise-revalidation` covers the abstract principle; the specific instance for live-API tests could earn its own citation if a second future site surfaces the same blind spot.
- **L2's test-budget under-estimation (predicted +9, shipped +17)** wasn't a problem in itself — each new test pins a distinct boundary; trimming below 17 would either collapse invariants or drop the Message-invariant pins — but the leg spec's mental model for budgeting was off. A future "dataclass-shape-invariants" leg in similar shape should budget tests at **"one pin per invariant boundary"** not "one pin per dataclass." The L2 leg ended up pinning normalization (5) × Message-invariant (4) × per-provider pass-through (4+2+2) = 17 distinct boundaries. That's correct; the leg-spec should have anticipated the multiplicative breakdown.
- **The live-API tier ran skipped in container CI** (no `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` set). The skip-pattern behaves correctly, but nothing in the project asserts the live tier actually ran successfully on the operator's machine before merge. F8 wrapped without operator-side `make test-live` confirmation; the pure-encoder tier IS the test of record, but the wire-level cross-provider round-trip remains supplementary confidence, not auto-verified end-to-end. This is not a blocking gap — it's a transparency gap in the criterion-coverage artifact (the cross-provider end-to-end has unit pinning + opt-in live confirmation, no auto-verified end-to-end).

### Technical

- **Test metrics**: 2669 passed, 4 skipped, 482 deselected, 0 failed, 197.27s wall (`make test-unit`). Trajectory: F2 baseline 2443 → F7 baseline 2645 → **F8 land 2669** (+24 vs F7; +226 vs F2). Wall time: F2 205.85s → F7 213.45s → **F8 197.27s** (a 16.18s / 7.6% wall-time improvement vs F7 despite +24 tests — likely run-to-run noise on a 3-min suite, but no regression). The 4 skips are pre-existing OS-conditional / external-service skips; the 482 deselected reflects the project's expanded live-marker registration (F8 L1's 5 new live tests are deselected by `make test-unit`'s `-m "not browser and not live and not pixel"` filter). Two warnings are pre-existing aiosqlite event-loop noise, unrelated to F8. No flakes observed on the single run.
- **Dead defensive `content is None` branch in `run_engagement_inference`** is now unreachable post-L2's `Message.__post_init__` assert. The L2 leg spec explicitly scoped this branch as out-of-scope cleanup (one-line maintenance-flight follow-up). Worth folding into the next routine-maintenance pass to tighten the contract.
- **Untested edge case: legacy DB rows with non-str `ToolResult.content`.** If pre-L2 production data ever stored non-str content (rare; only if a corruption path landed), the decode path at `codec.message_from_dict` would re-normalize via `ToolResult.__post_init__` (JSON-encoding the non-str content again — possibly double-encoding a Python-repr of a structured value). A direct corrupt `Message.content` would AssertionError; the latent-non-corrupt case would silently re-encode. If legacy rows of this shape don't exist in production, this is academic; if they might, a one-off audit of DB content shape (or a dedicated decode test pinning the legacy-row behavior) would close the gap.
- **`metadata: dict[str, Any] | None` field on `ToolResult` has no `__post_init__` invariant.** Not urgent — `metadata` doesn't currently traverse provider encoders the way `content` does — but if F5 OAuth work or similar grows the surface, add a parallel clause.
- **Wire-level cross-provider round-trip remains unverified by automated tests.** L1 verified the encoder boundary (`_to_api_message` accepts the canonical session list without raising for all 4 providers). It did *not* verify that wire-level round-trip preserves all shape (live tests all skipped in CI). A response-parser bug that emits a malformed-but-still-str `Message.content` would slip through the F8 invariants. The operator-side mechanism is `make test-live`; it is not a structural guarantee.

### Documentation

- **Convention text at `provider-shape-portability` mentions the legacy-decode AssertionError as "intentional signal of underlying corruption" but no runbook for an operator hitting one in production.** A one-line addition — "if you hit this AssertionError on a legacy row, capture the row id, downgrade the assert to a logged warning in a hotfix branch, and open a maintenance flight" — would close the operator-facing loop.
- **The "rename-not-delete" discipline applied at L2** (renaming `test_tool_result_content_non_str_diverges_per_provider` → `test_tool_result_content_normalized_at_construction_uniformly` rather than delete-and-readd) is mentioned in the flight log but not codified as a convention. If a second future leg applies the same pattern, it would earn n=2 and graduate to its own `agents.md` section.
- **The "annotation-extend-not-replace" discipline applied at L2** (`codec.py:truncate_for_event` docstring + the test file's module docstring — preserves rationale history rather than replaces) is also nominated but not codified. Same n=2 graduation rule applies.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L1 split the single "swap-test" bullet into two test methods (anthropic→openai and openai→anthropic), shipping 9 pure-encoder tests instead of bullet-count 8 | Per-direction tests have clearer test names and per-direction assertion specifics | Yes — bullets describing bidirectional behavior should split into per-direction tests by default |
| L2 shipped 17 new tests instead of predicted 9-11 | Multiplicative invariant-boundary breakdown (normalization × Message-invariant × per-provider pass-through); each is structurally a separate regression net | Yes — for dataclass-invariant legs, budget tests at "one pin per invariant boundary" not "one pin per dataclass" |
| L2 deleted `tests/test_connectors_inference.py::test_run_engagement_inference_returns_false_on_none_content` rather than rewriting | The defended-against corner case (Message with content=None) is structurally unreachable post-L2's assert; the defense moved from the consumer to the dataclass constructor | Yes — when an invariant makes a defended corner case unreachable, delete the test; note the dead consumer-side defensive branch as out-of-scope cleanup |
| L3 corrected one test-data string at implementation (`-123` not `t123` for the tail of `longersecret-token-123`) | Spec author's transcription error; caught at first test run; one-line fix | No (mechanical correction, not a methodology lesson) |
| L4 (`hat-multi-provider-swap`) retired during execution | Conditional on L1 surfacing a real fix; L1 surfaced no gap, no fix shipped, no HAT needed | Yes — conditional-on-prior-leg-outcome HAT planning is the right shape for substrate-hardening flights where the test outcome determines verification scope |

## Key Learnings

**The asymmetric `__post_init__` enforcement pattern is generalizable.** Candidates for the same shape in this codebase: any dataclass where one field is "wire-format with multiple legitimate constructor shapes that get canonicalized" (normalize) vs "wire-format that's always one shape and non-conforming is a defect" (assert). Examples to scan for n≥2 codification: `OutboundTarget`, `SendResult`, codec event payload shapes. Worth a maintenance-flight survey, not an immediate refactor.

**"Convention before code" reviewer pattern paid for itself.** Both L1 and L2 design-review cycle 1 caught real high-severity issues that would have cost re-spin loops at implementation time. The pattern: spawn a Developer-as-reviewer to cross-reference the leg's planned approach against the project's installed conventions and the actual codebase state — *before* writing code. Net cost: one extra agent spawn per leg. Net benefit: avoids the "mid-implementation realization that the leg called for a non-existent pattern" thrash.

**Substrate-hardening flights validate "what should already work."** L1's null-result outcome (no gap surfaced) is the right shape for substrate verification — it confirms the canonical Message format was already portable and turns the empirical confirmation into a regression net. The flight's framing should pre-set this as success, not as absence. The substrate flight closes the encoder boundary structurally; wire-level remains the next axis.

**The encoder boundary vs the wire level are distinct verification axes.** L1's pure-encoder tier covers what `_to_api_message` emits; the live tier covers what real provider HTTP accepts. F8 closed the encoder boundary axis structurally (via `__post_init__` invariants). The wire-level axis remains operator-driven via `make test-live`. Future cross-provider work that introduces new providers should pin both axes.

## Recommendations

1. **Hoist the dead defensive `content is None` branch in `run_engagement_inference`** into the next routine-maintenance flight. Unreachable post-L2's assert; removing it tightens the contract.
2. **Add a runbook one-liner** to the `provider-shape-portability` convention text covering the operator-facing response when a legacy-row AssertionError surfaces in production.
3. **Update the `/leg` skill template** with a "live-test convention check" line: before writing live/integration tests, identify the project's existing live-test convention file and mirror its skip-marker, host-discovery, and cleanup patterns. The pattern caught three high-severity issues at L1 cycle-1; codifying it would pre-empt the next instance.
4. **Survey the codebase for additional asymmetric-`__post_init__` candidates** (`OutboundTarget`, `SendResult`, codec event payload shapes) in a maintenance-flight survey. Don't refactor speculatively; do identify which dataclasses share the "one-shape-required vs multiple-legitimate-shapes" semantic.
5. **Flag wire-level cross-provider round-trip as an open verification axis** in the M11 mission-debrief. F8 closed the encoder boundary; the wire-level remains opt-in via `make test-live` with operator credentials. The criterion-coverage artifact for M11 should note this transparency gap.
6. **Re-run live-API tier locally with credentials** before merging the next provider-related flight (or as a periodic operator-driven cadence) to validate the wire-level invariant the encoder tier cannot exercise.
7. **Consider a `behavior-test` spec for cross-provider session-swap end-to-end** — not urgent for F8, but the canonical mechanism for closing the "Discord chat in real traffic with mid-session provider swap" coverage axis. Defer to F9+ planning or to the M11 mission-debrief's criterion-coverage gap analysis.

## Action Items

- [ ] **Maintenance**: hoist the dead `content is None` branch in `run_engagement_inference` (close the dead-code corollary of L2's invariant).
- [ ] **Documentation**: extend the `provider-shape-portability` convention text in `the_one/agents.md` with the runbook for legacy-row AssertionError in production.
- [ ] **Methodology**: propose to mission-control the `/leg` skill template update — "live-test convention check" line (see Recommendations #3).
- [ ] **Survey**: scan codebase for additional asymmetric-`__post_init__` candidates; nominate codification candidates if n≥2 found.
- [ ] **Mission-debrief**: flag wire-level cross-provider round-trip as an open verification axis when M11 debriefs.
- [ ] **Operator**: re-run `docker exec the-one pytest -m live tests/test_llm_provider_cross_provider_history.py -v` with credentials set on a local workstation to validate the wire-level invariant once before F9 starts.
