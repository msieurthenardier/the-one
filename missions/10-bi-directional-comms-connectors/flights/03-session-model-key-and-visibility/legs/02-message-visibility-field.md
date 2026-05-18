# Leg: message-visibility-field

**Status**: completed
**Flight**: [Session Model — Schema, Key Normalization, Visibility](../flight.md)

## Objective

Add the `visibility: str | None = None` field to the canonical `Message` dataclass, thread it through the four `Message` classmethod constructors, round-trip the field through `message_to_dict` / `message_from_dict`, project it through `messages_to_ui_events` when non-None, and publish the `OPERATOR_VISIBILITY = "operator"` constant from `the_one.connectors` so leg 4's dispatcher and downstream flights (F4 platform-send tool, F5 Chat UI) have a single source of truth for the operator-visibility tag.

## Context

- **Parent flight design decisions** (see `flight.md`):
  - `visibility: str | None = None` on the `Message` dataclass. Values: `None` (no operator-only restriction → platform-visible for connector sessions, the only layer for non-connector sessions) or `"operator"` (operator console only, never propagated to the platform).
  - Codec round-trip via the F5-L3 `d.get("metadata")` pattern at `the_one/db/codec.py:79` — the field is emitted only when non-None and absent-on-deserialize defaults to None. This guarantees back-compat with every pre-F3 session row.
  - `messages_to_ui_events` projects `event["visibility"]` only when source visibility is non-None; when None, the key is absent (frontends treat absent === platform-visible). Pure addition — no existing event keys move.
- **Dataclass permissiveness**: the `Message` dataclass annotates `visibility: str | None` (not `Literal["operator"] | None`). The flight's Design Decisions explicitly chose permissive-string + strict-construction-site (constants at the few production sites that set visibility) to mirror the project's general dataclass-permissive pattern. A typo like `visibility="opperator"` would persist silently; the mitigation is the module-level constant published from `the_one.connectors`.
- **Production Message construction sites**: only `the_one/db/codec.py:88` constructs `Message(...)` directly — all other call sites go through `Message.system / .user / .assistant / .tool`. None need signature changes (the new kwarg has a None default). F4 and F5 will be the first callers to actually set `visibility="operator"`.
- **`encode_messages` and `decode_messages`** at `the_one/db/codec.py:97-104` wrap `message_to_dict` / `message_from_dict` for list handling — round-trip inherits automatically once the inner pair is extended.
- **Constant location**: `OPERATOR_VISIBILITY = "operator"` lives in `the_one/connectors/__init__.py`. The connectors package is the subsystem that introduces and consumes operator-vs-platform visibility; the constant is part of its public surface. Putting it in `llm/base.py` next to `Message` would couple the LLM layer to a connector concept; a dedicated `connectors/visibility.py` module is overkill for one constant.

## Inputs

State that must exist before this leg runs:

- Leg 1 of this flight is `landed` (schema v16 in place; ChatSession + ConnectorAccount models extended; both repositories round-trip).
- `the_one/llm/base.py:42 — "@dataclass\nclass Message:"` — extant unfrozen 5-field dataclass.
- `the_one/llm/base.py:49 — "def system(cls, content: str) -> Message:"` (classmethod helpers — 4 total at lines 49, 53, 57, 63).
- `the_one/db/codec.py:54 — "def message_to_dict(msg: Message) -> dict[str, Any]:"` (serializer).
- `the_one/db/codec.py:66 — "def message_from_dict(d: dict[str, Any]) -> Message:"` (deserializer).
- `the_one/db/codec.py:79 — "metadata=tr.get(\"metadata\"),"` — F5 L3's `d.get` back-compat pattern (the canonical template for F3 L2's visibility field).
- `the_one/db/codec.py:107 — "def messages_to_ui_events(messages: list[Message]) -> list[dict[str, Any]]:"` — projection target.
- `the_one/connectors/__init__.py` — extant 60-line module exporting public connector surface; F3 L2 adds the `OPERATOR_VISIBILITY` constant.
- `tests/test_db_codec.py` — extant 424-line test file with codec coverage; F3 L2 extends it.
- Working tree on branch `flight/03-session-model-key-and-visibility` with leg 1's changes uncommitted (per agentic-workflow batched-review model).

