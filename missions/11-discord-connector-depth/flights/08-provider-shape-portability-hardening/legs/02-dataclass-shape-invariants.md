# Leg: dataclass-shape-invariants

**Status**: completed
**Flight**: [Provider-Shape-Portability Hardening](../flight.md)

## Objective

Apply Architect-resolved pick (c) — widen `ToolResult.content` annotation + `__post_init__` JSON-stringifies non-str on construction; add parallel `Message.content` `__post_init__` `isinstance` assertion — so the canonical dataclasses enforce shape invariants at construction time. Delete F7's surgical 12.l Anthropic coercion (now redundant); annotate 12.m `truncate_for_event` as belt-and-suspenders; verify `cli.py:83-85` works unchanged. Codify the `provider-shape-portability` convention in `the_one/agents.md`.

## Context

This is the second leg of F8 and the architectural heart of the flight. L1 landed clean (no gap surfaced at the encoder level), confirming the canonical Message shape is portable across all 4 providers' `_to_api_message` paths. L2 turns that empirical observation into a structural guarantee: the dataclasses themselves enforce the contract, so future tools, providers, and codec consumers inherit it without rediscovering the bug.

Relevant flight-level decisions (from `../flight.md`):
- **§1 enforcement shapes**: `ToolResult.content: str | dict | list[Any]` with `__post_init__` JSON-stringify normalization. `Message.content: str = ""` with `__post_init__` `assert isinstance(self.content, str)`. Assertion vs normalization is the deliberate asymmetry — structured tool returns are legitimate (channel-context tools return `list[dict]`); a non-str on a Message is a provider-parser defect we want surfaced.
- **§3 L2+L3 collapse — L3 had been Message.content invariant**: per operator decision, L3 was folded into L2 so both invariants ship in one commit/review surface. L3-renumbered (`mask-shape-single-source`) handles the api.py mask refactor.
- **Hard fence**: L1 forbade touching `the_one/llm/base.py`; L2 IS the leg that touches it. L3 (mask-shape) and any future L4 do not touch base.py.

Carry-forward from L1:
- L1's `test_tool_result_content_non_str_diverges_per_provider` was authored with a forward-looking comment ("this will need updating in L2 when `__post_init__` normalizes") at `tests/test_llm_provider_cross_provider_history.py:512-524`. L2 inverts it (per state-machine-reachability audit guidance: rename rather than delete-and-readd).
- L1's `_make_tool_msg`-equivalent pattern in the same test (lines 525-545) bypasses `__post_init__` via post-construction direct assignment. Under L2 this is an explicit anti-pattern.

Codebase landscape (verified):
- `the_one/llm/base.py:Message` (lines 41-96) and `ToolResult` (lines 27-32) — the targets.
- `the_one/agent/core.py:336` — `ToolResult(content=output)` wraps tool returns; this is THE construction site that benefits from `__post_init__` normalization (L10 channel-context tools return `list[dict]`).
- `the_one/llm/anthropic_provider.py:219-249` — the 12.l Anthropic coercion to delete.
- `the_one/db/codec.py:18-39` — `truncate_for_event` to annotate.
- `the_one/interfaces/cli.py:83-85` — recon-omitted consumer; `len(output)` works under L2 because content is str post-construction.
- 13+ test files construct `ToolResult(...)` directly (see Implementation Guidance §6 for the audit list); most use str content and are unaffected.

## Inputs

- L1 landed at HEAD; no commits between L1 and L2 (Phase 2 leg cycle defers all commits to Phase 2d).
- Branch: `flight/08-provider-shape-portability-hardening`, ahead of main by 1 commit (`b71a6e1` planning commit).
- Pre-L2 test baseline: 2656 passed (post-L1, recorded in flight-log Leg Progress entry for L1).
- F8 flight artifact + flight-log artifact ground truth.
- Stray `docker-compose.yml` modification in working tree — leave alone (per L1 inputs).

## Outputs

- `the_one/llm/base.py` modified:
  - `ToolResult.content` annotation widened to `str | dict | list[Any]`.
  - `ToolResult.__post_init__` added — JSON-stringifies non-str.
  - `Message.__post_init__` added — asserts `isinstance(self.content, str)`.
  - Docstrings updated to reflect new invariants.
