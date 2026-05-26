# Leg: mask-shape-single-source

**Status**: completed
**Flight**: [Provider-Shape-Portability Hardening](../flight.md)

## Objective

Unify the two mask emitters (`_mask_secret_value` and `_mask_api_key`) and the recognizer regex (`_MASK_SHAPE_RE`) in `the_one/interfaces/web/api.py` so the mask pattern has a single source-of-truth — a future maintainer cannot drift the emit shape from the recognize shape and silently corrupt secret round-trips. Codify the `single-source-of-truth-for-paired-helpers` convention in `the_one/agents.md`.

## Context

This is the third (and last autonomous) leg of F8. The flight's recon report (in flight-log.md) classified this item as `confirmed-live` (low-risk) — the literals `"***"` and `"***...{tail4}"` are duplicated across the emit helpers and the recognize regex, all in the same function block of api.py, but no shared constant prevents drift. Operator confirmed in-scope.

Relevant flight-level decisions:
- **F8 §5** (Design Decisions, flight.md): "kept as a separate leg ... rather than folded into the dataclass-shape-invariants commit ... atomic-leg discipline benefits." Refactor stays its own leg + commit-batch slot.
- **L2 carry-forward**: `provider-shape-portability` convention added to `the_one/agents.md` at line 134 (post-L2 state). L3's `single-source-of-truth-for-paired-helpers` convention is the second new convention this flight ships.
- **No production scope outside api.py**: same hard-fence discipline as L1 and L2. Touches `the_one/interfaces/web/api.py` only (production); tests + agents.md.

Codebase landscape (verified post-L2):
- **Two mask emitters** with the same output shape:
  - `_mask_secret_value(value: Any) -> Any` at `the_one/interfaces/web/api.py:642-664` — for MCP/connector secrets dicts (dict-of-Any value support; non-str → `"***"`).
  - `_mask_api_key(key: str | None) -> str | None` at `the_one/interfaces/web/api.py:3055-3060` — for LLM provider `api_key` (str-or-None signature; simpler).
  - Both produce: `"***"` for short/None/non-string, `f"***...{value[-4:]}"` for long strings.
- **One recognizer** at `the_one/interfaces/web/api.py:_MASK_SHAPE_RE` line 685 — `re.compile(r"^\*\*\*(\.\.\..{1,4})?$")`. Used by `_looks_masked` (line 707) which is called at PUT handlers (`api.py:1140, 2402, 3179`) to preserve existing values on round-trip.
- **Sentinel** at `_MASKED_API_KEY_SENTINEL` line 678 — `"__MASKED__"`, a separate-concept canonical "preserve" marker (orthogonal to the visual-mask shape). Not in L3 scope.
- **Existing test coverage**: `tests/test_api_secret_mask_roundtrip.py` (~437 LOC at L1 design; verify count) covers MCP + connector + provider GET/PUT round-trips. The tests assert observable behavior (round-trip preserves the stored value) — the L3 refactor must not change any observable behavior.

## Inputs

- L2 landed at HEAD; no commits between L2 and L3 (Phase 2 leg cycle defers all commits to Phase 2d).
- Branch: `flight/08-provider-shape-portability-hardening`, ahead of main by 1 commit (`b71a6e1` planning commit) plus L1+L2 uncommitted changes in working tree.
- Pre-L3 test baseline: 2664 passed (post-L2, recorded in L2 leg-progress entry).
- Stray `docker-compose.yml` modification in working tree — leave alone (per L1+L2 inputs).
- F8 flight artifact + flight-log artifact ground truth.

## Outputs

