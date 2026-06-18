# Leg: sanitize-tool-schema

**Status**: completed
**Flight**: [Anthropic Tool `input_schema` Compatibility (#122)](../flight.md)

## Objective

Create the pure, stdlib-only kernel `the_one/llm/_schema_sanitize.py` that normalizes
a JSON-Schema tool `input_schema` into a single top-level **object** schema with no
top-level `oneOf`/`allOf`/`anyOf` (the shape Anthropic's Messages API requires),
raising `UnsanitizableToolSchema(reason)` when no valid object schema can be produced —
fully covered by unit tests. No provider code is touched in this leg.

## Context

- This is **leg 01 of 4**; no prior legs. It builds the reusable kernel that leg 02
  (`wire-into-anthropic-adapter`) will call from the Anthropic transform override.
- Implements flight **DD1** (pure leaf kernel, stdlib-only, no `the_one.llm` imports),
  **DD2** (operate on a deep copy; never mutate the input), **DD3** (top-level only —
  nested combinators/`$ref` untouched), and the **DD4** rule table + the
  `UnsanitizableToolSchema(reason)` signal contract.
- The kernel encodes the **Anthropic** constraint set. Naming: a provider-neutral
  function name (`sanitize_tool_schema`) in a module documented as "a library of
  schema-normalization primitives" — a future OpenAI-strict capability flight would
  add its *own* function here rather than overloading this one (DD1 promotion path).
  Exact module/function names are an acceptable variation per the flight.
- **Why this is needed** (background, not re-derived here): tool schemas arrive verbatim
  from third-party MCP servers; a legal top-level combinator (e.g. goldfinch
  `press_key`'s `anyOf`) makes Anthropic 400 the *entire* turn. See flight Objective +
  Background.

## Inputs

What exists before this leg runs:
- `the_one/llm/` package with `_streaming.py` (the `_`-prefixed shared-module
  convention this file mirrors).
- `tests/CONVENTIONS.md` (test patterns) and the existing `tests/test_llm_base.py`
  (class-grouped, plain-`def` unit tests for a pure `the_one.llm` helper — the model
  for this leg's test file).
- Python 3.11+; `pytest` configured with `asyncio_mode = "auto"` (irrelevant here — all
  tests are synchronous).

## Outputs

What exists after this leg completes:
- New file `the_one/llm/_schema_sanitize.py` exporting:
  - `class UnsanitizableToolSchema(Exception)` carrying a `.reason: str`.
  - `def sanitize_tool_schema(schema: dict | None) -> dict` — pure, deep-copying.
- New file `tests/test_schema_sanitize.py` — exhaustive unit suite (all acceptance
  criteria below), green.
- No changes to any provider adapter, `base.py`, the MCP layer, or the web UI.

## Acceptance Criteria

Each maps to a unit test in `tests/test_schema_sanitize.py`.

**Transform correctness (DD4 rows):**
- [x] **Missing `type`, has `properties`** → output has `type: "object"`; properties
      unchanged.
- [x] **Empty `{}`** → `{"type": "object"}`.
- [x] **`None` input** (absent `parameters`) → `{"type": "object"}`.
- [x] **`type` is `["object", "null"]`** → collapses to the **scalar string** `type: "object"`
      (NOT `["object"]` — drop the array entirely). *(Provisional — pinned live in leg 04;
      encode the scalar collapse now.)*
- [x] **`type` is an array WITHOUT `"object"`** (e.g. `["string", "null"]`) → raises
      `UnsanitizableToolSchema`.
- [x] **Top-level `allOf` of object-fragments** → merged into one object: union of
      `properties`, **union** of `required` (across branches + any base-level
      `required`); `allOf` removed; `type: "object"` present.
- [x] **Top-level `allOf` with a non-object branch** (a `$ref`, scalar, or `not`) →
      raises `UnsanitizableToolSchema`.
- [x] **Top-level `anyOf`/`oneOf` of object/required-fragment branches** → branch
      `properties` unioned into top-level `properties`; `required` = **intersection**
      across branches, unioned with any base-level `required`; combinator removed;
      `type: "object"` present.
- [x] **`press_key` real fixture** (top-level `anyOf` of `{required:[...]}` + base
      `required:['wcId']` + base `properties`) → output has `type:"object"`, no
      `anyOf`, `properties` = `{wcId, name, key, modifiers}` intact, `required == ['wcId']`
      (order-insensitive). Anthropic-acceptance of this exact output is leg 04's job.
- [x] **`anyOf` with a key colliding across branches with *different* schemas** → that
      property becomes a **nested** `{"anyOf": [...]}` (nested combinators are legal and
      this is the only lossless option); identical collisions deduplicate to one.
- [x] **Top-level bare `$ref`** (`{"$ref": "#/$defs/Foo"}`, no `type`) → raises
      `UnsanitizableToolSchema`.
- [x] **Top-level `not`** (no object shape) → raises `UnsanitizableToolSchema`.
- [x] **Empty combinator list** (`{"allOf": []}` and `{"anyOf": []}`, no other constraint)
      → treated as no constraint: combinator dropped, output `{"type": "object"}`; does
      **not** raise.
- [x] **Both `anyOf` and `oneOf` at top level simultaneously** → each is processed
      (branches merged per the anyOf/oneOf rule), both combinator keys removed,
      `type:"object"` present, and the merge note is appended **exactly once**.
- [x] **Top-level `$ref` *alongside* an object shape** (`{"$ref": "#/$defs/X", "type":
      "object", "properties": {...}}`) → proceeds (it has an object shape): the sibling
      `$ref` is preserved **untouched** (DD3) and `type:"object"` is ensured. Only a *bare*
      top-level `$ref` (no `properties`, no object `type`) raises. This pins the DD3-vs-
      unsanitizable boundary.
- [x] **Non-mutation (DD2)**: after any call, the input object is `is`-identical to what
      was passed AND byte-equal to a pre-call `deepcopy` of it (verified via
      `copy.deepcopy` snapshot comparison).
- [x] **Preservation**: top-level `description`, `$defs`/`definitions`,
      `additionalProperties`, and `title` survive into the output unchanged (except
      `description`, which may gain an appended note — see next).
- [x] **Nested untouched (DD3)**: a property whose schema is itself a `{"$ref": ...}` or
      a nested `anyOf`/`oneOf` is carried through **unmodified** (only the *top* level is
      rewritten). Verified with a fixture that has both a `$defs` block and a property
      referencing it.
- [x] **Merge note**: when a top-level combinator was flattened, a one-line note is
      appended to the output `description` (e.g. "(Note: alternative input forms were
      merged; provide the fields that apply.)"); when no combinator was present, the
      `description` is byte-unchanged.
- [x] **`UnsanitizableToolSchema` carries a non-empty `.reason`** naming the offending
      shape (asserted for each unsanitizable case).

## Verification Steps

- `cd /home/cprch/projects/the-one`
- `python -c "import the_one.llm._schema_sanitize"` — module imports with **stdlib only**
  (no `the_one.llm` imports; grep the file to confirm: `grep -n "^from\|^import" the_one/llm/_schema_sanitize.py` shows only stdlib like `copy`).
- `pytest tests/test_schema_sanitize.py -q` — all tests pass.
- `pytest tests/test_schema_sanitize.py -q -k "non_mutation or press_key or nested"` —
  the three highest-risk invariants pass in isolation.
- `ruff check the_one/llm/_schema_sanitize.py tests/test_schema_sanitize.py` (if the repo
  lints in CI) — clean.

## Implementation Guidance

1. **Exception** — define in the same module:
   ```python
   class UnsanitizableToolSchema(Exception):
       """Raised when a tool input_schema has no representable top-level object form."""
       def __init__(self, reason: str) -> None:
           self.reason = reason
           super().__init__(reason)
   ```

2. **Entry point** — `sanitize_tool_schema(schema: dict | None) -> dict`:
   - `import copy` (stdlib only). If `schema is None` or `schema == {}` → return
     `{"type": "object"}`. If `schema` is not a `dict` → raise
     `UnsanitizableToolSchema(f"top-level schema is {type(schema).__name__}, not an object")`.
   - `work = copy.deepcopy(schema)` — **all** mutation happens on `work`; the input is
     never touched (DD2).

3. **Order of operations matters** — the `press_key` case has BOTH a top-level `type`
   AND a top-level `anyOf`, and Anthropic rejects the `anyOf` even when `type` is
   present. So: (a) resolve/merge combinators, (b) reconcile `type`, in that order.

4. **`type` reconciliation**:
   - `type` is a list → if `"object"` in it, set `type = "object"`; else raise
     `UnsanitizableToolSchema("top-level type {list} has no 'object' member")`.
   - `type` is a non-`"object"` string (e.g. `"string"`) and there are no combinators to
     merge into an object → raise `UnsanitizableToolSchema("top-level type is '{t}', tool inputs must be objects")`.
   - `type` absent → it will be set to `"object"` at the end (after combinator merge).

5. **`allOf` (DD4: union required)** — for each branch, require it be an object-fragment
   (a dict with `properties` and/or `required`, or `type:"object"`); a branch that is a
   `$ref`, `not`, scalar, or array → raise `UnsanitizableToolSchema`. Merge: `properties`
   = base ∪ all branches; `required` = base ∪ all branches (de-duplicated, order-stable).
   Delete `allOf`.

6. **`anyOf`/`oneOf` (DD4: intersection required)** — same branch-shape guard. Union
   branch `properties` into top-level `properties`; on a key present in ≥2 branches with
   *differing* schemas, set `properties[key] = {"anyOf": [<distinct variants>]}` (nested —
   legal); identical variants collapse to one. `required` = **intersection** of the
   branches' `required` lists, then unioned with the base-level `required` (base-level
   requirements are unconditional). Delete the combinator key. (Only one of
   `anyOf`/`oneOf` is expected at top level; if both appear, process each.)

7. **Bare `$ref` / `not` at top level** — if after the above there is no `properties`
   and no object `type` and the schema is just `{"$ref": ...}` or contains a top-level
   `not` with no object shape → raise `UnsanitizableToolSchema`. (Explicit branches, not
   an accidental fallthrough — see DD4.)

8. **Finalize** — ensure `work["type"] = "object"`. Leave `description`, `$defs`,
   `definitions`, `additionalProperties`, `title`, and any nested schemas exactly as
   deep-copied (DD3). If a combinator was flattened, append the one-line merge note to
   `work["description"]` (create it if absent) — append it **exactly once** even when
   more than one top-level combinator (e.g. both `anyOf` and `oneOf`) was flattened.

9. **Keep it pure** — no logging, no I/O, no provider imports. The adapter (leg 02) owns
   warnings/drop-and-proceed; this kernel only transforms or raises.

### `press_key` fixture (verbatim from goldfinch, the real-world trigger)

Use this exact schema as the primary `anyOf` fixture (source: goldfinch
`src/main/automation/mcp-tools.js`, the `press_key` tool; captured here so the test has
no live goldfinch dependency):

```python
PRESS_KEY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "wcId": {"type": "integer", "description": "webContents id of the target tab"},
        "name": {"type": "string", "description": "friendly key name (preferred) ..."},
        "key": {"type": "string", "description": "accepted alias for `name` ..."},
        "modifiers": {
            "type": "array",
            "items": {"type": "string", "enum": ["control", "shift", "alt", "meta"]},
            "description": "optional modifier keys held during the press ...",
        },
    },
    "required": ["wcId"],
    "anyOf": [{"required": ["name"]}, {"required": ["key"]}],
}
```
Expected after sanitize: no `anyOf`; `type == "object"`; `properties` keys ==
`{wcId, name, key, modifiers}` (each unchanged); `required == ["wcId"]`.

## Edge Cases
- **Both `type:"object"` and a top-level combinator present** (the `press_key` case):
  the combinator must still be removed/merged — do not short-circuit just because `type`
  is already `"object"`.
- **`required` referencing a property not in any merged `properties`**: keep it as-is
  (Anthropic does not require `required` entries to resolve; do not invent properties).
- **`anyOf` branch that carries its own `properties`** (not just `required`): union those
  properties up too — the rule is the same union/intersection logic; required-only
  fragments are just the common sub-case.
- **Empty `anyOf`/`allOf` list** (`[]`): treat as "no constraint" → drop it, ensure
  `type:"object"`; do not raise.
- **`type` already `"object"` with no properties and no combinator** → valid; return as
  deep-copied (plus ensure `type:"object"`).

## Files Affected
- `the_one/llm/_schema_sanitize.py` — **new**; the pure kernel + `UnsanitizableToolSchema`.
- `tests/test_schema_sanitize.py` — **new**; exhaustive unit suite.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (`pytest tests/test_schema_sanitize.py -q` green)
- [ ] Module confirmed stdlib-only (no `the_one.llm` imports)
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not the final leg — do NOT flip flight/mission status)
- [ ] Commit all changes together (code + artifacts)

---

## Citation Audit

2 source citations verified against current code at leg design time:
- `the_one/llm/_streaming.py` (the `_`-prefixed shared-module convention) — **OK**, file exists.
- `tests/test_llm_base.py` (class-grouped pure-helper test model) and `tests/CONVENTIONS.md` — **OK**, both exist and match the described patterns.

The `press_key` fixture is sourced from the external goldfinch repo
(`src/main/automation/mcp-tools.js`, `press_key` tool) — captured verbatim above and
verified live this session; it is intentionally inlined so the test carries no
cross-repo dependency. Flight/DD references (`flight.md`, DD1–DD4) are non-source and
out of audit scope.
