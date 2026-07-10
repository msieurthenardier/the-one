# Leg: str-consumer-hardening

**Status**: landed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Add a reusable `content_to_text` projection helper and harden the **one** genuine
USER-content reader that a `list`-content message would break
(`_inference.py::_render_history_for_prompt`), while documenting the remaining
recon-flagged sites as verified-safe under DD3 (assistant/tool-gated).

## Context

- **Depends on L01** (types). Entirely **defensive/forward-looking**: no producer
  creates `list` content at runtime yet (L08 deferred), so nothing breaks today —
  but per the flight's ordering (Architect-affirmed) consumer-hardening lands
  *before* any list-content path can flow. Proven hermetically by passing
  list-content messages through the hardened site in tests.
- **The blast radius is smaller than the recon's ~6.** Both the recon and the F12
  design review converged: under **DD3** (list content only on `Role.USER`), the
  assistant/tool-side str-consumers stay valid — only a **USER-content reader**
  genuinely breaks. Independent re-check confirmed **exactly one within L03's scope**:
  `the_one/connectors/_inference.py::_render_history_for_prompt` (iterates USER +
  ASSISTANT messages, does `content = m.content` then f-string interpolation → a
  `list` stringifies to its Python repr, corrupting the classifier-LLM prompt).
- **A second USER-content reader exists but is out of L03's scope:**
  `the_one/db/codec.py::messages_to_ui_events` (USER branch) emits `msg.content`
  opaquely into a WS/JSON event. It is **already tracked** — the flight's Out-of-Scope
  section (via the L02 review) records it as a **prerequisite of any producer
  (L08 / the frontend follow-up)**, safe only while there is no producer. L03 does
  **not** re-litigate it — the "exactly one" above is scoped to L03, not full-stop.
- **Verified-safe under DD3 (no change, documented):**
  - `agent/core.py` (`response.content.strip()`) — reads the **assistant** response.
  - `connectors/_inference.py` classifier-output parse (`result.content.strip()…`) —
    **assistant** response.
  - `connectors/post_step_metadata.py` (`.startswith`) — **TOOL** message (content
    mirrors `ToolResult.content`, always str).
  - `interfaces/cli.py` (`Markdown(msg.content)`) — **`role == Role.ASSISTANT`-gated**
    (the recon over-flagged this; the role gate makes it str-safe).
  - `interfaces/web/app.py` (`" ".join(reply_parts)`) — **assistant** reply parts.
  Each is str under DD3; changing them would add churn + risk for no runtime gain.
  If DD3 ever loosens (assistant structured content), they become a follow-up.

## Inputs

