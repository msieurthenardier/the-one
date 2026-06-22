# Leg: toolcall-recovery-kernel

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

## Objective

Add a pure, stdlib-only recovery kernel `the_one/llm/_toolcall_recovery.py` exposing
`recover_tool_calls(content: str) -> list[dict]` that recovers text-form tool calls — the
gemma3:4b ` ```tool ` fenced Python-call form (primary, reproduced), Hermes
`<tool_call>…</tool_call>` tags, and bare-JSON tool-call objects — into plain dicts
`{"name": str, "arguments": dict}`, returning `[]` when no high-precision marker is present.

## Context

- Implements DD1–DD3 of the flight. The kernel is a **leaf** module: it imports ONLY the
  stdlib (`ast`, `json`, `re`) — **not even** `the_one.llm.base` (it returns plain dicts; the
  Ollama adapter maps them to `ToolCall` in leg 02, synthesizing ids per DD4). This mirrors the
  import discipline of `the_one/llm/_streaming.py` (which depends only on `base`); this kernel
  goes one step further and depends on nothing in-repo, so it is exhaustively unit-testable in
  isolation with no provider or network. *(DD1 also names Flight 2's `_schema_sanitize.py` as a
  sibling precedent, but that module exists only on the unmerged `flight/02` branch — do not try
  to read it here; `_streaming.py` is the live in-branch precedent.)*
- The reproduced primary fixture (Flight 1 spike, live gemma3:4b — see
  `flights/01-recon-root-cause-spike/legs/02-ollama-gemma-repro.md`) is a fenced block
  ` ```tool\nget_weather(city='Paris')\n``` ` returned with `tool_calls: null`. The model emits
  the call as Python-call syntax inside the fence.
- This leg builds and tests the kernel **in isolation only**. Wiring it into `OllamaProvider`
  (recover-on-empty-structured, content-strip, id synthesis) is leg 02 — out of scope here.

## Inputs

- `the_one/llm/_streaming.py` exists as the import-discipline precedent (leaf-ish helper).
- The captured gemma fixture string (above), transcribed verbatim into the test module.
- No structured `the_one.llm` types are needed (kernel returns plain dicts).

## Outputs

- `the_one/llm/_toolcall_recovery.py` — new module, stdlib-only, `recover_tool_calls()` + private
  per-format helpers.
- `tests/test_toolcall_recovery.py` — exhaustive unit suite (hermetic; no markers, runs under
  default `make test`).

## Acceptance Criteria

- [x] `the_one/llm/_toolcall_recovery.py` exists and imports only `ast`, `json`, `re` (and
      `__future__`/`logging` if needed) — no `the_one.*` imports. Verify:
      `grep -nE '^(from|import) ' the_one/llm/_toolcall_recovery.py` shows only stdlib.
- [x] `recover_tool_calls(content: str) -> list[dict]` is the sole public entry point; each
      returned element is exactly `{"name": str, "arguments": dict}`.
- [x] **Gemma fenced Python-call** (primary): `recover_tool_calls("```tool\nget_weather(city='Paris')\n```")`
      returns `[{"name": "get_weather", "arguments": {"city": "Paris"}}]`. Also recognizes an
      untagged ```` ``` ````/` ```python ` fence whose body is a single bare call.
- [x] **Keyword args parsed via `ast`** — `ast.parse(mode="eval")` → `Call`; func name from
      `Name.id` or dotted `Attribute`; each keyword value via `ast.literal_eval`. **No `eval`**
      anywhere (verify: `grep -n 'eval(' the_one/llm/_toolcall_recovery.py` shows only
      `ast.literal_eval`, never builtin `eval`).
- [x] **Positional args** are carried under `arguments["__positional_args__"] = [...]` (never
      silently dropped) and a WARN is logged. A call with positional args is recovered, not
      discarded.
- [x] **Hermes tags**: `recover_tool_calls('<tool_call>{"name": "get_weather", "arguments": {"city": "Paris"}}</tool_call>')`
      returns the single call; multiple `<tool_call>` tags in one content return multiple calls
      in document order.
- [x] **Bare-JSON object**: a content that *is* a JSON object of tool-call shape recovers — both
      `{"name", "arguments"}` and the `{"type":"function","function":{"name","arguments"}}` /
      `{"tool":…,"arguments":…}` shapes are accepted.
- [x] **Within-format multi-call**: a content with two recognized blocks **of the same format**
      (two `<tool_call>` tags, or two fenced calls) returns an ordered 2-element list. **Cross-
      format multi-call is out of scope** (see DD-note in guidance): "first non-empty recognizer
      wins," so a content mixing one fenced call + one Hermes tag recovers only the
      first-matching recognizer's calls — pin this with a test asserting the documented behavior.
- [x] **Dotted function name**: `recover_tool_calls("```tool\ntools.get_weather(city='Paris')\n```")`
      returns `name == "tools.get_weather"` (full dotted path preserved; downstream resolves it).
- [x] **No false positives on prose**: plain prose, a prose mention of a function name, and a
      fenced code block that is *not* a tool-call form all return `[]`. The bare-JSON recognizer
      fires only on whole-content exact tool-call-shaped JSON (tightest gate).
- [x] **Bare-JSON only whole-content**: a tool-call-shaped JSON object **embedded inside
      surrounding prose** (not the whole content) returns `[]` — the bare-JSON recognizer never
      fires mid-prose. This pins the DD2 whole-content gate.
- [x] **Malformed input never raises**: unparseable fence body, invalid JSON in a Hermes tag, or
      a `Call` with non-literal args returns `[]` (or skips that block) rather than propagating an
      exception. `recover_tool_calls` is total over `str`.
- [x] `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py -x --timeout 30` is green.

## Verification Steps

- `grep -nE '^(from|import) ' the_one/llm/_toolcall_recovery.py` — only stdlib imports.
- `grep -n 'eval(' the_one/llm/_toolcall_recovery.py` — only `ast.literal_eval`, no builtin `eval`.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py -x --timeout 30` — all green.
- Each acceptance criterion above has a corresponding named test in `tests/test_toolcall_recovery.py`.