- `the_one/interfaces/web/api.py` modified:
  - New module-level constants for the mask shape (single source-of-truth): `_MASK_PREFIX`, `_MASK_TAIL_SEPARATOR`, `_MASK_TAIL_LEN`.
  - New private helper `_emit_mask(value: str) -> str` — the single emit site. Returns `_MASK_PREFIX` for ≤`_MASK_TAIL_LEN`-char strings; `f"{_MASK_PREFIX}{_MASK_TAIL_SEPARATOR}{value[-_MASK_TAIL_LEN:]}"` for longer.
  - `_mask_secret_value` and `_mask_api_key` REFACTORED to call `_emit_mask` for str inputs. Each retains its existing guard logic (None/empty passthrough; non-str → wholesale `_MASK_PREFIX` for `_mask_secret_value`).
  - `_MASK_SHAPE_RE` REWRITTEN to build from the same constants via `re.escape` so the regex literal is no longer the duplication site.
- `tests/test_api_secret_mask_roundtrip.py` — extended with new tests that pin the regex-emit pairing (regex matches emit output uniformly across short and long strings; if a maintainer drifts one constant without the other, these tests fail). EXISTING tests must continue to pass unchanged (no observable behavior change).
- `the_one/agents.md` — new `single-source-of-truth-for-paired-helpers` convention section added under `## Project Conventions`. Placement near `provider-shape-portability` (L2's addition at line 134) as the strongest thematic anchor (both conventions concern preventing drift between paired/related helpers).
- `flight.md` — check off `mask-shape-single-source` in the Legs list.
- Flight log entry under "Leg Progress" with: pre-leg baseline, post-leg total, files touched, refactor LOC delta.

## Acceptance Criteria

- [x] Three new module-level constants exist near the existing mask helpers in `the_one/interfaces/web/api.py`:
  - `_MASK_PREFIX = "***"`
  - `_MASK_TAIL_SEPARATOR = "..."`
  - `_MASK_TAIL_LEN = 4`
- [x] New helper `_emit_mask(value: str) -> str` exists, returns `_MASK_PREFIX` for short (≤`_MASK_TAIL_LEN`) input and `f"{_MASK_PREFIX}{_MASK_TAIL_SEPARATOR}{value[-_MASK_TAIL_LEN:]}"` for longer. Docstring explains the single-source-of-truth role.
- [x] `_mask_secret_value` no longer has hardcoded `"***"` / `f"***...{value[-4:]}"` literals; it calls `_emit_mask(value)` for str inputs. Non-str (defensive wholesale-mask) still returns `_MASK_PREFIX` (also drawn from the constant, not a literal). None/empty preservation unchanged.
- [x] `_mask_api_key` no longer has hardcoded literals; it calls `_emit_mask(key)` for non-None/non-empty inputs. None/empty preservation unchanged.
- [x] `_MASK_SHAPE_RE` is rebuilt from `_MASK_PREFIX`, `_MASK_TAIL_SEPARATOR`, and `_MASK_TAIL_LEN` via `re.escape` — NO hardcoded `r"^\*\*\*(\.\.\..{1,4})?$"` literal remains in the file (verify by grep: `grep -n '\\\\\\*\\\\\\*' the_one/interfaces/web/api.py` should show no matches).
- [x] Existing tests at `tests/test_api_secret_mask_roundtrip.py` ALL continue to pass with NO changes to their assertions. The refactor must not alter observable behavior.
- [x] New tests added (in the same file or a new sibling — see Implementation Guidance §3) pinning the regex-emit pairing (5 total):
  - `test_mask_shape_re_matches_emit_mask_output_for_short_string` — `_MASK_SHAPE_RE.match(_emit_mask("ab"))` is truthy.
  - `test_mask_shape_re_matches_emit_mask_output_for_long_string` — `_MASK_SHAPE_RE.match(_emit_mask("longersecret123"))` is truthy AND output endswith expected tail (4 chars).
  - `test_mask_shape_re_rejects_unrelated_user_input` — values like `"***hello"` or `"abc"` do NOT match (regression coverage for the existing anchored-regex contract).
  - `test_mask_emitters_route_through_emit_mask` — `_mask_secret_value(x) == _emit_mask(x)` and `_mask_api_key(x) == _emit_mask(x)` for representative str inputs (pins the routing invariant).
  - `test_rendered_regex_matches_pre_l3_literal` — `_MASK_SHAPE_RE.pattern == r"^\*\*\*(\.\.\..{1,4})?$"` (regression net: catches a future Python `re.escape` semantic change OR an accidental constant-shape edit).
- [x] New `single-source-of-truth-for-paired-helpers` convention section added to `the_one/agents.md` under `## Project Conventions`, placed near `provider-shape-portability` (the convention text is in Implementation Guidance §4).
- [x] `make test-unit` passes; **predicted post-L3 count = 2664 + 5 (new pairing tests) = 2669**. If the actual count deviates by >2 from this prediction, document in flight log. Zero failures.
- [x] **Diff scope audit**: `git diff --stat L2-HEAD..HEAD` shows only `the_one/interfaces/web/api.py`, `tests/test_api_secret_mask_roundtrip.py`, `the_one/agents.md`, `flight.md`, `flight-log.md`, and this leg artifact touched. NO other production paths.
- [x] Flight log entry under "Leg Progress" with: pre/post baseline counts, files touched, LOC delta, new convention citation.

## Verification Steps

1. **Constants and helper exist**:
   ```
   docker exec the-one python -c "
   from the_one.interfaces.web.api import _MASK_PREFIX, _MASK_TAIL_SEPARATOR, _MASK_TAIL_LEN, _emit_mask, _MASK_SHAPE_RE
   assert _MASK_PREFIX == '***'
   assert _MASK_TAIL_SEPARATOR == '...'
   assert _MASK_TAIL_LEN == 4
   assert _emit_mask('ab') == '***'
   assert _emit_mask('longersecret123') == '***...t123'
   assert _MASK_SHAPE_RE.match(_emit_mask('longersecret123'))
   print('OK')
   "
   ```

2. **No hardcoded literals remain**:
   ```
   grep -nE '"\*\*\*' the_one/interfaces/web/api.py
   ```
   Expected: only matches that reference `_MASK_PREFIX` or that are inside `_emit_mask`'s f-string template (which is allowed — that's the construction site).

   ```
   grep -n 'f"\*\*\*\.\.\.' the_one/interfaces/web/api.py
   ```
   Expected: NO matches (the f-string template no longer hardcodes the prefix or separator).

   ```
   grep -n 'r"\^\\\\\\*\\\\\\*' the_one/interfaces/web/api.py
   ```
   Expected: NO matches (the regex is constructed from `re.escape(_MASK_PREFIX)`, not a raw-string literal).