## Outputs

State that must exist after this leg completes:

- `the_one/llm/base.py:Message` has a new field `visibility: str | None = None` (as the last field of the dataclass, after `usage`).
- The four classmethod helpers (`system`, `user`, `assistant`, `tool`) each accept `visibility: str | None = None` as an optional kwarg and forward it to the `cls(...)` call. Existing call sites are unchanged (None default).
- `the_one/db/codec.py:message_to_dict` emits `d["visibility"] = msg.visibility` IFF `msg.visibility is not None` (mirror of the `tool_result.metadata` pattern at lines 45-46).
- `the_one/db/codec.py:message_from_dict` reads `visibility=d.get("visibility")` into the `Message(...)` constructor — defaults to None when the key is absent (back-compat with all pre-F3 JSON).
- `the_one/db/codec.py:messages_to_ui_events` adds `event["visibility"] = msg.visibility` (only when `msg.visibility is not None`) to each emitted event dict across all four branches (user, assistant content, tool_call, tool_result). Visibility key is ABSENT when source is None.
- `the_one/connectors/__init__.py` defines and exports `OPERATOR_VISIBILITY: Final[str] = "operator"`, added to `__all__`.
- `tests/test_db_codec.py` extended with:
  - Round-trip for `visibility="operator"` through `message_to_dict` ↔ `message_from_dict` (key present on serialize; restored on deserialize).
  - Round-trip for `visibility=None` (key absent on serialize; None preserved on deserialize).
  - Back-compat: deserialize a pre-F3 JSON without the `visibility` key produces `Message(...visibility=None)`.
  - `messages_to_ui_events` emits `event["visibility"]` on tagged messages and omits the key on untagged.
  - `messages_to_ui_events` mixed-tag scenario: a session with one user message tagged `"operator"` and one tagged `None` produces two events with correct (present/absent) visibility keys.
- `tests/test_llm_base.py` may not be the right home (the file does not exist; tests for `Message` shape currently live in `test_db_codec.py`); leg 2 adds the new dataclass-construction-via-classmethods tests to `test_db_codec.py` alongside the round-trip tests, OR creates a small new `test_llm_base.py` if cleaner. Leg-2 author's call.
- Flight log gains a "Leg Progress: message-visibility-field" entry.
- Leg status flipped to `landed` in this file's header (NOT `completed` — agentic-workflow batched-review defers `completed` to flight-end commit).

## Acceptance Criteria