## Implementation Guidance

1. **Module skeleton** (mirror `_streaming.py`'s header/comment density):
   ```python
   """Pure text-form tool-call recovery kernel for loose/open-model output.

   M16 F03 L01 (#105): open/local models (e.g. gemma3:4b via Ollama) often
   emit a tool call as loose text — a fenced Python-call block, a Hermes
   <tool_call> tag, or a bare JSON object — instead of a structured
   tool_calls array. This kernel recovers those into plain dicts that the
   Ollama adapter (M16 F03 L02) maps to ToolCall.

   Import discipline: stdlib only (ast, json, re). This is a true leaf —
   it imports nothing from the_one, so it is unit-testable with no provider
   or network. NEVER uses builtin eval; ast.parse + ast.literal_eval only.
   """
   from __future__ import annotations
   import ast, json, logging, re
   logger = logging.getLogger(__name__)

   def recover_tool_calls(content: str) -> list[dict]: ...
   ```

2. **Dispatch order in `recover_tool_calls`** — try recognizers most-specific-first; **the first
   recognizer that returns a non-empty list wins, and its full list is returned** (no recovery
   from later recognizers). This makes *within-format* multi-call work (a recognizer returns all
   its own matches) while keeping *cross-format* mixed multi-call deliberately out of scope —
   simpler, and matches the captured reality (a model emits one format at a time). Order:
   1. Hermes `<tool_call>…</tool_call>` tags (regex `re.findall`, `json.loads` each inner body) —
      returns **all** tags found.
   2. Fenced blocks tagged `tool` (also accept untagged / ` ```python ` whose body is a single
      call). Parse each fence body with `_parse_python_call`; returns all that parse.
   3. Whole-content bare-JSON object (only if `content.strip()` parses as a dict of tool-call
      shape).
   Each recognizer is a private helper returning `list[dict]`; wrap each in try/except so a
   malformed match contributes nothing rather than raising.

3. **`_parse_python_call(src: str) -> dict | None`** (the gemma path, first-class):
   - `tree = ast.parse(src.strip(), mode="eval")`; require `isinstance(tree.body, ast.Call)`.
   - Function name: `tree.body.func` is `ast.Name` → `.id`; `ast.Attribute` → reconstruct dotted
     path (`a.b.c`). Anything else → `None`.
   - Keyword args: for each `ast.keyword`, value = `ast.literal_eval(kw.value)`; key = `kw.arg`.
     If any value isn't a literal (`literal_eval` raises) → return `None` (don't partially
     recover).
   - Positional args: `tree.body.args` → `[ast.literal_eval(a) for a in args]`; if non-empty,
     set `arguments["__positional_args__"] = [...]` and `logger.warning("recovered positional "
     "args for %s; built-in/MCP tools expect named args", name)`.
   - Return `{"name": name, "arguments": arguments}`. (`__positional_args__` is a **reserved
     sentinel key** — assume no real tool schema defines a parameter of that name; leg 02's
     dispatcher treats it specially.) Positional and keyword args coexist in the same dict.

4. **Hermes helper** — match the tag body up to the closing tag, NOT the first `}`: use
   `re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL)` and `json.loads` the
   stripped body of each match (a non-greedy `(\{.*?\})` would truncate a payload whose
   `arguments` contains a nested object at the first inner `}`). `json.loads` each; **skip** any
   match whose body isn't valid JSON or lacks a `name` (no `KeyError`); normalize to
   `{"name", "arguments"}` (accept `arguments` missing → `{}`).

5. **Bare-JSON helper** — only attempt if `content.strip()` starts with `{`. `json.loads`; accept:
   - `{"name": str, "arguments": dict}` → as-is;
   - `{"type": "function", "function": {"name", "arguments"}}` → unwrap;
   - `{"tool"|"function": str, "arguments"|"parameters": dict}` → normalize key names.
   Reject (return `[]`) anything else — this is the riskiest recognizer, gate it tightest.

6. **Tests** (`tests/test_toolcall_recovery.py`) — one test per acceptance criterion, named
   descriptively: `test_gemma_fenced_python_call_kwargs`, `test_positional_args_carried_not_dropped`,
   `test_positional_and_keyword_coexist`, `test_dotted_function_name_preserved`,
   `test_hermes_single_and_multi`, `test_hermes_nested_object_arguments`,
   `test_hermes_missing_name_skipped`, `test_bare_json_shapes`,
   `test_bare_json_only_whole_content` (embedded-in-prose → `[]`), `test_multi_call_ordered`,
   `test_cross_format_first_recognizer_wins`, `test_no_false_positive_on_prose`,
   `test_no_false_positive_on_plain_code_fence`, `test_malformed_never_raises`,
   `test_empty_and_whitespace`. Use the verbatim captured fixture for the gemma test. For the
   positional WARN, assert with `caplog`.

## Edge Cases

- **Empty / whitespace content** → `[]`.
- **Fence body that is multiple statements or not a single Call** → that fence yields nothing.
- **`literal_eval` on a non-literal kwarg** (e.g. `city=some_var`) → skip that call (return `None`
  from `_parse_python_call`) rather than guessing.
- **Nested/dotted function name** (`tools.get_weather(...)`) → recover the dotted name as-is; the
  adapter/registry resolves or errors on it downstream (not this kernel's concern).
- **Hermes tag with invalid JSON inside** → skip that tag, continue with others.
- **Hermes object missing `"name"`** → skip that tag (no `KeyError`).
- **Hermes `arguments` containing a nested object** → recovered intact (the up-to-closing-tag
  match, not first-`}`, preserves it).
- **A code example that prints tool-call-shaped JSON as intentional output** → accepted risk per
  DD2; bounded by marker precision (whole-content gate for bare-JSON). Not mitigated further here.

## Files Affected

- `the_one/llm/_toolcall_recovery.py` — new pure kernel.
- `tests/test_toolcall_recovery.py` — new hermetic unit suite.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py -x --timeout 30`) — 19 passed
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (deferred-review model — `completed` is set at flight commit)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight-landing steps)
- [x] (Deferred-review model: do NOT commit per-leg; commit happens after the last autonomous leg)