3. **Existing mask round-trip tests pass unchanged**:
   ```
   docker exec the-one pytest tests/test_api_secret_mask_roundtrip.py -x --timeout 30 -v
   ```
   Expected: all tests pass; pre-existing test methods unchanged. Verify via `git diff tests/test_api_secret_mask_roundtrip.py` that only NEW test methods were added — no existing test body modified.

4. **New pairing tests pass**:
   ```
   docker exec the-one pytest tests/test_api_secret_mask_roundtrip.py -k "mask_shape_re" -x --timeout 30 -v
   ```
   Expected: 3+ new tests pass.

5. **Full unit suite passes**:
   ```
   make test-unit
   ```
   Expected: predicted count 2667 (pre-L3 2664 + 3 new). Zero failures.

6. **Diff scope audit**:
   ```
   git diff --stat main..HEAD -- the_one/ tests/ | grep -v -E "(missions/|^\s*$)"
   ```
   Expected files (production + tests, post-L1+L2+L3):
   - `the_one/llm/base.py` (L2)
   - `the_one/llm/anthropic_provider.py` (L2)
   - `the_one/db/codec.py` (L2)
   - `the_one/agents.md` (L2 + L3)
   - `the_one/interfaces/web/api.py` (L3)
   - `tests/test_llm_provider_cross_provider_history.py` (L1 + L2 rename)
   - `tests/test_llm_provider_tool_result_serialization.py` (L2 rewrite)
   - `tests/test_truncate_for_event_non_str_coercion.py` (L2 annotate)
   - `tests/test_connectors_inference.py` (L2 deletion)
   - `tests/test_api_secret_mask_roundtrip.py` (L3 additions)

   NO other production files. NO connector / agent / UI / studio paths.

