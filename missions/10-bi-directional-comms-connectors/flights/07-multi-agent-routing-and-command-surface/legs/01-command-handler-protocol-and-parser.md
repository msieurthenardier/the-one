# Leg: command-handler-protocol-and-parser

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Land the `CommandHandler` Protocol type-level surface in `the_one/connectors/base.py` and the `_parse_command` text-prefix parser in a new `the_one/connectors/_commands.py` module; close the 5 F1 forward-reference docstring sites with landed-feature citation language; ship parser + Protocol surface tests. No dispatcher integration (L5), no command-handler implementations (L6).

## Context

This is the first F7 leg. Per Design Decisions in `flight.md`:

- **"CommandHandler Protocol via structural satisfaction (additive, optional)"** — single-method optional Protocol declared in `base.py` adjacent to (not widening) `ConnectorPlugin`. v1 commands are NOT routed through it — they ride the dispatcher's built-in text-prefix parser (L5). The Protocol is the additive extension point for plugins that want to register platform-native slash commands (F8 Discord, F9 Slack).
- **F6 prior art** — `connectors/_pairing.py` (`_validate_pairing_prefix`) is the shape this leg mirrors for `_parse_command`: pure function, no I/O, byte-equality comparisons (case-sensitive), module docstring citing the leg that introduces it.
- **F1 forward-references** — five docstring sites predict `CommandHandler`'s arrival in F7. The flight log's reconnaissance report enumerates them; L1 rewrites each from prediction-language to citation-language.
- **Regression posture** — the stub plugin does NOT implement `CommandHandler`. F1–F6 dispatcher / e2e / resolver test suites pass byte-identically.

Key learnings from prior legs (from the flight log):

- F1–F6 scaffolding inventory confirms zero existing `_commands`, `CommandHandler`, or `_parse_command` symbols outside the 5 docstring forward-references.
- `agents.md`'s "structural-Protocol-satisfaction" convention applies: implementations expose method names rather than inherit.
- `agents.md`'s "canonical-import + convenience-re-export" convention applies: Protocol identity is canonical via `the_one.connectors.base`; `the_one/connectors/__init__.py` may re-export for convenience.

## Inputs

What exists before this leg runs:

- `the_one/connectors/base.py` containing `ConnectorPlugin`, `ConnectorClient`, `InboundEnvelope`, `OutboundTarget`, `SessionKey`, `DoctorReport`, `SendResult`, `Permit`, `NeedsPairing`, `Deny`, `ResolveOutcome`, `_default_permit`. Two `CommandHandler` forward-reference docstring sites at `base.py:19` and `base.py:294-297`.
- `the_one/connectors/_pairing.py` exporting `_validate_pairing_prefix(text, code)` — the shape this leg mirrors.
- `the_one/connectors/__init__.py` re-exporting public surface from `base.py`.
- `the_one/connectors/README.md` with `CommandHandler` forward-reference docstring sites at `README.md:31` and `README.md:88-90`.
- `the_one/agents.md` with `CommandHandler` forward-reference at `agents.md:337`.
- Stub plugin at `the_one/connectors/_stub.py` — does NOT and MUST NOT implement `handle_command`.
- F1–F6 test suite green: `docker exec the-one pytest tests/test_connectors* -x --timeout 30`.

## Outputs

What exists after this leg completes:

- `the_one/connectors/base.py` with two new public symbols (`CommandHandler` Protocol; `CommandResponse` dataclass) and two updated docstrings (module + `ConnectorPlugin` Protocol).
- `the_one/connectors/_commands.py` (NEW) exporting `_parse_command(text: str) -> tuple[str, list[str]] | None`.
- `the_one/connectors/__init__.py` with `CommandHandler` and `CommandResponse` added to the convenience re-export block.
- `the_one/connectors/README.md` with the two forward-reference sites rewritten to landed-feature citation language.
- `the_one/agents.md` with the F7 subsystem-table entry rewritten to landed-feature citation language.
- `tests/test_connectors_commands.py` (NEW) pinning parser behavior + Protocol surface.
- F1–F6 test suites pass byte-identically.