- `the_one/llm/base.py` — `TextContent`/`ImageContent`/`ContentBlock` (L01);
  `build_user_message_content` (the helper's neighbor).
- `the_one/connectors/_inference.py` — `_render_history_for_prompt` (the fix site).
- The MCP precedent (`mcp/client.py`) already flattens image blocks to a text
  placeholder — the same idea `content_to_text` generalizes.

## Outputs

- `the_one/llm/base.py` — a `content_to_text(content) -> str` helper.
- `the_one/connectors/_inference.py` — `_render_history_for_prompt` uses it.
- Tests for the helper + the hardened render.

## Acceptance Criteria

- [x] **`content_to_text(content: str | list[ContentBlock]) -> str`** in `base.py`:
      `str` → returned unchanged; `list` → `TextContent.text` values joined with a
      single space, `ImageContent` → a `"[image]"` placeholder (mirrors the MCP
      layer's image→placeholder flattening). Never raises on a well-formed content
      value.
- [x] **`_render_history_for_prompt` hardened**: replace `content = m.content` with
      `content = content_to_text(m.content)` (before the operator-prefix wrap), so a
      `list`-content USER turn renders as `"user text [image]"` in the classifier
      history rather than a Python-repr. The operator-prefix + role-label behavior is
      otherwise unchanged; the **str path is byte-identical**.
- [x] **Documented no-change sites**: the leg records (here + a brief code comment at
      `_render_history_for_prompt` if useful) that the assistant/tool-side
      str-consumers are DD3-safe and intentionally untouched.
- [x] **str path byte-identical**: existing `_inference` tests pass unmodified.
- [x] **Tests**: `content_to_text` (str passthrough; list of text-only; list with an
      image → placeholder; mixed text+image ordering preserved; empty list → `""`);
      `_render_history_for_prompt` with a `list`-content USER message (with + without
      the operator-visibility prefix) produces sane flattened text, and the str case
      is unchanged.
- [x] **Scope**: `git diff --stat` shows only `base.py`, `_inference.py`, and their
      test files (+ flight artifacts). No provider/codec/other-consumer change.
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_llm_base.py <inference-test-file> -x --timeout 30`.

## Verification Steps

- Run the helper + `_inference` test files — green, incl. list-content render + str byte-identical.
- `git diff --stat` — only `base.py` + `_inference.py` + their tests (+ flight artifacts).
- Read the `_render_history_for_prompt` diff — confirm the str path is unchanged and only the content projection is inserted.

## Implementation Guidance

1. **`content_to_text`** in `base.py` (near `build_user_message_content`):
   ```python
   def content_to_text(content: str | list[ContentBlock]) -> str:
       """Flatten message content to a plain-text projection for str-only consumers.

       ``str`` → returned as-is. ``list`` → ``TextContent`` texts joined by a single
       space; each ``ImageContent`` → a ``"[image]"`` placeholder (mirrors the MCP
       layer's image→placeholder flattening in ``mcp/client.py``). For consumers that
       need a text view of content and cannot render blocks (e.g. the inference
       classifier's history render).
       """
       if isinstance(content, str):
           return content
       parts: list[str] = []
       for b in content:
           if isinstance(b, TextContent):
               parts.append(b.text)
           elif isinstance(b, ImageContent):
               parts.append("[image]")
       return " ".join(parts)
   ```
   (Dispatch by `isinstance` — do NOT read a `type` string. Consistent with the F10
   Rec 5 no-hardcoded-type-filter guidance.)
2. **`_render_history_for_prompt`** (`_inference.py`): change `content = m.content` to
   `content = content_to_text(m.content)`. Leave the `[operator]` prefix + role-label
   + join logic exactly as-is (they now operate on a guaranteed `str`). Import
   `content_to_text` from `the_one.llm.base`.
3. **Tests**: helper unit tests (in `tests/test_llm_base.py`, next to the L01 block
   tests); `_render_history_for_prompt` tests in **`tests/test_connectors_inference.py`**
   (it already imports `_render_history_for_prompt` directly) with a `list`-content
   USER message. Note: `_render_history_for_prompt` reads **raw `m.content`** (NOT
   `build_user_message_content` output), so the DD4 prefix block is NOT present here —
   `content_to_text` sees only the user's own blocks, so there is no prefix/user-text
   join-spacing concern. Add an explicit test asserting the flattened line has no
   stray double space.
4. Do **not** touch the documented-safe sites, providers, codec, or
   `messages_to_ui_events`. Optionally add a one-line comment at
   `_render_history_for_prompt` noting the other USER/assistant/tool `.content`
   readers are DD3-safe or deferred (helps a future reader who lands here without the
   leg doc).

## Edge Cases

- **Empty list** → `""` (matches L01's lenient empty-list; renders as an empty
  history line, harmless).
- **Image-only content** (no `TextContent`) → `"[image]"` — the classifier sees a
  non-empty, sensible token rather than an empty string or a repr.
- **Consumer never receives a list today** (no producer) — the fix is forward-looking
  insurance; tests construct the list-content message directly.
- **Unknown block subtype** — `content_to_text` silently skips anything that is
  neither `TextContent` nor `ImageContent` (there is no third type; the `isinstance`
  chain is exhaustive over `ContentBlock`). Not a filter-drop risk since the union is
  closed.

## Files Affected

- `the_one/llm/base.py` — `content_to_text` helper.
- `the_one/connectors/_inference.py` — `_render_history_for_prompt` hardened.
- `tests/test_llm_base.py` + the `_inference` test file — tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed` (in this file's header — matches the L01/L02
      precedent and the CLAUDE.md leg lifecycle; `completed` is reserved past batch
      review + commit)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight/mission status change)
- [x] Changes stay uncommitted — batch commit after L07 (do NOT commit at leg end)