7. **Flight log entry**:
   ```
   grep -A 3 "### mask-shape-single-source" missions/11-discord-connector-depth/flights/08-provider-shape-portability-hardening/flight-log.md
   ```

## Implementation Guidance

### 1. Order of operations

1. **Re-verify pre-L3 baseline**: run `make test-unit`, confirm count is 2664 (post-L2). Record actual in flight log.
2. Update leg status `ready` → `in-flight`.
3. Read the current code at `the_one/interfaces/web/api.py:642-707` (mask helpers + regex + recognizer) AND at `api.py:3055-3060` (provider api_key mask). Both will be modified.
4. **Implement the constants** at module level near the existing helpers (insert just before `_mask_secret_value`):
   ```python
   # Mask-shape single source-of-truth. The emit helper, the recognize
   # regex, and any future paired helper read these constants; never
   # hardcode the literals. M11 F8 L3.
   _MASK_PREFIX = "***"
   _MASK_TAIL_SEPARATOR = "..."
   _MASK_TAIL_LEN = 4
   ```
5. **Implement `_emit_mask`** (insert immediately after the constants):
   ```python
   def _emit_mask(value: str) -> str:
       """Single source-of-truth for mask shape.

       Assumes a non-empty ``str`` input — callers guard ``None`` / empty
       / non-str before calling. Returns ``_MASK_PREFIX`` (no tail) for
       short values where exposing the tail would leak too much; returns
       ``_MASK_PREFIX + _MASK_TAIL_SEPARATOR + value[-_MASK_TAIL_LEN:]``
       for longer values.

       Pair: ``_MASK_SHAPE_RE`` (below) recognizes the output of this
       helper. Both read from the same constants so a future maintainer
       cannot drift the emit shape from the recognize shape. See
       ``the_one/agents.md`` → ``single-source-of-truth-for-paired-helpers``.
       """
       if len(value) <= _MASK_TAIL_LEN:
           return _MASK_PREFIX
       return f"{_MASK_PREFIX}{_MASK_TAIL_SEPARATOR}{value[-_MASK_TAIL_LEN:]}"
   ```
6. **Refactor `_mask_secret_value`** (at lines 642-664) to route str inputs through `_emit_mask`:
   ```python
   def _mask_secret_value(value: Any) -> Any:
       """Mask a single secret value mirroring ``_mask_api_key``'s shape.

       [Existing docstring preserved, with the update noting it now
       routes through ``_emit_mask`` for the str case.]
       """
       if not value:
           return value
       if not isinstance(value, str):
           # Non-string secret values (e.g., a nested dict for OAuth
           # tokens in F5) — mask wholesale to avoid leaking nested
           # structure. F5 will revisit this when access/refresh tokens
           # land. M11 F8 L3: drawn from _MASK_PREFIX constant.
           return _MASK_PREFIX
       return _emit_mask(value)
   ```
7. **Refactor `_mask_api_key`** (at lines 3055-3060) to route through `_emit_mask`:
   ```python
   def _mask_api_key(key: str | None) -> str | None:
       if not key:
           return key
       return _emit_mask(key)
   ```
8. **Rebuild `_MASK_SHAPE_RE`** (at line 685) from constants:
   ```python
   # Matches the exact output shape of ``_emit_mask`` — either
   # ``_MASK_PREFIX`` alone (short / non-string secrets) or
   # ``_MASK_PREFIX + _MASK_TAIL_SEPARATOR + tail-of-1-to-_MASK_TAIL_LEN-chars``
   # (longer secrets). Anchored on both sides so a legitimate user-supplied
   # value that merely starts with ``***`` (e.g. ``***hello``) is NOT
   # mistaken for a mask. Built from the same constants ``_emit_mask`` uses
   # so the emit and recognize shapes cannot drift. M11 F8 L3.
   _MASK_SHAPE_RE = re.compile(
       rf"^{re.escape(_MASK_PREFIX)}"
       rf"({re.escape(_MASK_TAIL_SEPARATOR)}.{{1,{_MASK_TAIL_LEN}}})?$"
   )
   ```

   Verify the rendered pattern is byte-identical to the old hardcoded `r"^\*\*\*(\.\.\..{1,4})?$"`. (Both `re.escape("***")` → `\*\*\*` and `re.escape("...")` → `\.\.\.` produce the same escape sequences.)