## Acceptance Criteria

- [ ] `CommandResponse` dataclass declared in `the_one/connectors/base.py`: `@dataclass(frozen=True, slots=True)`; single field `text: str`. Placed IMMEDIATELY BEFORE the `CommandHandler` Protocol at the end of the file (co-located with its only consumer, not interleaved into the F6 `Permit`/`NeedsPairing`/`Deny`/`ResolveOutcome` ADT cluster).
- [ ] `CommandHandler` Protocol declared in `the_one/connectors/base.py`: `@runtime_checkable`; single async method `handle_command(envelope: InboundEnvelope, command_name: str, args: list[str]) -> CommandResponse | None`. Placed AFTER `ConnectorPlugin` Protocol (at end of file), with `CommandResponse` immediately above it.
- [ ] `the_one/connectors/_commands.py` ships `_parse_command(text: str) -> tuple[str, list[str]] | None`:
  - Returns `(command_name, args)` if `text` starts with `/`, the immediate next characters match `[a-z][a-z0-9-]*` (lowercase command-name shape), and the command name is followed either by end-of-string or by whitespace + args.
  - Returns `None` otherwise.
  - Pure function. Module docstring cites M10 F7 L1, mirrors `_pairing.py`'s tone.
  - No regex required — string ops only, mirroring `_pairing.py`.
- [ ] `the_one/connectors/__init__.py` adds `CommandHandler` and `CommandResponse` to BOTH (i) the `from the_one.connectors.base import (...)` block AND (ii) the `__all__` list's `# Protocols + supporting types` group at `__init__.py:69-80` — alphabetically positioned in both. Canonical-import discipline note in the existing module docstring is unchanged and still applies.
- [ ] Five forward-reference docstring sites rewritten to landed-feature citation language:
  - `the_one/connectors/base.py:19` (module docstring `:class:\`CommandHandler\` Protocol (introduced by flight 7)`) — drop the "future" framing; cite "F7 L1".
  - `the_one/connectors/base.py:294-297` (`ConnectorPlugin` docstring `Flight 7 will introduce a separate :class:\`CommandHandler\` Protocol...`) — drop "will introduce"; cite "F7 L1 declares".
  - `the_one/connectors/README.md:31` (`# Future home of CommandHandler (Flight 7).`) — replace with landed comment.
  - `the_one/connectors/README.md:88-90` (`CommandHandler` (Flight 7) — connectors that handle...) — rewrite entry to mirror the `resolve` entry's shape (declared on `base.py`, structural satisfaction, return-`None`-falls-through-to-dispatcher's-built-in semantic, F8 / F9 as future consumers).
  - `the_one/agents.md:337` (subsystem-table entry referencing `(Flight 7)`) — rewrite to landed citation (`F7 L1`).
- [ ] `tests/test_connectors_commands.py` (NEW) lands and passes. Style mirrors `tests/test_connectors_resolver.py` (type-level surface tests + inline minimal fixtures, NOT the heavyweight `_connector_dispatch_helpers`). Test classes:
  - `TestParseCommand` — parser happy paths and negatives (see Verification Steps for the case enumeration).
  - `TestCommandHandlerProtocol` — `runtime_checkable` works for a sample handler; stub plugin does NOT satisfy (`not isinstance(StubPlugin(), CommandHandler)`).
  - `TestCommandResponse` — frozen, slotted, equality, hashability.
- [ ] F1–F6 regression suite passes byte-identically. Run command (per project's docker entrypoint convention from leg-execution.md's Implement prompt — uses the glob over the connector test files so newly-added connector test modules are picked up automatically):
  ```
  docker exec the-one pytest tests/test_connectors*.py tests/test_pairing*.py -x --timeout 30
  ```
  The `tests/test_pairing*.py` glob is empty today (L8 introduces `tests/test_pairing_prefix.py`); it's included now so the regression command needs no further edits when L8 lands.
