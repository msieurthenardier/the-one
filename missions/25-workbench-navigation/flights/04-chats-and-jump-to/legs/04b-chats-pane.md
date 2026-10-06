# Leg: chats-pane

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Give the Chats **detail pane** its board shape:
- **the header** (§5.2): an `h1` title with "with {agent}";
- **the new-chat state** (§5.4): the model badge, the agent's name and description, and
  "Pick a different agent";
- **the empty and setup-guidance states**, under one "Hello." `h1`.

Extract the composer into a DOM-built `areas/chat/composer.js`, with its markup carried
over (leg 5 restyles it). Remove the last chat HTML-string sink.

Retire the welcome agent list, the header `new-chat-btn` and `h2.session-agent-badge`, and
replace leg 3a's seam guard with `RETIRED_SELECTORS` entries.

Split from leg 4 at its design review. **4a** (the sidebar and the picker) has landed
before this leg.

## Context

- **Flight decisions:** DD3, DD6 (the header and the new-chat state; the composer
  restyle is leg 5's), DD12 and DD15 (A20). The leg 4 design review answers are in the
  flight log.
- **One `h1` in every state.** In `joined`, `pending` and `starting` the `h1` is the
  header's title. With no chat open, it is the welcome's "Hello." greeting
  (`h1.chat-welcome-greeting`, kept, as `test_flow_new_chat.py` pins).
- **`.chat-chrome` stays** as the class of the pane wrapper that holds the header, the
  messages, the queued region, telemetry and the composer.
  `test_flow_context_overlay_thresholds.py` (around 62 and 85) queries it.
- **The `chat-welcome` testid** stays on the empty and guidance container. Its children
  `chat-welcome-mascot`, `.chat-welcome-greeting`, `.chat-welcome-prompt`,
  `.chat-welcome-guidance` and `.chat-welcome-link` stay, and are **exempt** from
  retirement. `test_flow_provider_setup.py:35` and `test_router_items.py` around 763–765
  use them.

## Inputs

- After 4a:
  - `chat.js`, with the content sink (`content.innerHTML = …`, around 292) holding the
    welcome canvas (mascot, greeting, prompt, `.chat-welcome-list`), the `.chat-chrome`
    header (`h2.session-agent-badge` plus `new-chat-btn`), messages and attachments, and
    the composer (`.input-area`);
  - `welcome.js` (`renderWelcomeList`: the guidance and ready modes);
  - `showWelcome`/`showChrome`, `updateAgentBadge` and the welcome keydown.
- Leg 3b's session state and `requestPick`. 4a's `openPicker`, the `chats-list` render and
  the `providers` resolution helper.
- `tests/test_nav_helper.py`'s `CHAT_SEAM_*` block (around 444): `CHAT_SEAM_SELECTORS`,
  `CHAT_SEAM_ALLOWLIST` (`test_flow_new_chat.py`), and the guard, self-test and
  stale/missing checks.

## Acceptance Criteria

**A. The header and the new-chat state.**

- [ ] **AC1. The header** (§5.2), testid `chat-header`, inside `.chat-chrome`:
  - 48px tall, with a bottom border and the `padding: 0 16px 0 24px` from §5.2;
  - an **`h1`** (13px, weight 600) holding:
    - in `joined`: the session title **read from the `sessions` store by id**, falling
      back to the `session_joined` payload, so it follows auto-titling;
    - in `pending` or `starting`: "New chat";
  - "with {agent}" (12px, `--fg-muted`, testid `chat-agent-line`). "Default agent" stands
    for a null agent.

  `h2.session-agent-badge` is removed. Leg 6 adds the drawer toggle here.
- [ ] **AC2. The new-chat state** (§5.4), testid `chat-new-state`, shown **only** in
  `pending`, centred, with a max width of 480px:
  - a `badge badge--{providerType}` whose **text is the model** (A20). The type comes
    through 4a's providers resolution, with an unknown-type fallback;
  - an `<h2>` holding the agent name;
  - the description, in `--fg-secondary`;
  - **Pick a different agent** (`btn-ghost btn-sm`, testid `chat-pick-different-btn`),
    which calls `openPicker({opener: <it>})`.

  In `starting` and `joined` the message log shows instead.

**B. The empty and guidance states (DD3).** These live in the `chat-welcome` container,
shown only in `idle` with no chat to auto-join, and never during `joining`, so no empty
state flashes.

- [ ] **AC3. The common parts.** The mascot (`chat-welcome-mascot`, prepended by the
  caller), the **`h1.chat-welcome-greeting`** "Hello.", and `.chat-welcome-prompt`.
- [ ] **AC4. Setup complete, no sessions.**
  - The prompt reads "Start a conversation with one of your agents."
  - A **New chat** button (`btn-filled-primary`, testid `chat-empty-new-btn`) opens the
    picker.
- [ ] **AC5. Setup incomplete.**
  - The prompt and the guidance links are rebuilt with DOM APIs:
    `.chat-welcome-guidance`, `.chat-welcome-link`, and the same copy and hrefs as
    `welcome.js` today.
  - There is no New chat button here, and 4a's list button is disabled.
- [ ] **AC6. Gone:** the welcome **agent list** (`.chat-welcome-list` and
  `.chat-welcome-item`, `renderWelcomeList`'s ready mode, the welcome keydown handler).

**C. The composer extraction and the sinks.**

- [ ] **AC7. `areas/chat/composer.js`** (new) is a pure DOM builder. It returns
  `{el, input, fileInput, attachBtn, stopBtn, sendBtn, attachmentsEl, attachmentsStatusEl}`.
  - It carries today's markup over **behaviourally unchanged**: the same testids and
    classes, the `hidden` and `aria-keyshortcuts` attributes, the attachments container's
    `display:none` with its footgun comment, and the Stop button's icon built with
    `App.ui.util.icon`.
  - `chat.js` uses the returned references instead of `content.querySelector` lookups
    (around 348–357).
  - **Leg 5** restyles it.
- [ ] **AC8. No chat sink.**
  - The pane is built with DOM APIs, so the content sink is gone.
  - `tests/test_ui_guards.py`'s `DYNAMIC_SINK_BASELINE` has **no entries** for any
    `areas/chat*` path.
  - The non-baselined `loadEl.innerHTML` literal (around 1430), `thinking-indicator.js`
    (around 15) and the `innerHTML = ''` clears are left alone, or converted if trivial;
    the flight log says which.

**D. Retirement and the guard swap.**

- [ ] **AC9. Removed:**
  - the header `new-chat-btn` and `updateAgentBadge`;
  - `h2.session-agent-badge`;
  - the welcome list.

  `chat.css` loses `.chat-welcome-item*`, `.chat-welcome-list`, `.session-agent-badge` and
  `.new-chat-header`. `components.css` loses `.new-chat-header`, if nothing else uses it;
  grep first.
- [ ] **AC10. Selectors.**
  - The registry's "Retired testids" table gains `new-chat-btn`.
  - `RETIRED_SELECTORS` gains `new-chat-btn` and the class fragments `chat-welcome-item`
    and `session-agent-badge`.
  - **The whole `CHAT_SEAM_*` block** in `tests/test_nav_helper.py` is **removed**: the
    selectors, the allow-list, the guard, its self-test and the stale/missing checks.
    `RETIRED_SELECTORS` now covers them, and `_chats.py` is subject to it, so its bodies
    name none of them.
  - The kept `chat-welcome*` classes and the `chat-welcome` testid are not retired, and a
    comment says so.
- [ ] **AC11. Tests.**
  - **`_chats.py`:**
    - `expect_chat` reads `chat-header` and `chat-agent-line`;
    - `welcome` stays;
    - `new_chat_button` returns the list's `chats-new-btn`;
    - `welcome_item` and `agent_badge` are removed, and `pending_row` and the related
      helpers are checked against 4a.
  - **`test_flow_new_chat.py`:**
    - `test_welcome_with_agent_shows_listbox`,
      `test_picking_agent_from_welcome_starts_session` and
      `test_header_new_chat_button_starts_session_with_current_agent` are **replaced** by
      pane tests: the empty-state New chat opens the picker, and "Pick a different agent"
      re-picks;
    - `test_welcome_no_setup_shows_both_links` and
      `test_welcome_provider_only_shows_studio_link` stay. Their greeting and prompt
      assertions (around 55–90) are checked against AC3–AC5;
    - `test_delete_last_session_returns_to_welcome` stays, now through the row action;
    - **the flight log maps** old to new.
  - **`test_flow_chat_start_flow.py`:** around 394 (the header new-chat) moves to "Pick a
    different agent" or the list button. Around 429 and 436 (welcome visible) are checked
    against the idle rules.
  - **`test_flow_context_overlay_thresholds.py`** is unchanged (`.chat-chrome` is kept).
  - **A new `test_flow_chat_pane.py`** (chats lane) covers:
    - the header in each state, including the title following an auto-title through the
      store;
    - the new-chat state (badge text = model, type class, description, Pick a different
      agent);
    - the empty state with New chat;
    - the guidance state;
    - exactly one `h1` in every state;
    - no empty-state flash during `joining`.
- [ ] **AC12. Accessibility.**
  - There is one `h1` per state, and the landmarks and skip link are intact.
  - The resolver probe on `#chats` finds no new unnamed control in the pending, joined,
    empty or guidance states. Squawk 0110 (`chat-image-input`) stays allow-listed until
    leg 5.
- [ ] **AC13. Gates.**
  - `make lint` and format;
  - every static guard;
  - `make test-unit`;
  - the lanes `chats`, `shared` (`TEST_TIMEOUT=3600`), `contracts`
    (`THE_ONE_REQUIRE_WEBKIT=1`, only if a `ui/` file changed), `agents`, `settings` and
    `library`, through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`.
  - The numbers go in the flight log.
- [ ] **AC14. Docs.**
  - `CLAUDE.md`: the Chats paragraph gains the pane, the testids `chat-header`,
    `chat-agent-line`, `chat-new-state`, `chat-pick-different-btn` and
    `chat-empty-new-btn`, and `composer.js`.
  - `the_one/agents.md`.
  - The inventory and the registry.
  - The behavior specs that name "Select Agent", the welcome agent list or "Chat History"
    are **leg 8's** re-authoring. List them in the flight log for leg 8.

## Verification Steps

- AC13.
- **A manual pass** at 1440 and 1024, in Light and Dark, on a dev instance (port 8486 or
  higher, scratch data dir), covering pending, joined, empty and no-provider states. Stop
  it afterwards.
- **Falsify once:** render the new-chat badge with the provider type instead of the
  model, and watch the A20 test fail. Restore, and record it.

## Files Affected

- New: `static/js/areas/chat/chat-pane.js`, `areas/chat/composer.js` and
  `tests/browser/test_flow_chat_pane.py`.
- Changed: `static/js/areas/chat.js`, `areas/chat/welcome.js` (guidance only, or folded
  into `chat-pane.js`), `index.html`, `css/chat.css` and `css/components.css`.
- Tests: `_chats.py`, `test_flow_new_chat.py`, `test_flow_chat_start_flow.py`,
  `tests/test_nav_helper.py`, `tests/test_ui_guards.py` and
  `tests/test_index_asset_cache_busting.py`.
- Docs: `CLAUDE.md`, `the_one/agents.md`, the inventory and the registry.
