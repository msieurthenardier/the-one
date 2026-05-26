# Flight Log: Provider-Shape-Portability Hardening

**Flight**: [Provider-Shape-Portability Hardening](flight.md)

## Summary

(Populated during and after execution.)

---

## Reconnaissance Report

**Date**: 2026-05-26 (Phase 1b, F8 planning)
**Source artifact**: [F7 flight debrief](../07-mentions-aware-response-policy/flight-debrief.md) — "What Could Be Improved → Technical" section and "Recommendations → #1" (line 83).

Items in F7-debrief Recommendation #1 walked against current code:

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| **(a) `ToolResult.content` typing — runtime enforcement** | `already-satisfied` (surgical), `confirmed-live` (permanent fix) | Surgical: 12.l at `the_one/llm/anthropic_provider.py:219-249` (Anthropic-only `json.dumps` coercion guarded by `isinstance(content, str)`); 12.m at `the_one/db/codec.py:18-39` (`truncate_for_event` non-str coercion). **Additional consumer (Architect-flagged at Phase 5b, recon-omitted):** `the_one/interfaces/cli.py:83-85` does `len(output)` and slices to 500 chars on `tool_result.content` — would crash on non-str. Construction site: `the_one/agent/core.py:336` wraps tool output as `ToolResult(content=output)`. Tests: `tests/test_llm_provider_tool_result_serialization.py` (8 tests), `tests/test_truncate_for_event_non_str_coercion.py` (6 tests). Trigger sites unchanged: `the_one/tools/connector_history.py:134, 233, 321, 416` still return `list[dict[str, Any]]`. | Permanent fix is real F8 work. **Resolved at Phase 5b: Architect pick (c) hybrid** — widen annotation + `__post_init__` JSON-stringifies non-str. Operator-confirmed. |
| **(b) `Message.content` ASSISTANT/SYSTEM audit** | `confirmed-live` (partially-satisfied) | `build_user_message_content` at `the_one/llm/base.py:148-184` defends USER-role only via `if msg.role != Role.USER: return msg.content` (line 174-175). ASSISTANT+tool_calls branches pass `msg.content` through unguarded: `anthropic_provider.py:250-258` (line 253 inline text block); `openai_provider.py:262-277` (line 265); `ollama_provider.py:256-279` (line 262). No `__post_init__` validator on `Message` dataclass at `base.py:42-44`. | Real F8 work. Audit + enforce at chosen layer (matches L2's approach). |
| **(c) GET/PUT mask sentinel sweep — `api.py:1588` and beyond** | `already-satisfied` | Line 1588 (POST `/test/connect` MCP body-override) already uses `_looks_masked()` check at `the_one/interfaces/web/api.py:688-707` which recognizes both `_MASKED_API_KEY_SENTINEL` and the regex shape. Connector `/test/connect` at `api.py:2598-2679` has no body override (no asymmetry possible). Tests: `tests/test_api_secret_mask_roundtrip.py` (437 lines, covers MCP + connector + provider GET/PUT). | Retire from F8 scope. Documented here as closed. |
| **Mask-shape regex / `_mask_secret_value` shared-constant** | `confirmed-live` (low-risk) | `_mask_secret_value` at `api.py:642-664` emits `"***"` or `f"***...{value[-4:]}"`. `_MASK_SHAPE_RE` at `api.py:685` is `^\*\*\*(\.\.\..{1,4})?$`. Literals identical, adjacent (same function block), but no shared constant. Drift unlikely structurally but not prevented mechanically. | Fold into F8 as L4. Small refactor (~10 LOC). Operator confirmed in-scope. |
| **(d) Cross-provider chat-history (task #25)** | `needs-human-recheck` → resolved by operator (real concern, in scope) | No code reference to "task #25" found in repo (grepped commits, comments, TODOs). Provider landscape: Anthropic (271 LOC), OpenAI (286 LOC), OpenRouter (157 LOC, inherits OpenAI), Ollama (282 LOC). Canonical `Message` dataclass at `the_one/llm/base.py:42-44` is the portable shape. Cross-provider parity test exists at `tests/test_llm_provider_user_content_projection.py` (17 tests) but covers USER-role projection only, not full assistant + tool-call round-trip across provider swaps. | F8 L1: pin via cross-provider tool-call round-trip test for Anthropic↔Ollama (qwen) and Anthropic↔OpenRouter (`google/gemma-4-26b-a4b-id:free`). Test+fix atomic. |

### Retirements from F7-debrief Rec #1 scope
- **Item (c) — GET/PUT mask sentinel sweep at `api.py:1588`**: already-satisfied per recon evidence above. Confirmed retired by operator (implicit via "F8 stays focused on the typing axis" framing during planning).

### Carry-forwards from F7 debrief NOT in F8 scope
- F7 Rec #3 candidates (`.tool-enable-switch` CSS default flip, `_inbound.py` helper extraction, studio-event-bus pattern lift, field-row-3-column primitive): routine-maintenance candidates, not F8.
- F7 Rec #5 (re-run discord-engagement behavior test in fresh session): one-off action item, may happen alongside F8 but not part of the flight scope.
- F7 Rec #4 (codify inline-hotfix-during-HAT discipline in mission-control): cross-project methodology work, lives on `skill/wbt` branch — separate from this flight.

### Operator decisions during F8 planning (logged here for traceability)
- **F8 scope**: provider-shape-portability hardening only (not bundled with pairing+detach per the original mission flight list); pairing+detach becomes F9; subsequent flights renumber accordingly.
- **`ToolResult.content` enforcement shape**: deferred to Architect at Phase 5b. **Resolved**: pick (c) Hybrid — widen annotation + `__post_init__` JSON-stringifies non-str. Operator-confirmed.
- **Task #25 framing**: real concern (per operator: "I think it's real but we should test"). L1 pins the gap via a test; if test passes from the start, the concern was overstated and L1 ships clean.
- **Mask-shape constant refactor**: in F8 scope as L3 (was L4 before L2+L3 collapse).
- **HAT**: conditional on L1 outcome — only added as L4 (was L5) if L1 surfaces a real fix.
- **Provider test pairs**: Anthropic↔Ollama (qwen-family) + Anthropic↔OpenRouter (`google/gemma-4-26b-a4b-it:free`). OpenRouter inherits OpenAI, so OpenAI is implicitly covered.

### Phase 5b Architect review summary (2026-05-26)
- **Verdict**: approve with changes.
- **`ToolResult.content` pick**: (c) Hybrid. Rationale: trigger sites (channel-context tools) legitimately return `list[dict]`; pushing JSON-encoding to tool authors (option a) puts serialization in the wrong layer; option (b) leaves multiple consumer sites needing audit-and-coercion forever (anthropic_provider.py:236, db/codec.py:38, cli.py:83-85, plus openai/ollama branches that currently pass through unchecked); option (c) collapses to a single normalization site at construction so every consumer reads `str` uniformly. **Operator-confirmed.**
- **High-severity issue**: OpenRouter model slug `google/gemma-4-26b-a4b-id:free` was likely a typo; operator confirmed the correct slug at Phase 5b is `google/gemma-4-26b-a4b-it:free`.
- **Medium-severity issue**: recon missed `cli.py:83-85` as a `ToolResult.content` consumer. Now added to item (a) evidence column.
- **Medium-severity issue**: L2 and L3 collapse cleanly under pick (c) — L3 becomes ~5 LOC. **Operator-confirmed**: collapse into one `dataclass-shape-invariants` leg.
- **Low-severity issue**: L1 needs a concrete divert threshold. **Resolved**: ~80 LOC across more than one module triggers divert; flight artifact's Adaptation Criteria updated.
- **Codebase-state observations**: the-one is on branch `flight/07-mentions-aware-response-policy` (not main); F7 landed at `b42c609`, debriefed at `9949dbe`. Stray `docker-compose.yml` modification in working tree — Architect-flagged for stash/commit before F8 starts. Added to Prerequisites.
- **Convention naming**: `provider-shape-portability` and `single-source-of-truth-for-paired-helpers` are collision-free against existing `agents.md` conventions.

---

## Leg Progress

### cross-provider-history-roundtrip

**Status**: landed
**Started**: 2026-05-26
**Completed**: 2026-05-26

#### Changes Made
- Added `tests/test_llm_provider_cross_provider_history.py` (~620 LOC) with two test classes:
  - `TestCrossProviderHistoryPureEncoder` — 9 pure-encoder tests across all 4 providers, covering canonical-session encoding (Anthropic / OpenAI / Ollama / OpenRouter-inherits-OpenAI), bidirectional cross-provider swap (Anthropic↔OpenAI shape ID resilience), the Anthropic-vs-OpenAI empty-content+tool_calls divergence edge case, F7 12.l str-passthrough invariant, and current (pre-L2) non-str divergence behavior (Anthropic JSON-encodes; OpenAI/Ollama pass through).
  - `TestCrossProviderHistoryLive` — 5 `@pytest.mark.live` tests across Anthropic↔Ollama (qwen) and Anthropic↔OpenRouter (`google/gemma-4-26b-a4b-it:free`) pairs. Includes the required tool-payload swap test (`test_anthropic_with_tools_to_ollama_swap_live`) that exercises a synthetic `noop` tool round-trip through Anthropic → ToolResult → Ollama. Inline skip-checks at function entry mirror the canonical pattern from `tests/test_input_tokens_cross_provider_live.py`; reused `_aclose_provider_client` via cross-file import. Ollama base-URL/model discovery mirrors the canonical helper (probe `/api/tags` after stripping `/v1`, prefer `LIVE_OLLAMA_MODEL` → `qwen2.5:7b` → first available); OpenRouter has explicit `NotFoundError`/`AuthenticationError`/`PermissionDeniedError` → skip conversion.

#### Notes
- **Gap surfaced**: none. All 4 provider encoders accept the canonical multi-shape session list (USER with peer+channel + ASSISTANT with content+tool_calls + TOOL with str content + empty-content ASSISTANT+tool_calls + TOOL with short str + final ASSISTANT) without raising. OpenRouter is byte-identical to OpenAI. The Anthropic-vs-OpenAI empty-content divergence at the encoding boundary is documented per-provider, not "fixed" — both are valid per their APIs. The pre-L2 non-str ToolResult.content divergence is also documented in the test (with a forward-looking comment pointing at F8 L2). The "task #25" concern from F7 debrief Rec #1(d) appears overstated at the encoder level — the canonical Message shape is portable across all 4 providers.
- **Live-API skip status**: all 5 live tests skipped cleanly (no `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` in container env at L1 implementation time). Each skip cites the missing credential by name. Live verification at the wire level is operator-side via `make test-live` with credentials set.
- **Model used for Ollama**: not exercised at L1 implementation (live tests skipped). Auto-discovery logic preserved unchanged from the canonical pattern.
- **Test-metric delta**: pre-leg baseline 2647 passed (re-pinned via `make test-unit` per leg §8 step 1; the F7-debrief 2645 number does NOT apply — different filter). Post-leg 2656 passed. Delta = +9 (matches the 9 new pure-encoder tests; the 5 new live tests are deselected by the `not live` marker filter). Deselected count delta = +5 (matches the 5 new live tests). Zero failures, zero regressions.
- **LOC**: ~620 LOC for the test file. No production code touched. `the_one/llm/base.py` not touched (hard fence per leg §5 / L2 territory).
- **Deviations from leg spec**: split the single swap-test bullet (which mentioned both `anthropic→openai` AND `openai→anthropic` directions) into two distinct test methods for clearer test naming and per-direction assertions. Net pure-encoder test count is 9 instead of the bullet-count 8; functionally equivalent (each direction is its own test). All other acceptance criteria met as specified.

### dataclass-shape-invariants

**Status**: landed
**Started**: 2026-05-26
**Completed**: 2026-05-26

#### Changes Made
- `the_one/llm/base.py`: added `import json`; widened `ToolResult.content` annotation to `str | dict | list[Any]`; added `ToolResult.__post_init__` that JSON-normalizes non-str content at construction; added `Message.__post_init__` that asserts `isinstance(self.content, str)`. Two new docstring blocks reference `the_one/agents.md` → `provider-shape-portability`.
- `the_one/llm/anthropic_provider.py`: deleted the F7 12.l Anthropic encoder-level coercion (the `if not isinstance(content, str): content = json.dumps(content)` branch at old lines 219-249, ~25 LOC removed plus the multi-paragraph comment). Replaced with a single-line pass-through that reads `msg.tool_result.content` directly — the dataclass invariant guarantees the str shape. Removed `import json` from the top of the file (no remaining `json.` uses — verified via `grep -n "json\." the_one/llm/anthropic_provider.py` → no match).
- `the_one/db/codec.py`: `truncate_for_event` docstring extended (NOT replaced) with a post-L2 reachability paragraph: the non-str coercion branch is unreachable from normal flow under the L2 invariant but kept as belt-and-suspenders against direct non-str callers / future invariant loosening.
- `tests/test_llm_provider_tool_result_serialization.py`: REWRITTEN in place. Module docstring rewritten to reflect the post-L2 construction-time-normalization boundary. Deleted: the 8 pre-L2 tests (4 Anthropic + 2 OpenAI + 2 Ollama) plus the `_make_tool_msg` helper (whose post-construction direct-assignment pattern is now an anti-pattern per the convention). Added: 17 new tests across 5 classes:
  - `TestToolResultContentNormalizationAtConstruction` (5 tests): list/dict/nested non-str normalization, str byte-identical pass-through, `Message.tool(ToolResult(content=non_str))` composes correctly.
  - `TestMessageContentInvariantAtConstruction` (4 tests): non-str/None/dict content raise `AssertionError`; the four factory methods all build str-content messages.
  - `TestAnthropicToolResultSerialization` (4 tests, classes preserved for git-blame): post-L2 the encoder is a str pass-through (list, dict, plain str, is_error flag).
  - `TestOpenAIToolResultSerialization` (2 tests): str pass-through for normalized-list and plain-str content.
  - `TestOllamaToolResultSerialization` (2 tests): same as OpenAI.
- `tests/test_llm_provider_cross_provider_history.py`: renamed `test_tool_result_content_non_str_diverges_per_provider` → `test_tool_result_content_normalized_at_construction_uniformly`; dropped the post-construction-assignment pattern (`tr.content = non_str_payload`) in favor of direct construction via `ToolResult(content=non_str)`; inverted assertions (all 4 providers now see the same JSON-str output); removed the pre-L2 forward-looking comment block.
- `tests/test_truncate_for_event_non_str_coercion.py`: module docstring extended (NOT replaced) with the post-L2 reachability paragraph mirroring the codec.py docstring annotation.
- `tests/test_connectors_inference.py`: DELETED the `test_run_engagement_inference_returns_false_on_none_content` test (was at lines ~588-618). The test constructed `Message(role=Role.ASSISTANT, content=None)` deliberately to bypass `Message.assistant`'s `content=""` default and pin the consumer's defensive None-content branch. Under L2's `Message.__post_init__` assert, that construction crashes at `__init__`-time — the corner case is structurally unreachable. The corresponding defensive branch in `run_engagement_inference` is now dead code and is left as out-of-scope cleanup for a future maintenance leg. A comment marker replaces the deleted test for future readers.
- `the_one/agents.md`: added `provider-shape-portability` convention section at line 134, immediately after `cross-subsystem-pattern-premise-revalidation` (the strongest thematic anchor per the leg's §8 — it cites the F7 12.l audit history that L2 directly closes) and before `prompt-discipline-needs-mechanical-fallback`. Convention body covers: the canonical-shape mechanism (both `__post_init__` invariants), source citation (M11 F8 L2 + the two pinning test files), when-this-matters (new provider / new tool / codec refactor), and the post-construction direct-assignment anti-pattern.
- `flight.md`: checked off `dataclass-shape-invariants` in the Legs list (already at `[x]`).

#### Notes
- **Pre-L2 baseline**: 2656 passed, 4 skipped, 482 deselected (re-pinned via `make test-unit` per leg §1.1 — matches the post-L1 count recorded in L1's leg-progress entry above).
- **Post-L2 total**: 2664 passed, 4 skipped, 482 deselected, zero failures. Delta = +8 net.
- **Delta breakdown vs prediction**:
  - Predicted: 2657-2658 (+9 new − 8 deleted from serialization file − 1 deleted from connectors_inference; plus 1-2 for Message.__post_init__ pin tests).
  - Actual: +17 new − 8 deleted − 1 deleted = +8 net. The deviation from the upper-bound prediction (2658) is +6, above the leg's "deviation > 2 → document" threshold.
  - **Rationale for the deviation**: the design predicted 9 new tests but the leg's §3 sketch (TestToolResultContentNormalizationAtConstruction + TestAllProvidersSeeStrToolResultContent) and §7 (preserve three per-provider classes + add the new normalization class) when combined produce more than 9 distinct concrete tests. I implemented 5 normalization tests + 4 Message-invariant pin tests + 4 + 2 + 2 per-provider pass-through tests = 17. Each test pins a distinct boundary (non-str list / non-str dict / str byte-identical / nested normalization / Message.tool composition for ToolResult; assertion variants for non-str/None/dict content + factory-methods sanity for Message; then per-provider encoder pass-through for normalized + plain-str content). Trimming below 17 would either collapse distinct invariants into fewer assertions or drop the Message-invariant pin tests entirely. The +8 net is well within the spirit of the leg ("pin invariants at construction") and the zero-failure result demonstrates the implementation is correct.
- **CLI `cli.py:83-85` consumer**: verified unchanged-but-correct via a targeted one-liner — `len(msg.tool_result.content)` works under the L2 invariant because content is str post-construction.
- **`_make_tool_msg`'s removal**: documents the anti-pattern of post-construction direct assignment (now explicit in the `provider-shape-portability` convention text). The L1 cross-provider test's rename (rather than delete-and-readd) preserves git-blame intent per the state-machine-reachability-audit guidance.
- **Anthropic `import json` removal**: confirmed via `grep -n "json\." the_one/llm/anthropic_provider.py` → no match. The import was used only by the deleted 12.l site.
- **`run_engagement_inference` dead defensive branch**: out-of-scope cleanup for a future maintenance leg per the leg spec.
- **Production-code scope**: only `the_one/llm/base.py`, `the_one/llm/anthropic_provider.py`, `the_one/db/codec.py`, and `the_one/agents.md` touched. `the_one/connectors/`, `the_one/agent/`, `the_one/tools/`, `the_one/interfaces/web/`, and any UI files are untouched. Audited via `git status` (only the 4 production files + 4 test files + 2 flight artifacts appear).
- **Stray `docker-compose.yml`**: operator-side, untouched.
- **Deviations from leg spec**: net new test count exceeds the leg's prediction by +6 (see rationale above). All other acceptance criteria met as specified — both `__post_init__` implementations land in the documented order (ToolResult first, then Message); 12.l deletion is verified by grep; truncate_for_event docstring extends rather than replaces; agents.md convention lands at the documented thematic anchor.

### mask-shape-single-source

**Status**: landed
**Started**: 2026-05-26
**Completed**: 2026-05-26

#### Changes Made
- `the_one/interfaces/web/api.py`:
  - Added module-level constants `_MASK_PREFIX = "***"`, `_MASK_TAIL_SEPARATOR = "..."`, `_MASK_TAIL_LEN = 4` (the single source-of-truth for mask shape).
  - Added `_emit_mask(value: str) -> str` — single emit helper. Returns `_MASK_PREFIX` for `len <= _MASK_TAIL_LEN`; `f"{_MASK_PREFIX}{_MASK_TAIL_SEPARATOR}{value[-_MASK_TAIL_LEN:]}"` otherwise.
  - Refactored `_mask_secret_value` (lines 642-664 pre-L3) to route str through `_emit_mask`; non-str wholesale-mask drawn from `_MASK_PREFIX` constant. None/empty preservation unchanged. Docstring updated to cite the L3 routing.
  - Refactored `_mask_api_key` (lines 3055-3060 pre-L3) to route through `_emit_mask`. None/empty preservation unchanged.
  - Rebuilt `_MASK_SHAPE_RE` from `re.escape(_MASK_PREFIX)` and `re.escape(_MASK_TAIL_SEPARATOR)` so the regex pattern adapts to constant changes. Rendered pattern byte-identical to pre-L3 literal `r"^\*\*\*(\.\.\..{1,4})?$"`.
  - Updated `_looks_masked` docstring to cite `_emit_mask` as the canonical source. Kept the union-recognition language (sentinel OR visual mask) — both semantics still matter at PUT-handler sites.
- `tests/test_api_secret_mask_roundtrip.py`: added `TestMaskShapeSingleSourceOfTruth` class with 5 new tests pinning the regex-emit pairing (short / long match; reject unrelated; emitter routing; rendered-regex byte-identity regression net). No existing test bodies modified — only additions appended after `TestLooksMaskedHelper`.
- `the_one/agents.md`: added `single-source-of-truth-for-paired-helpers` convention section at line 153, placed immediately after L2's `provider-shape-portability` (line 134) as the strongest thematic anchor (both conventions concern preventing drift between paired/related helpers).
- `flight.md`: checked off `mask-shape-single-source` in the Legs list (line 149).
- Leg artifact status: `ready` → `in-flight` → `landed`.

#### Notes
- **Pre-L3 baseline**: 2664 passed, 4 skipped, 482 deselected (re-pinned via `make test-unit` per leg §1.1 — exact match to the post-L2 count recorded in L2's leg-progress entry above).
- **Post-L3 total**: 2669 passed, 4 skipped, 482 deselected, zero failures. Delta = +5 net, exactly matching the leg's prediction.
- **Rendered regex equality**: verified via inline `python -c` check (Implementation Guidance §2) — `re.escape("***")` produces `\*\*\*` and `re.escape("...")` produces `\.\.\.`, so the rendered pattern is byte-identical to the pre-L3 literal. Additionally pinned at test time by `test_rendered_regex_matches_pre_l3_literal`.
- **Observable-behavior preservation**: all 16 pre-existing tests in `tests/test_api_secret_mask_roundtrip.py` pass unchanged. Verified via `git diff tests/test_api_secret_mask_roundtrip.py` — only appended new class after line 505; no existing test body modified.
- **Production-code scope**: only `the_one/interfaces/web/api.py` and `the_one/agents.md` touched in L3. The L1+L2 production files (`the_one/llm/base.py`, `the_one/llm/anthropic_provider.py`, `the_one/db/codec.py`) remain unchanged by L3 — verified via `git diff --stat`. Untouched: `the_one/connectors/`, `the_one/agent/`, `the_one/tools/`, `the_one/db/` (excluding L2's codec), UI / studio. No `_MASKED_API_KEY_SENTINEL` touched per Edge Cases.
- **Refactor LOC**: api.py +35 / -8 (net +27); agents.md +20 / -0 (convention block); test file +62 / -0 (new class).
- **Stray `docker-compose.yml`**: operator-side, untouched.
- **Deviations from leg spec**: ONE minor — the leg §3 sketch for `test_mask_shape_re_matches_emit_mask_output_for_long_string` had `assert masked.endswith("t123")` but the input string `"longersecret-token-123"` ends in `-123` (not `t123`); corrected the assertion to `assert masked.endswith("-123")` with a comment explaining the tail-of-4 derivation. Caught at test run; no impact on the test's invariant (regex match + tail length). All other acceptance criteria met as specified.

---

## Decisions

(Runtime decisions not in original plan.)

---

## Deviations

(Departures from planned approach.)

---

## Anomalies

(Unexpected issues encountered.)

---

## Session Notes

(Chronological notes from work sessions.)

---

## Flight Director Notes

### 2026-05-26 — Flight start

- Loaded `agentic-workflow` skill. Project crew phase file at `.flightops/agent-crews/leg-execution.md` validated (Crew + Interaction Protocol + Prompts sections present with fenced blocks). Developer = Sonnet (implement + design review); Reviewer = Haiku; Accessibility Reviewer disabled (no UI surface in F8).
- Flight status: `ready` → `in-flight`. F7 confirmed merged on origin/main via PR #76 (2026-05-26T13:13:12Z); local main fast-forwarded; F8 branch `flight/08-provider-shape-portability-hardening` created off updated main; planning commit `b71a6e1` pushed to origin with upstream tracking.
- Total legs: 3 mandatory (L1 `cross-provider-history-roundtrip`, L2 `dataclass-shape-invariants`, L3 `mask-shape-single-source`) + 1 conditional (L4 `hat-multi-provider-swap`, interactive HAT, activated only if L1 surfaces a real fix).
- Workflow shape: Phase 2 leg cycle (design → design-review → implement, NO per-leg commit) repeated for L1 → L2 → L3, then Phase 2d (single Reviewer pass + one commit covering all autonomous-leg changes). If L4 activates, it runs interactively after Phase 2d commits.
- Stray `docker-compose.yml` modification in working tree is operator-side; will remain unstaged throughout F8 unless operator commits or restores it. Developer agent prompts will need to be explicit about staging only F8 files.

### 2026-05-26 — L1 landed; L4 HAT retired

- L1 landed cleanly: 9 new pure-encoder tests + 5 new live-marked tests, baseline re-pinned at 2647, post-leg 2656 (+9), zero regressions. **No gap surfaced** — canonical Message shape is portable across all 4 providers' encoders. "Task #25" concern from F7 debrief Rec #1(d) appears overstated at the encoder level.
- **L4 (`hat-multi-provider-swap`) retired per F8 conditional plan**: L4 was gated on L1 surfacing a real fix; L1 surfaced no gap, no fix shipped. F8 now ships as a 3-leg flight (L1 + L2 + L3). The "Legs" list in the flight artifact still reads with L4 marked optional; the Phase 2d commit will check it off as "skipped (L1 surfaced no gap requiring HAT validation)".
- Phase 2c → Phase 2a (L2 design).

### Pending operator prerequisites
- Stash/commit/restore the stray `docker-compose.yml` modification before final commit, OR Flight Director carefully stages only F8-relevant paths at Phase 2d commit time (the latter is the default since operator hasn't acted).