- [ ] `grep -nE "future :class:\`CommandHandler|Future home of CommandHandler|will introduce" the_one/connectors/base.py the_one/connectors/README.md the_one/agents.md` returns zero hits. (Matches Verification Steps' "Forward-reference closure" pattern — same grep both places, so prediction-language can't leak past one and not the other.)
- [ ] `grep -n "CommandHandler\|CommandResponse" the_one/connectors/base.py the_one/connectors/__init__.py the_one/connectors/_commands.py` confirms the new symbols are declared in `base.py` and re-exported from `__init__.py`. (`_commands.py` does NOT need to reference `CommandHandler`/`CommandResponse` directly — the parser is independent of the Protocol; L5 will be the first call site that consumes both.)

## Verification Steps

How to confirm each criterion is met:

**Parser happy paths** (in `TestParseCommand`):

- `_parse_command("/agents")` → `("agents", [])`
- `_parse_command("/whoami")` → `("whoami", [])`
- `_parse_command("/help")` → `("help", [])`
- `_parse_command("/new")` → `("new", [])`
- `_parse_command("/reset")` → `("reset", [])`
- `_parse_command("/talk-to alice")` → `("talk-to", ["alice"])`
- `_parse_command("/talk-to alice extra")` → `("talk-to", ["alice", "extra"])`
- `_parse_command("/talk-to   alice   bob")` → `("talk-to", ["alice", "bob"])` (`str.split()` collapses runs of whitespace)
- `_parse_command("/talk-to   ")` → `("talk-to", [])` (trailing whitespace alone produces no args)

**Parser negatives** (in `TestParseCommand`):

