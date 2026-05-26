# Flight: Provider-Shape-Portability Hardening

**Status**: ready
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

This is a substrate-hardening flight that closes the technical-debt scope from F7 debrief Recommendation #1. It does not directly close a mission criterion. It supports:

- [ ] **#19** (full working-day daily-driver run) — provider-shape invariants reduce the probability of a latent shape-loss surfacing during a long-running session that swaps models or accumulates tool calls across many turns.

The flight artifact also closes F7 action item: *"Open a M11 follow-up flight artifact for provider-shape-portability hardening."*

---

## Pre-Flight

### Objective

Close F7 debrief Recommendation #1 by turning the surgical hotfixes (12.l, 12.m) and the partially-audited invariants (Message.content ASSISTANT/SYSTEM branches, mask-shape constant duplication) into structurally enforced guarantees that any future provider, codec consumer, or session restore inherits without rediscovering the bugs.

Three concrete deliverables:

1. **Cross-provider chat-history round-trip is pinned by tests** — a session containing assistant `tool_calls` + tool `ToolResult` content, accumulated under one provider, can be re-sent through another provider without shape-loss. Pair coverage: Anthropic ↔ Ollama (`qwen2.5:7b` or whichever local default is configured) and Anthropic ↔ OpenRouter (`google/gemma-4-26b-a4b-id:free`).
2. **`ToolResult.content` and `Message.content` shape-invariants are codified** — either at construction (`__post_init__`) or via widened-annotation-with-audited-consumers (architect-resolved at Phase 5b). The surgical 12.l/12.m coercions either become unnecessary or get replaced by a single shared helper.
3. **Mask-shape duplication is removed** — `_mask_secret_value` (api.py:642-664) and `_MASK_SHAPE_RE` (api.py:685) share a single source-of-truth literal so a future maintainer cannot drift one and silently corrupt round-trips.

### Open Questions

- [x] **`ToolResult.content` permanent-fix shape** — **RESOLVED at Phase 5b (Architect pick, operator-confirmed): option (c) Hybrid.** Widen annotation to `str | dict | list[Any]`; add `__post_init__` that JSON-stringifies non-str on construction. Single normalization site at construction. Under this pick: the 12.l coercion at `the_one/llm/anthropic_provider.py:219-249` is deleted (revert to `content=msg.tool_result.content`); 12.m at `the_one/db/codec.py:18-39` `truncate_for_event` is kept as belt-and-suspenders (unreachable under the new invariant but defends the projection path if the invariant ever loosens); `the_one/interfaces/cli.py:83-85` (does `len(output)` on `tool_result.content` — recon-omitted consumer flagged by Architect) works unchanged. See Design Decisions §1 for full rationale.
- [ ] **Will L1's cross-provider round-trip test reveal a real gap, and what shape?** Operator framing during planning: "I think it's real but we should test." Pure-encoder primary (mocked HTTP, exercises `_to_api_message` symmetrically) + live-API supplementary (skip-marked if API unavailable). If L1's test passes from the start across both swap pairs, no fix work is needed and L1 ships test-only. If it surfaces a real gap, L1 fixes it in the same atomic leg (test+fix), bounded by a divert threshold (see Adaptation Criteria). L4 (HAT, if activated) is conditionally enabled based on L1's outcome.
- [x] **`Message.content` ASSISTANT/SYSTEM invariant — enforce or document?** **RESOLVED (Architect-recommended, operator-confirmed): enforce via parallel `__post_init__` assertion** on `Message` that requires `isinstance(self.content, str)`. Assertion (not JSON-normalization) because a non-str on an ASSISTANT/SYSTEM message signals a real provider-parser bug we want to surface — unlike `ToolResult.content` where structured returns from channel-context tools are legitimate. **Folded into L2** (operator-confirmed L2+L3 collapse): one leg ships both invariants as `dataclass-shape-invariants`.

### Design Decisions