9. **Update the `_looks_masked` docstring** at lines 688-707 to reference `_emit_mask` instead of "`_mask_secret_value` / `_mask_api_key`" (one canonical source now). The docstring body otherwise unchanged.
10. **Add new pairing tests** in `tests/test_api_secret_mask_roundtrip.py` — see §3.
11. **Codify the convention** in `the_one/agents.md` — see §4.
12. **Verify**: run `make test-unit` (expect 2667 passed); run the targeted verification commands from Verification Steps above.
13. Update flight-log.md with the leg-progress entry — see §5.
14. Set leg status to `landed`.
15. Check off `mask-shape-single-source` in flight.md Legs list.
16. **Do NOT commit** — Flight Director batches at Phase 2d. Signal `[HANDOFF:review-needed]`.

### 2. Refactor risks

- **Behavior preservation is paramount**. The whole point of the refactor is that observable behavior is identical. Run `tests/test_api_secret_mask_roundtrip.py` after each step (after constants+helper added; after each emitter refactored; after regex rebuilt) — if any test fails, the refactor introduced a drift that the refactor was supposed to prevent.
- **The regex rebuild step is the riskiest**. Verify the rendered pattern equals the old:
  ```
  docker exec the-one python -c "
  import re
  PREFIX = '***'
  SEP = '...'
  TAIL = 4
  new = rf'^{re.escape(PREFIX)}({re.escape(SEP)}.{{1,{TAIL}}})?$'
  old = r'^\*\*\*(\.\.\..{1,4})?$'
  print(f'new: {new!r}')
  print(f'old: {old!r}')
  assert new == old, 'pattern mismatch'
  print('OK — patterns are identical')
  "
  ```
- **`_mask_secret_value`'s "non-str → wholesale" path** must stay defensive. Read the existing docstring — the comment about "non-string secret values (e.g., a nested dict for OAuth tokens in F5) — mask wholesale to avoid leaking nested structure" is doctrine; preserve it. The only change is `return "***"` → `return _MASK_PREFIX`.

### 3. New pairing tests

Add to `tests/test_api_secret_mask_roundtrip.py` (likely near the existing `_looks_masked` / regex tests if they exist; otherwise as a new class at the end of the file). Read the file's existing class structure first to decide placement.