- `_parse_command("")` → `None`
- `_parse_command("hello")` → `None`
- `_parse_command("/")` → `None` (no command word)
- `_parse_command("//double")` → `None` (single-leading-slash rule)
- `_parse_command(" /agents")` → `None` (commands must be at column 0; matches `_validate_pairing_prefix`'s `startswith`)
- `_parse_command("/Agents")` → `None` (case-sensitive; lowercase only — matches `_validate_pairing_prefix` precedent)
- `_parse_command("/-foo")` → `None` (must start with `[a-z]`)
- `_parse_command("/9foo")` → `None` (must start with `[a-z]`)
- `_parse_command("/foo_bar")` → `None` (`_` not in `[a-z0-9-]`)

**Protocol surface** (in `TestCommandHandlerProtocol`):

- `isinstance(_SampleHandler(), CommandHandler)` is `True` where `_SampleHandler` is a tiny inline class with the right `async def handle_command(...)` signature.
- `isinstance(StubPlugin(), CommandHandler)` is `False` — stub plugin does not implement `handle_command`. (Confirms regression-net preservation.)
- `CommandHandler` is `runtime_checkable` (instantiate a class without the method and assert `isinstance` returns `False`).
- `isinstance(_SyncSampleHandler(), CommandHandler)` is `True` where `_SyncSampleHandler` exposes a SYNCHRONOUS `def handle_command(...)` (no `async`) with otherwise-identical signature. This pins the stdlib limitation `@runtime_checkable` Protocols verify method NAMES only — they do NOT verify signature, async-ness, or return type. Test docstring documents the implication: L5's dispatcher MUST treat the return as awaitable per the Protocol's declared shape, not per the runtime-check guarantee. (A plugin that violates the declared async signature breaks the runtime contract; the runtime check does not catch it. This is acceptable and documented.)
- `CommandHandler.__module__ == "the_one.connectors.base"` — pins canonical-import identity. (Mirrors the same-named assertion in `test_connectors_resolver.py` for `_default_permit`.)
- `CommandResponse.__module__ == "the_one.connectors.base"` — same rationale.

**Dataclass surface** (in `TestCommandResponse`):

- `CommandResponse(text="hi")` constructs; `.text == "hi"`.
- `CommandResponse(text="hi") == CommandResponse(text="hi")` is `True` (frozen + slotted + equal).
- `hash(CommandResponse(text="hi"))` does not raise.
- Mutation raises `dataclasses.FrozenInstanceError`.

**Forward-reference closure**:

- `grep -nE "future :class:\`CommandHandler|Future home of CommandHandler|will introduce" the_one/connectors/base.py the_one/connectors/README.md the_one/agents.md` returns zero hits. (Landed citations such as `F7 L1` or `flight 7 leg 1` are fine — only prediction language is removed. NOTE: `(Flight 7)` is deliberately omitted from the grep because that bare-parenthesized form may legitimately appear in unrelated content such as flight-log entries; the rewrites below replace the specific `(Flight 7)` occurrences at `README.md:88-90` and `agents.md:337` directly.)

**Regression**:

- Run the long pytest command in Acceptance Criteria; all tests pass with no new failures and no skips beyond what F1–F6 already skipped.

## Implementation Guidance

### 1. Add the dataclass and Protocol to `base.py`

Place `CommandResponse` IMMEDIATELY BEFORE `CommandHandler` Protocol at the END of the file. This co-locates the dataclass with its only consumer (the Protocol) and keeps the F6 `Permit`/`NeedsPairing`/`Deny`/`ResolveOutcome` ADT cluster (lines 174–213) visually intact. Mirror their dataclass style:

```python
@dataclass(frozen=True, slots=True)
class CommandResponse:
    """Result of a :class:`CommandHandler` handling a platform-side command.

    The handler returns this value; the dispatcher (F7 L5) emits ``text``
    via the system-outbound path (``pool_acquire(agent_name, account_id)
    → client.send(target, text)``) — the same path the platform-send tool
    uses, invoked dispatcher-internally rather than via the tool registry.

    Returning ``None`` from :meth:`CommandHandler.handle_command` is
    distinct from returning ``CommandResponse(text="")`` — ``None`` means
    "fall through to the dispatcher's built-in handler"; an empty-text
    response means "this handler handled the command and the response is
    intentionally empty" (and the dispatcher MUST NOT fall through).
    """

    text: str
```

Then `CommandHandler` Protocol immediately after `CommandResponse` (end of file). Mirror the existing Protocol docstring tone (runtime_checkable, structural satisfaction, etc.):

```python
@runtime_checkable
class CommandHandler(Protocol):
    """Optional platform-side command handler.

    Declared as a SEPARATE Protocol from :class:`ConnectorPlugin` — not a
    widening — so the existing 4-method plugin contract stays stable and
    plugins opt into command-handling additively. Connectors that want to
    register platform-native command surfaces (Discord slash commands via
    the Interactions API in F8; Slack slash commands via app manifest in
    F9) structurally satisfy this Protocol in addition to
    :class:`ConnectorPlugin`. Connectors that do NOT implement it (the
    stub plugin in this flight; the F8 / F9 plugins until they opt in)
    fall through to the dispatcher's built-in text-prefix command parser
    (F7 L5).

    Returning ``None`` from :meth:`handle_command` means "I don't handle
    this command; let the dispatcher's built-in handler take over." This
    lets plugins handle a subset of platform-native commands while still
    inheriting the v1 text-prefix vocabulary for the remainder.

    Per ``agents.md`` ``structural-Protocol-satisfaction``: implementations
    do NOT inherit from this Protocol. ``runtime_checkable`` Protocol
    checks method NAMES only.
    """

    async def handle_command(
        self,
        envelope: InboundEnvelope,
        command_name: str,
        args: list[str],
    ) -> CommandResponse | None:
        """Handle ``command_name`` parsed from ``envelope.text``.

        ``command_name`` is the bare command word (e.g. ``"agents"``,
        ``"talk-to"`` — no leading slash). ``args`` is the
        whitespace-separated remainder (empty list when the command has
        no args).

        Returns :class:`CommandResponse` if this plugin handles the
        command and the dispatcher should emit the response via the
        system-outbound path. Returns ``None`` to fall through to the
        dispatcher's built-in handler (F7 L5).
        """
        ...
```

### 2. Rewrite the two `base.py` forward-reference docstring sites

`base.py:19` — the module docstring currently mentions the "future" `CommandHandler`. Rewrite that single clause to drop "future" framing and reference the landed declaration. Example replacement:

> The three-outcome ADT (:class:`Permit`, :class:`NeedsPairing`, :class:`Deny`, exposed as :data:`ResolveOutcome`) and the :class:`CommandHandler` Protocol (F7 L1) live alongside the Protocols in this file — "single contract file" is the mission criterion, not "single Protocol".

`base.py:294-297` — `ConnectorPlugin` docstring currently says "Flight 7 will introduce a separate :class:`CommandHandler` Protocol...". Rewrite to:

> F7 L1 declares a separate :class:`CommandHandler` Protocol in this file that command-aware connectors structurally satisfy in addition to :class:`ConnectorPlugin`.

### 3. New module `the_one/connectors/_commands.py`

```python
"""Platform-side command text-prefix parser.

M10 F07 L1: parses leading-slash commands of the form ``/<name> [args...]``
from an inbound envelope's text. v1 vocabulary: ``/agents``, ``/talk-to``,
``/whoami``, ``/new``, ``/reset``, ``/help`` (F7 L6 ships the handlers; F7
L5 wires the parser into the inbound dispatcher).

Pure function — no I/O. Mirrors :mod:`the_one.connectors._pairing`'s shape:
byte-equality comparisons, no regex, returns a discriminated value the
dispatcher can branch on. Case-sensitive (lowercase command names only) —
same convention as :func:`_validate_pairing_prefix`'s ``PAIR`` keyword.
"""

from __future__ import annotations

_COMMAND_PREFIX = "/"

# Lowercase letters / digits / hyphen for the command word's tail.
# The leading character must be a lowercase letter — matches the slug
# shape used elsewhere in the project (agent names, connector type
# identifiers, etc.). Frozen literal sets (NOT ``string.ascii_lowercase``)
# match the project's existing character-class convention — see
# ``_INTERACTIVE_SHELL_BASENAMES``, ``GATED_METHODS``, ``OAUTH_MANAGED_SECRET_KEYS``;
# zero existing ``import string`` usages in ``the_one/``.
_NAME_HEAD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz")
_NAME_TAIL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def _parse_command(text: str) -> tuple[str, list[str]] | None:
    """Parse ``text`` as ``/<name> [args...]``.

    Returns ``(command_name, args)`` if ``text`` starts with a single
    forward slash, the next character is a lowercase letter, the
    following characters are all in ``[a-z0-9-]``, and the command name
    is terminated either by end-of-string or by whitespace.

    Returns ``None`` if any of those conditions fail (including: empty
    text, leading whitespace, a non-slash prefix, a double slash, an
    uppercase or underscore in the name, etc.).

    ``args`` is ``text``'s post-name remainder split on whitespace via
    :meth:`str.split` (no argument) — runs of whitespace collapse;
    trailing whitespace alone produces no args.
    """
    if not text.startswith(_COMMAND_PREFIX):
        return None
    rest = text[len(_COMMAND_PREFIX) :]
    if not rest:
        return None
    head = rest[0]
    if head not in _NAME_HEAD_CHARS:
        return None
    # Walk the name characters until we hit whitespace or end-of-string.
    name_end = 1
    while name_end < len(rest):
        c = rest[name_end]
        if c.isspace():
            break
        if c not in _NAME_TAIL_CHARS:
            return None
        name_end += 1
    command_name = rest[:name_end]
    args_text = rest[name_end:]
    args = args_text.split()
    return command_name, args
```

### 4. Update `__init__.py` re-exports

Add `CommandHandler` and `CommandResponse` to the alphabetically-positioned list in the `from the_one.connectors.base import (...)` block. Do NOT modify the canonical-import discipline note — it already covers the new Protocol identity (callers wanting `isinstance(..., CommandHandler)` continue to use the canonical `the_one.connectors.base` path).

### 5. Rewrite the three `README.md` / `agents.md` forward-reference sites

`README.md:31` — current text: `#                      # _default_permit fallback. Future home of CommandHandler` / `#                      # (Flight 7).`

Replace the "Future home of CommandHandler (Flight 7)." clause with `Home of F7 L1's CommandHandler Protocol and CommandResponse dataclass.` Keep the comment lines aligned with the surrounding ASCII-art tree-diagram style.

`README.md:88-90` — current entry under §4:

```
- `CommandHandler` (Flight 7) — connectors that handle platform-side
  commands (`/agents`, `/talk-to`, etc.) will additionally satisfy this
  Protocol.
```

Rewrite to landed-feature description, mirroring the `resolve` entry's shape immediately above:

```
- `CommandHandler` Protocol (F7 L1) — declared in `base.py`. Connectors
  that want to register platform-native command surfaces (Discord slash
  commands in F8, Slack in F9) structurally satisfy it in addition to
  `ConnectorPlugin`. Handler may return `None` to fall through to the
  dispatcher's built-in text-prefix parser (F7 L5); returns
  `CommandResponse(text=...)` to emit a response via the system-outbound
  path. NOT a `ConnectorPlugin` widening.
```

`agents.md:337` — current line:

```
- `CommandHandler` (Flight 7) — platform-side command surface (`/agents`, `/talk-to`, `/whoami`, `/reset`, `/new`, `/help`)
```

Rewrite to landed citation:

```
- `CommandHandler` (F7 L1) — optional platform-side command-handler Protocol; structural satisfaction in addition to `ConnectorPlugin`; v1 vocabulary (`/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help`) is handled by the dispatcher's built-in text-prefix parser, with plugins free to register platform-native equivalents that supersede the built-in handler.
```

### 6. Test file `tests/test_connectors_commands.py`

Style mirrors `tests/test_connectors_resolver.py` exactly:

```python
"""Type-level surface tests for F7 L1's CommandHandler Protocol and
CommandResponse dataclass plus the text-prefix command parser in
``_commands.py``.

Leg 1 of M10 F07 lands the surfaces but no consumer; leg 5 will wire
``_parse_command`` into the inbound dispatcher and leg 6 will ship the
six v1 command handlers. These tests pin:

- the parser's happy paths and negatives (case-sensitivity, single-slash
  rule, lowercase-letter-leading rule, whitespace handling, no-args
  default)
- ``CommandResponse`` is frozen + slotted + equal + hashable
- ``CommandHandler`` is runtime_checkable and accepts a sample handler
- the ``StubPlugin`` does NOT implement ``handle_command`` (regression-net
  preservation; F1–F6 dispatcher tests exercise the fall-through path)

Inline minimal fixtures (mirrors ``test_connectors_resolver.py``).
"""
```

Then three classes: `TestParseCommand`, `TestCommandResponse`, `TestCommandHandlerProtocol`. Each test is a small `def test_...` taking no fixtures.

### 7. Order of file edits

The leg has no inter-file ordering dependencies — `_commands.py` doesn't import `CommandHandler`, and the docstring rewrites are pure-text edits. Suggested order for clean diffs:

1. `_commands.py` (new file)
2. `base.py` (add `CommandResponse` + `CommandHandler`; rewrite two docstring sites)
3. `__init__.py` (extend re-export block)
4. `README.md` (rewrite two sites)
5. `agents.md` (rewrite one site)
6. `tests/test_connectors_commands.py` (new file)

## Edge Cases

- **`/talk-to` with no args** (`_parse_command("/talk-to")`) → `("talk-to", [])`. The dispatcher (L5) and handler (L6) decide whether empty-args is an error for `/talk-to` specifically; the parser stays generic.
- **Command names exactly equal to a substring of another** — there's no `_NAME_LENGTH_LIMIT`; `/talk-to-the-hand` parses as `("talk-to-the-hand", [])`. The dispatcher (L5) decides what is and isn't a known command via lookup against the v1 vocabulary table — the parser does not enforce the v1 set.
- **Unicode whitespace** — `str.split()` with no argument splits on any whitespace (per Python's stdlib semantics). Acceptable; the parser does not need to be exotic about which whitespace counts.
- **Whitespace before the first arg** — handled by `str.split()`'s collapse-runs behavior. `/talk-to   alice` parses identically to `/talk-to alice`.
- **Empty command name after slash** (`/`) — caught by the `if not rest:` guard.
- **Command name with trailing slash** (`/agents/` or `/agents/foo`) — `_NAME_TAIL_CHARS` does not include `/`. Returns `None`. (`/agents/foo` could conceivably be a nested command in some future world; L1 rejects it and leaves design space for L5+ to revisit.)
- **Stub plugin** — MUST continue to NOT implement `handle_command`. The F6 dispatcher tests rely on the stub NOT being a `CommandHandler` (the fall-through path). Adding `handle_command` to the stub here would break the regression net AND would couple the stub to L5's not-yet-shipped dispatcher integration.

## Files Affected

- `the_one/connectors/base.py` — add `CommandResponse` dataclass + `CommandHandler` Protocol; rewrite two forward-reference docstring sites (`base.py:19` module docstring; `base.py:294-297` `ConnectorPlugin` docstring).
- `the_one/connectors/_commands.py` (NEW) — `_parse_command` text-prefix parser.
- `the_one/connectors/__init__.py` — add `CommandHandler` and `CommandResponse` to the convenience re-export block.
- `the_one/connectors/README.md` — rewrite two forward-reference sites (`README.md:31` architecture comment; `README.md:88-90` §4 optional-hook entry).
- `the_one/agents.md` — rewrite forward-reference site at `agents.md:337` (subsystem-table entry).
- `tests/test_connectors_commands.py` (NEW) — pin parser behavior + Protocol surface + dataclass surface.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

5 code-location citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/connectors/base.py:19` (`:class:\`CommandHandler\` Protocol (introduced by flight 7)` clause in module docstring) | OK | Verified via `grep -n` — single hit at line 19 |
| `the_one/connectors/base.py:294-297` (`Flight 7 will introduce a separate :class:\`CommandHandler\` Protocol...` in `ConnectorPlugin` docstring) | OK | Verified via `grep -n` — line 295 lands the `:class:\`CommandHandler\` Protocol,` clause; surrounding paragraph spans 294-297 |
| `the_one/connectors/README.md:31` (`# _default_permit fallback. Future home of CommandHandler` / line 32: `# (Flight 7).`) | OK — drifted by one line | Forward-reference clause spans `README.md:31-32`; the leg artifact's grep target covers both |
| `the_one/connectors/README.md:88-90` (`CommandHandler` (Flight 7) — connectors that handle...`) | OK | Verified — entry at lines 88-90 |
| `the_one/agents.md:337` (`CommandHandler` (Flight 7) — platform-side command surface...`) | OK | Verified via `grep -n` — single hit at line 337 |

Test-file references: `tests/test_connectors_resolver.py` confirmed present (126 lines; inline minimal fixtures pattern). `tests/test_connectors_inbound.py` confirmed present (1100+ lines; uses heavyweight helpers — NOT the pattern this leg mirrors).

Prior-art references: `the_one/connectors/_pairing.py:18-41` confirmed — single-function module, byte-equality comparisons, case-sensitive prefix, returns 2-tuple. Faithful shape for `_parse_command` to mirror.