**§1. `ToolResult.content` and `Message.content` enforcement shapes (Architect pick c, operator-confirmed)**:
- `ToolResult.content`: widen annotation to `str | dict | list[Any]`; `__post_init__` JSON-stringifies non-str on construction. Single normalization site means every consumer (4 providers, codec, telemetry, cli) reads `str` post-construction.
- `Message.content`: kept as `str = ""`; `__post_init__` adds `assert isinstance(self.content, str)`. Assertion rather than normalization — a non-str on an ASSISTANT/SYSTEM message means a provider-parser bug we want surfaced, not silently coerced.
- Rationale: structured tool returns (`list[dict]` from `fetch_channel_history` et al.) are legitimate; the agent loop at `the_one/agent/core.py:336` wraps them into `ToolResult(content=output)` and `__post_init__` normalizes there — the agent loop never sees the structured shape leak forward. By contrast, `Message.content` is constructed exclusively at message-parsing sites (provider response parsers, codec decoders, factory methods); any non-str there is a defect, not a feature. The two invariants share the `__post_init__` enforcement *style* but differ in *semantic* (normalize vs assert) by deliberate design.
- Trade-off (ToolResult): widening the annotation slightly loosens the type-contract for callers that pre-serialize. Mitigation: the docstring on `ToolResult.content` documents that the public contract is "str post-construction"; callers that pre-serialize lose nothing.
- Trade-off (Message): an `assert` makes the invariant a Python `-O`-strippable check. Acceptable for substrate hardening because tests cover the surface; if production-O-mode masks a real bug, the cross-provider tests catch it before deployment.
- Follow-on under this pick: delete the 12.l Anthropic coercion at `the_one/llm/anthropic_provider.py:219-249`; keep 12.m `truncate_for_event` defensive isinstance check with a comment noting it's unreachable under the new invariant but defends if the invariant ever loosens; verify `cli.py:83-85` works unchanged (Architect-flagged recon-omitted consumer).

**§2. Test-first atomic L1**: cross-provider round-trip test AND any fixes it surfaces land in one leg. Test layering: pure-encoder symmetric test (mocked HTTP, exercises `_to_api_message` both directions) as **primary**; live-API integration tests against Anthropic ↔ Ollama qwen and Anthropic ↔ OpenRouter `google/gemma-4-26b-a4b-it:free` as **supplementary** (skip-marked if API unavailable).
- Rationale: main never carries a failing or `xfail`-marked test between commits; the atomic-leg pattern (M10 convention) holds; if the test passes from the start, L1 is a small green-test leg and that's also fine — the test becomes the regression net. The pure-encoder primary tier means the canonical-shape invariant is verifiable without network access; the live-API supplementary tier catches anything the pure-encoder layer misses (real Discord-shaped tool calls round-tripped through real provider HTTP).
- Trade-off: L1's scope is harder to pre-size since it depends on what the test surfaces. Mitigation: explicit divert threshold (~80 LOC across more than one module — see Adaptation Criteria).

**§3. L2+L3 collapse into one `dataclass-shape-invariants` leg** (operator-confirmed after Architect note):
- Under pick (c), L3's Message.content assertion is ~5 LOC + tests, all in `the_one/llm/base.py`. Adding an entire leg for that scope inflates artifact count without atomic-leg benefit; the two invariants share a file and a review surface.
- Rationale: one commit, one review pass, two related invariants. The single-leg framing also makes the agents.md `provider-shape-portability` convention land in one citation rather than two.
- Trade-off: leg surface widens slightly (~30 LOC under pick c vs ~20 if split). Within atomic-leg budget; not a real cost.