```python
class TestMaskShapeSingleSourceOfTruth:
    """M11 F8 L3: pin the regex-emit pairing. If a maintainer drifts the
    emit shape from the recognize shape (e.g., by changing the prefix in
    one but not the other), these tests fail loud.

    See ``the_one/agents.md`` → ``single-source-of-truth-for-paired-helpers``.
    """

    def test_mask_shape_re_matches_emit_mask_output_for_short_string(self) -> None:
        from the_one.interfaces.web.api import _emit_mask, _MASK_SHAPE_RE
        masked = _emit_mask("ab")
        assert _MASK_SHAPE_RE.match(masked), f"Regex must match emit output {masked!r}"

    def test_mask_shape_re_matches_emit_mask_output_for_long_string(self) -> None:
        from the_one.interfaces.web.api import _emit_mask, _MASK_SHAPE_RE, _MASK_TAIL_LEN
        masked = _emit_mask("longersecret-token-123")
        assert _MASK_SHAPE_RE.match(masked), f"Regex must match emit output {masked!r}"
        assert masked.endswith("t123")  # tail of _MASK_TAIL_LEN chars

    def test_mask_shape_re_rejects_unrelated_user_input(self) -> None:
        from the_one.interfaces.web.api import _MASK_SHAPE_RE
        # Values that merely START with the prefix but aren't masks:
        assert not _MASK_SHAPE_RE.match("***hello")
        assert not _MASK_SHAPE_RE.match("abc")
        assert not _MASK_SHAPE_RE.match("")
        # Trailing content past the tail length:
        assert not _MASK_SHAPE_RE.match("***...too_long_tail")

    def test_mask_emitters_route_through_emit_mask(self) -> None:
        """Spot-check both wrapper functions produce identical output to
        _emit_mask for str inputs. Tightens the routing invariant — if a
        future refactor accidentally re-introduces a literal in one of
        the wrappers, this test catches it.
        """
        from the_one.interfaces.web.api import (
            _emit_mask,
            _mask_secret_value,
            _mask_api_key,
        )
        value = "supersecret-token-xyz789"
        assert _mask_secret_value(value) == _emit_mask(value)
        assert _mask_api_key(value) == _emit_mask(value)

    def test_rendered_regex_matches_pre_l3_literal(self) -> None:
        """Regression net: pin the rendered regex pattern byte-for-byte
        against the pre-L3 literal. Catches a future Python ``re.escape``
        semantic change for ASCII (very unlikely, but exactly the
        scenario this leg's "single source-of-truth" defends against).
        Also catches an accidental edit to ``_MASK_PREFIX`` /
        ``_MASK_TAIL_SEPARATOR`` / ``_MASK_TAIL_LEN`` that drifts the
        rendered pattern away from the established round-trip contract.
        """
        from the_one.interfaces.web.api import _MASK_SHAPE_RE
        assert _MASK_SHAPE_RE.pattern == r"^\*\*\*(\.\.\..{1,4})?$"
```

Five tests total (predicted +5; predicted post-L3 total ~2669).

### 4. Codifying `single-source-of-truth-for-paired-helpers` in `the_one/agents.md`