- [ ] `Message` dataclass at `the_one/llm/base.py:42` has 6 fields: `role`, `content`, `tool_calls`, `tool_result`, `usage`, `visibility`. `visibility: str | None = None` is the last field.
- [ ] All four `Message` classmethods (`system`, `user`, `assistant`, `tool`) accept `visibility: str | None = None` as a keyword-only-or-positional kwarg (positional acceptable — keep simple) and forward to the `cls(...)` call. Existing single-positional-arg callers are unchanged.
- [ ] `message_to_dict` at `the_one/db/codec.py:54` emits `d["visibility"] = msg.visibility` only when `msg.visibility is not None`. When None, the key is ABSENT from the dict (storage-efficiency + back-compat).
- [ ] `message_from_dict` at `the_one/db/codec.py:66` passes `visibility=d.get("visibility")` to the `Message(...)` constructor. Absent → None; present → the stored value.
- [ ] `messages_to_ui_events` at `the_one/db/codec.py:107` adds `event["visibility"] = msg.visibility` to each emitted event dict IFF `msg.visibility is not None`. All four event branches (user, assistant content, tool_call, tool_result) honor this — search the function body for "events.append(" and confirm each call site applies the visibility tag. **Pure addition**: existing keys (`type`, `content`, `source`, `name`, `arguments`, `parent_message_id`, `tool_call_id`, `is_error`) are unchanged.
- [ ] `the_one/connectors/__init__.py` defines `OPERATOR_VISIBILITY: Final[str] = "operator"` as a module-level constant; adds it to `__all__`. `Final` is imported from `typing`.
- [ ] New tests in `tests/test_db_codec.py` (or a new sibling file, leg-2 author's call):
  - `test_message_to_dict_emits_visibility_when_non_none` — Message(`visibility="operator"`) → dict contains `"visibility": "operator"`.
  - `test_message_to_dict_omits_visibility_when_none` — Message(`visibility=None`) → dict does NOT contain a `"visibility"` key.
  - `test_message_from_dict_restores_visibility` — dict with `{"visibility": "operator"}` → Message with `.visibility == "operator"`.
  - `test_message_from_dict_back_compat_no_visibility_key` — dict without the key → Message with `.visibility is None`.
  - `test_messages_to_ui_events_projects_visibility_on_tagged_user_message` — user Message with `visibility="operator"` → event dict has `"visibility": "operator"`.
  - `test_messages_to_ui_events_omits_visibility_on_untagged_user_message` — user Message with `visibility=None` → event dict has NO `visibility` key.
  - `test_messages_to_ui_events_projects_visibility_on_assistant_content` — assistant Message with `visibility="operator"` and non-empty content → assistant-event dict has the tag.
  - `test_messages_to_ui_events_projects_visibility_on_tool_call_event` — assistant Message with `tool_calls=[...]` and `visibility="operator"` → each tool_call event dict has the tag.
  - `test_messages_to_ui_events_projects_visibility_on_tool_result_event` — tool Message with `visibility="operator"` → tool_result event dict has the tag.
  - `test_messages_to_ui_events_mixed_visibility_session` — list of 2 messages, one tagged + one not, produces 2 events with present-and-absent visibility keys respectively.
  - `test_classmethod_user_accepts_visibility_kwarg` — `Message.user("hi", visibility="operator")` returns a Message with `visibility == "operator"`.
  - Parallel tests for `Message.system`, `Message.assistant`, `Message.tool` accepting the kwarg.
- [ ] `OPERATOR_VISIBILITY` constant verified usable: a test imports `from the_one.connectors import OPERATOR_VISIBILITY` and asserts it equals `"operator"`.
- [ ] `make test` clean (no regressions; new test count is added).
- [ ] `make lint` clean (no new ruff findings).
- [ ] Flight log updated with leg-completion entry citing test counts before/after, deviations encountered (if any), any unforeseen findings.
- [ ] Leg status flipped to `landed` in this file's header (agentic-workflow Flight Director flips to `completed` at flight-end commit).
- [ ] This leg ticked off in `flight.md` under `### Legs`.

## Verification Steps

- **Field present on Message** — `grep -n "visibility: str | None" the_one/llm/base.py` shows the new field.
- **Classmethods forward** — `grep -n "visibility" the_one/llm/base.py` shows the kwarg in all four classmethod signatures and in the `cls(...)` forwards.
- **Codec round-trip** — `grep -n "visibility" the_one/db/codec.py` shows three sites: serializer-emit (with the `is not None` guard), deserializer-restore via `d.get`, and the projection-emit in `messages_to_ui_events`.
- **Constant exported** — `grep -n "OPERATOR_VISIBILITY" the_one/connectors/__init__.py` shows the declaration AND the `__all__` entry.
- **Scoped tests** — `docker exec the-one pytest tests/test_db_codec.py -x --timeout 30 -v` shows all new tests pass + existing codec tests are unchanged.
- **Full suite** — `docker exec the-one pytest -x --timeout 30` shows green (~1816 → ~1830 expected, depending on exact new-test count).
- **Lint** — `docker exec the-one ruff check the_one/ tests/` shows no new findings.

## Implementation Guidance

1. **Extend `Message` dataclass** at `the_one/llm/base.py:41`:

   ```python
   @dataclass
   class Message:
       role: Role
       content: str = ""
       tool_calls: list[ToolCall] = field(default_factory=list)
       tool_result: ToolResult | None = None
       usage: TokenUsage | None = None
       # M10 F03 L02: visibility tag for two-layer connector-session model.
       # None = no operator-only restriction (platform-visible for connector
       # sessions; the only layer for non-connector sessions).
       # "operator" = operator-console only; never propagated to the platform.
       # Constant published as ``OPERATOR_VISIBILITY`` from
       # ``the_one.connectors`` — use it at every production set site
       # (dispatcher in F3 L4; platform-send tool in F4; Chat-UI
       # operator-input path in F5).
       visibility: str | None = None
   ```

2. **Thread the kwarg through the four classmethods** at `the_one/llm/base.py:49-65`. **`visibility` is keyword-only** (`*, visibility: ...`) — design-review-confirmed shape. Every existing classmethod caller passes the second-and-later args as kwargs, so keyword-only costs nothing and prevents positional-misuse drift in F4/F5 dispatcher code:

   ```python
   @classmethod
   def system(cls, content: str, *, visibility: str | None = None) -> Message:
       return cls(role=Role.SYSTEM, content=content, visibility=visibility)

   @classmethod
   def user(cls, content: str, *, visibility: str | None = None) -> Message:
       return cls(role=Role.USER, content=content, visibility=visibility)

   @classmethod
   def assistant(
       cls,
       content: str,
       tool_calls: list[ToolCall] | None = None,
       usage: TokenUsage | None = None,
       *,
       visibility: str | None = None,
   ) -> Message:
       return cls(
           role=Role.ASSISTANT,
           content=content,
           tool_calls=tool_calls or [],
           usage=usage,
           visibility=visibility,
       )

   @classmethod
   def tool(cls, result: ToolResult, *, visibility: str | None = None) -> Message:
       return cls(
           role=Role.TOOL,
           content=result.content,
           tool_result=result,
           visibility=visibility,
       )
   ```

3. **Extend `message_to_dict`** at `the_one/db/codec.py:54`:

   ```python
   def message_to_dict(msg: Message) -> dict[str, Any]:
       """Serialize a Message dataclass to a plain dict."""
       d: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
       if msg.tool_calls:
           d["tool_calls"] = [_tool_call_to_dict(tc) for tc in msg.tool_calls]
       if msg.tool_result is not None:
           d["tool_result"] = _tool_result_to_dict(msg.tool_result)
       if msg.usage is not None:
           d["usage"] = _usage_to_dict(msg.usage)
       # M10 F03 L02: emit visibility only when non-None. Pre-F3 rows had
       # no visibility key; preserve that shape for back-compat and
       # storage efficiency.
       if msg.visibility is not None:
           d["visibility"] = msg.visibility
       return d
   ```

4. **Extend `message_from_dict`** at `the_one/db/codec.py:66`:

   ```python
   def message_from_dict(d: dict[str, Any]) -> Message:
       """Deserialize a plain dict back into a Message dataclass."""
       tool_calls = [
           ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
           for tc in d.get("tool_calls", [])
       ]
       tool_result = None
       if "tool_result" in d:
           tr = d["tool_result"]
           tool_result = ToolResult(
               tool_call_id=tr["tool_call_id"],
               content=tr["content"],
               is_error=tr.get("is_error", False),
               metadata=tr.get("metadata"),
           )
       usage = None
       if "usage" in d:
           u = d["usage"]
           usage = TokenUsage(
               input_tokens=u.get("input_tokens", 0),
               output_tokens=u.get("output_tokens", 0),
           )
       return Message(
           role=Role(d["role"]),
           content=d.get("content", ""),
           tool_calls=tool_calls,
           tool_result=tool_result,
           usage=usage,
           # M10 F03 L02: visibility — None on legacy rows without the key.
           visibility=d.get("visibility"),
       )
   ```

5. **Extend `messages_to_ui_events`** at `the_one/db/codec.py:107`:

   The function emits events into a list across four branches (USER, ASSISTANT content, ASSISTANT tool_call, TOOL tool_result). Add the projection at each `events.append(...)` site so the visibility tag flows into every event derived from a tagged Message. **The cleanest approach** is to compute a per-iteration `_visibility = {"visibility": msg.visibility} if msg.visibility is not None else {}` dict, then spread it into each appended event:

   ```python
   for i, msg in enumerate(messages):
       if msg.role == Role.SYSTEM:
           continue
       # M10 F03 L02: visibility tag flows into every event derived from
       # this message. Absent key when source visibility is None.
       vis = {"visibility": msg.visibility} if msg.visibility is not None else {}
       if msg.role == Role.USER:
           events.append({"type": "user", "content": msg.content, "source": "restored", **vis})
       elif msg.role == Role.ASSISTANT:
           if msg.content:
               events.append({"type": "assistant", "content": msg.content, **vis})
           if msg.tool_calls:
               current_parent_id = f"replay-msg-{i}"
               for tc in msg.tool_calls:
                   events.append(
                       {
                           "type": "tool_call",
                           "name": tc.name,
                           "arguments": tc.arguments,
                           "parent_message_id": current_parent_id,
                           "tool_call_id": tc.id,
                           **vis,
                       }
                   )
       elif msg.role == Role.TOOL:
           if msg.tool_result:
               events.append(
                   {
                       "type": "tool_result",
                       "content": truncate_for_event(msg.tool_result.content),
                       "is_error": msg.tool_result.is_error,
                       "parent_message_id": current_parent_id,
                       "tool_call_id": msg.tool_result.tool_call_id,
                       **vis,
                   }
               )
   ```

   The `**vis` spread expands to nothing when `vis = {}` and to `"visibility": "operator"` when set. All existing keys remain at their existing positions; tests pinning the existing key sets still pass (a `==` dict equality assertion that omits visibility will still equal the event dict that lacks the key — Python dict `==` is order-independent).

6. **Add `OPERATOR_VISIBILITY` constant** to `the_one/connectors/__init__.py`. **Plain assignment, NOT `Final[str]`** — design-review-confirmed: the codebase has zero existing `typing.Final` usages, and the typo-mitigation argument depends on having a single named constant, not on the `Final` annotation specifically. Match the existing module-level-constant style (e.g. `MAX_TOOL_RESULT_INLINE_CONTENT` at `the_one/db/codec.py:15`):

   ```python
   # M10 F03 L02: visibility tag for connector-attached chat sessions.
   # See ``the_one.llm.base.Message.visibility`` for semantics.
   # The string literal lives here so F3 L4's dispatcher, F4's
   # platform-send tool, and F5's operator-input path all reference one
   # constant — a typo like ``"opperator"`` at a production set-site is
   # caught at import / IDE time rather than persisting silently.
   OPERATOR_VISIBILITY = "operator"
   ```

   Update `__all__` to include `"OPERATOR_VISIBILITY"`. Add it at the end of the list with a comment marking it as a constant (parallel to how the existing entries are grouped — Protocols, exceptions, registry).

7. **Add tests**:
   - **Codec + Message visibility round-trip + projection tests** in `tests/test_db_codec.py` (the natural home — the file already covers `message_to_dict / message_from_dict / messages_to_ui_events`). Use distinct top-level test functions OR a new `TestMessageVisibility` class — leg-2 author's call based on the existing style of the file. Cover all the acceptance-criteria scenarios above.
   - **`OPERATOR_VISIBILITY` constant test** in `tests/test_connectors.py` (the file exists and owns the connectors-package surface coverage). One small test: `from the_one.connectors import OPERATOR_VISIBILITY; assert OPERATOR_VISIBILITY == "operator"`. This pins both the value and the export.
   - **Classmethod kwarg tests**: cover all four classmethods accepting `visibility="operator"` AND keyword-only (a positional call should raise `TypeError`). Specifically `Message.user("hi", "operator")` raises (positional rejected); `Message.user("hi", visibility="operator")` works.

8. **Run tests** per the leg-execution prompt's containerized test discipline:
   ```
   docker exec the-one pytest tests/test_db_codec.py -x --timeout 30 -v
   ```
   Iterate until green, then run the full suite as the regression gate:
   ```
   docker exec the-one pytest -x --timeout 30
   ```
   Then `docker exec the-one ruff check the_one/ tests/`.

9. **Update flight log** with a "Leg Progress: message-visibility-field" entry per the ARTIFACTS.md format: started/completed timestamps, changes-made summary, test-count delta (before from leg 1: 1816 passed; after: expected ~1828-1830), any deviations or surprises.

10. **Flip leg status to `landed`** in this file's header. **Check off this leg in `flight.md`** under `### Legs`. **Do NOT commit** — agentic-workflow batched-review defers commit to flight end. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Back-compat with all pre-F3 session JSON**: every existing session row was serialized without a `visibility` key. `d.get("visibility")` returns None for those rows, which is exactly the new default — no migration needed for stored messages. Verified by the `test_message_from_dict_back_compat_no_visibility_key` test.

- **Existing codec tests using `==` equality on whole dicts**: any test asserting `assert events[0] == {"type": "user", "content": "hi", "source": "restored"}` will still pass when the source Message has `visibility=None` because the projected event dict has no `visibility` key. New tests use partial-key assertions (`assert "visibility" not in events[0]` + `assert events[1]["visibility"] == "operator"`) to cover both presence and absence explicitly.

- **`Message` with empty `tool_calls` AND empty content (ASSISTANT, no content, no tool_calls)**: the existing `messages_to_ui_events` skips emitting an assistant-content event when `msg.content` is empty, and skips tool_call events when `msg.tool_calls` is empty. If a connector-attached session somehow produces an empty assistant Message with `visibility="operator"`, NO event is emitted (no shape changes here — `events` simply gets nothing for this message). Document this in passing in the leg's test plan to set expectations correctly.

- **Connector plugins or third-party code constructing `Message` directly via `Message(role=..., content=..., visibility="operator")`**: dataclass `__init__` accepts the new kwarg. No third-party callers exist today; F4's platform-send tool and F5's operator-input path will be the first.

- **Typed/static-analysis tools (mypy, ruff)**: `visibility: str | None` is non-controversial. No new dependencies. The `Final[str]` annotation on `OPERATOR_VISIBILITY` is a standard `typing.Final` import.

- **Forward compatibility with F4 / F5**: F4 will import `OPERATOR_VISIBILITY` from `the_one.connectors`. F5 will likely do the same when implementing the operator-input path. F3 L2 publishes the contract; downstream legs/flights consume it.

## Files Affected

- `the_one/llm/base.py` — extend `Message` dataclass; thread kwarg through 4 classmethods
- `the_one/db/codec.py` — extend `message_to_dict`, `message_from_dict`, `messages_to_ui_events` (3 functions; ~5-10 LoC each)
- `the_one/connectors/__init__.py` — add `OPERATOR_VISIBILITY: Final[str] = "operator"` constant + `__all__` entry
- `tests/test_db_codec.py` — add ~12-15 new tests covering round-trip + projection + classmethod kwarg + back-compat (or a new sibling file if cleaner)
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight-log.md` — leg-completion entry
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight.md` — tick leg 2 under `### Legs`
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/legs/02-message-visibility-field.md` — this file's status → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (scoped + full suite)
- [ ] Lint clean
- [ ] Update flight-log.md with leg progress entry (timestamps + test-count delta + any deviations)
- [ ] Set this leg's status to `landed` (the agentic-workflow Flight Director flips to `completed` at flight-end commit time per the batched-review model)
- [ ] Check off this leg in flight.md's Legs list
- [ ] Do NOT commit — agentic-workflow batched-review model defers commit to flight end
- [ ] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

8 citations verified against current code at leg design time:

- `the_one/llm/base.py:42` (`@dataclass\nclass Message:`) — verified at line 41-47 (the dataclass starts at 41, `class Message:` at 42; classmethods at 49, 53, 57-61, 63).
- `the_one/llm/base.py:49-65` (4 classmethod helpers) — verified.
- `the_one/db/codec.py:54` (`def message_to_dict`) — verified.
- `the_one/db/codec.py:66` (`def message_from_dict`) — verified.
- `the_one/db/codec.py:79` (F5 L3 `d.get("metadata")` template) — verified (the line is inside `message_from_dict`'s `tool_result` block).
- `the_one/db/codec.py:107` (`def messages_to_ui_events`) — verified.
- `the_one/db/codec.py:45-46` (F5 L3 `tr.metadata` emit-when-non-None template) — verified (inside `_tool_result_to_dict`).
- `the_one/connectors/__init__.py` (extant 60-line module with explicit `__all__`) — verified.
- `tests/test_db_codec.py` (extant 424-line test file) — verified.