**§4. Provider coverage for cross-provider round-trip test**: two specific swap pairs, with named models.
- Rationale: operator-specified — Anthropic ↔ Ollama (qwen-family, operator's local default) and Anthropic ↔ OpenRouter (`google/gemma-4-26b-a4b-it:free`, operator-confirmed slug at Phase 5b). These pairs exercise the two non-OpenAI canonical-format providers against the Anthropic baseline. OpenRouter inherits OpenAI's `_to_api_message` with zero override (`the_one/llm/openrouter_provider.py:46` confirmed by Architect), so OpenRouter-vs-OpenAI is covered without separate testing. OpenAI-vs-Anthropic is implicitly covered by the existing parity tests at `tests/test_llm_provider_user_content_projection.py`.
- Trade-off: not exhaustive (4×4 = 16 directed pairs would be exhaustive; we cover 4). Justified by the canonical-Message-format invariant — if any pair loses shape, the bug is in the Message dataclass or the provider's `_to_api_message`, not in the pair-relationship per se.

**§5. Mask-shape constant folded into F8 rather than maintenance**: kept as a separate leg (L3 after collapse) rather than folded into the dataclass-shape-invariants commit.
- Rationale: F8 is already in the substrate-typing neighborhood (codec, providers, mask-handling helpers in api.py); the refactor is ~10 LOC and shares the "drift-prevention via single-source-of-truth" theme with the typing work. Architect-recommended: keep as a standalone leg for review-surface cleanliness — the `api.py` change is unrelated to the LLM-providers change at file level, and bundling would cross-cut the PR.
- Trade-off: F8 keeps a separate small leg. Acceptable — atomic-leg discipline benefits.

**§6. HAT is conditional, not pre-committed**:
- Rationale: a substrate flight with strong test coverage (cross-provider round-trip, ASSISTANT-invariant assertions, mask round-trip tests) is invariant-bounded. HAT adds value only if L1 reveals a real bug that warrants end-to-end verification under live Discord traffic. If L1 passes from the start, HAT is overhead.
- Trade-off: planning carries an unknown — will HAT happen or not. Mitigation: L4 HAT leg is drafted but marked optional; activated at L1 completion if a real fix landed.

**§7. `agents.md` convention citations**: this flight will codify (or update) these conventions in the project's `the_one/agents.md`:
- `cross-subsystem-pattern-premise-revalidation` (existing) — the provider audit re-validates F7's audit, which only covered USER-role.
- `mechanical-fallback-prompt-truth-pairing` (existing) — the invariants being added get paired with docstring contracts so reviewers see the truth source mechanically.
- `provider-shape-portability` (NEW, this flight) — proposed: the canonical `Message` dataclass is the portable shape; any provider-specific encoding lives entirely in `_to_api_message`; any provider-specific decoding lives entirely in the response parser. No provider-specific shape leaks back into the Message before persistence. Confirmed at L1 (cross-provider round-trip test) and L2 (dataclass invariants).
- `single-source-of-truth-for-paired-helpers` (NEW, this flight) — proposed for the mask refactor: when an emitter and a recognizer share a literal pattern, the pattern lives as a single constant or generator function. Confirmed at L3 (mask-shape unification).

### Prerequisites

- [ ] F7 is landed and merged into main (Architect-observation: the-one is currently on branch `flight/07-mentions-aware-response-policy` with F7 landed at `b42c609` and debriefed at `9949dbe`; main may need to absorb F7 before F8 branches). Flight Director confirms the branching strategy at L1 start.
- [ ] **Stray `docker-compose.yml` modification** in the-one's working tree (Architect-flagged) is either committed (if intentional) or stashed (if not) before F8 starts. F8's L1 baseline must be clean.
- [ ] Operator has API credentials for: Anthropic (existing), OpenRouter (existing — `google/gemma-4-26b-a4b-it:free` operator-confirmed slug at Phase 5b), Ollama (running locally with qwen-family model installed). If any provider is unavailable at L1 time, the live-API supplementary test for that pair is skipped with an explicit `pytest.skip` and a flight-log note. The pure-encoder primary test runs without network and is not skippable.
- [ ] Working test suite baseline: 2645 passed at F7 land (per F7 debrief `flight-debrief.md:71`). F8 baseline measured at flight start; any regression vs F7 baseline is investigated before L1 lands.
- [ ] Mission-control `skill/wbt` branch state (HAT methodology) is unchanged or improved — F7 dogfood was on `skill/wbt` and the methodology is now codified. F8 does not change behavior-test methodology; if L4 (HAT) is activated, the existing `/behavior-test discord-engagement` spec or a new provider-swap-focused spec is used.

### Pre-Flight Checklist

- [x] All planning-time open questions resolved (`ToolResult.content` and `Message.content` shapes resolved by Architect + operator at Phase 5b; L1 outcome resolves L4 HAT conditionality at run time — not a planning-time decision)
- [x] Design decisions documented above (§1-§7)
- [ ] Prerequisites verified (depend on operator stash/commit + branch-state confirmation)
- [x] Validation approach defined (tests primary: pure-encoder + live-API; HAT conditional)
- [x] Legs defined (see In-Flight § Legs)

---

## In-Flight

### Technical Approach

F8 hardens three substrate axes (plus a conditional HAT) in sequence:

**Axis 1 — Cross-provider chat-history round-trip (L1)**. Two-tier test coverage:

*Primary (pure-encoder, no network):* a canonical `Message` list containing user, assistant-with-tool-calls, tool-result-with-`list[dict]`-content, and assistant-final-reply is built once and fed through each provider's `_to_api_message` symmetrically. Asserts: each provider emits a syntactically valid request shape; a "swap" (messages built under provider A's response-parser path, then sent through provider B's `_to_api_message`) produces a valid request to provider B. Pure-Python, fast, runs in CI without API credentials.

*Supplementary (live API, skip-marked if unavailable):* same canonical Message list, but actually round-tripped through the live APIs of the operator-named pairs:
- Anthropic ↔ Ollama (qwen-family, operator's local default)
- Anthropic ↔ OpenRouter (`google/gemma-4-26b-a4b-it:free`)

Catches anything the pure-encoder layer misses (real Discord-shaped tool calls, real provider response variations).

If either tier surfaces a real gap, the fix lands in L1 (atomic test+fix), bounded by the divert threshold (~80 LOC across more than one module — see Adaptation Criteria).

**Axis 2 — Dataclass shape invariants (L2, collapsed from L2+L3)**. Two related invariants ship together in `the_one/llm/base.py`:

*`ToolResult.content` (Architect pick c):* widen annotation to `str | dict | list[Any]`; `__post_init__` JSON-stringifies non-str on construction. Single normalization site means downstream consumers (4 providers, codec, telemetry, cli) read `str` uniformly. Under this fix:
- Delete the 12.l Anthropic coercion at `the_one/llm/anthropic_provider.py:219-249` (revert to `content=msg.tool_result.content`).
- Keep 12.m `truncate_for_event` defensive isinstance check at `the_one/db/codec.py:18-39` as belt-and-suspenders with a comment noting it's unreachable under the new invariant but defends if the invariant ever loosens.
- Verify `the_one/interfaces/cli.py:83-85` (does `len(output)` on `tool_result.content` — Architect-flagged recon-omitted consumer) works unchanged.
- Update `tests/test_llm_provider_tool_result_serialization.py` and `tests/test_truncate_for_event_non_str_coercion.py` to pin the `__post_init__` normalization at construction rather than at consumer sites.

*`Message.content` (parallel invariant):* add `__post_init__` assert `isinstance(self.content, str)`. Assertion (not normalization) because a non-str on an ASSISTANT/SYSTEM message means a provider-parser bug we want surfaced. The ASSISTANT+tool_calls branches at `anthropic_provider.py:250-258`, `openai_provider.py:262-277`, `ollama_provider.py:256-279` get a smoke test that builds an ASSISTANT message with non-str content and asserts the assertion fires.

Codify the `provider-shape-portability` convention in `the_one/agents.md` if it earned its keep through L1+L2.

**Axis 3 — Mask-shape single-source-of-truth (L3, was L4)**. The literals at `api.py:642-664` (`_mask_secret_value` returning `"***"` or `f"***...{value[-4:]}"`) and `api.py:685` (`_MASK_SHAPE_RE = re.compile(r"^\*\*\*(\.\.\..{1,4})?$")`) are unified. Cleanest shape: a single constant or helper function that GENERATES the mask and a regex that VALIDATES against the same pattern source. The unification site is co-located with the existing helpers (no module move). Existing mask round-trip tests (`tests/test_api_secret_mask_roundtrip.py`) continue to pass. Codify the `single-source-of-truth-for-paired-helpers` convention in `agents.md`.

**Axis 4 — Conditional HAT (L4, was L5)**. Only if L1 surfaced a real bug that warranted a fix. Walks the Discord engagement flow with mid-session provider swap; observes that an assistant accumulated under provider A (with tool calls fired) continues coherently when re-bound to provider B. Uses the `/behavior-test` skill on the mission-control `skill/wbt` baseline.

### Checkpoints

- [ ] **L1 lands**: cross-provider round-trip test exists; pure-encoder tier passes; live-API tier passes (or skip-marked with rationale) for both swap pairs (Anthropic↔Ollama qwen, Anthropic↔OpenRouter `gemma-4-26b-a4b-it:free`). If L1 surfaced a gap, the fix landed atomically with the test.
- [ ] **L2 lands**: `ToolResult.content` widened annotation + `__post_init__` normalization in place; `Message.content` `__post_init__` assertion in place; 12.l Anthropic coercion deleted; 12.m kept with comment; `cli.py:83-85` verified working; tests updated.
- [ ] **L3 lands**: `api.py` mask-helper duplication closed via single source-of-truth; existing mask round-trip tests still pass; `agents.md` convention citation added.
- [ ] *(conditional)* **L4 lands**: if a real cross-provider fix shipped in L1, HAT confirms the fix end-to-end via `/behavior-test`.

### Adaptation Criteria

**Divert if**:
- L1's round-trip test reveals a deep architectural gap (e.g., Message dataclass cannot represent some required shape) rather than a localized shape-loss. Divert means: pause F8, write a finding to the flight log, present back to operator for re-scoping. F8 might split into "tests + small fix" + "architectural rework as F8.5".
- **L1's atomic test+fix exceeds ~80 LOC across more than one module** (Architect-recommended divert threshold). At that point, split: L1 ships test-only (perhaps with `xfail` or `skip` markers documenting the gap), and a new leg L1b ships the fix. Keeps atomic-leg discipline.
- Any leg's tests show a regression in the F7 baseline (2645 passed at land). Investigate before continuing.

**Acceptable variations**:
- L3 (mask refactor) lands before L2 if it's a smaller surface and shipping it first unblocks parallel review.
- L2 lands before L1 if the L1 pure-encoder tier reveals an issue that wants the L2 invariants in place first. The flight log records the reordering rationale.
- The `agents.md` convention additions (`provider-shape-portability`, `single-source-of-truth-for-paired-helpers`) get refined names during the legs that codify them. The semantics are committed; the names may shift.
- The pure-encoder tier of L1's test stays even if the live-API tier is fully skipped (no API credentials at flight start). The pure-encoder primary tier IS the test of record; the live-API tier is supplementary confidence.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `cross-provider-history-roundtrip` — Add cross-provider tool-call round-trip tests in two tiers: pure-encoder (primary, no network) and live-API supplementary against Anthropic↔Ollama (qwen-family) and Anthropic↔OpenRouter (`google/gemma-4-26b-a4b-it:free`). Test+fix atomic, bounded by ~80 LOC divert threshold. Closes the F7-debrief task-#25 concern by pinning the round-trip behavior.
- [ ] `dataclass-shape-invariants` — Apply Architect pick (c) to `ToolResult.content`: widen annotation to `str | dict | list[Any]`, add `__post_init__` JSON-stringify normalization. Add parallel `__post_init__` `isinstance` assertion on `Message.content`. Delete 12.l Anthropic coercion (`anthropic_provider.py:219-249`); keep 12.m `truncate_for_event` defensive check with annotation; verify `cli.py:83-85` works unchanged. Update tests at `tests/test_llm_provider_tool_result_serialization.py` and `tests/test_truncate_for_event_non_str_coercion.py` to pin invariants at construction. Codify `provider-shape-portability` in `the_one/agents.md`.
- [ ] `mask-shape-single-source` — Unify `_mask_secret_value` (api.py:642-664) and `_MASK_SHAPE_RE` (api.py:685) so the mask pattern has one source-of-truth. Codify `single-source-of-truth-for-paired-helpers` in `agents.md`.
- [ ] `hat-multi-provider-swap` *(conditional — only if L1 surfaced a real fix)* — Discord engagement HAT with mid-session provider swap; observe coherent continuation. Uses `/behavior-test` skill on `skill/wbt` methodology baseline.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed (L1-L3 mandatory; L4 HAT conditional on L1's outcome)
- [ ] F7's surgical 12.l Anthropic coercion is deleted at `the_one/llm/anthropic_provider.py:219-249`; the 12.m `truncate_for_event` defensive check is kept with comment annotation
- [ ] `cli.py:83-85` verified working unchanged under the new `ToolResult.content` invariant
- [ ] Cross-provider round-trip tests pass for both swap pairs (pure-encoder primary always; live-API supplementary unless skip-marked with documented rationale)
- [ ] `ToolResult.content` widened annotation + `__post_init__` normalization in place; `Message.content` `__post_init__` assertion in place; tests updated
- [ ] `api.py` mask-helper duplication is closed
- [ ] Test suite baseline at F8 land is recorded (compared against F7's 2645 passed / 213.45s wall)
- [ ] `the_one/agents.md` updated with new conventions (`provider-shape-portability`, `single-source-of-truth-for-paired-helpers`) cited from legs L2 and L3 respectively
- [ ] Criterion-coverage artifact updated: F8 doesn't close any criterion directly; `Last touched` column for #19 is updated with F8 reference (indirect contribution via provider portability supporting full-day robustness)
- [ ] Flight-debrief written, including:
  - Whether L1 surfaced a real bug (validates or invalidates the F7-debrief "task #25" framing)
  - Final shape of the dataclass invariants (Architect pick c confirmed in practice, or deviation rationale)
  - Any new conventions codified
  - Test-metric delta vs F7 baseline

### Verification

- **Tests**: full `uv run pytest tests/ --ignore=tests/browser --ignore=tests/behavior -x` passes; cross-provider round-trip tests pass for both swap pairs (pure-encoder always, live-API per credentials availability); mask round-trip tests pass; F7 baseline (2645 passed) is matched or improved.
- **Invariants**: a non-str passed to `ToolResult(content=...)` is JSON-stringified at construction (test pins this); a non-str passed to `Message(content=...)` raises AssertionError at construction (test pins this).
- **Conventions**: `the_one/agents.md` review — any new conventions are cited from the legs that codified them; existing conventions cited (no rot).
- **Hotfix cleanup**: confirm the 12.l site at `anthropic_provider.py:219-249` is gone; 12.m at `db/codec.py:18-39` is retained as belt-and-suspenders with explanatory comment; no surgical-coercion shape remains as the de-facto contract.
- **(conditional) HAT**: if L4 ran, the HAT run-log lives at `tests/behavior/{slug}/runs/{ts}.md` with pass/fail per step.