- `the_one/llm/anthropic_provider.py:219-249` — 12.l coercion deleted; reverts to single-line `content=msg.tool_result.content`.
- `the_one/db/codec.py:18-39` — `truncate_for_event` docstring annotated: "unreachable under L2 invariant but defends if invariant ever loosens."
- `tests/test_llm_provider_tool_result_serialization.py` — fully rewritten: old tests (12.l encoder-level coercion) replaced with construction-level normalization tests. The file's name stays (still tests tool-result serialization, just at the new boundary). The `_make_tool_msg` helper is removed (its post-construction-assignment pattern is now an anti-pattern).
- `tests/test_llm_provider_cross_provider_history.py:test_tool_result_content_non_str_diverges_per_provider` — renamed to `test_tool_result_content_normalized_at_construction_uniformly`; assertions inverted (all 4 providers now see JSON-str, no divergence). Comment block removed (no longer "current pre-L2 behavior").
- `tests/test_truncate_for_event_non_str_coercion.py` — kept; docstring header annotated to note the path is unreachable from normal flow post-L2 (defends only against direct callers of `truncate_for_event` with non-str input, which is now an anti-pattern).
- `tests/test_connectors_inference.py` — **DELETE** the test at lines ~580-620 (the "provider returns Message with content=None → function returns False without AttributeError" test, which constructs `Message(role=Role.ASSISTANT, content=None)` to bypass `Message.assistant`'s `content=""` default). Under L2's `Message.__post_init__` assert, that construction crashes at `__init__`-time — the corner case the test defends against is now structurally unreachable, and the defense moves from the consumer (`run_engagement_inference`) to the dataclass constructor. The corresponding defensive branch in `run_engagement_inference` (whatever its content-is-None handling is) becomes dead code; L2 does NOT remove it (out-of-scope — that's an inference-engine cleanup for a future maintenance leg). Just delete the test and note the dead code in the flight log.
- `flight.md` — status header already at `in-flight` from L1; check off `dataclass-shape-invariants` in the Legs list under "In-Flight".
- New tests added (in the rewritten `test_llm_provider_tool_result_serialization.py` OR a new `test_llm_dataclass_invariants.py` — see Implementation Guidance §7 for the call):
  - `ToolResult(content=non_str)` normalizes at construction (list, dict, nested).
  - `Message(content=non_str)` raises AssertionError at construction.
  - `Message.tool(ToolResult(content=non_str))` works (because ToolResult normalizes first).
  - Factory methods (`Message.system`, `Message.user`, `Message.assistant`, `Message.tool`) all build str-content messages.
- `the_one/agents.md` — new `provider-shape-portability` convention section added under `## Project Conventions` (specific position per Implementation Guidance §8).
- Flight log entry under "Leg Progress" with pre-leg baseline, post-leg total, files touched, and rewritten-test-count.

## Acceptance Criteria

- [x] `ToolResult.content` annotation in `the_one/llm/base.py` reads `str | dict | list[Any]`.
- [x] `ToolResult.__post_init__` exists at `the_one/llm/base.py` and JSON-stringifies non-str content. Verifiable via:
  ```python
  tr = ToolResult(tool_call_id="t1", content=[{"k": "v"}])
  assert isinstance(tr.content, str)
  assert json.loads(tr.content) == [{"k": "v"}]
  ```
- [x] `Message.__post_init__` exists at `the_one/llm/base.py` and asserts `isinstance(self.content, str)`. Verifiable via:
  ```python
  with pytest.raises(AssertionError):
      Message(role=Role.USER, content=42)  # type: ignore[arg-type]
  ```
- [x] The 12.l Anthropic coercion at `the_one/llm/anthropic_provider.py:219-249` is DELETED. The TOOL+tool_result branch reverts to:
  ```python
  if msg.role == Role.TOOL and msg.tool_result:
      return {
          "role": "user",
          "content": [
              {
                  "type": "tool_result",
                  "tool_use_id": msg.tool_result.tool_call_id,
                  "content": msg.tool_result.content,
                  "is_error": msg.tool_result.is_error,
              }
          ],
      }
  ```
  The `import json` at the top of `anthropic_provider.py` may now be unused — verify and remove if so (no other use in the file per grep).
- [x] `the_one/db/codec.py:truncate_for_event` keeps its `if not isinstance(content, str):` branch but its docstring is updated to note that the branch is unreachable from normal flow post-L2 invariant; defends only against direct non-str passes by callers that bypass the invariant.
- [x] `the_one/interfaces/cli.py:83-85` — `len(msg.tool_result.content)` works unchanged. Verifiable by running CLI tests / smoke-running the CLI agent loop with a channel-context tool call.
- [x] `tests/test_llm_provider_tool_result_serialization.py` rewritten:
  - The 8 existing tests (which exercise 12.l encoder-level coercion via `_make_tool_msg` post-construction assignment) are REPLACED with construction-level normalization tests.
  - New tests pin: `ToolResult(content=...)` normalizes at construction (list, dict); all 4 providers' `_to_api_message` see str content; the encoder branches no longer perform any coercion; `Message.tool(ToolResult(content=non_str))` produces a Message with str content.
  - The `_make_tool_msg` helper is removed.
- [x] `tests/test_llm_provider_cross_provider_history.py:test_tool_result_content_non_str_diverges_per_provider` renamed to `test_tool_result_content_normalized_at_construction_uniformly`; assertions inverted (all 4 providers see same JSON-str output); pre-L2 comment block removed.
- [x] `tests/test_truncate_for_event_non_str_coercion.py` kept; module-level docstring annotated to reflect post-L2 reachability.
- [x] New `provider-shape-portability` convention section added to `the_one/agents.md` under `## Project Conventions` → `### Project-wide` (alphabetical ordering by convention slug if the file follows that; otherwise insert near the existing related conventions — see Implementation Guidance §8).
- [x] `make test-unit` passes; **predicted post-L2 count = 2656 + 9 (new construction-time + provider-consumes-str tests) − 8 (deleted from `test_llm_provider_tool_result_serialization.py`) − 1 (deleted `Message(content=None)` test from `test_connectors_inference.py`) = 2656** (net delta = 0). Plus 1-2 new tests for `Message.__post_init__` assertion behavior (added in §3 or in a new module-level location). Final predicted count: 2657-2658. If the actual count deviates by >2 from this prediction, document the deviation in the flight log. Zero failures.
- [x] No production code outside L2's scope is touched. Specifically: NO changes to `the_one/connectors/`, `the_one/agent/`, `the_one/tools/`, `the_one/interfaces/web/`, or any UI files. (Audit via `git diff --stat` at leg end.)
- [x] Flight log entry under "Leg Progress" with: pre/post baseline counts, files touched, tests added/deleted/renamed, anti-pattern note for `_make_tool_msg` removal.

## Verification Steps

1. **`ToolResult.__post_init__` works**:
   ```
   docker exec the-one python -c "
   from the_one.llm.base import ToolResult
   import json
   tr = ToolResult(tool_call_id='t1', content=[{'k': 'v'}])
   assert isinstance(tr.content, str), f'Expected str, got {type(tr.content)}'
   assert json.loads(tr.content) == [{'k': 'v'}]
   print('OK')
   "
   ```

2. **`Message.__post_init__` asserts**:
   ```
   docker exec the-one python -c "
   from the_one.llm.base import Message, Role
   try:
       Message(role=Role.USER, content=42)
       print('FAIL — should have raised AssertionError')
   except AssertionError:
       print('OK')
   "
   ```

3. **12.l deletion verified**:
   ```
   grep -n "json.dumps(content)" the_one/llm/anthropic_provider.py
   ```
   Expected: NO match (the only `json.dumps(content)` in that file was the 12.l coercion).

   ```
   grep -nE "^\s*import json" the_one/llm/anthropic_provider.py
   ```
   Expected: either NO match (if `json` was only used by 12.l — verify with `grep -n "json\." the_one/llm/anthropic_provider.py`) OR a single match if `json` is still used elsewhere in the file.

4. **CLI works unchanged**:
   ```
   docker exec the-one python -c "
   from the_one.llm.base import Message, Role, ToolResult
   tr = ToolResult(tool_call_id='t1', content=[{'k': 'v', 'large': 'x' * 100}])
   msg = Message.tool(tr)
   # cli.py:83-85 logic equivalent
   output = msg.tool_result.content
   assert isinstance(output, str)
   truncated = output[:500] + ('...' if len(output) > 500 else '')
   print(f'OK — content is str, length={len(output)}, truncated_ok={len(truncated)<=503}')
   "
   ```

5. **Full unit suite passes**:
   ```
   make test-unit
   ```
   Expected: count = pre-L2 (2656) + N_new - N_deleted (8 from `test_llm_provider_tool_result_serialization.py`). Zero failures.

6. **Targeted test files run cleanly** (verify the rewrites + renames):
   ```
   docker exec the-one pytest tests/test_llm_provider_tool_result_serialization.py tests/test_llm_provider_cross_provider_history.py tests/test_truncate_for_event_non_str_coercion.py -x --timeout 30 -v
   ```

7. **Diff scope audit** — verify no out-of-scope production code touched:
   ```
   git diff --stat main..HEAD
   ```
   Expected files in production-code paths (excluding tests, missions/, agents.md):
   - `the_one/llm/base.py` (touched)
   - `the_one/llm/anthropic_provider.py` (touched — 12.l deletion)
   - `the_one/db/codec.py` (touched — docstring only)
   - `the_one/agents.md` (touched — new convention)

   NO other production-code paths should appear.

8. **Flight log entry**:
   ```
   grep -A 5 "### dataclass-shape-invariants" missions/11-discord-connector-depth/flights/08-provider-shape-portability-hardening/flight-log.md
   ```
   Expected: leg-progress section with outcome summary.

## Implementation Guidance

### 1. Order of operations

1. **Re-pin pre-L2 baseline**: run `make test-unit`, record the passed count (should be 2656 from L1; verify).
2. Update leg status `planning` → `ready` → `in-flight` (this artifact's header).
3. **Implement `ToolResult.__post_init__` FIRST** at `the_one/llm/base.py`. Widen the annotation, add post_init. Run a targeted test to confirm: `docker exec the-one python -c "from the_one.llm.base import ToolResult; print(ToolResult(tool_call_id='t', content=[1,2]).content)"` should print `"[1, 2]"`.
4. **Run `make test-unit`** to see what breaks. Likely failures: the 8 tests in `test_llm_provider_tool_result_serialization.py` that pass non-str via `_make_tool_msg` and expect encoder-level coercion. They'll fail because (a) the helper does post-construction assignment which still bypasses post_init, so non-str reaches the encoder, AND (b) after deleting 12.l in step 6, Anthropic passes through non-str which would crash at the wire (but we don't reach the wire in unit tests — the test asserts the encoded dict). So actually they may fail at the assertion level, not at the wire.
   - **Important**: the existing tests use `_make_tool_msg` which does `tr.content = content` AFTER construction. `__post_init__` only runs at `__init__`-time, so direct field assignment bypasses normalization. The tests would still pass non-str to the encoder.
   - The right fix is to REWRITE these tests (per state-machine-reachability audit) rather than rely on the helper. See §3.
5. **Implement `Message.__post_init__` SECOND**. Add the assert. Run `make test-unit` — expected: no new failures (Message construction always uses str content per the codebase audit; the assert is defensive).
6. **Delete the 12.l Anthropic coercion** at `the_one/llm/anthropic_provider.py:219-249`. Verify the import is still needed (`grep -n "json\." the_one/llm/anthropic_provider.py`) — if not, remove `import json` from the top of the file.
7. **Annotate `truncate_for_event` docstring** at `the_one/db/codec.py:18-39`. Add a sentence about post-L2 unreachability.
8. **Rewrite `tests/test_llm_provider_tool_result_serialization.py`** — see §3.
9. **Rename + invert** the L1 test `test_tool_result_content_non_str_diverges_per_provider` at `tests/test_llm_provider_cross_provider_history.py:507-545` — see §4.
10. **Annotate** `tests/test_truncate_for_event_non_str_coercion.py` module docstring — see §5.
11. **Codify the convention** in `the_one/agents.md` — see §8.
12. **Run `make test-unit`** to confirm green. Resolve any failures.
13. **Run** the verification steps from above.
14. Update flight-log.md with the leg-progress entry — see §9.
15. Set leg status to `landed`.
16. **Do NOT commit** — Flight Director batches at Phase 2d. Signal `[HANDOFF:review-needed]`.

### 2. The two `__post_init__` implementations

Read the current `Message` (lines 41-96) and `ToolResult` (lines 27-32) carefully — they're `@dataclass` decorated. `__post_init__` is a stdlib dataclass hook.

`ToolResult`:

```python
@dataclass
class ToolResult:
    tool_call_id: str
    content: str | dict | list[Any]
    is_error: bool = False
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Normalize non-str content to JSON-str at construction.

        M11 F8 L2: the canonical wire-shape for tool_result content is
        ``str``. The agent loop at ``the_one/agent/core.py:336`` wraps
        tool returns as ``ToolResult(content=output)`` where ``output``
        may be a structured ``dict``/``list`` (e.g. L10 channel-context
        tools return ``list[dict]``). Normalizing here means every
        downstream consumer — provider ``_to_api_message``, codec
        encoding, telemetry projection, CLI rendering — reads ``str``
        uniformly. Removes the need for F7 12.l's per-encoder coercion.

        See ``the_one/agents.md`` → ``provider-shape-portability``.
        """
        if not isinstance(self.content, str):
            self.content = json.dumps(self.content)
```

Note: `json` import must be added to `the_one/llm/base.py` top — it's not currently imported there.

`Message`:

```python
@dataclass
class Message:
    role: Role
    content: str = ""
    # ... (existing fields)

    def __post_init__(self) -> None:
        """Assert content is str at construction time.

        M11 F8 L2: ``Message.content`` is constructed at three classes
        of sites — provider response parsers (build str from API
        response), codec decoders (decode str from JSON), and factory
        methods (``Message.system``/``user``/``assistant``/``tool``).
        A non-str arriving here means a provider-parser defect, NOT
        a legitimate structured payload (compare ``ToolResult.content``
        which CAN be structured pre-normalization). Assert rather than
        normalize so the defect surfaces loudly.

        See ``the_one/agents.md`` → ``provider-shape-portability``.
        """
        assert isinstance(self.content, str), (
            f"Message.content must be str, got {type(self.content).__name__}"
        )
```

### 3. Rewriting `tests/test_llm_provider_tool_result_serialization.py`

The existing 8 tests pin 12.l encoder-level coercion. Under L2 the contract moves to `ToolResult.__post_init__`. The rewrite shape:

- **Delete** `_make_tool_msg` helper (lines 86-98) — its post-construction-assignment pattern is the anti-pattern documented in the `provider-shape-portability` convention text (§8) — direct attribute assignment after construction bypasses `__post_init__` and reintroduces the shape-loss this leg prevents.
- **Delete** the 8 existing test methods.
- **Add** new tests that pin construction-time normalization:

```python
class TestToolResultContentNormalizationAtConstruction:
    def test_tool_result_normalizes_list_of_dicts_to_json_string(self) -> None:
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        assert isinstance(tr.content, str)
        assert json.loads(tr.content) == LIST_OF_DICTS_RESULT

    def test_tool_result_normalizes_dict_to_json_string(self) -> None:
        tr = ToolResult(tool_call_id="t1", content=DICT_RESULT)
        assert isinstance(tr.content, str)
        assert json.loads(tr.content) == DICT_RESULT

    def test_tool_result_preserves_string_content_byte_identical(self) -> None:
        tr = ToolResult(tool_call_id="t1", content="plain string result")
        assert tr.content == "plain string result"  # byte-identical, not JSON-encoded

    def test_tool_result_normalizes_nested_structure(self) -> None:
        nested = {"channels": [{"id": "ch1", "members": [{"name": "alice"}]}]}
        tr = ToolResult(tool_call_id="t1", content=nested)
        assert isinstance(tr.content, str)
        assert json.loads(tr.content) == nested


class TestAllProvidersSeeStrToolResultContent:
    """Post-L2, every provider's _to_api_message receives str content
    because ToolResult.__post_init__ has already normalized. The
    encoders no longer need provider-specific coercion (12.l deleted).
    """

    def test_anthropic_encodes_normalized_content_without_special_casing(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["content"] == tr.content  # already-str
        assert json.loads(block["content"]) == LIST_OF_DICTS_RESULT

    def test_openai_encodes_normalized_content_without_special_casing(
        self, openai_provider: OpenAIProvider
    ) -> None:
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        result = openai_provider._to_api_message(msg)
        assert result["content"] == tr.content  # already-str
        assert json.loads(result["content"]) == LIST_OF_DICTS_RESULT

    def test_ollama_encodes_normalized_content_without_special_casing(
        self, ollama_provider: OllamaProvider
    ) -> None:
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT)
        msg = Message.tool(tr)
        result = ollama_provider._to_api_message(msg)
        assert result["content"] == tr.content
        assert json.loads(result["content"]) == LIST_OF_DICTS_RESULT

    def test_preserves_is_error_flag_through_encoder(
        self, anthropic_provider: AnthropicProvider
    ) -> None:
        tr = ToolResult(tool_call_id="t1", content=LIST_OF_DICTS_RESULT, is_error=True)
        msg = Message.tool(tr)
        result = anthropic_provider._to_api_message(msg)
        block = result["content"][0]
        assert block["is_error"] is True
```

Keep the module-level fixtures and `LIST_OF_DICTS_RESULT` / `DICT_RESULT` constants — they're useful regardless.

The module docstring at the top of the file (lines 1-28) should be updated to reflect the new contract — the 12.l hotfix framing is gone, replaced by "construction-time normalization at ToolResult.__post_init__."

### 4. Renaming + inverting the L1 cross-provider divergence test

At `tests/test_llm_provider_cross_provider_history.py:507-545` the L1 test `test_tool_result_content_non_str_diverges_per_provider` exists. Under L2 this test name is wrong (no divergence) and the assertions are inverted. Apply:

- Rename method: `test_tool_result_content_non_str_diverges_per_provider` → `test_tool_result_content_normalized_at_construction_uniformly`.
- Remove the post-construction assignment pattern (`tr.content = non_str_payload`) — instead construct via `ToolResult(content=non_str)` directly so `__post_init__` runs.
- Invert assertions:
  - All 4 providers see str content (because of construction-time normalization).
  - Anthropic, OpenAI, Ollama all emit the SAME str content (via different shapes — Anthropic in `content[0]["content"]`, OpenAI/Ollama in top-level `content`).
- Remove the forward-looking comment block at lines 512-524 (no longer applicable).

New test body (approximate):

```python
def test_tool_result_content_normalized_at_construction_uniformly(
    self,
    anthropic_provider: AnthropicProvider,
    openai_provider: OpenAIProvider,
    ollama_provider: OllamaProvider,
) -> None:
    """Post-L2 (F8 dataclass-shape-invariants), ToolResult.__post_init__
    normalizes non-str content to JSON-str at construction. Every
    provider's _to_api_message receives str content uniformly — no
    provider-specific coercion at the encoder boundary.
    """
    non_str_payload: list[dict[str, object]] = [{"k": "v"}]
    expected_json = json.dumps(non_str_payload)

    # Construction-time normalization (no post-construction assignment).
    tr = ToolResult(tool_call_id="toolu_norm", content=non_str_payload)
    assert tr.content == expected_json  # already normalized

    msg = Message.tool(tr)
    assert msg.content == expected_json  # propagates through factory

    # Anthropic
    a_result = anthropic_provider._to_api_message(msg)
    assert a_result["content"][0]["content"] == expected_json

    # OpenAI
    o_result = openai_provider._to_api_message(msg)
    assert o_result["content"] == expected_json

    # Ollama
    ol_result = ollama_provider._to_api_message(msg)
    assert ol_result["content"] == expected_json
```

### 5. Annotating `truncate_for_event` and `tests/test_truncate_for_event_non_str_coercion.py`

The 6 tests in this file exercise `truncate_for_event`'s isinstance branch with direct non-str inputs (`truncate_for_event([{"k": "v"}])`). Under L2 this code path is reachable only by:
- Direct callers of `truncate_for_event` that pass non-str (anti-pattern; should pass `ToolResult.content` which is always str).
- A future loosening of the invariant.

**Two annotation sites** — keep tests, extend prose at BOTH:

(a) `the_one/db/codec.py:truncate_for_event` (lines 18-39): the existing docstring already has a paragraph explaining the non-str coercion rationale (the "Non-string content (e.g. structured dicts/lists)..." paragraph at current lines 25-31). **Do NOT replace this prose** — it preserves the rationale's git-blame history. Instead, APPEND a new paragraph at the end of the docstring:

> M11 F8 L2 update — post-L2 reachability: this defensive branch is no longer reached by normal flow because `ToolResult.__post_init__` JSON-normalizes non-str content at construction. The branch remains as belt-and-suspenders that defends the projection path if the L2 invariant ever loosens or a caller passes a non-`ToolResult.content` value directly. See `the_one/agents.md` → `provider-shape-portability`.

(b) `tests/test_truncate_for_event_non_str_coercion.py`: extend the module-level docstring (top of file) with a matching note:

> Post-L2 reachability: these tests exercise `truncate_for_event`'s defensive non-str coercion branch. Post-L2 (`ToolResult.__post_init__` normalization), normal flow never reaches this branch; the tests defend the projection path against a future invariant-loosening or direct non-str caller. Mirror of the rationale at `the_one/db/codec.py:truncate_for_event` docstring.

### 6. Audit: `ToolResult` constructions across tests and source

The 13+ test files plus 5 source files that construct `ToolResult(...)` were audited at design time. Findings:

- **All current source-side constructions use str content** at construction time:
  - `the_one/db/codec.py:106` — decodes from dict, `content=tr["content"]`; pre-L2 stored content may be non-str (rare, only if pre-L2 the codec serialized a non-str ToolResult). Under L2, `__post_init__` normalizes on first decode. **No code change needed**; the back-compat is automatic.
  - `the_one/agent/core.py:265, 343, 356` — wraps tool execute outputs; this is THE intentional non-str source. `__post_init__` normalizes. **No code change needed**.
- **Test-side constructions** — most pass str content; the exceptions are the `_make_tool_msg`-using tests in `test_llm_provider_tool_result_serialization.py` (rewritten per §3) and the L1 test's post-construction assignment pattern (renamed per §4). No other tests need rewriting.

The `Message(role=..., content=...)` direct constructions are sparse. The `message_from_dict` decoder at `codec.py:119-133` decodes from a JSON dict where `content` is always str. Provider response parsers always build str content. The assert is safe.

### 7. Test file placement: rewrite in place + preserve class shape

Per the state-machine-reachability audit, the rename-and-invert pattern is preferred over delete-and-readd for git-blame preservation. Apply this at the FILE level: keep `tests/test_llm_provider_tool_result_serialization.py` in place; rewrite its CONTENTS. Do NOT create a new `test_llm_dataclass_invariants.py` — the file's purpose is still "test tool-result serialization," the boundary just moved from encoder to construction.

**Class structure**: preserve the existing per-provider class shape AND add a new class for construction-time tests:

- **Keep** the three existing per-provider classes (`TestAnthropicToolResultSerialization`, `TestOpenAIToolResultSerialization`, `TestOllamaToolResultSerialization`) as the homes for the rewritten provider-encodes-normalized-content tests. Rename their docstrings (and possibly rename the classes — e.g., suffix `…UnderL2Invariant`) to reflect the new boundary. The class shape is the file's organization signature; preserving it makes the L2 rewrite legible as "what used to test encoder coercion now tests post-normalization passthrough."
- **Add** one new class `TestToolResultContentNormalizationAtConstruction` containing the construction-time tests (`tr = ToolResult(content=non_str)` → assert `tr.content` is JSON-str). This class doesn't fit the per-provider pattern; it's the canonical-shape-at-construction class.

The §3 sketch above shows both shapes mixed together for clarity; the actual file should keep them in three per-provider + one normalization classes.

### 8. Codifying the `provider-shape-portability` convention in `the_one/agents.md`

Insert as a new section. Use this text (refine wording during implementation if it feels off):

```markdown
### `provider-shape-portability`

**Convention**: The canonical `Message` and `ToolResult` dataclasses in `the_one/llm/base.py` ARE the portable shape across LLM providers. Provider-specific encoding lives entirely in each `LLMProvider._to_api_message`; provider-specific decoding lives entirely in the response parser. No provider-specific shape leaks back into the dataclass before persistence.

**Mechanism**:
- `ToolResult.__post_init__` JSON-stringifies non-str content at construction — so every consumer (4 providers, codec, telemetry, CLI) reads `str` uniformly. Removes the need for per-encoder coercion (the F7 12.l hotfix that this convention replaces).
- `Message.__post_init__` asserts `isinstance(self.content, str)` — non-str arrival is a provider-parser defect surfaced as `AssertionError`, not silently coerced.

**Source**: M11 F8 L2 (dataclass-shape-invariants). Pinned by `tests/test_llm_provider_cross_provider_history.py` (canonical session round-trip across all 4 providers) and `tests/test_llm_provider_tool_result_serialization.py` (construction-time normalization).

**When this matters**:
- Adding a new provider — `_to_api_message` is the ONLY site where shape translation happens; consume `str` content uniformly.
- Adding a new tool — the agent loop wraps tool returns as `ToolResult(content=output)`; `__post_init__` normalizes structured returns automatically. Tool authors return native shapes; the canonical-wire-shape conversion is at the dataclass boundary.
- Refactoring the codec — both encode and decode paths produce/consume str content via the dataclass invariants.

**Anti-pattern**: post-construction direct field assignment (e.g., `tr.content = some_list`). Bypasses `__post_init__` and reintroduces the shape-loss this convention prevents. The annotation is `str | dict | list[Any]` for permissive constructor callers; `__post_init__` enforces the str invariant once the dataclass exists. Tests that need a non-str field must construct fresh via `ToolResult(content=non_str)` (which normalizes), or use `dataclasses.replace`. Never reach in via attribute assignment.
```

Position: **insert under `## Project Conventions` → `### Project-wide`, near `cross-subsystem-pattern-premise-revalidation` (line 122).** The agents.md conventions are organized thematically (not alphabetical, despite that initial guess at design time — cycle-1 reviewer caught this), and `cross-subsystem-pattern-premise-revalidation` is the strongest thematic anchor: it codifies the F7 audit-history pattern that L2 directly closes by replacing the 12.l surgical-coercion with the dataclass-shape invariant. Insert `provider-shape-portability` immediately AFTER `cross-subsystem-pattern-premise-revalidation` and BEFORE `prompt-discipline-needs-mechanical-fallback`. The implementer should re-read the surrounding conventions before settling the exact line; if a better thematic neighbor appears, justify the choice in the flight log.

### 9. Flight-log entry template

Append under `## Leg Progress`:

```markdown
### dataclass-shape-invariants

**Status**: landed
**Started**: {ISO timestamp}
**Completed**: {ISO timestamp}

#### Changes Made
- `the_one/llm/base.py`: widened `ToolResult.content: str | dict | list[Any]`; added `ToolResult.__post_init__` (JSON-normalize) and `Message.__post_init__` (str-assert).
- `the_one/llm/anthropic_provider.py`: deleted 12.l coercion (lines were 219-249 pre-L2; resulting branch is ~10 LOC). `json` import {removed | retained — describe}.
- `the_one/db/codec.py`: `truncate_for_event` docstring annotated.
- `tests/test_llm_provider_tool_result_serialization.py`: REWRITTEN. Deleted: 8 tests + `_make_tool_msg` helper. Added: {N} construction-time normalization + provider-consumes-str tests.
- `tests/test_llm_provider_cross_provider_history.py`: renamed `test_tool_result_content_non_str_diverges_per_provider` → `test_tool_result_content_normalized_at_construction_uniformly`; inverted assertions; removed forward-looking comment.
- `tests/test_truncate_for_event_non_str_coercion.py`: module docstring annotated (post-L2 unreachability note).
- `the_one/agents.md`: added `provider-shape-portability` convention section.

#### Notes
- Pre-L2 baseline: 2656 passed (per L1 leg progress).
- Post-L2 total: {N} passed. Delta = +{new} − 8 (deleted from serialization test file) = {net delta}.
- The `cli.py:83-85` consumer was verified unchanged-but-correct: `len(msg.tool_result.content)` works under the L2 invariant because content is str post-construction.
- `_make_tool_msg`'s removal documents the anti-pattern of post-construction direct assignment. The L1 test renaming preserves git-blame intent.
- No production code touched outside the L2 scope (audited via `git diff --stat`).
```

## Edge Cases

- **`Message.__post_init__` and `Message.tool(result)`** — the factory at base.py:138-145 calls `cls(role=Role.TOOL, content=result.content, tool_result=result, ...)`. If `result.content` is already str (which `ToolResult.__post_init__` guarantees), the assert passes. **Implement ToolResult's post_init BEFORE Message's** so the dataclass-decode order doesn't trip up.
- **`message_from_dict` at `codec.py:97-133`** — decodes `content=d.get("content", "")`. JSON-parsed values are str (or absent → ""). The assert passes for normal data. For legacy rows with non-str content (rare, only if pre-L2 the codec round-tripped a non-str), `__post_init__` would `AssertionError`. **This is intentional** — the assert surfaces the corruption. If a legacy row with non-str content is encountered, that's an L2-uncovered codec bug that L2 surfaces; document the AssertionError in flight log and treat as a real bug.
- **Python `-O` mode strips asserts** — `Message.__post_init__`'s assert disappears in `-O` mode. The trade-off is documented in F8 flight Design Decisions §1; cross-provider tests in L1 + the new construction tests catch defects before deployment. No mitigation needed beyond awareness.
- **`anthropic_provider.py` `import json` removal** — if `import json` is no longer used after deleting 12.l, remove it. Verify via grep before removing: `grep -n "json\." the_one/llm/anthropic_provider.py`. If `json` is used elsewhere (the codebase audit suggests it isn't, but verify), leave the import.
- **Existing tests using `dataclasses.replace(tr, content=non_str)`** — `replace` calls `__init__` which runs `__post_init__`. Non-str input gets normalized. Tests that depend on this behavior are functionally unchanged.
- **`metadata: dict[str, Any] | None` field on ToolResult** — not in L2 scope; no invariant added. Currently no `__post_init__` validation. Future maintenance flight may extend the convention.

## Files Affected

- `the_one/llm/base.py` — primary target. Two `__post_init__` additions + annotation widening + `import json`. ~25 LOC added.
- `the_one/llm/anthropic_provider.py` — 12.l deletion. ~25 LOC removed (the coercion branch + comment block). `import json` possibly removed (1 line).
- `the_one/db/codec.py` — docstring-only update at `truncate_for_event`. ~3 LOC of comment added.
- `tests/test_llm_provider_tool_result_serialization.py` — REWRITTEN. Existing ~280 LOC → new ~200 LOC (estimated). Delta is negative.
- `tests/test_llm_provider_cross_provider_history.py` — one test method renamed + body rewritten. ~30 LOC touched.
- `tests/test_truncate_for_event_non_str_coercion.py` — module docstring annotated. ~5 LOC added.
- `the_one/agents.md` — new convention section. ~25 LOC added.
- This leg artifact — status transitions.
- Flight log entry.

**Do NOT touch**:
- `the_one/connectors/` — out of L2 scope. The post-L2 ToolResult invariant applies but no connector code needs changes.
- `the_one/agent/core.py` — the construction site `ToolResult(content=output)` at line 336 still works; `__post_init__` runs at construction. No edit needed.
- `the_one/tools/connector_history.py` — channel-context tools keep returning `list[dict]`; the wrap site (`core.py:336`) normalizes. No edit needed.
- `the_one/interfaces/web/api.py` — out of scope (that's L3's territory for mask refactor).
- Any UI / studio / chat / mcp file — out of scope.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified via the commands in Verification Steps
- [x] Tests passing — full suite + targeted file run
- [x] Update flight-log.md with leg progress entry (template in Implementation Guidance §9)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Diff scope audit confirms no out-of-scope production code touched
- [x] **Do NOT commit** — Flight Director batches commits across all autonomous legs at Phase 2d
- [x] Signal `[HANDOFF:review-needed]`

## Citation Audit

15 citations verified against current code at leg design time (14 from initial draft + 1 added during cycle 1):

Initial draft:
- `the_one/llm/base.py:Message` lines 41-96 — OK
- `the_one/llm/base.py:ToolResult` lines 27-32 — OK (current annotation `content: str`)
- `the_one/llm/base.py:Message.tool` factory lines 138-145 — OK (uses `cls(...)` so `__post_init__` runs)
- `the_one/llm/anthropic_provider.py` 12.l coercion lines 219-249 — OK (confirmed live, contains the `json.dumps(content)` to delete)
- `the_one/llm/anthropic_provider.py` `import json` line 3 — OK (will likely be unused after 12.l deletion; verify with grep `json\.` after edit)
- `the_one/db/codec.py:truncate_for_event` lines 18-39 — OK (current isinstance branch to annotate; existing prose at lines 25-31 preserved)
- `the_one/db/codec.py:message_from_dict` lines 97-133 — OK (the decode path that runs `__post_init__` on legacy rows)
- `the_one/db/codec.py:_tool_result_to_dict` lines 46-56 — OK (encode side; `content=tr.content` — under L2, tr.content is always str)
- `the_one/agent/core.py:336` — OK (ToolResult wrap site; the canonical construction-time normalization beneficiary)
- `the_one/interfaces/cli.py:83-85` — OK (`len(output)` consumer; works unchanged under L2)
- `tests/test_llm_provider_tool_result_serialization.py` `_make_tool_msg` helper lines 86-98 — OK (anti-pattern to delete)
- `tests/test_llm_provider_cross_provider_history.py:test_tool_result_content_non_str_diverges_per_provider` lines 507-545 — OK (to rename + invert)
- `tests/test_truncate_for_event_non_str_coercion.py` — OK (path becomes belt-and-suspenders)
- `the_one/agents.md` `## Project Conventions` → `### Project-wide` section — initial guess of "alphabetical, near `prompt-discipline-needs-mechanical-fallback`" was WRONG (cycle-1 reviewer correction): the file is thematically organized. Updated reference: insertion point is near `cross-subsystem-pattern-premise-revalidation` (line 122) which is the strongest thematic anchor (cites the F7 12.l audit history that L2 closes).

Added during cycle 1 (Developer feedback):
- `tests/test_connectors_inference.py:603` — OK (the missed `Message(role=Role.ASSISTANT, content=None)` site that would crash on L2's assert; cycle-1 reviewer flagged as HIGH; resolution: delete the test per the leg's Outputs section).

## Design-Review Cycle Log

**Cycle 1 (2026-05-26, Developer reviewer)**: approve with changes. Findings + resolutions:

- **HIGH**: `tests/test_connectors_inference.py:603` constructs `Message(role=Role.ASSISTANT, content=None)` deliberately bypassing `Message.assistant`'s default. Under L2's assert this construction crashes. **Resolution**: DELETE the test (per Outputs section). The defended-against corner case becomes structurally unreachable post-L2; the dead consumer-side defensive branch in `run_engagement_inference` is noted as out-of-scope cleanup for a future maintenance leg.
- **MEDIUM**: agents.md insertion-point claim "alphabetical by slug" was incorrect — file is thematically grouped. **Resolution**: updated §8 to insert near `cross-subsystem-pattern-premise-revalidation` (line 122) as the strongest thematic anchor (cites F7 12.l audit history).
- **LOW**: flight.md update belongs in Outputs section, not just Post-Completion Checklist. **Resolution**: added to Outputs section.
- **LOW**: Predict exact net delta. **Resolution**: predicted 2657-2658 (2656 + 9 new − 8 deleted − 1 deleted; plus 1-2 new for Message.__post_init__ tests). Documented in Acceptance Criteria.
- **LOW**: §10 reference was orphaned (no §10 existed in leg). **Resolution**: §3's reference to "§10" replaced with cross-reference to the convention text in §8.
- **LOW**: `truncate_for_event` annotation should EXTEND existing prose, not replace. **Resolution**: §5 updated to make extend-not-replace explicit at both annotation sites (codec.py docstring + test file docstring).

Suggestions applied:
- Test class structure pinned: keep three per-provider classes (rewritten to reflect post-L2 boundary) + add `TestToolResultContentNormalizationAtConstruction` class for construction tests. §7 updated.
- 8-test count + helper deletion verified accurate (4 Anthropic + 2 OpenAI + 2 Ollama).
- `cli.py:83-85` consumer pattern verified unchanged-but-correct.
- `mcp/client.py:827` is `MCPToolResult` (distinct dataclass), correctly excluded.
- `json` import at `anthropic_provider.py:3` used only at 12.l site — will become removable after 12.l deletion.

Questions resolved at design time:
- Q: rewrite vs delete `test_connectors_inference.py:603`? **A: delete.** The assert IS the defense; the corner case is unreachable post-L2.
- Q: agents.md insertion thematic anchor? **A: `cross-subsystem-pattern-premise-revalidation`** (audit-pairing theme; cites the F7 12.l audit L2 closes).
- Q: test class structure for rewritten serialization file? **A: preserve per-provider classes + add new normalization class.**

Cycle 2: skipped (cycle-1 issues mechanical, fixes verifiable by re-reading the leg). If implementation surfaces new design issues that weren't addressed by cycle 1's fixes, escalate to human.

**Leg approved for implementation.** [HANDOFF:review-needed]
