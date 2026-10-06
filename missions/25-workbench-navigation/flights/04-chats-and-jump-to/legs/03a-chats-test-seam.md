# Leg: chats-test-seam

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Move every browser test that starts, joins or inspects a chat onto a new
`tests/browser/_chats.py` helper and a `seed_session` seeder. The helpers implement
**today's** semantics against **today's** DOM. This is the seam DD12 asks for: no app
change, and every lane stays green. Leg 3b can then flip the semantics, and leg 4 the DOM,
inside the helpers, with failures pointing at one place.

## Context

- Leg 3 was split at its design review (Flight Director Notes). This half is mechanical
  and has no app change.
- **Today's start path.**
  - Tests click a `.chat-welcome-item` (or change the `agent-select` dropdown, or click
    `new-chat-btn`).
  - They then wait for the `.session-agent-badge` text, or for `_currentSessionId` to be
    set.
  - A session exists right after the start, because today's client sends `new_session`.
- **Site counts** (the leg 3 design review's greps under `tests/browser`):

  | Selector or token | Sites | Files |
  |---|---|---|
  | `chat-welcome-item` | 45 | 18 |
  | `session-agent-badge` | 51 | 18 |
  | `new-chat-btn` | 3 | 2 |
  | `agent-select` | 8 | 4 |
  | `.session-item` | 16 | 4 |
  | `new_session` | 12 | 3 |

  That is about 23 distinct files. The largest are `test_flow_new_chat.py`,
  `test_flow_chat_image_attach.py` and `test_flow_markdown_chat.py`.
- `test_visual_snapshots.py` is `-m pixel`, local-only and in no lane. Migrate it too, for
  consistency, but its run is not a gate.
- **Some sites remain**, and that is expected. Tests that pin the retired surfaces
  themselves (for example `test_flow_new_chat.py`'s welcome-listbox tests, or the
  dropdown test) keep using those selectors until leg 4 rewrites or deletes them. Route
  them through helpers only where a helper fits; do not force it.

## Inputs

- The browser tests listed by the greps above, `tests/browser/_nav.py`, `_lists.py` and
  `seeders.py`.
- `POST /api/chat/sessions` accepts a full `ChatSession`, including `created_at`,
  `updated_at` and `platform` (`api.py` around 4314–4322).

## Outputs

- `tests/browser/_chats.py` (new), with today's semantics:
  - `start_chat(page, agent)`: clicks the agent's welcome item, or falls back to the
    dropdown, and waits until the chat is ready to type: the badge shows the agent, and
    `chat-input` is enabled. **Today** a session exists afterwards.
  - `send_first(page, text)`: fills `chat-input`, presses Enter, and waits for the reply
    to start. **Today** it is the same as any send.
  - `expect_chat(page, agent)`: the joined chat shows `agent`, today through the badge.
  - `current_session_id(page)`: wraps `App.areas.chat._currentSessionId` (or the existing
    accessor).
  - `chat_row(page, id)` and `open_chat(page, id)`: today's `.session-item[data-id]`
    locator, and a click.
  - `chat_frames(page)`: collects the WebSocket frames sent, through CDP
    `Network.webSocketFrameSent` (or the init-script interception
    `test_flow_chat_start_recovery.py` uses), and returns the parsed JSON list.
  - `welcome(page)` and `new_chat_button(page)`: today's locators, for the tests that
    still need them.
- `tests/browser/seeders.py`: `seed_session(base, agent_name, title, updated_at,
  created_at=None, platform=None, messages=None)`, which uses `POST /api/chat/sessions`
  and returns the id.
- The migrated test files: each direct use of the selectors above that a helper covers is
  replaced by the helper call.
- **A guard** in `tests/test_nav_helper.py`, or a new static test, that fails if a browser
  test outside `_chats.py` uses `.chat-welcome-item` or `.session-agent-badge` **to start
  or expect a chat**.
  - It is an allow-list of files that still pin the retired surfaces themselves: the
    welcome and dropdown tests. Leg 4 empties it.
  - Its wording mirrors the Flight 3 retired-selector guard.

## Acceptance Criteria

- [ ] **AC1. The helpers.** `_chats.py` exists with the functions above, each with a
  docstring naming today's mechanism and the leg (3b or 4) that will change its body.
- [ ] **AC2. The seeder.** `seed_session` exists, and a browser test (or the seeder's own
  test, if `seeders.py` has one) creates a session with a past `updated_at` and a
  `platform`, and reads them back through `GET /api/chat/sessions`. Leg 1 added
  `platform` to the summary.
- [ ] **AC3. The migration.** Every test that starts, joins or expects a chat goes through
  `_chats.py`. A re-grep under `tests/browser` (excluding `_chats.py`) for
  `chat-welcome-item` and `session-agent-badge` finds only the guard's allow-listed
  files. The flight log records the before and after counts per selector.
- [ ] **AC4. No behaviour change.** No file under `the_one/` changes in this leg.
- [ ] **AC5. Lanes green.** These run through `scripts/run-tests.sh` with
  `THE_ONE_TEST_NETNS=1` and `PYTHON=.venv/bin/python`, with counts and times recorded in
  the flight log:
  - `chats`;
  - `shared` (`TEST_TIMEOUT=3600`);
  - `settings`, which has `test_flow_provider_setup.py`;
  - `library`, which has `test_flow_studio_knowledge_inventory.py`;
  - `agents`;
  - `make test-unit` (for the guard).

  The test counts per lane are **unchanged** from leg 1's numbers (a migration, not new
  tests), apart from any new helper or seeder tests, which are listed.
- [ ] **AC6. Lint.** `make lint` and `ruff format --check` are clean.

## Verification Steps

- `grep -rn "chat-welcome-item\|session-agent-badge" tests/browser --include=*.py | grep
  -v _chats.py`, before and after.
- The lane commands in AC5.

## Implementation Guidance

1. **Write `_chats.py`** by reading three or four representative tests (`test_flow_chat.py`,
   `test_flow_new_chat.py`, `test_flow_chat_image_attach.py`, `test_router_items.py`) to
   capture the exact wait conditions they use today.
2. **Migrate file by file.** Run that file through `scripts/run-tests.sh <file> -x` after
   each one; do not batch blind.
3. **Keep the assertions** the tests make **about** behaviour. Only the mechanics move
   into helpers.
4. **The guard last**, once the greps show only the allow-listed files.

## Edge Cases

- **Tests that drive WebSocket frames directly** (`test_router_items.py` with
  `new_session`): keep their frame logic, but route the start through `start_chat`.
  Their `new_session` expectations are inverted in leg 3b, not here.
- **Tests in shared-lane files** (`test_shell_rail.py`, `test_router_core.py`,
  `test_nav_guard.py`, `test_flow_hash_routing.py`, `test_flow_keyboard.py`,
  `test_oauth_modal_flow.py`): migrate them too. They are part of the seam.

## Files Affected

- `tests/browser/_chats.py` — new.
- `tests/browser/seeders.py`.
- About 23 `tests/browser/test_*.py` files.
- `tests/test_nav_helper.py`, or a new static guard.
