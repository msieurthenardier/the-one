# Leg: bug-h-slash-text-hyphenate-command-name

**Status**: landed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

> **Discovered at L10 re-run #2 via Validator source-analysis after L12 (Bug G.1) failed to fix the `/talk_to` routing.** Bug G.1 added underscore→hyphen normalization inside `_dispatch_builtin_command`, but `_parse_command` (the gate BEFORE `_dispatch_builtin_command`) rejects underscore entirely — so the envelope text `/talk_to Sonos Agent` never even reaches the dispatcher. The G.1 unit test passed only because it called `_dispatch_builtin_command("talk_to", ...)` directly, bypassing `_parse_command`. The real fix is one level upstream: hyphenate in `_build_slash_envelope` so the synthesized text can parse.

## Objective

Fix `/talk_to` slash commands by correcting the envelope text synthesis in `_build_slash_envelope` so `_parse_command` can parse the command name. The other five commands are unaffected (no underscore in their names).

## Root Cause

`_build_slash_envelope` (`_discord.py`) synthesized the envelope text as `f"/{command_name} {args_str}"` — with the Discord-registered name verbatim. For `talk_to` the text became `/talk_to Sonos Agent`.

`_parse_command` (`_commands.py`) accepts only `[a-z0-9-]` in the command name tail (`_NAME_TAIL_CHARS`). Underscore is excluded. When it encounters `_` in the name it returns `None` immediately. The dispatcher's step 11 receives `None` from `_parse_command` and falls through to `agent.step` — the "thinking…" ack never resolves to a routing confirmation.

**Why Bug G.1 was unreachable:** `_dispatch_builtin_command` is only called when `_parse_command` succeeds. The G.1 normalization (`_HANDLERS.get(command_name.replace("_", "-"))`) is defensive-depth for hypothetical direct callers, but in the real Discord slash path `_parse_command` gates everything. The G.1 test called `_dispatch_builtin_command("talk_to", ...)` directly, so it never exercised `_parse_command` — a blind spot.

## Fix Applied

**Primary fix (`the_one/connectors/_discord.py`, `_build_slash_envelope`):**

Before synthesizing the envelope text, hyphenate the command name:

```python
cmd_text = command_name.replace("_", "-")
text = f"/{cmd_text}" if not args_str else f"/{cmd_text} {args_str}"
```

For `talk_to` with `args="Sonos Agent"` the text becomes `/talk-to Sonos Agent` — `_parse_command` yields `("talk-to", ["Sonos", "Agent"])` — `_HANDLERS["talk-to"]` → `_handle_talk_to` runs. The other five v1 commands (`agents`, `whoami`, `new`, `reset`, `help`) have no underscore; the replacement is a no-op.

Updated `_build_slash_envelope`'s docstring (the prior text incorrectly claimed that `/talk_to my-agent` reaches the dispatcher unchanged — that was the bug) and the `_SLASH_COMMAND_VOCAB` module-level comment to describe the hyphenation bridge.

**Belt-and-suspenders comment (`the_one/connectors/_commands.py`, `_dispatch_builtin_command`):**

The G.1 normalization is retained as a defensive backstop but a multi-line comment now clarifies that it is NOT the primary fix — the real protection is in `_build_slash_envelope`. The normalization guards against hypothetical future direct-call sites that bypass the envelope layer.

## Tests

**`tests/test_connectors_discord.py` — two new unit tests:**

- `test_build_slash_envelope_talk_to_hyphenates_command_name`: calls `_build_slash_envelope(command_name="talk_to", args="Sonos Agent", ...)` and asserts:
  1. `envelope.text == "/talk-to Sonos Agent"` (hyphen, not underscore)
  2. `_parse_command(envelope.text)` returns `("talk-to", ["Sonos", "Agent"])` (proves the round-trip through the parser succeeds)
  - Would FAIL pre-fix: text was `/talk_to Sonos Agent` → `_parse_command` → `None`.

- `test_build_slash_envelope_non_underscore_commands_unchanged`: iterates the other five commands and asserts each produces `f"/{cmd}"` text that also parses cleanly — confirms the hyphenation is a no-op for them.

**`tests/test_connectors_discord.py` — existing test updated:**

`test_slash_command_body_dispatches_envelope` previously asserted `envelope.text == "/talk_to my-agent"`. Updated to `"/talk-to my-agent"` with a comment explaining the Bug H fix. This test was **encoding the bug** — it would pass pre-fix and fail post-fix without the update.

**`tests/test_connectors_commands.py` — docstring update:**

`TestBugGHandlerKeyMismatch` class docstring updated with a Bug H note clarifying that the G.1 normalization in `_dispatch_builtin_command` is now a belt-and-suspenders backstop (the underscore form never reaches this dispatcher via the real Discord slash path post-fix), and that the coverage must NOT be removed. Individual test docstrings also updated to reflect this.

## Acceptance Criteria

- [x] `_build_slash_envelope` hyphenates the command name before synthesizing the envelope text (`cmd_text = command_name.replace("_", "-")`). `talk_to` → text is `/talk-to …`; other commands unchanged.
- [x] Docstring for `_build_slash_envelope` corrected: no longer claims `/talk_to my-agent` reaches the dispatcher; describes the hyphenation and the reason.
- [x] `_SLASH_COMMAND_VOCAB` module-level comment updated to describe the hyphenation bridge (Bug H fix, M11 F14 L13).
- [x] G.1 normalization in `_dispatch_builtin_command` retained with a multi-line comment that labels it belt-and-suspenders and names the primary fix site.
- [x] Regression tests in `tests/test_connectors_discord.py` that exercise the full `_build_slash_envelope` → `_parse_command` round-trip for `talk_to` (fail pre-fix, pass post-fix).
- [x] Existing `test_slash_command_body_dispatches_envelope` updated: asserts `/talk-to my-agent` (was incorrectly asserting the bug form `/talk_to my-agent`).
- [x] `TestBugGHandlerKeyMismatch` in `test_connectors_commands.py` annotated with Bug H clarification; coverage retained.
- [x] Targeted test run: 155 passed (was 153, +2 new tests).
- [x] Full backend (`-m 'not browser and not live and not pixel' -q`): **2820 passed, 4 skipped, 0 errors** (prior: 2818 at L12, +2 new).

## Files Affected

- `the_one/connectors/_discord.py` — `_build_slash_envelope` text synthesis + docstring; `_SLASH_COMMAND_VOCAB` module-level comment.
- `the_one/connectors/_commands.py` — `_dispatch_builtin_command` G.1 normalization comment updated.
- `tests/test_connectors_discord.py` — 2 new regression tests; 1 existing test assertion corrected.
- `tests/test_connectors_commands.py` — `TestBugGHandlerKeyMismatch` docstring + test docstring updates.

---

## Post-Completion Checklist

- [x] Fix in place; regression tests added that fail pre-fix; existing test corrected
- [x] Full backend green (2820 passed, 4 skipped; 2818 prior + 2 new)
- [x] Update flight-log.md with an L13/Bug H leg-progress entry
- [x] Set this leg's status to `landed`
- [ ] Do NOT commit yet (FD commits at the re-HAT close)