Insert a new section under `## Project Conventions` → `### Project-wide`. **Placement near `provider-shape-portability`** (L2's addition at line 134) — both conventions concern preventing drift between paired/related helpers in different parts of the codebase. The implementer should re-read the surrounding conventions to settle the exact insertion point.

Use this text (refine wording during implementation if it feels off):

```markdown
### `single-source-of-truth-for-paired-helpers`

**Convention**: When two helpers form a tightly-coupled pair — one EMITS a pattern and the other RECOGNIZES it (or one CONSTRUCTS state and the other PARSES it back, or one ENCODES and the other DECODES) — both helpers must read from the same constant(s) or generator function. Never hardcode the same literal in both places.

**Mechanism**: extract the shape into module-level constants (e.g., `_MASK_PREFIX = "***"`, `_MASK_TAIL_LEN = 4`). The emitter builds output from the constants. The recognizer (regex / parser / matcher) is also built from the same constants — for regexes, use `re.escape(CONST)` so the pattern adapts when the constant changes.

**Source**: M11 F8 L3 (mask-shape-single-source). Pinned by `tests/test_api_secret_mask_roundtrip.py::TestMaskShapeSingleSourceOfTruth` — tests assert `regex.match(emitter(x))` for representative inputs, so if a maintainer drifts one without the other, the tests fail.

**When this matters**:
- Mask emitters + regex recognizers (the M11 F8 L3 motivating case).
- Encoders + decoders that share a wire format (the canonical Message dataclass invariant from `provider-shape-portability` is a structural variant of this).
- Tokenizers + parsers, prefix-stripping helpers, sentinel emitters + matchers, any helper pair where one PRODUCES what the other RECOGNIZES.

**Anti-pattern**: two functions that build/recognize the same literal pattern with copy-pasted hardcoded strings or regexes. If you find yourself writing the same `"***"` (or `\*\*\*` regex escape) in two adjacent functions, extract the constant.

**Pair with**: `mechanical-fallback-prompt-truth-pairing` (the analogous discipline for prompt-vs-code pairings) and `provider-shape-portability` (the same single-source-of-truth principle applied to dataclass shapes across LLM providers).
```

### 5. Flight-log entry template

Append under `## Leg Progress`:

```markdown
### mask-shape-single-source

**Status**: landed
**Started**: {ISO timestamp}
**Completed**: {ISO timestamp}

#### Changes Made
- `the_one/interfaces/web/api.py`:
  - Added module-level constants `_MASK_PREFIX`, `_MASK_TAIL_SEPARATOR`, `_MASK_TAIL_LEN` (the single source-of-truth for mask shape).
  - Added `_emit_mask(value: str) -> str` — single emit helper.
  - Refactored `_mask_secret_value` to route str through `_emit_mask`; non-str wholesale-mask drawn from `_MASK_PREFIX`.
  - Refactored `_mask_api_key` to route through `_emit_mask`.
  - Rebuilt `_MASK_SHAPE_RE` from `re.escape(_MASK_PREFIX)` and `re.escape(_MASK_TAIL_SEPARATOR)` so the regex pattern adapts to constant changes.
  - Updated `_looks_masked` docstring to cite `_emit_mask` as the canonical source.
- `tests/test_api_secret_mask_roundtrip.py`: added `TestMaskShapeSingleSourceOfTruth` class with 4 new tests pinning the regex-emit pairing.
- `the_one/agents.md`: added `single-source-of-truth-for-paired-helpers` convention section, placed near `provider-shape-portability` (L2 line ~134 + offset for L3's addition).

#### Notes
- Pre-L3 baseline: 2664 passed (per L2 leg-progress).
- Post-L3 total: {N} passed. Delta = +5 (new pairing tests). Predicted 2669.
- Observable-behavior preservation verified: `tests/test_api_secret_mask_roundtrip.py` existing tests pass unchanged.
- Refactor LOC: ~{N} LOC of net change in `api.py` (additions for constants + helper - removals for literals; existing helpers shrink slightly via helper extraction).
- Rendered regex pattern verified identical to pre-L3 literal at design time AND post-implementation (run the rendering-equality check from Implementation Guidance §2).
- No production code touched outside `the_one/interfaces/web/api.py`.
```

## Edge Cases

- **Rendered regex equality**: `re.escape("***")` produces `\*\*\*`; `re.escape("...")` produces `\.\.\.`. Both match the pre-L3 raw-string literal. If for some reason the Python version produces a different escape sequence (unlikely — these are deterministic for ASCII), the test `test_mask_shape_re_matches_emit_mask_output_for_long_string` would catch the discrepancy by failing.
- **`_MASKED_API_KEY_SENTINEL` is OUT OF SCOPE**: this constant (`"__MASKED__"`) is a separate-concept "preserve existing value" marker, orthogonal to the visual-mask shape. Do NOT touch it. The `_looks_masked` helper recognizes BOTH the sentinel AND the visual mask; that union semantic stays.
- **The non-str defensive branch in `_mask_secret_value`**: preserve the wholesale-mask behavior (`return _MASK_PREFIX` instead of `return "***"`). Test this branch survives via the existing `test_api_secret_mask_roundtrip.py` coverage; if no existing test exercises non-str values, this refactor doesn't reveal a gap (L3 is a refactor, not a coverage extension).
- **Other secret-handling code outside `api.py`**: a grep for `"***"` across `the_one/` may surface other ad-hoc mask literals in unrelated files (e.g., test fixtures, logging). Out of L3 scope. The leg targets ONLY the api.py mask-emit + regex pair.
- **`re.escape` cost at module load**: negligible; constants are computed once.

## Files Affected

- `the_one/interfaces/web/api.py` — primary target. ~30 LOC of net change (constants + helper + refactored emitters + regex rebuild).
- `tests/test_api_secret_mask_roundtrip.py` — ~40 LOC added (new pairing class with 4 tests).
- `the_one/agents.md` — ~25 LOC added (new convention section).
- `flight.md` — leg-list checkbox.
- `flight-log.md` — leg-progress entry.
- This leg artifact — status transitions.

**Do NOT touch**:
- `the_one/connectors/` — out of scope.
- `the_one/agent/` — out of scope.
- `the_one/tools/` — out of scope.
- `the_one/db/` — out of scope.
- `the_one/llm/` — out of scope (L2's territory).
- Any UI / studio / chat file — out of scope.
- `_MASKED_API_KEY_SENTINEL` constant or its callers — separate concept, see Edge Cases.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified via the commands in Verification Steps
- [x] Tests passing — full suite + targeted file run
- [x] Existing `test_api_secret_mask_roundtrip.py` tests pass UNCHANGED (only additions, no edits to existing test bodies)
- [x] Rendered regex pattern verified byte-identical to pre-L3 literal (Implementation Guidance §2)
- [x] Update flight-log.md with leg progress entry (template in §5)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Diff scope audit confirms no out-of-scope production code touched
- [x] **Do NOT commit** — Flight Director batches commits across all autonomous legs at Phase 2d
- [x] Signal `[HANDOFF:review-needed]`

## Citation Audit

9 citations verified against current code at leg design time:

- `the_one/interfaces/web/api.py:_mask_secret_value` lines 642-664 — OK (defensive Any → Any signature; `"***"` for short/non-str; `f"***...{value[-4:]}"` for long)
- `the_one/interfaces/web/api.py:_MASKED_API_KEY_SENTINEL` line 678 — OK (`"__MASKED__"`; OUT OF L3 SCOPE per Edge Cases)
- `the_one/interfaces/web/api.py:_MASK_SHAPE_RE` line 685 — OK (`re.compile(r"^\*\*\*(\.\.\..{1,4})?$")`)
- `the_one/interfaces/web/api.py:_looks_masked` lines 688-707 — OK (recognizer; docstring cites the two emitters by name)
- `the_one/interfaces/web/api.py:_mask_api_key` lines 3055-3060 — OK (str | None signature; same shape output)
- `the_one/interfaces/web/api.py` PUT-handler sites at lines 1140, 2402, 3179 — OK (call `_looks_masked(value)`; behavior unchanged by L3)
- `tests/test_api_secret_mask_roundtrip.py` — OK (505 LOC verified post-L2; existing tests cover round-trip behavior that L3 must preserve)
- `the_one/agents.md` — OK (L2 added `provider-shape-portability` at line 134; L3's `single-source-of-truth-for-paired-helpers` placement near it as thematic anchor)
- `the_one/interfaces/web/api.py` provider PUT handler at line 1588 (`v == _MASKED_API_KEY_SENTINEL`) — OK (sentinel comparison, not visual-mask; unchanged by L3)

9 citations verified clean.

## Design-Review Cycle Log

**Cycle 1 (2026-05-26, Developer reviewer)**: approve with changes. Findings + resolutions:

- **MEDIUM**: AC test-count drifted between +3 and +4 across the leg artifact. **Resolved**: reconciled to **+5** (after adding the regression-net test per the other medium issue).
- **MEDIUM**: no AC-level regression assertion pinning the rendered regex pattern. **Resolved**: added `test_rendered_regex_matches_pre_l3_literal` — asserts `_MASK_SHAPE_RE.pattern == r"^\*\*\*(\.\.\..{1,4})?$"`. Permanent regression net rather than design-time-only manual check.
- **LOW**: Verification Step 3 had a self-correcting paragraph (in-progress thinking left in spec). **Resolved**: rewritten to a clean single instruction.
- **LOW**: Citation Audit overcounted test file LOC (~437 stale from L1-design context; actual is 505 post-L2). **Resolved**: updated to 505.

Suggestions noted (non-blocking; flagged for implementer):
- Run `make test-unit` immediately before starting to record actual pre-L3 count rather than relying on the L2-recorded 2664.
- Keep `_looks_masked` docstring's union-recognition language (sentinel + visual mask) — `_emit_mask` becomes the canonical visual-mask source, but the union semantic at PUT-handler sites stays unchanged.

No questions raised; convention overlap with `mechanical-fallback-prompt-truth-pairing` resolved cleanly (distinct domains; the proposed text correctly cross-references both).

Cycle 2: skipped (cycle-1 issues mechanical, no new high-severity risks). If implementation surfaces new design issues, escalate to human.

**Leg approved for implementation.** [HANDOFF:review-needed]
