# Flight Log: Chats, and closing every count to zero

**Flight**: [Chats, and closing every count to zero](flight.md)

## Summary
Planned 2026-10-26 from `main` at `2e82aaa` (Flight 5 merged as #328). The branch `flight/06-chats-and-closing-the-counts` is cut from `main` at flight start.

---

## Planning Notes

- **Operator direction, 2026-10-26:**
  - the provider model picker and the library squawks (0269, 0270, 0185) are in the flight; the OAuth fixture (Flight 5 debrief, Recommendation 2) is a separate sortie;
  - a HAT leg closes the flight, and Flight 7 stays optional;
  - the closing leg runs the mission-close UI behavior specs;
  - squawk 0271 (the MCP editor test-file split) rides in groundwork;
  - the chat controls live in `js/ui/` as `App.ui.*` factories.
- **The review page** (https://claude.ai/artifact/2TBSM1R3Aa3pGaU8uLPkUM), with the operator's decisions returned the same day:
  - **Defects:** 0.1, 0.2, 0.3 and 0.4 are all fixed in this flight. 0.2 and 0.4 were changed from the recommendation, which was a squawk and a known issue.
  - **Obvious items:** all of A1-A18 approved.
  - **Taste items:** B1 (a), B2 (a), B3 (b), B4 (b), B5 (a), B6 (a), B7 (b), B8 (a), B9 (a), B10 (b), B11 (b), B12 (b, changed from the recommendation: the "no tools" chip stays), B13 (a), B14 (b).
  - **Design questions:** D1 (a), D2 (a), D3 (a), D4 (a), D5 (b), D6 (a), D7 (a), D8 (a).
  - **Operator note:** "We only have a copy button for code blocks; we should have a copy button for the entire reply as well. Also, when the number of iterations runs out, it just dies silently." These became F1 and F2 (DD8). The FD confirmed F2 by reading `the_one/agent/core.py:286`: the loop exits with nothing yielded.
- **Follow-up answers, 2026-10-26:**
  - F1 copies the markdown source, from finished agent replies only;
  - F2's notice reaches the web chat and connectors and is not stored in history.

## Planning Surveys

Two read-only crew ran at `2e82aaa`. Their reports are in the FD scratchpad.
- **Code survey:** `f6-code-survey.md`. It covers:
  - the `chat.js` structure map and the split (DD3);
  - every sink and allowance use with its replacement;
  - the library gaps and the handle shapes, and the flash contract and its callers;
  - the `markdown.js` security surface;
  - the side-effect inventory;
  - 14 defects found by reading;
  - the squawk recheck, the tests and lanes, the style cleanup, the alias recount;
  - 15 open questions, which became D1-D8 and the FD decisions.

  The five unit guard files passed at HEAD (66 tests). No browser test was run.
- **Presentation debt:** `f6-presentation-debt.md`, with 242 screenshots in `$HOME/the-one-f6-debt/shots/`.
  - **Instance:** a scratch instance on port 8496 inside `unshare -rn`, data dir `$HOME/the-one-f6-debt/data`, cwd `$HOME/the-one-f6-debt/cwd`.
  - **Safety:** each PID was stopped by PID (2696393, 2699438, 2709772, 2717918, 2718943, 2720127). Port 8484 and the default data dir (`/home/cprch/.local/share/the-one`) were never touched.
  - **Stubs:** the MCP sign-in states were driven by injected WebSocket frames and a stubbed `/api/oauth/start`, and the Pull stream by an in-page `fetch` override.

## Reconnaissance Report

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Squawk 0215: a stale sign-in link after a failed `/api/oauth/start` | confirmed-live | `chat.js:1306-1309` `abandon()` deletes the flow and closes the popup, but does not reset the group (`resetLoginGroups` at `:1332-1344` already does it for `auth_failed`) | leg 05b (DD11 9) |
| Squawk 0249: the OAuth popup test flake | confirmed-live; root cause found by reading | `test_oauth_modal_flow.py:188-230` never stubs `POST /api/oauth/start`. The 404 for `src-3` (`api.py:5001-5004`) runs `abandon()`, which closes the popup before the second frame can navigate it. The sibling `:244-268` passes falsely for the same reason | leg 01 (stubs plus a falsification check; one confirming run) |
| Squawk 0259: the `chats` lane at budget | partially-satisfied (in progress) | F5 L01 391 s, F5 L12 388 s against 450 s; the quiet-host rule is in CLAUDE.md | leg 01: re-measure, split `chats`, close |
| Squawk 0269: the kv remove button's name after a rename | confirmed-live | `ui/key-value-table.js:181-192` `onInput` never refreshes `row.remove`'s name; only `renumber()` does (`:437-443`) | leg 03c |
| Squawk 0270: the rename hint lingers after an empty save | confirmed-live | `setRow` hits `continue` (`key-value-table.js:529`) when nothing differs, so `setHint(null)` never runs | leg 03c |
| Squawk 0185: Jump to's active row moves under the user | confirmed-live (by design, DD10 of M25) | `jump-to.js:302-312`; `ui/search-list.js:223-283` resets `activeIndex` | leg 03b (D4 (a): keep the row by id) |
| Squawk 0271: split the MCP editor test file | confirmed-live | `tests/browser/test_flow_studio_mcp_editor.py` is still one file; `mcp_pat` holds it alone | leg 01 (operator) |
| Squawk 0272: the stale lane-time sentence; four `agents.md` patterns | confirmed-live | CLAUDE.md still says "about 24 minutes … (1470 s, 13 lanes)"; the `ui-kv-center` strut, the overlay typography reset and flash-to-page are missing from `agents.md` | leg 09a |
| F5 debrief Rec 1: `App.ui.flash`'s container contract | confirmed-live | `ui/feedback.js:128-145`; the MCP and connector "created" flashes are lost to their own remount (`mcp-server-editor.js:299`, `connector-editor.js:679`) | leg 03a (DD5) |
| F5 debrief Rec 3: the unit tier after every post-gate change | process | the F5 HAT fix pass failed the gate at the unit tier | DD13 standing rule |
| F5 debrief Rec 4: Flight 6 as one split-first flight | adopted | this plan | DD1, DD3 |
| Mission Known Issue: the alias shims | confirmed-live | code calls: `App.confirmDelete(` 1, `App.showFlash(` 3, `App.icon(` 2 (incl. `icons.js`), `App.iconNode(` 1, `App.consentLink.` 4; plus the dead `App.escapeHtml` / `App.escapeAttr` | legs 03a, 05b, 07, 09a |

## Presentation-Debt Survey (summary)

- **§0 functional defects** (all in the flight):
  - 0.1 focus is lost after an agent pick;
  - 0.2 an OpenAI-compatible provider's errors name Ollama;
  - 0.3 a deleted agent's chat keeps Attach enabled (plus a context-window 404);
  - 0.4 strikethrough, task lists and bare URLs are not rendered.
- **§A obvious items (18), all approved:**
  - markdown headings unstyled (A1);
  - the code Copy as a page toast (A2);
  - "Log in" against "Sign in" (A3);
  - the agent error as a neutral notice (A4);
  - the hand-built health banner (A5);
  - glyph remove and cancel buttons (A6, A7);
  - lowercase "thinking" (A8);
  - the search-list meta squeezing the label (A9);
  - model-id typefaces (A10);
  - the accent VRAM value (A11);
  - "Pull Model" (A12);
  - Ollama's raw pull status (A13);
  - flash wording (A14);
  - timestamp contrast 3.1 / 3.5:1 (A15);
  - "discord" lowercase (A16);
  - the stray "Agents" (A17);
  - the 4 px telemetry focus offset (A18).
- **§B taste items (14).** Decided as above.
- **§C keep list.** The migration must preserve:
  - the Chats list's captions, times, selection, hover trash, armed and lapse states, and its empty state;
  - the picker's search field, rows and hints (Jump to matches);
  - the 48 px header with both lines truncating;
  - the drawer's push at 1280 and overlay at 1024;
  - the composer's focus ring, growth to about 8 lines, mono model id, and Stop and Send states;
  - the bubbles' 46 rem cap, wrapping and sideways-scrolling code;
  - the library consent block;
  - 2 px focus rings;
  - no horizontal overflow at 1024 or 1280;
  - the Ollama panel's sections, LEDs, actions, Pull confirm and progress.
- **Noticed outside:** the agent and provider editors' title-case labels became D7 (a), in the flight.

## Visible-Differences Ledger

Rows 1-38 at planning (legs updated after Architect cycle 1). Every leg appends its differences; the HAT walks the list.

| # | Leg | Surface | Change | Source |
|---|---|---|---|---|
| 1 | 07 | Chat reply | Markdown headings on the type tokens, never larger than the page heading | A1 |
| 2 | 07 | Chat reply | The code-block Copy is the library icon button; it confirms in place (check icon, "Copied") with no page toast | A2, D1 |
| 3 | 05b | Chat sign-in | "Sign-in needed" and "Sign in to {server}" on a library primary button | A3 |
| 4 | 05c | Chat | An agent error is a danger-tone headline ("The agent couldn't finish this reply.") with the raw text under "Technical details" (confirmed in the captures) | A4 |
| 5 | 05a | Chat | The deleted-agent warning is the library warning banner (confirmed in the captures: a left-ruled warning band above the composer, left-aligned, replacing the centred top-ruled bar) | A5 |
| 6 | 05a | Composer | A staged image's remove is the library icon-only remove button (confirmed: a grey 24px x, replacing the small red glyph; the thumbnail's alt is empty and the chip is named "Staged image N") | A6 |
| 7 | 05a | Composer | The queued message's cancel is a library icon button; the label is "Queued" (confirmed: a chip in the chip fill, not a dashed card; the text is no longer italic and stays one line with an ellipsis) | A7 |
| 8 | 05c | Chat | "Thinking…" and "Loading model…" in sentence case on one control | A8 |
| 9 | 03b | Agent picker, Jump to | Long secondary text truncates before the row's name | A9 |
| 10 | 08 | Provider models | Model ids in mono in the generic list | A10 |
| 11 | 08 | Ollama panel | The VRAM value in plain secondary text | A11 |
| 12 | 08 | Ollama panel | "Use Pull to download one." | A12 |
| 13 | 08 | Ollama panel | Pull progress keeps "Pulling {model}…" plus the percentage | A13 |
| 14 | 03a | Toasts | "Agent saved"; no "Error:" prefix; no exclamation marks | A14 |
| 15 | 05c | Chat | Message timestamps at AA contrast (opacity dropped) | A15 |
| 16 | 05b | Chats list | The connector badge shows the platform's display name ("Discord") | A16 |
| 17 | 08 | Provider models | "Agents" is linked inside the intro sentence | A17 |
| 18 | 05c | Composer | The telemetry readout's focus offset is 2 px | A18 |
| 19 | 07 | Chat reply | Wide tables scroll sideways in their own wrapper | B1 |
| 20 | 05c | Chat | The thinking disclosure sits above the reply it belongs to | B2 |
| 21 | 05c | Chat | The trace summary keeps the mono voice, with the library chevron and "Tool activity · 4" | B3 |
| 22 | 05c | Chat | "Operator only" is a small chip | B5 |
| 23 | 05a | Chats empty state | The text column is centred under the mascot (confirmed: greeting, prompt and New chat centred) | B6 |
| 24 | 05c | Chat | After Stop: a muted "Stopped." line, plus "Queued message discarded." when one was held | B9 |
| 25 | 05a | Composer | Blocked: the box is dimmed with the disabled tokens, and Attach is disabled (confirmed: a dashed box on the page background) | B13, 0.3 |
| 26 | 03c | Agent and provider editors | Sentence-case labels ("LLM configuration", "System prompt", "Max iterations", "Context window", "Reasoning effort", "OpenAI-compatible", …) | D7 |
| 27 | 05a | Chat | After an agent pick, focus is in the message box (confirmed by test; the picker test that expected the opener now expects the message box, and a leave-guard Stay still keeps the opener) | 0.1 |
| 28 | 06 | Chat | An OpenAI-compatible provider's connection error names that provider type, not Ollama | 0.2 |
| 29 | 07 | Chat reply | `~~struck~~`, task lists (disabled checkboxes) and bare URLs (as links) render | 0.4 |
| 30 | 05c | Chat reply | A finished agent reply has an icon-only "Copy reply" in its attribution row; it copies the markdown source | F1 |
| 31 | 06 | Chat, connectors, CLI | At the step limit: "Stopped: this agent used its {n} steps for this message. Send another message to continue, or raise Max iterations in its settings." (web, with a settings link when the agent has a record); "(Stopped: reached its step limit for this message.)" in connector chats, always; not stored | F2 |
| 32 | 03b | Jump to, agent picker | The highlighted row stays the same row when data lands | D4, squawk 0185 |
| 33 | 07 | Chat reply | A link that leaves the app's origin through `\` or control characters renders as `#`; a root-relative or `#` link still works within the app | D3 |
| 34 | 05b | Chats list | Deleting while offline reverts the arm and says why | DD11 6 |
| 35 | 05b | Chat sign-in | A failed sign-in start removes the sign-in block and shows the button again | squawk 0215 |
| 36 | 03c | MCP editor (Headers / Env) | The row's remove button is named after the key as typed, and the rename hint clears after a re-baselining Save | squawks 0269, 0270 |
| 37 | 03a | Toasts | A toast survives its editor's remount and a closing modal (the MCP and connector "created" toasts now show) | DD5 |
| 38 | 03a | Toasts | A new toast replaces the one showing; two never overlap | DD5 (operator, 2026-10-26) |
| 39 | 04 / 05c | Chat trace | A tool message inside a trace caps at the trace's width (`max-width: 100%`), so a 200-character unbroken word wraps instead of overflowing | the leg 04 parity check (a degenerate-input fix) |
| 40 | 05a | Every chip with a remove button (chat staged image and queued message, Library and MCP editors) | The remove button is a 24x24 target with no negative margin (was 22x22 with a negative margin); a chip with one is a few pixels taller | WCAG 2.2 target size (the B2 accessibility review) |
| 41 | 05a | Chat composer | Send follows `blocked` or `busy`: clearing the health banner while a turn runs keeps Send disabled (the banner's clear path used to enable it); a latent defect, not reachable through a real flow today, so no visible change | DD7, leg 04 contract |
| 42 | 05a | Composer | A short queued message's chip now fits its text instead of filling the region's width (the library chip is inline); a long one keeps one line with an ellipsis | leg 05a (A7 consequence; for the HAT to judge) |
| 43 | 05c | Chat | A "Loading model…" line that never settled is removed when the turn ends in an agent error, `done` or Stop (it used to keep spinning); a deleted agent's chat makes no context-window request (no console 404) | DD11 4, 0.3 |
| 44 | 07 | Chat reply | The code-block Copy code button is the library icon button at size `sm` (24 x 24, the secondary outlined look, 14px icon); it was a hand-built 28 x 24 button on the surface fill. Same top-right placement and the 0.6 resting opacity with the hover/focus reveal | A2 |
| 45 | 07 | Chat reply | A task item's disabled checkbox replaces its bullet (`li.markdown-task`, `list-style: none`, checkbox in the bullet's place); a table with unbreakable cell text now overflows into its own focusable "Table" region instead of the bubble (B1; the table's own width is unchanged: auto) | 0.4, B1 |
| 46 | 08 | Provider models | A model id in either list carries its full id as a tooltip (`title`); the generic list keeps its compact rows (4px padding, default cursor) and only the font changes (row 10) | DD10 |

## Leg Progress

### Leg 01: groundwork-and-before-set (landed, not committed)

**The before set.**
- **Path:** `$HOME/.cache/the-one-ui-capture/m31-f6-before` (outside the repo, never committed). **172 PNGs = 43 surfaces x 2 themes x 2 widths, 0 failed, 0 skipped.** 38 new `needs_chat` surfaces plus five existing ones (`ollama-models-panel`, `agent-general`, `provider-edit-mock`, `provider-edit-ollama`, `flash-after-save`).
- **Command:** `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f6-before --surfaces "<the 38 needs_chat names>,ollama-models-panel,agent-general,provider-edit-mock,provider-edit-ollama,flash-after-save"`. The manifest's `git_sha` is `3b3d42ac1c6c26eefd344900d981ccb44aaeb970`.
- **Order held:** `git diff main -- the_one/` and `git status --porcelain the_one/` were both empty at capture (the manifest records `git_status_the_one: []`). The uncommitted `scripts/ui_capture.py` has sha256 `2b77c27ad9d2713ea6fa0ee3488b15d98b4d626451fc2a0a2352d744d9e711d6` (unchanged to the end of the leg). A first full capture had one failure (`chats-list-row-hover` detached its row when the list repainted); the hover step now waits and retries, and the whole set was retaken, so the set is from one tool version.
- **Determinism:** a second full run of the same 43 surfaces into a scratch directory compared with PIL `ImageChops.difference(...).getbbox()`: 172 compared, **0 differ** (no mask needed beyond the existing rules). No instance, fixture or browser process of either run was left alive.
- **Groups:** the manifest's `chat_seed` holds every session id with its expected group, and `chats-list-groups` (the last surface, taken after every live surface) read each row's group heading off the page and failed the capture on any mismatch. It passed: Today (rich, long names), Yesterday (peer), Last 7 days (week, untitled, ghost), Last 30 days (month), Older (old).
- **Tool changes:** `Surface.setup` (a pre-`goto` hook, called after the clock and routes), `Surface.needs_chat`, `Ctx.state`; `seed_chat()`; one `SocketScript` (WebSocket route, `connect_to_server`, a join rewrite to `is_processing`, blanked session lists, `message`/`cancel` frames swallowed, injected frames to every socket); the instance gets `THE_ONE_PURGE_CHECK_INTERVAL_SECONDS=2592000` only when a chat surface is selected, and `seed_chat` asserts every session is still listed. `chat-consent-link` is now produced, not skipped. Safety refusals untouched (`tests/test_ui_capture_safety.py` passes). The agent-name limit of 64 characters (sortie 06) shaped the long agent name (exactly 64).

**Run 1 (before the lane splits, the flight's baseline)**: start load 0.62 (`uptime` 09:14:11, no other test process), `PARALLEL_RESULT rc=0 total=1653s lanes=13 failed=-`. Per lane: mcp 516, routing 535, agents 461, contracts-controls 385, chats 421, library 361, knowledge 317, providers 344, shared 338, agent-tabs 306, settings 283, settings-tools 257, contracts-overlay 184. No lane over budget; `chats` was at 94% of 450 s. No flake in the run, so squawk 0249's test was not seen to fail.

**Sinks and bookkeeping.** `chat.js:215`, `:685`, `:743`, `:924` became `replaceChildren()`; `:1647` was deleted (the next line's `textContent` write clears the row). `HTML_SINK_ALLOWANCE = {}`, `SINK_TOTAL = 0`, `SINK_START_FILES` and `SNIPPET_START_FILES` empty; `test_chat_area_has_no_baselined_sink` now fails on a sink of any kind in `areas/chat*`. `START_ROWS` is the 25 current `OWNERSHIP_ALLOWANCE` keys ("as of M31 F6 L01"; it had listed 40-odd Flight 5 rows). Static guards and ownership: 396 passed.

**Squawk 0249.**
- The three unstubbed tests now call `_stub_oauth_start(page)`; `chat.js` reads nothing from that response.
- **Demonstration** (a temporary test, deleted): the unstubbed click held until the real POST answered gave `DEMO oauth/start status: 404`, then `DEMO popup closed by abandon() before the second frame`, then `DEMO popup href after second frame: about:blank` and `AssertionError: assert 'about:blank' == 'https://idp.example.com/authorize?state=ST'`.
- **Falsification:** with the global popup close removed from the `auth_resolved`/`auth_failed` handler in `chat.js` (a temporary edit), `test_popup_closes_on_auth_resolved_event` failed (`Timeout 10000ms exceeded`); reverted byte-for-byte (`cmp` against the saved copy clean, `git diff` shows only the sink edits).
- `test_oauth_modal_flow.py`: 18 passed. `shared` passed in run 2.

**Squawk 0271: the MCP file mapping** (the AST splitter: sections by banner, the `test_reset_*` tests that fell under the Server banner moved to status, helpers by usage). 149 test functions, 178 items, node ids identical with the path stripped, every test and helper AST-identical to the original (only the unused `_CLOCK` dropped). `tests/browser/_mcp_editor.py` holds 34 shared names (295 lines).

| New file | Tests | Lines | Lane |
|---|---|---|---|
| `_create.py` (create, edit, delete, create-form Save, resp.ok) | 14 | 545 | `mcp` |
| `_fields.py` (sandbox, runtime dropdown, connection fields) | 29 | 894 | `mcp` |
| `_kv_chips.py` (chip lists, env and headers, kv polish) | 30 | 737 | `mcp` |
| `_signin_lifecycle.py` (sortie 04 sign-in, lifecycle and poll) | 15 | 549 | `mcp-connection` |
| `_status.py` (tools cache, Reset, Test body, connection status) | 26 | 947 | `mcp-connection` |
| `_server_info.py` (Server section, tools list) | 11 | 433 | `mcp-connection` |
| `_controller.py` (B4 review fixes, Leg 10 controller) | 24 | 676 | `mcp-connection` |

(All named `test_flow_studio_mcp_editor_<suffix>.py`.) Live comments naming the old file were updated (`conftest.py` x2, `test_flow_agent_tabs.py`, `test_flow_studio_knowledge_inventory.py`, CLAUDE.md); a grep of `tests/ scripts/ docs/ ci/ CLAUDE.md the_one/agents.md` finds the old name only in the docstrings that say "split from" and history records.

**Lanes.** `chats-transcript` (the 11 listed files) and `chats` (the rest, `chats_files()`): the old `chats` list equals their union (diffed against the pre-change script). `mcp` and `mcp-connection` as above; `agents_files()` subtracts the new list (`--lane agents --list` has no `test_flow_studio_mcp_editor*` file). New by-file pair tests and the updated lane string in `tests/test_run_tests_lanes.py` (17 passed).

**Run 2 (after the splits)**: start load 0.74 (09:46:52, no other test process), `PARALLEL_RESULT rc=0 total=1600s lanes=15 failed=-`. Per lane (budget): routing 533 (600), agents 466 (540), contracts-controls 360 (480), library 333 (420), knowledge 304 (420), providers 327 (420), shared 345 (420), agent-tabs 306 (360), mcp-connection 289 (390 new), settings 279 (360), mcp 254 (330 new), settings-tools 251 (330), chats 283 (360 new), chats-transcript 122 (180 new), contracts-overlay 184 (270). **New budgets** (measured plus 25%, rounded up to 30 s): `chats` 360, `chats-transcript` 180, `mcp` 330 (unchanged value), `mcp-connection` 390; every other lane moved under 15% and kept its budget. No lane over budget against the final table. The split is uneven (283 s against 122 s) because the leg fixed the transcript list in advance; both are within budget with room, so it was not re-balanced. CLAUDE.md's table and `scripts/run-tests.sh`'s were compared by a script (15 rows equal). Counts updated: fifteen lanes, fourteen named.

**Unit tier** (after both browser runs, never concurrent): `make test-unit` 7787 passed, 12 skipped, 3249 deselected (the expected 12 for this host without `fr_FR`/`de_DE`). Static guards (`test_ui_guards`, `test_ui_ownership`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_capture_safety`, `test_run_tests_lanes`): 413 passed. `ruff check` and `ruff format --check` on `scripts/` and `tests/`: clean.

**Squawk 0259:** corrective action and verification written; status stays `in-progress` until the flight's commit (sign-off by the flight-end Reviewer). Squawks 0249 and 0271 carry their corrective actions and verification and are `in-progress`, not closed (Flight Director closes at the commit).

**Not done / notes.** The FD spot-check of the Chats list, rich chat, Ollama panel and a live state is the FD's. `chat-consent-link` uses a pinned fake consent URL (`FIXED_CONSENT_URL`). The leg's flight-end commit was not made.

**Flight Director Notes:** Leg 01 landed (`[LAND:leg]`). The FD spot-checked four images of the before set, all as the survey described them:
- `chats-list-groups` (light, 1280): five groups, the pinned times, the Discord row;
- `chat-joined-rich-top` (dark, 1280): today's unstyled headings (A1) and the squeezed table (B1);
- `ollama-models-panel` (light, 1024): the accent VRAM line (A11) and the "no tools" chips (B12, kept);
- `chat-live-streaming` (light, 1280): mid-stream with Stop visible and the list unchanged.

The determinism check (0 of 172 differ) and the group check passed. Batch B1 continues with leg 02; the review and checkpoint commit follow it.

### Leg 02: chat-split (landed, not committed)

**Step 1's map (one owner per name; as the leg's table, with these notes).** Shared mutable state moved into one `state` object in `chat.js` (the 20 names of the table, plus nothing else). Owners: `ws`, `boundOn`, `reconnectTimer`, `connect`, `socketOpen`, `sendBinding` in `socket.js` (`ctx.ws()`); `pendingJoinId` and the transition functions in `session-flow.js` (handle `pendingJoinId()`/`setPendingJoinId()` for the `_pendingJoinId` seam); `stagedImages` in `attachments.js` (handle `staged()`, `clearStagedImages`, `prependStaged`, `renderAttachments`); `pendingQueuedEl`/`pendingQueuedRegionEl` in `hold-queue.js`; `thinkingEl`, `traceShells` (handle `traceShellFor`, `resetTraceShells`), the streaming variables and the pacing timer in `transcript.js`; `oauthPopups`, `sourceNames`, `loginFlows` in `sign-in.js`; `NOTE_TOOLS` in `turn-frames.js`. `chat.js` keeps `chatState` and the DOM refs, passed through `ctx`.

**Module map (final line counts).**

| File | Lines |
|---|---|
| `areas/chat.js` | 525 (was 2398) |
| `chat/transcript.js` | 385 |
| `chat/socket.js` | 359 |
| `chat/session-flow.js` | 384 |
| `chat/sign-in.js` | 334 |
| `chat/attachments.js` | 236 |
| `chat/turn-frames.js` | 237 |
| `chat/send.js` | 161 |
| `chat/hold-queue.js` | 91 |

**Boundary shifts from the owner table (all recorded here, none behavioural).**
- The model-loading row stays inside `handleSystem` in `turn-frames.js` (it keeps its own timer on the element and no module state, so moving it into `transcript.js` would have meant re-indenting and splitting `handleSystem`).
- The live `assistant_chunk` branch body became `transcript.onAssistantChunk(data)` (it writes `currentStreamingMsg`/`pendingChars`, which never leave `transcript.js`); `clearStreamingVisibility()` replaces the six `currentStreamingVisibility = null;` statements in the gated chain.
- The three `auth_*` branch bodies became `signIn.onAuthRequired/onAuthResolved/onAuthFailed` and the pre-gate close `signIn.settleClose(data)`; the `if (auth_resolved || auth_failed)` stays in `socket.js`.
- `chat.js` is 525 lines, well under the 650-750 projection, so no extra group needed moving. The attach listeners went with `attachments.js` (they are in `create`), and `startSend`/`applyStartFailed` use `attachments.staged()`/`prependStaged(images)` for the two statements that touched `stagedImages` directly (`stagedImages = p.images.concat(stagedImages); renderAttachments();` is the one text change beyond prefixes, kept as one handle call).
- `toSessionSummary` stays in `chat.js`; `socket.js` aliases it (`var toSessionSummary = ctx.toSessionSummary;`) so `state.sessions.map(toSessionSummary)` reads as before.

**Frame order** (`chat/socket.js`, read): `boundOn = sock` on `session_joined`; `sessions_changed`, `session_updated`, `session_list`, `session_joined`, `start_failed`, `join_failed`, `session_deleted` (each returns); the `auth_resolved`/`auth_failed` popup close (`signIn.settleClose`); the gate `if (!chatState.onFrame(data).accept) return;`; `ctx.turnFrames.handle(data)`. One `sock.onmessage` entry; the `session_joined` handler is one block. `registerPickerHost` is the last call before `self._agentDrawer`.

**Checks.**
- Bare-name audit (a script over every `var`/`function` at the old closure's indent in the original file, checked against each new file's own declarations and aliases): after one finding fixed (`NOTE_TOOLS`, now declared in `turn-frames.js`), no bare use of any moved name (state or function) in `chat.js` or any new module. A second script checked every `ctx.<module>.<name>` use against that module's returned handle: no missing member.
- ES5 grep (`=>`, `let`, `const`, backtick) over `chat.js` and the eight modules: one hit, the original string literal `'```'` in `findSafeRenderBoundary` (inside quotes, moved verbatim). Modules are `'use strict'` IIFEs like the other chat modules; `node --check` clean.

**MOVES entries** (`tests/_ui_ownership_allowance.py`, `retire_by` in the last column): `api:App.consentLink.` x4, `consent-link` x1, `btn-filled-primary` x1 (`chat.js` -> `chat/sign-in.js`, 05b); `chip` x1 (`chat.js` -> `chat/attachments.js`, 05a). The four old `chat.js` rows were deleted and four rows added under the new files; `confirm-delete` x2 and `api:App.confirmDelete(` x1 stay in `chat.js`. `TOTAL_USES` unchanged. `tests/test_area_module_size.py` lost its `chat.js` entry.

**Re-anchored tests** (path and spelling only; counts, windows and strengths kept):
- `tests/test_store_static.py`: a `_chat_src()` helper (chat.js plus every `areas/chat/*.js`) for the two "not in" checks; the `session_list`/`sessions_changed`/`session_joined` windows read `chat/socket.js`; `toSessionSummary` and `renderChatsList` stay on `chat.js`; the `renderPending`/`openConversation`/`resetToIdle`/`clearConversation` windows read `chat/session-flow.js`; the history needle is `ctx.transcript.renderHistory(`; `refreshSessionList` (definition and its `list_sessions`) is read from `session-flow.js`; `sendBinding({ action: 'leave' })` is read from `session-flow.js`.
- `tests/test_consent_link_static.py`: the script-order consumer is `areas/chat/sign-in.js`; the `isSafeUrl(` >= 2 and `consentSafe` >= 3 counts are read from `chat/sign-in.js`.
- No browser test was edited.

**Verification.**
- Static guards (`test_area_module_size`, `test_ui_ownership`, `test_ui_guards`, `test_store_static`, `test_consent_link_static`, `test_index_asset_cache_busting`, `test_token_definitions`, `test_design_tokens_a11y`): 399 passed.
- Scoped lanes while iterating: `chats` 150 passed, `chats-transcript` 41 passed, `test_oauth_modal_flow.py` 18 passed (unchanged).
- **The full gate** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`: unit **7784 passed, 15 skipped, 3249 deselected** (15 is the expected count under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=1561s lanes=15 failed=-` (start load about 1.2, no other test process). Lanes (budget): routing 538 (600), agents 473 (540), contracts-controls 360 (480), library 334 (420), knowledge 306 (420), providers 329 (420), shared 330 (420), mcp-connection 280 (390), chats 290 (360), agent-tabs 291 (360), settings 268 (360), mcp 248 (330), settings-tools 246 (330), contracts-overlay 209 (270), chats-transcript 122 (180). No lane over budget; no re-budgeting.
- `ruff check` and `ruff format --check` (the_one, tests, scripts, evals): clean.

**Docs.** `the_one/agents.md`: a "Chat module map" paragraph after the session-state-machine paragraph, and the passages naming moved internals (the drawer notes' live refresh, `toSessionSummary`/the live-refresh flags, the `renderChatsList`/welcome/composer/drawer notes, the invalidation table's `session_joined` row). CLAUDE.md: the `setInputValue` mention now names `chat/send.js`.

**Not done / notes.** Nothing deferred. No commit.


---

### Leg 03a: flash-and-feedback-options (landed, not committed)

**What changed.**
- **`App.ui.flash`** (`ui/feedback.js`): one lazily created `div.app-flash-region` (`App.ui.flash.region()`, re-appended if detached, no CSS), the topmost open modal's dialog when one is open (`App.ui.modal.top()`, new in `modal.js`), the newest toast replacing the one showing (its timers cleared through handles on the node), a passed `container` ignored. `modal.js` `finish` moves (not clones) the closing dialog's `.app-flash` children to `top()` or the region after the `stack.splice` and before the dialog is removed.
- **Callers:** `container` dropped at every site (providers, agent editor, MCP, connector, tools page and editor, provider-models, agent-data, mcp-connection-status) and in the `App.showFlash` delegate (signature kept, container ignored), so markdown's copy toast leaves `.messages`. A14: "Agent saved" (both sites), no "Error: " prefix on the provider delete error; no other flash string ended in "!" apart from markdown's "Copied!" (leg 07). Flight 5 page-flash comments simplified; `provider-editor.js` stays at 896 lines.
- **`App.ui.badge.live`**, **`App.ui.button.setIcon`**, the icon-only **copy confirmation** (check icon plus `title` "Copied" for 2 s, "Copy failed" keeps the copy icon), **`App.ui.noteFlag({sources})`** (callers moved; `App.noteFlag` and `App.iconNode` deleted from `icons.js`). `chat-pane.js` and `agent-drawer.js` use `badge.live`.
- **CSS:** the unlayered `.note-flag*` and `.consent-link*` tail moved to the end of `@layer components`, unchanged; `tests/test_css_layers.py` (new) fails on any top-level rule in `components.css` outside an `@layer`.
- **Docs and specs:** catalogue rows (Flash, Badge, Copy, Button, Modal, new Note flag), `the_one/agents.md` (the stale `rescueFlashes` sentence rewritten, the `App.noteFlag`/`App.iconNode` lines, a Feedback-controls addendum), `docs/ui-testid-registry.md`, and the two behavior specs ("Agent saved").

**Failing first (seen failing on the pre-change library before the fix; JS under `the_one/` stashed, tests kept).**
- `test_code_copy_toast_is_on_the_page_not_in_the_message_log` (chats-transcript), `test_connector_created_toast_survives_the_remount` (library), `test_mcp_created_toast_survives_the_remount` (mcp): 3 failed, the toasts absent or inside `.messages`.
- Flash contract tests in `test_ui_feedback_contract.py` (newest-replaces, container removed, region re-attach, toast in a modal, survives the modal's close, re-home to the next dialog, same viewport position): 12 failed (6 x 2 engines) on the old code, 14 passed on the new.
- `tests/test_css_layers.py::test_components_css_has_no_rule_outside_a_layer` failed against the old `components.css` (the tail was unlayered) and passes now; the scanner test also proves a stray rule appended after the last layer is reported.
- The badge-live, copy-confirmation, note-flag and computed-style tests exercise APIs that did not exist, so "failing first" is trivial (not separately run on the old tree).

**Retargeted, not deleted.** `test_flash_roles_visible_and_removal` now flashes one toast; the old two-toasts-visible assertion became `test_flash_newest_replaces_and_keeps_its_role`; `test_flash_container_default_and_detached_container` became `test_flash_survives_its_caller_container_and_ignores_the_option`. A14 is asserted by `test_flow_agent_editor_frame.py::test_same_identity_save_patches_without_remount` ("Agent saved") and the new `test_flow_provider_editor.py::test_delete_error_toast_has_no_error_prefix`. The four "no flash" tests (`test_flow_admin_tools_editor_save.py:177`, `test_flow_admin_tools_grid_library.py:132`, `test_flow_provider_library.py:92`, `test_flow_studio_loadall_error.py:63`) pass unchanged in their lanes.

**Allowance.** `OWNERSHIP_ALLOWANCE` lost 4 rows (`chat-pane.js` badge x2, `agent-drawer.js` badge x2, `js/icons.js` `App.icon(` x1, `js/icons.js` `App.iconNode(` x1): 25 rows / 36 uses -> 21 rows / 30 uses. `TOTAL_USES`: `badge` 5 -> 1, `api:App.icon(` 2 -> 1, `api:App.iconNode(` deleted. `START_ROWS` and `MOVES` unchanged.

**Verification.**
- Guards (ownership, library_source, control_inventory, emitted_classes, area_module_size, ui_guards, token_definitions, design_tokens_a11y, css_layers): 448 passed.
- Lanes (`THE_ONE_TEST_NETNS=1`, `THE_ONE_REQUIRE_WEBKIT=1`, three at a time): contracts-controls 984 passed 4 skipped; contracts-overlay 510 passed 1 skipped; providers 135; mcp 85; mcp-connection 94; library 104; knowledge 65; agents 166; settings 108; settings-tools 169; chats 150; chats-transcript 42; agent-tabs 126; shared 268. No failures.
- `make test-unit` (netns): 7786 passed, 15 skipped. `ruff check` and `ruff format --check`: clean.

**Ledger rows 14, 37, 38** confirmed as written (no amendment).

### Leg 03b: layout-options (landed, not committed)

**What changed.**
- **Library options:** `searchList({variant: 'chooser'})`; `drawer({reserveHeaderEnd})`; `modal({footerEnd})`; `textInput({minWidth})`. Base-rule moves: `.ui-list-pane { flex: 1 1 0 }`, `.badge { flex-shrink: 0 }`, `.tabpanel { padding: 16px 20px 80px }`, and the section default flip (`.editor-section { padding: 12px 20px }`, `--flush` with no `!important`). Deleted: the twelve `chat.css`/`studio.css` rules (plus `studio.css:45`, a no-op) and `agent-picker.js`'s footer class. Consumers: the agent picker, agent drawer and the Self-configuration grant input.
- **A9 (ledger row 9):** the meta ellipsizes before the label (meta `flex: 0 1000 auto`, 64px floor, right-aligned; text column `flex: 1 1 auto`, description `contain: inline-size`).
- **D4 (ledger row 32, squawk 0185):** `searchList.refresh()` keeps the active option by `(group index, id)`, moved or not, `nearest` scroll; an input event or changed query activates the first; `keepScroll` is unified (now only "restore offset, do not scroll"). `jump-to.js` lost `lastFirstId`.

**Deviations (for the FD).**
1. **The picker field's "40px" never existed.** The old `height: 40px` rule never applied (`.field-input` is `flex: 1` in a column `.field-group`, so the basis ignores `height`; measured 34px on the old CSS in the harness). The chooser variant keeps the real 34px with the body-lg font and drops the dead line, since the leg's rule is no visible change. The contract test asserts 34px. If the operator wants a real 40px field it is a separate visible change (a candidate squawk).
2. **A9 flex values differ from the design review's:** text `flex: 1 0 auto` made a 200-character label overflow the row (no ellipsis; seen in the first capture after the change), so the text column is `flex: 1 1 auto` and the meta gets shrink factor 1000 with the 64px floor and `text-align: right` (the floor otherwise left-aligned short metas, visible on `gpt-4o`). A test for a very long label was added.
3. `.api-key-wrap .field-input { flex: 1 }` (`components.css`) left in place: it is a redundant library rule, not an allowance row, and `api-key-wrap` still has a user.
4. Jump to keeps its own `gap: 0` (it restyles the field into a bar and overrides the list padding, so adopting the chooser variant would not be identical); recorded.

**Audits.**
- **Badge:** users are the list-pane row badges (wrapper `flex-shrink: 0`), the tool tile badge (`flex: none`), the drawer head, the new-chat state (a column), the notes tab's origin badge (inline-flex), and the dots. Every badge is `white-space: nowrap` with an auto minimum width, so none can shrink below its text; `kb-item-badge` is a chip, not a badge. Base rule chosen, no `noShrink` option.
- **List pane:** the three hosts (Chats aside, Agents and Library wrappers) are column flex containers that want `flex: 1`; the contract harness is block flow, where the declaration is inert (computed-style test in a flex host and a block host).
- **Section inset:** outside `.area-studio`, every `App.ui.section` (Settings pages, `tools-editor.js`) passes `inset: 'none'`; every studio section (agent tabs, Library editors, knowledge, MCP) keeps 20px. `--flush` now wins by order and its `!important` is deleted. Tabs: only the agent editor (default padding) and the tools grid (`panelPadding: 'none'`) use `App.ui.tabs`.

**Failing first (seen failing before the fix).** 42 new contract tests failed on the old code (D4 x3, chooser, `footerEnd`, `reserveHeaderEnd`, `minWidth`, section padding, list pane, tab panel, badge, plus the A9 tests); the A9 long-meta test was re-seen failing on the old CSS (label 138 of 222) after a harness bug in the first run was fixed. The cold-landing flow test failed once on a test bug (`unroute` before `continue_`), fixed.

**Pins rewritten (D4 deliberately; each reason).**
- `test_each_source_call_makes_the_first_option_active` became `test_a_query_change_makes_the_first_option_active` (the refresh half now asserts keep-by-identity, covered by the new tests).
- `test_without_keep_scroll_a_refresh_resets` became `test_a_refresh_keeps_the_active_item_whatever_keep_scroll_says` (one keep rule).
- `test_flow_jump_to.py`: the "first row is active once every collection has arrived (DD10)" assertion and `test_palette_resolver_active_row_and_keys` now warm the chats store first (the first row at open is the newest chat) and say why; new `test_cold_data_landing_never_moves_the_highlighted_row`; `_jump`'s load wait (the squawk 0168 workaround) removed.
- `test_ui_modal_contract.py` chooser fixtures use `footerEnd`.
- `tests/behavior/jump-to-palette.md` step 2 re-authored (highlighted row does not move) and step 3 annotated.
`test_keep_scroll_resets_on_a_changed_query_or_a_vanished_id` and `test_keep_scroll_restores_on_an_unchanged_query` pass unchanged.

**Squawk 0185.** Corrective action and verification written in the squawk; status left `in-progress` for the flight-end sign-off.

**Captures.** Leg-start set `m31-f6-03b-start` (25 surfaces x 4), after `m31-f6-03b-after` and `-after2` (PIL `ImageChops`). Differences: the picker open/search and Jump to rows with long meta (A9, row 9), and the MCP editor and Date and time zone list only before the fixes (a clock text and the 64px floor's left alignment; the zone list is identical after). Everything else identical: agent tabs (General, Rules and notes, Knowledge, MCPs, Tools, Self-configuration), Library start, KB detail, connector, MCP, provider editor, Settings pages, the rich chat (drawer at 1280 push and 1024), the Chats list. The `mcp-edit-stdio` difference was a timestamp. (`after2` ran fewer surfaces, so its picker bottom row differs by seed data.)

**Allowance.** 21 rows / 30 uses to 8 rows / 14 uses: 12 `css` rows (15 uses) and the `agent-picker.js` row removed; `TOTAL_USES` sums to 14. `MOVES` unchanged.

**Ledger rows 9 and 32** confirmed as written.

**Verification.** Guards (ownership, library_source, control_inventory, emitted_classes, ui_guards, token_definitions, design_tokens_a11y, area_module_size, css_layers): 448 passed. Full browser gate (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 --parallel 3`): all 15 lanes rc=0 except `shared` (the cold-landing test bug above, fixed; `test_flow_jump_to.py` rerun 24 passed); contracts-controls 401 s, contracts-overlay 246 s, none over budget. `make test-unit` (netns): 7786 passed, 15 skipped. `ruff check` and `ruff format --check`: clean. `provider-editor.js` untouched (896 lines).

### Leg 03c: chip, confirm, key-value and labels (landed, uncommitted)

**What changed.**
- **`App.ui.chip`:** `lead` (Node before the label, wrapped in `span.chip-lead`; the label then sits in `span.chip-label`), `onRemove` + `removeLabel` (throws without it) + `removeTestid`: a trailing library ghost small icon-only `x` button, the chip's only control. Without these the DOM is unchanged (`<span class="chip">plain</span>`). New owned classes `chip--lead`, `chip-lead`, `chip-label`, `chip-remove-btn` (catalogue). `.chip-remove` stays for leg 05a.
- **`App.ui.confirm` `onArmChange(armed)`:** `true` on arm; `false` on revert (which lapse and a caller's `revert` both reach, lapse after the announcement is queued) and on the commit click. Catalogue row updated; no caller changes.
- **`keyValueTable`:** squawk 0269 (key-column `onInput` refreshes the remove name) and squawk 0270 (`setRow` calls `setHint(null)` on a secret control when the patch carries its `storedKey`).
- **D7 (ledger rows 26 and 36 confirmed).** Final list: "LLM configuration", "System prompt" (title and label), "Chat history retention (days)", "Max iterations", "Context window" (label and the two validation messages), "Reasoning effort", "Anthropic account", "My provider" (name placeholder, found by the final grep), and the server's "OpenAI-compatible" provider-type label. "Base URL" kept. `provider-editor.js` stays 896 lines (in-place edits). Final grep for title-case labels in both editors and their tab modules found nothing else ("Danger zone" was already sentence case).
- **Specs:** `studio-agent-crud.md` ("Danger Zone" to "Danger zone"; its other label text needed no change), `agent-retention-setting-roundtrip.md` ("Max iterations") and `save-preserves-config.md` ("Reasoning effort"). Run logs untouched.

**Deviations.**
1. **Squawk 0270 "no Show button" does not hold.** After a renamed sensitive header saves with an empty value the row is an ordinary empty secret cell, and its eye is the normal one (a new sensitive row has it too). The MCP test asserts only that the stale hint is gone; the contract test covers `setRow`.
2. The MCP 0270 test's hint assertion was not seen failing on reverted code in the editor (the first reverted run failed on the dropped Show assertion); the contract test was seen failing first.

**Failing first.** On code with the two `keyValueTable` hunks removed: `test_remove_name_follows_a_typed_key` and `test_set_row_rebaseline_clears_the_rename_hint` (both engines) and the MCP `test_kv_remove_name_follows_a_typed_key` failed; all pass with the fix. The chip and confirm contract tests were written with their options (new options, so they cannot pass on old code: unknown option ignored).

**Pins retargeted.** `test_flow_provider_editor.py` (Context window label), `test_flow_studio_retention_error_message.py` and `test_flow_agent_tabs.py` (docstrings). `test_ui_info_contract.py` and `test_ui_secret_input_contract.py` carry their own fixture copy of "Context Window" and were left. No assertion relaxed.

**Squawks 0269 and 0270.** Corrective action and verification written in each squawk; status left `in-progress` for the flight-end sign-off.

**Verification.** Guards (ownership, emitted_classes, control_inventory, library_source, ui_guards, token_definitions, design_tokens_a11y, area_module_size): 446 passed; `ruff check` and `ruff format --check` clean. Contract files run in both engines: 198 passed. Batch-end full `--parallel 3` browser run and `make test-unit`: `PARALLEL_RESULT rc=0 total=1573s lanes=15 failed=-` (all 15 lanes rc=0, none over budget, including the full `shared` lane); `make test-unit` (netns): 7786 passed, 15 skipped; ruff clean.


### Leg 04: chat-controls (landed, not committed)

**What changed.**
- **Six factories** in `js/ui/`, loaded after `drawer.js`: `App.ui.composer` (`composer.js`), `App.ui.message` with `message.attribution` and `message.relabel` (`message.js`), `App.ui.thinking` (`thinking.js`), `App.ui.trace` with `trace.find` and `trace.thinking` (`trace.js`), `App.ui.telemetry` with `telemetry.formatTokens` (`telemetry.js`) and `App.ui.notice` (`notice.js`). Owned rules are one section in `components.css` (`ui-composer*`, `ui-message*`, `ui-thinking*`, `ui-trace*`, `ui-telemetry*`, `ui-notice*`). Testids are caller-supplied only; ES5; no app global. **No consumer changed:** `git diff` shows nothing under `js/areas/` and nothing in `chat.css`.
- **Catalogue:** Composer, Telemetry and Message rows moved to `library:`; "Thinking indicator, trace shell" split into Thinking indicator and Trace rows; a new Notice row. Each lists every class and modifier by name.
- **The `contracts-chat` lane** (six files, provisional 300 s budget in `scripts/run-tests.sh` and CLAUDE.md). Bookkeeping: `LANE_LIST`, `CANON_LANES`, `BUDGET`, `contracts_chat_pat`, `contracts_controls_files()` (third pattern subtracted), `resolve_lane`, header comments; `tests/test_run_tests_lanes.py` (`LANES`, the lane string, a three-way union and a new by-file test); CLAUDE.md (bullets, table, counts: sixteen lanes, fifteen named, the `contracts` alias), `the_one/agents.md` (the lane summary and a "Chat controls" paragraph) and the `ci/tasks/browser.yml` comment. The parity test joins `chats_transcript_pat`.

**Contract cases (each file runs in Chromium and WebKit under `THE_ONE_REQUIRE_WEBKIT=1`).** composer 19 per engine (38), message 17 (34), thinking 7 (14), trace 13 (26), telemetry 10 (20), notice 6 (12): 144 in all, `--lane contracts-chat` 144 passed in 46 s. Cases include the amendments' list: Enter while busy, Enter with empty text, blocked then unblocked while busy, an attach click calling `onAttach` and never the picker, IME by a composition-flagged event and by `keyCode` 229 in both engines, streaming with an operator marker and a peer label, an empty finalize, a double finalize, a `commit` with an empty fragment, a thinking node never attached that keeps ticking, a function `thresholds` that changes between updates, and a 200-character word in a message, a trace and a composer.

**Parity check** (`tests/browser/test_flow_chat_controls_parity.py`, lane `chats-transcript`, removed in leg 05c): 9 message roles and modifiers, markdown descendants, 3 attributions, thinking and the system loading line, the trace closed and open (with and without an operator-only tool message, pseudo-elements included), the thinking disclosure closed and open, telemetry in a warn state, and the live composer against a second new one. It was seen failing on a deliberately changed colour (the message-system and trace-count edits) and the edit was reverted. **Intended differences** (the `INTENDED` set; a stale entry fails):
1. A tool message inside a trace has `max-width: 100%`, not `none`: with an unbreakable word the old rule let it overflow the trace (found by the 200-character contract case, and fixed in the new rule).
2. (Behavioural, asserted separately) a blocked composer disables Attach (B13), and Send is disabled while `blocked` or `busy`.

The telemetry percentage is NOT mono: today's `.telemetry .t-ctx-pct` rule never matched the summary's percentage (it sits outside `.telemetry`), so the new control copies what is drawn, not what the rule intended. A mono percentage is a one-line change for 05c if the operator wants it (a presentation-debt candidate, not changed here).

**Cascade notes recorded for 05a-05c** (also in `components.css` above the chat-controls section):
- `.msg.user.msg-from-peer` beat `.msg.user` by source order; the new peer and api looks are compound selectors, so order no longer matters.
- The tool-in-trace override (0,5,0 in `.area-chat`) beat `.msg.msg-operator-only` (0,3,0); the new `.ui-trace-body .ui-message--tool` (0,2,0) ties `.ui-message.ui-message--operator-only` (0,2,0) and is declared AFTER it to win. If 05c reorders `components.css`, keep that order.
- Markdown descendant rules are scoped under `.ui-message--assistant` only.
- No `@layer areas` rule targets an element inside `.area-chat`, so none beats the new component rules (re-checked by grep: every `chat.css` rule is class-qualified).
- A modifier on an `.ui-message` sets `align-self`; a consumer that puts a message in a non-flex parent loses it.

**Decisions.**
- `App.ui.disclosure` was not reused for the trace: its summary is named by `aria-labelledby` over its text and meta nodes, which cannot give the exact name "Tool activity, N items", and its look (proportional text, bordered card) is not the trace's mono, left-ruled voice. The trace is its own native `<details>`.
- The attribution's Copy reply is `App.ui.copyButton` (icon only, `size: 'sm'`); with a shared `liveEl` the node is the bare button.
- The trace re-wraps by reading `data-trace-label` and its count-style class from the DOM, so `find` needs no stored state.
- `message` takes the visibility chip through `App.ui.chip` wrapped in `span.ui-message-operator-chip` (the chip takes no `className`).
- The blocked composer's dim is `background: var(--bg)`, a dashed border and `--fg-muted` input text; each is an audited pair (`fg_muted` x `bg`), so the contrast audit needed no new pair. 05a may choose another dim through the same class.
- `App.ui.notice` has no old renderer, so no parity pair; its look is a muted or danger body-sm line.

**Verification.** Guards (control inventory, library source, emitted classes, ownership, ui guards, token definitions, design-tokens a11y, run-tests lanes, index cache busting): 487 passed. `--lane contracts-chat` 144 passed; `contracts-controls` 1000 passed, 4 skipped (all `test_ui_*` outside the new lane; `--list | grep -c test_ui_` is 22 before and after, so the six files left no other lane); `chats-transcript` 43 passed (the parity test included); `chats` 150 passed. The three were run concurrently, never with the unit suite. `make test-unit` (under `THE_ONE_TEST_NETNS=1`): 7805 passed, 15 skipped (from 7786 / 15 at the B2 close). `ruff check` and `ruff format --check` clean. The `contracts-chat` budget is a **provisional 300 s** (a solo run took 46 s, which is not a budget input: squawk 0259).

**Not done.** Nothing in scope. The `contracts-chat` budget stays provisional until the quiet-host run at 09b.

### Leg 05a: composer-and-attachments (landed, not committed)

**What changed.**
- **The composer is `App.ui.composer`**, built once in `chat.js` with the legacy test ids and the callbacks `onSend` (`send.send(raw)`; the area's guards and its clearing on success stay in `send.js`, and a busy or empty Enter reaches the hold queue there), `onStop` (`stopTurn`, moved from the old listener), `onAttach` (`attachments.attach()`, which keeps the busy and blocked guard and calls `openFilePicker()`) and `onFiles` (`attachments.addFiles`). `areas/chat/composer.js`, its script tag and the `.area-chat .composer*`, `.chat-attachments`, queued-chip and `.chat-session-banner` rules are deleted. `ctx` no longer carries `inputEl`, `sendBtn`, `stopBtn`, `fileInputEl` or `attachBtn`: every module writes the handle (`ctx.composer`).
- **One blocked computation, written first:** `computeBlocked()` (`state.bannerActive`, or a pending chat with setup incomplete or validating) and `applyComposerState()` (`setBlocked` + `setBusy(isCurrentBusy())`). Every former `state.sessionBannerEl` guard (`send.js`, `attachments.js`, `socket.js` x3, `turn-frames.js` x3) now calls it; `updateStopControl` is `composer.setBusy(isCurrentBusy())`; the `sendBtn.disabled = true` writes in `performSend`, `startSend` and the `is_processing` join are gone (busy covers them). `state.sessionBannerEl` became `state.bannerActive` plus one persistent `App.ui.banner({tone: 'warning', live: 'status'})` driven by `set(text)`, empty collapsing it (A5).
- **A6/A7:** the staged-image chip is `App.ui.chip({label: 'Staged image N', labelHidden, lead: img (alt ''), onRemove, removeLabel: 'Remove staged image N', removeTestid, testid: 'chat-attachment', dataset})`; the queued chip is `App.ui.chip({label: text, truncate, lead: 'Queued' span, onRemove, removeLabel: 'Cancel queued message', ...})` in the live queued slot. The `chip` ownership row and its `MOVES` entry are gone.
- **Library additions (each with a contract test in both engines):** `composer.fileInput` and the persistent `aria-live="polite"` queued slot (`test_ui_composer_contract.py`, +1 case, 38 -> 40 across engines); `chip` `labelHidden` and `truncate`, and the 24x24 remove button with no negative margin (`test_ui_feedback_contract.py::test_chip_label_hidden_truncate_and_24px_remove_button`, both engines). The legacy `.chip-remove` rule (its last user was the staged chip) is deleted; its contrast gate moved to the ghost remove icon: `--fg-secondary` on the composited chip fill at 4.5:1 (covering the icon's 3:1 and the queued chip's "Queued" lead text), over bg, surface and surface-elevated, both themes.
- **0.1:** `requestPick` (the picker path only: Jump to's "New chat..." goes through it too) focuses the message box after `goPick` resolves true; a leave-guard Stay resolves false and focus stays on the opener. `chatWith`, direct hash entry and re-renders never move focus.
- **B6:** `.chat-welcome-inner` centres its text; `.chat-welcome-actions` centres the button.
- **Guards:** `tests/_ui_guard_helpers.py` `_TESTID_NAME` widened from `<lower>Testid` to `<camel>Testid` so the registry sees the composer's `fileInputTestid` and `attachmentsStatusTestid` (a stricter guard; the registry rows for `chat-image-input` and `chat-attachments-status` would otherwise have read as stale). `scripts/ui_capture.py` shots `.composer` -> `.ui-composer`.
- **Docs:** CLAUDE.md "Chats pane" and "Chat composer"; `the_one/agents.md` "Chat composer" (the header paragraph, with the legacy class names renamed to `ui-` throughout) and the chat module map; the catalogue's Composer and Chip rows and the chip-list row; the testid registry row for the attachments row; `tests/behavior/vision-round-trip.md` (the composer note; the spec never named the glyph or `.chip-remove`, so no step changed).

**Failing first (written and seen failing before the fix, 10 failures in the first run):** after a pick `chat-input` is focused (0.1); a deleted agent's chat has a `role=status` `.ui-banner` `banner-warning` and Attach disabled (0.3); the staged chip's remove is named "Remove staged image 1" and is 24px; the queued chip reads "Queued" (no colon) with a "Cancel queued message" button and its region is `aria-live=polite`; the empty state's text and button are centred (computed `text-align` and the button's and mascot's horizontal centres against the pane's); and the contract cases (`fileInput`, the live queued slot, `labelHidden`, `truncate`, the 24px button). **Not provable failing first: the `blocked || busy` Send fix.** The old banner-clear path set `sendBtn.disabled = false`, but no real flow clears a banner while the active chat is busy (a pick or an idle go has no busy chat, and a join's `is_processing` branch set it back synchronously), so it was a latent defect with no browser-observable failure. It is pinned by the leg 04 composer contract (blocked then unblocked while busy keeps Send disabled) and by `test_the_banner_clears_when_another_chat_opens_and_send_follows_busy`, which passes before and after; ledger row 41 says so.

**Locators retargeted and deliberate assertion changes (nothing relaxed).**
- `test_flow_chat_composer.py`: `.composer*` classes -> `.ui-composer*`, `.chat-attachments` and `.pending-queued-region` -> their testids, the Attach/Stop/Send class strings gain `ui-composer-`; **deliberate:** the chrome's children are now `[header, new-state, messages, banner, composer]` (the persistent health banner, collapsed while empty) and the telemetry slot and box are named by their `ui-composer-*` classes.
- `test_flow_chat_image_attach.py` (names test): the chip's name is its visually hidden `.chip-label` ("Staged image 1/2") and the thumbnail's `alt` is `""` (the amendment's FD answer: the label names the chip, never twice); the remove-button names are unchanged.
- `test_flow_chat_picker.py::test_enter_picks_and_a_re_pick_replaces`: the focus assertion after a completed pick was the opener and is now `chat-input` (0.1); `test_a_guard_stay_keeps_the_pickers_opener_focused` is unchanged and passes.
- `test_flow_chat_controls_parity.py`: the composer pair and its B13 check are removed (the old renderer is gone); its docstring says so. `test_index_asset_cache_busting.py`: the fixture script is `areas/chat/send.js`. `test_nav_helper.py`: the synthetic selector fixtures use `.ui-composer-*`. `test_design_tokens_a11y.py`: the `.pending-queued-chip` comment and the moved gate.
- `RETIRED_SELECTORS` gained nothing: the removed names are CSS classes the registry's testid table does not cover, and `git grep -nE "\.area-chat \.composer|\.composer-(box|input|toolbar|model|send|stop|telemetry)\b|pending-queued-(chip|label|text)\b|chat-session-banner|\.chip-remove[ {,:]|App\.chat\.composer" -- the_one/ tests/` finds nothing. (`pending-queued-cancel` is kept as a testid.)

**Capture comparison** (`$HOME/.cache/the-one-ui-capture/m31-f6-l05a-after` against `m31-f6-before`, PIL threshold 8, 11 surfaces x light/dark x 1280/1024): **identical** (0 differing pixels): `chat-composer-focused`, `chat-composer-multiline`, `chat-live-streaming`, `chat-pending-new`, `chat-pending-long-name`, `chat-joined-empty`. **Differing only where a ledger row says so:** `chat-composer-staged-images` (a 110x34 region: the chip and its remove button, rows 6 and 40), `chat-live-queued` (the queued chip, row 7), `chat-joined-ghost-agent` and `chat-live-thinking` (both agents' sessions carry a health banner: the library banner, row 5, and the dashed blocked box, row 25), `chats-empty` (the centred column, row 23). The queued capture holds a long message, which keeps one line with an ellipsis.

**Lanes (each with `THE_ONE_REQUIRE_WEBKIT=1`, `THE_ONE_TEST_NETNS=1`, three at a time, never with the unit suite):** `chats` 156 passed; `chats-transcript` 43; `contracts-chat` 146; `contracts-controls` 1002 passed, 4 skipped; `library` 104; `mcp` 87; `mcp-connection` 94; `knowledge` 65; `agents` 166. **Unit:** `make test-unit` 7805 passed, 15 skipped (the same as the leg 04 close; the leg adds browser tests only). `ruff check` and `ruff format --check` clean. Guards (ownership, ui guards, token definitions, design-tokens a11y, area module size, index cache busting, control inventory, emitted classes, nav helper): 468 passed.

**Flake triage.** In the first concurrent `chats` run `test_flow_chat_list.py::test_row_delete_arms_confirms_and_focuses_the_neighbour` failed (an `expect(action).to_be_focused()` after a Tab); it passed in isolation, in a three-file re-run and in the final full `chats` run, so it is recorded as a load flake (not a regression). The other first-run failures were the retargets above.

**Allowance deltas.** `OWNERSHIP_ALLOWANCE` 8 rows / 14 uses -> 7 rows / 13 uses (`js/areas/chat/attachments.js` `chip` removed; its `MOVES` entry and `TOTAL_USES["chip"]` removed); HTML-string sinks unchanged at 5 (`chat.js`); `chat.js` is 516 lines and every module is under 800.

**Not done / notes.** The queued chip hugs its text instead of filling the region's width when the message is short (the chip takes no layout hook; the long case fills to the ellipsis). Row 41's fix has no failing-first browser evidence (see above). The deleted-agent drawer and the context-window 404 stay with 05c as the leg says.

### Leg 05c: transcript (landed, not committed)

**What changed.**
- **Order followed:** the parity test was deleted first (`run-tests.sh` list now names `test_flow_chat_transcript_library.py`), then the failing-first tests, then the migration.
- **The transcript is on the library:** `transcript.js` builds `App.ui.message` / `.attribution` (roles, `api`/`error`, peer, operator chip), the streaming bubble through `appendText` / `tail()` / `commit` / `finalize` with the full received text kept per bubble (F1), `App.ui.thinking` ("Thinking", "Loading model"), `App.ui.trace` (icon chevron, dot count, `.find` after a re-join) and `App.ui.trace.thinking`, and `App.ui.notice`. One `clearLog()` (called by `renderPending`, `clearConversation` and `renderHistory`) drops the thinking, model-loading and stream handles and the trace map (DD11 4). `chat.js` builds one `App.ui.telemetry` (`ctx.telemetry`, seam `_telemetry()`, testid `chat-telemetry`), one `chat-copy-status` live node (in the area panel, outside the log), and the zone relabel is `App.ui.message.relabel`.
- **B2:** a per-iteration anchor (streaming bubble or last assistant bubble; cleared at `tool_call`, `tool_result`, `user`, `done`, `cancelled`; on replay only the immediately preceding `assistant`); no anchor appends in stream order. **B9:** `stopTurn` records `state.discardedOnStop[id]` before clearing the held message; `cancelled` appends "Stopped." and, for the flag or a still-held message, "Queued message discarded."; neither is stored. **A4:** an `Agent error: ` system frame is a danger notice with the headline and the raw text under a plain "Technical details" disclosure (the bubble is finalized first; the model-loading line is dropped). **DD11 5 / 0.3:** the context-window fetch is skipped for a join `status` other than `ok` or a loaded store without the agent, and applied only while the bound session and agent are unchanged.
- **Library addition (one):** `App.ui.message.visibilityStyles` ({label, chip}) so the area names the chip style without the owned class token as a string (the ownership ratchet counts string literals; the alternative was a new allowance row). Catalogue row updated; no contract pin changed.
- **Deleted:** `message-bubble.js`, `thinking-indicator.js`, `trace-shell.js`, `telemetry-overlay.js` and their script tags; the `chat.css` rules for `.msg*`, `.trace*`, `.thinking*`, `.model-loading`, `.telemetry*`, `.context-bar*` (the dead `.trace-shell ... .login-required-*` rules with them); `.msg-pending-approval*` and `.messages .login-required-*` stay. A15 (`opacity: 0.75` removed) and A18 (2px offset) are `components.css` edits.
- **Registry and docs:** testids `chat-agent-error`, `chat-agent-error-details`, `chat-copy-status`, `chat-discarded`, `chat-stopped`, `chat-telemetry`, `message-copy`, `model-loading`; CLAUDE.md (transcript paragraph, composer telemetry, lane list), `agents.md` ("Chat transcript on the library", module map, telemetry, relabel), the catalogue's five rows. `scripts/ui_capture.py`: telemetry and message selectors retargeted; `CHAT_ERROR_TEXT` now carries the real "Agent error: " prefix so the capture exercises A4.

**Failing first (seen failing against the old code, behavioural, run from a temporary selector-swapped copy that was deleted):** DD11 4 (a 120 ms interval still alive after a picker switch), DD11 5 (`99.0k` in B's readout after A's late response), 0.3 (a context-window request made for a deleted agent). The other new cases (F1, B2 live/replay/multi-iteration, B9 x3, A4, A8, A15, A18, B3, B5, the zero-max restore, the stopped-reply drain) all failed in the first run too, but on the new selectors and testids, so that is selector evidence, not behavioural; all 18 pass now.

**Locators retargeted (helper `_chats.message_sel(role, *modifiers)` / `_chats.messages(page, role)`, plus `_chats.telemetry`, `emit_frame`):** about 55 `[data-testid="message"].role` locators across 15 files by script (`test_chats_helper`, `test_flow_chat`, `_composer`, `_image_attach`, `_pane`, `_queued_render`, `_start_flow`, `_start_reconnect`, `test_flow_context_overlay_thresholds`, `test_flow_markdown_chat`, `test_flow_new_chat`, `test_flow_streaming`, `test_flow_usage_restore`, `test_nav_guard` (routing), `test_visual_snapshots` (pixel)); by hand: `.msg*`, `.trace-*`, `.thinking-*`, `.telemetry-*`, `.context-bar`, `.t-*`, `.msg-attribution*` in `peer_attribution`, `visibility_distinction`, `thinking_disclosure`, `time_zone`, `oauth_modal_flow` (shared), `chat_pane`, `chat_start_flow`, `context_overlay_thresholds` (drive through `_telemetry()`), `usage_restore`. **Deliberate assertion changes:** `[operator-only]` label -> "Operator only" chip (B5); the trace count `1` -> "Tool activity · 1" (B3); `from-agent` / `from-peer` / `from-you` -> `ui-message-attribution--*`; composer chrome pin unchanged (the live node sits in the area panel). Contrast: `_TELEMETRY_RESTING_OPACITY` comment retargeted; new `test_message_timestamp_passes_body_aa` (`--fg-faint` on `--bg` 5.12:1 light, 5.34:1 dark) and a usage pin that `.ui-message-attribution-ts` has no opacity.

**Behavior specs re-authored:** `stub-connector-round-trip` steps 5-7, `agent-governance-and-search` preconditions and step 8, `extended-thinking-tool-turn` steps 4-5, `chat-loop-hang-and-cancel` steps 2 and 4.

**Capture comparison** (`$HOME/.cache/the-one-ui-capture/m31-f6-l05c-after` against `m31-f6-before`, 33 chat surfaces x light/dark x 1280/1024, PIL threshold 8, scratch `--out` outside the repo). Identical: none of the transcript surfaces; every difference maps to a row: Chats list "Discord" badge (230 px at the badge, `chat-joined-empty`, `chat-pending-*`, `chats-list-groups`; row 16, leg 05b); `chats-empty` and guidance (row 23, 05a); `chat-joined-ghost-agent`, `chat-live-thinking` (banner rows 5 and 25, and "Thinking…" row 8); `chat-live-agent-error` (row 4: danger headline and collapsed "Technical details"); `chat-live-after-stop` (rows 24, 30, 15); `chat-live-streaming` and `chat-live-queued` (rows 30, 15, 7); `chat-joined-peer` (rows 22, 30, 15); `chat-joined-long-names` (rows 30, 15); every rich-chat surface is 22 px taller (Copy reply in the attribution rows, row 30) and shows the thinking disclosure above its reply (row 20), "Tool activity · 4" with the icon chevron (row 21) and, in the connector chat, the chip (row 22); the telemetry surfaces are unchanged apart from the A18 offset (not visible at rest). Row 39 is covered by the trace tool-message cap (not visible in these captures: no unbroken word).

**Lanes (three at a time):** `chats-transcript` 60 passed, `chats` 159 (run before the last small edits), `shared` 271, `routing` 186, `contracts-chat` 146 (WebKit required). Guards (ownership, ui guards, token definitions, a11y 317, nav helper, area module size, cache busting, inventory, emitted classes, lanes) 169 passed. `ruff check` and `ruff format --check` clean. **Full gate** (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`): the first run failed one unit test (`test_store_static.py::test_start_session_join_refreshes_the_list_that_primes_sessions` counts `return;` in the `session_joined` block; the new context-window `.then` had one, now restructured); the re-run: unit 7810 passed, 15 skipped; `PARALLEL_RESULT rc=0 total=1795s lanes=16 failed=-`.

**Allowance.** `OWNERSHIP_ALLOWANCE` holds only `markdown.js` (`api:App.icon(` 1, `api:App.showFlash(` 3); no `js/areas/chat*` or `css/chat.css` row; `MOVES` empty; no HTML-string sink in the chat files.

### Leg 06: turn-end-messages (landed, not committed)

**What changed.**
- **The flag (core.py):** `Agent.stopped_at_step_limit` (public, default `False`, commented in `__init__`; cleared as the first statement of `step()`, of `resume_after_auth()` before its no-op return, and in `reset()`; set after the `while` in `_run_iterations` with no `return`, so before the generator returns).
- **Web (app.py):** `_process_and_broadcast` gained `turn_info: dict | None = None`; it captures the flag into the local `hit_step_limit` right after its `async for` (inside the `try`, before any other await), sends `{"type": "step_limit", "steps": session.agent.max_iterations}` in the non-paused branch after `_save_session_to_db` and immediately before `done`, and writes `turn_info["step_limit"]`. `_resume_paused_session` sends the same frame inside `if not re_paused:` immediately before its `done` (its later save not moved). Both through `_send_to_session`; never `add_event`, so `Session.history` and the DB hold nothing. The "Agent error" path is unchanged (and keeps its `"Agent error: "` prefix, leg 05c's contract). REST: `/api/chat` passes a `turn_info` dict and adds `"step_limit": true` only when set.
- **Connectors (inbound.py):** `_reply_target(envelope, connector_id)` (shared by `_auto_deliver_reply` and the new helper) and `_send_step_limit_line(...)`, which catches `ConnectorClientError` and every other `Exception` and never raises. `dispatch_inbound` captures the flag into a local right after its `async for`, and calls the helper in the `else:` of the persist's `try/except`, so after `chat_repo.update` and never after a failed step. Always sent, including after a `send_to_platform_channel` turn. Line: `(Stopped: reached its step limit for this message.)`.
- **CLI (cli.py):** `step_limit_text(steps)` and `_print_step_limit_notice(agent)` (dimmed), called after the turn's loop.
- **Client:** `turn-frames.js` handles `step_limit` (`hideThinking`, `finalizeStreamingBubble`, `clearStreamingVisibility`, then `transcript.addStepLimitNotice(steps, state.currentAgentName)`); `transcript.js` builds the notice with `App.ui.notice({tone: 'muted'})`, testids `chat-step-limit` and `chat-step-limit-link` (registry rows added), "Max iterations" a link to `#agents/{name}` only when `App.store.peek('agents')` holds a record with that name. No change was needed to the frame gate (`accepts` has no allowlist: every non-list frame is accepted while joined). One test seam added: `chat.js` `self._turnFrames()` (beside `_telemetry`).
- **0.2:** `PROVIDER_TYPE_LABELS` beside `PROVIDER_TYPES` in `db/_provider_types.py` (asserted to have the same keys); `GET /api/providers/types` reads it (picker order unchanged, labels identical). The factory passes `server_label` to `OllamaProvider` for the `ollama` registry name; `ollama_api.server_phrase(label, sentence_start=False)` renders "Ollama" or "the OpenAI-compatible server"; `chat_stream` and `show_model` take `server_label="Ollama"`; `ollama_provider.py`'s own status error uses it. **Ollama-only call audit:** every other Ollama-only call on this type is guarded by `provider.type == "ollama"` (`_ensure_ollama_model_loaded`, `_get_ollama_base_url`, the models/test branches); only the two known `/api/show` probes (`supports_tools`, `_resolve_max_context_tokens`) reach an `openai-compatible` provider. No divert.
- **Spec:** `tests/behavior/agent-step-limit-notice.md` (status `draft`; run in leg 09b).
- **Docs:** `the_one/agents.md` (WebSocket table row for `step_limit`, "Step-limit flag" paragraph with the lifecycle, the connector line and the CLI), `the_one/connectors/README.md` (the line), `docs/ui-testid-registry.md` (two testids). CLAUDE.md and SECURITY-MODEL.md list no frames, so no change.

**The frame contract as implemented.** `{"type": "step_limit", "steps": <agent.max_iterations>}`; session-scoped (gate: joined only); sent immediately before `done` on the step path (after the save) and on the resume path (inside `if not re_paused`); not sent when paused, re-paused or when the step raised; broadcast-only. REST key `"step_limit": true`, absent otherwise.

**0.2 wording, per message** (`openai-compatible`; `ollama` is unchanged):
- `chat_stream`: "Cannot connect to the OpenAI-compatible server at {url}: {exc}"; "Timeout streaming from the OpenAI-compatible server at {url}: {exc}"; "The OpenAI-compatible server returned {status} from {url}: {detail}".
- `show_model` (logged, not user-facing): "Cannot connect to the OpenAI-compatible server at {url}: {exc}"; "Timeout connecting to the OpenAI-compatible server at {url}: {exc}"; "Model '{model}' not found on the OpenAI-compatible server at {url}".
- `ollama_provider.complete`'s status error: "The OpenAI-compatible server returned {status} from {url}: {detail}".
- Left as they are: `chat_native`, `chat_stream_native`, `list_models`/`list_running`, pull/delete/load/unload (Ollama-only, type-guarded).

**Failing first.** Unit: `tests/test_agent_step_limit.py` 13 of 13 failed with `core.py` stashed; `tests/test_step_limit_web.py` 4 of 8 failed with `app.py` stashed (the 4 that assert the frame/key; the negative cases pass by design); `tests/test_ollama_server_label.py` 2 of 3 failed with `ollama_api.py` and `ollama_provider.py` stashed (the Ollama-unchanged case passes by design). Browser: `test_the_step_limit_notice_links_to_the_agent_and_is_not_stored` failed with `turn-frames.js` stashed. The connector and CLI tests were written with the code (not run against a stash). Ledger rows 28 and 31 confirmed with the final wording above.

**Tests added.** `test_agent_step_limit.py` (13), `test_step_limit_web.py` (8: step path order and payload, broadcast-only, normal turn, error path, resume zero budget, re-pause, REST key present and absent), `test_connectors_inbound.py` (+5: once and not stored, after `send_to_platform_channel`, normal turn, send failure keeps the persisted turn, no live client logged and dropped), `test_cli_step_limit.py` (3), `test_ollama_server_label.py` (3), `test_factory.py` (label per type, parametrised), browser `test_flow_chat_transcript_library.py` (+3: notice text, tone and position, reload shows none; link goes to `#agents/{name}/general`; deleted agent is plain text). Existing stubs that feed `_process_and_broadcast` (`_FakeAgent` in `test_ws_start_session.py`, `StubAgent` in `test_app_websocket_pause_resume.py`) gained the two attributes the web path now reads; `fake_chat_stream` fakes (`scripted_transport.py`, `test_ollama_provider_recovery.py`) accept `server_label`.

**Eval.** Not run: the notice and the connector line are never stored or sent to the model, and no platform prompt text changed (0.2 changes provider error wording only), so the CLAUDE.md "Prompt evals" rule does not apply.

**Lanes and counts.** `chats-transcript` 66 passed (after the last test fix, the file's 21 passed), `chats` 159 passed (two lanes concurrently, never with the unit suite), static guards (ui_guards, token definitions, a11y, nav helper, ownership, lanes) 469 passed, `make test-unit` 7842 passed, 15 skipped (netns). `ruff check` and `ruff format --check` clean.

### Leg 07: markdown (landed, not committed)

**Negative tests first** (`tests/browser/test_markdown.py`, 173 tests after adding them; run against the untouched renderer: 27 failed, 146 passed).

| Case | Result against today's renderer |
|---|---|
| `[x](/\evil.example)`, `[x](/<TAB>/evil.example)`, `[x](/<LF>/evil.example)`; also a backslash or control inside an `https:` path, a DEL in a `#` href, a tab after `mailto:` (7 cases) | **FAILED today** (href kept). `[x](\/evil.example)` already gave `#`: regression guard |
| Fence info string: ```` ```js is-hidden ````, a tab-separated second token, ```` ```js" onmouseover=... ````, a 33-character tag (4 cases) | **FAILED today** (the whole remainder became the class). The valid-token cases (`c++`, `objective-c`, `c#`) and the no-lang case passed |
| Nested link `[a [b](https://x)](https://y)` | **FAILED today** (it nested). `[https://a](https://a)` and `[see https://a now](https://b)` passed (no autolinks yet): guards |
| `[`]`](u)` label with a bracket in a code span | **FAILED today** |
| Attribute injection in an href, `javascript&colon;`, `%6Aavascript:`, `&#106;avascript:` | pass today: **regression guards** |
| Same-origin `/about?x=1#y` and `#top` still links | passes today: guard |
| Autolink negatives (bare `javascript:`, `http://` alone, `foohttp://`, code span, fence) | pass today (nothing links yet): guards that now hold with autolinks on |
| Autolink positives (6), contexts, strikethrough (7 of 10 render cases; `~single~`, unclosed, code-span and cross-paragraph cases passed as guards), the STRIKE AST | **failed today** (features absent) |

**What changed.**
- **`safeHref`:** returns the original string; `#` for any `\` or C0/DEL character anywhere, `//host`, and anything outside `http(s)`, `mailto`, `tel`, or a `/`/`#` link that resolves to `location.origin` (`new URL`; an opaque `"null"` origin or no `location` is not same-origin). Every existing `SAFEHREF_BOUNDARY_CASES` expectation is unchanged.
- **Fence:** the parser keeps the first whitespace token only if it matches `^[A-Za-z0-9_+#.-]{1,32}$` (else `lang: null`); `renderCodeBlock` re-checks. The `:948` pin is rewritten (docstring says why): the injection case now has no class and no extra attribute.
- **Inline:** `scanInline(text, ctx)` with `{noEmphasis, noLinks}`; link labels use `noLinks` (the nested link was real and is fixed unconditionally), emphasis bodies keep strike and autolinks. `parseLink` skips code spans when counting label brackets (fixed, small). `STRIKE` node (`~~` only; closer skips code spans; unmatched stays literal). Autolink at a word boundary, stopping at whitespace, `<`, `>`, `\`, controls; trailing `.,;:!?*_~` and an unbalanced `)` trimmed (balanced Wikipedia parens kept); `safeHref(url) !== url` gives plain text, so it never emits `#`. `www.`, `mailto:` and `<https://...>` are out of subset (module header says so).
- **Task lists:** `parseList` detects `^\[([ xX])\](?:\s+|$)` on the first line, strips it, sets `meta.task = {checked}` only on task items; render adds `li.markdown-task` with a disabled checkbox named from the first paragraph's text ("Task" when empty).
- **Tables:** every table is inside `div.markdown-table-wrap` (`tabindex=0`, `role=region`, `aria-label=Table`).
- **Copy:** `renderCodeBlock` builds `App.ui.copyButton({iconOnly, size: 'sm', label: 'Copy code', text, className: 'markdown-copy-btn', liveEl})`; markdown makes its own `span.visually-hidden[role=status]` in the wrap, so the root is the bare button (a test asserts the wrap's height equals the `pre`'s). `injectIcon`, `App.icon` and `App.showFlash` are gone from `markdown.js`; `NodeType` has 20 constants.
- **CSS (where it lives):** `components.css`, A1/B1/task rules beside the `.ui-message--assistant` descendant rules; `.markdown-copy-btn` keeps only `position/top/right`, resting `opacity: 0.6` and the hover/focus reveal (a visibility affordance, not a disabled state, so the no-opacity rule for disabled buttons does not apply). Background, border, radius, padding, colour, svg size and hover border are the library's.
- **Counts:** `OWNERSHIP_ALLOWANCE` is now `{}` (the two `markdown.js` rows are removed, also from `START_ROWS`), `TOTAL_USES` is `{}` (4 uses removed).
- **Tests retargeted:** exact copy markup became `test_markdown_code_block_structure`; `test_markdown_copy_button` asserts name "Copy code", the check state ("Copied"), the in-wrap status text, clipboard text and no `.app-flash`; the `.messages` toast test in `test_flow_markdown_chat.py` became `test_code_copy_confirms_in_place_with_no_toast`; table render cases use the wrapper; `test_markdown_nodetype_constants` has `STRIKE`; the streaming test gained `see https://exa`, a cut at a backslash and `~~half`; the DOMParser seam text in `tests/test_ui_guards.py` and `tests/_ui_guard_helpers.py` is updated.
- **A1/B1 measurements:** h1..h6 computed 18, 16, 15, 14, 13, 13 px (cap `--font-size-h1` = 18); with a 420px column and 160-character cells, the wrapper's `scrollWidth` exceeds its `clientWidth` while the bubble's does not (`overflow-x: auto`, table `width: auto`).
- **Docs:** `the_one/agents.md` Markdown rendering section, `docs/ui-control-inventory.md` (Copy row), the module header, and `tests/behavior/discord-markdown-links.md` step 4 (bare-URL clause added; no re-author needed, it does not rely on `/` or `#` links). Squawk 0275 (`App.safeUrl` blind spot) stays deferred.
- **Ledger:** rows 1, 2, 19, 29, 33 confirmed as written; rows 44 and 45 added (copy button size and look; task checkbox and table overflow).

**Lanes and counts.** `test_markdown.py` 181 passed; `shared` 332 passed; `chats` 159 passed (includes `test_flow_markdown_chat.py` and the transcript files); `contracts-controls` 1002 passed, 4 skipped (WebKit required); static guards (`test_ui_guards`, `test_ui_ownership`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_control_inventory`) 379 passed; `make test-unit` 7845 passed, 12 skipped; `ruff check` and `ruff format --check` clean. Three lanes ran together, never with the unit suite.

### Batch B3 review fixes (landed, not committed)

- Chip focus (WCAG 2.4.3): `attachments.js` `removeStagedImage` and `hold-queue.js` `cancelPendingQueued` move focus only when the removed button held it (next chip's remove button, else previous, else the composer input; the queued cancel goes to the composer input). Tests: two in `test_flow_chat_image_attach.py`, one in `test_flow_chat_queued_render.py` (chats-transcript).
- Queued live region (WCAG 4.1.3): `ui/composer.js` no longer sets `hidden` on `slots.queued`; `hold-queue.js` only inserts and removes the chip; `.ui-composer-queued:empty` has no margin, so the collapsed layout is unchanged (no ledger row). Composer contract tests updated (both engines).
- `ui/thinking.js`: the dots span is `aria-hidden="true"`; contract assertion added.
- Stale references updated (config.py, self-config-history.js, self-configuration-tab.js, test_flow_chat_pane.py, agents.md; the CLAUDE.md `--lane` list gained `contracts-chat`). Accepted: bare function-name mentions (`renderMessage`, `updateTelemetry`) in two test comments and an app.py comment.
- Verification: static guards 467 passed; contracts-chat 146, chats-transcript 63, chats 159 passed; `make test-unit` 7810 passed, 15 skipped (netns); ruff clean.

## Decisions
Runtime decisions not in the original plan.

### An eighth chat module, `send.js` (leg 02 design)
**Context**: Leg 02's design review counted what DD3 leaves in `chat.js` at about 760 lines before the `create(ctx)` plumbing, so the 800-line cap was at risk.
**Decision**: The send path (`performSend`, `sendHeld`, `send`, `setInputValue`, `updateStopControl`, `isCurrentBusy`) moves to `js/areas/chat/send.js`. The `chat.js` bound is restated as about 650-750 lines, with a hard cap of 800. This is within the flight's acceptable variations ("module boundaries and names inside DD3").
**Impact**: Eight new script tags in leg 02 instead of seven. Leg 05a's composer migration touches `send.js` as well as `chat.js`.

---

## Deviations
Departures from the planned approach.

---

## Anomalies
Unexpected issues encountered.

---

## Flight Director Notes

- **2026-10-26, planning.** Loaded the flight skill (plugin 1.2.3) and `.flightops/agent-crews/flight-design.md`. Spawned two read-only survey crew in parallel (code and presentation). Built and published the review page, and the operator returned decisions the same day. Recorded the flight spec and this log on `main`'s working tree, uncommitted; they move to the flight branch at flight start.
- **Architect cycle 1 (Opus): approve with changes.** 16 Citation Audit rows were spot-checked and all held; the unit guard baseline was green (148 passed). All findings were applied to the spec:
  - **[high] class policy:** DD4 adopts the `toolTile` precedent. Leg 04 emits new `ui-*` classes; the consumer legs delete the legacy names and retarget the locators; no control owns a bare role word.
  - **[high] F2:** DD8 pins the flag's lifecycle and the `{"type": "step_limit", "steps": n}` frame. The frame is broadcast-only (never `add_event`). The connector line, the REST key, the CLI line, the missing-agent link and `n < 1` are all specified.
  - **[medium] the flash contract:** `App.ui.modal.top()`; a toast is re-homed when its modal closes; the newest toast replaces the old.
  - **[medium] sequencing:** DD9 test 6 and DD11 7 move to 03a, and A14 folds into 03a.
  - **[medium] notice control:** `App.ui.notice` is added to DD4.
  - **[medium] DD11 2:** the divert is reworded around the two known `/api/show` probes.
  - **[medium] captures:** pinned against the clock and zone.
  - **[medium] leg sizes:** 03b is split into 03b/03c, 05a into 05a/05b/05c, and 09 into 09a/09b. That makes 14 autonomous legs, under the 15-leg divert line.
  - **[medium] behavior specs:** the re-reads move to the legs that change their text, adding `agent-retention-setting-roundtrip` and `save-preserves-config`.
  - **The lows,** each applied: the copy announcement under `role=log`; the 0.4 negative cases; the stale line counts; the durable copies of the surveys (`$HOME/.cache/the-one-ui-capture/m31-f6-planning/`); `App.ui.badge.live`; F1's full streamed source; `current_time` for the F2 mock; the lane-budget source; the `contracts` alias; the contrast audits moving with their rules.
- **Operator answers to the Architect's questions, 2026-10-26:**
  - toasts: the newest replaces the old (ledger row 38);
  - the connector step-limit line: neutral wording, "(Stopped: reached its step limit for this message.)", always sent.
- **Architect cycle 2 (Opus): approve with changes**, with nothing high. Every cycle-1 finding was confirmed resolved against the code. The findings, all applied:
  - the resume path's `step_limit` placement and its tests (medium);
  - two behavior specs that name deleted classes added to 05c (medium);
  - the lows: stale cross-references (DD7 03c, the reconnaissance table, DD14's `iconNode`), `notice` in the criteria, A16 moved to 05b, A14 named in `studio-agent-crud`'s re-authoring, the 03a lanes and 04's lane bookkeeping, and citation drift.
  - The suggestions were taken too: modifiers listed by name in the catalogue; area code never queries `ui-*`; catalogue row 82 split; `page.clock.set_fixed_time`; `provider-editor.js`'s zero headroom; the catalogue header prose.
  - The review cycle ends here (max 2).
- **2026-10-27: the operator approved the spec, and the flight status is `ready`.** `main` advanced to `3b3d42a` (sortie 06, #329, safe names), and the FD checked it against the plan. The allowance and sink counts are unchanged; it does not touch the chat area; `provider-editor.js` is still 896 lines; and the `studio.css` rows that DD6 retires are unchanged. No planning premise moved.
- **FD calls on the Architect's other questions:**
  - the notice links to `#agents/{name}` only for an agent with a stored record, and is plain text otherwise;
  - the chat controls get new `ui-*` names, and the browser tests are retargeted in the consumer legs;
  - DD7's platform-badge check compares against one display-name table, not the chat header;
  - a connector turn's step limit shows nothing in an open web chat (not stored; expected at the HAT).

- **2026-10-27, flight start.** Re-loaded the agentic-workflow skill (plugin 1.2.3) and `.flightops/agent-crews/leg-execution.md` (Developer Sonnet; Reviewer Haiku, or Sonnet for security-sensitive diffs; Accessibility Reviewer Sonnet). Cut `flight/06-chats-and-closing-the-counts` from `main` at `3b3d42a`. Flight status `in-flight`. 14 autonomous legs plus the HAT.
- **Leg 01 designed and tiered high.** It is not a product change, but it changes shared test infrastructure: the lane definitions and budgets, the allowance bookkeeping, and a 4,920-line test-file split. The before set's integrity also depends on ordering (captures before any `the_one/` change). A Developer design review was spawned.
- **Leg 02 designed and tiered high** (a behaviour-free restructure of the largest area file; per the flight spec). Its Developer design review ran read-only during leg 01's quiet-host runs (no test runs) and approved with changes, all applied: the owner table, `send.js` (see Decisions), the anchor specifics and the allowance-row steps. No second cycle. The leg goes `ready` once leg 01 lands and the line numbers are re-checked.
- **2026-10-27, `main` advanced to `8a80590`** (sortie 06's debrief, #330): docs only. It changes the sortie's debrief, flight log and flight file, squawk 0241, and adds new squawks 0273 (the agent editor's header errors are not announced, outside this flight's surfaces) and 0274 (scrub operator paths from mission docs). It overlapped no uncommitted file, so the FD fast-forwarded the flight branch (no commits yet) and the local `main` during leg 01. No code changed, so the before-set rule (`git diff main -- the_one/` empty) is unaffected. **This flight's new squawks start at 0275.**
- **Leg 03a designed and tiered high** (a shared interface with every editor as consumer; per the flight spec). Its design review ran read-only during leg 02 and approved with changes, all applied. FD answers: `noteFlag` takes `opts` (`{sources}`) rather than changing the factory-line guard; the region is exported as `App.ui.flash.region()`; `badge.live` coexists with `App.ui.badge`. The "Saved" behavior-spec steps are re-authored in 03a. The leg is `ready`; it starts after batch B1's review and commit.
- **Leg 03b designed and tiered high** (the `searchList` and `modal` contract changes reach Jump to, the picker and the Date and time list). Its design review approved with changes, all applied.
  - **D4** is kept as the operator chose it on the review page (option (a), keep the highlighted row by identity, moved or not). It explicitly supersedes M25 DD10, and the pinned tests and `jump-to-palette` steps 2-3 are rewritten deliberately.
  - **The other changes:** identity is `(group, id)`; the A9 flex approach has a 64px floor; the section inset becomes a default flip; `width: 'fill'` is dropped for a `minWidth` option.
  - The flight spec's DD6 rows are annotated. The leg is `ready`.
- **Leg 03c designed and tiered low** (out loud):
  - the chip `lead` and `onRemove` and the confirm `onArmChange` are additive library options in established patterns, with no consumer change in the leg;
  - the two `keyValueTable` fixes are squawk-sized (0269, 0270);
  - D7 is label text, done in place within `provider-editor.js`'s zero headroom.

  No per-leg design review. The batch B2 review covers the code. The leg is `ready`.
- **Leg 02 landed** (`[LAND:leg]`). `chat.js` went from 2,398 to 525 lines across eight modules. Full gate: unit 7784 passed / 15 skipped (netns); browser `PARALLEL_RESULT rc=0 total=1561s lanes=15 failed=-`. The host was checked clear of leftover test processes afterwards.
- **Batch B1 end (legs 01-02).** No product class or selector was deleted in this batch, so there was no deleted-selector grep. The deleted MCP test file's name was grepped in leg 01. A Reviewer was spawned: **Sonnet**, because the diff moves the OAuth sign-in and consent-link checks (`isSafeUrl`, `consentSafe`) and is large. No Accessibility Reviewer, since the batch has no visible change.
- **Batch B1 review (Sonnet): `[HANDOFF:confirmed]`, no blocking issues.**
  - **Reviewer checks:** a normalised statement-level comparison showed leg 02 behaviour-free apart from the recorded boundary shifts and leg 01's clears; the frame order and sign-in checks are intact; the static tests keep their strength; the bookkeeping is consistent; the capture-tool refusals are intact. The guard set passed 443 tests, and `chats-transcript` passed 41.
  - **Non-blocking:** the three squawks' sign-off sections stay empty until the flight's commit.
  - Legs 01 and 02 are `completed`, with checkpoint commit B1.
- **Leg 04 designed and tiered high** (six new library controls with update handles). Design review cycle 1 approved with changes, applied as an amendments section:
  - the composer's send semantics: busy Enter holds, empty sends, never clears, `blocked || busy`;
  - exact streaming primitives;
  - old-look defaults with options for B3 and B5;
  - the missing variants (`--api`, tool in trace, markdown descendants);
  - thinking composing the message;
  - telemetry thresholds as a function, and `update` keeping the server shape;
  - caller-only testids;
  - parity-test hygiene;
  - a provisional 300 s `contracts-chat` budget (never from a solo run).

  Because the amendments are substantive, **a second cycle runs when batch B2 lands**, against the landed library.
- **Leg 03a landed** (`[LAND:leg]`). The allowance went from 25 rows / 36 uses to 21 / 30. The three consumer tests and 12 flash contract cases were seen failing first, as was the CSS-layer test.
  - The two A14 string tests are new assertions that were not run against the old code. The FD accepts this: the leg required assertion, not failing first, for those strings.
  - Every lane, the guards (448) and the unit tier (7786 / 15) passed.
  - Leg 03b's Developer was spawned.
- **Leg 06 designed and tiered high** (the agent loop, the WebSocket protocol, connectors). Its design review approved with changes, all applied:
  - the connector line in a never-raising helper after the persist;
  - REST through a `turn_info` out-parameter;
  - `PROVIDER_TYPE_LABELS` beside `PROVIDER_TYPES`, with 0.2 narrowed to the reachable paths;
  - client finalize before the notice.

  The leg is `ready`; it starts after batch B3.
- **Leg 07 designed and tiered high** (a security surface). Its design review approved with changes, applied as amendments:
  - the inline context object, so autolinks are off in link labels; the nested link is real today and fixed;
  - an autolink never emits `#`;
  - strike is `~~` only;
  - the copy button through `liveEl`;
  - an 18px A1 cap;
  - an accessible B1 scroll region;
  - the missed test pins.

  The sibling `App.safeUrl` gap was logged as **squawk 0275** (deferred, outside the flight). The leg is `ready`.
- **Leg 08 designed and tiered high** (it moves a complex panel's reconcile and focus logic into the library). Its design review approved with changes, applied as amendments:
  - the row state machine owned by the control (busy, done, failure; held focus; Delete's revert);
  - the focus fallback order plus `onFocusLost`;
  - the live region kept as today;
  - compact density for the basic list;
  - the chips moved onto the control;
  - A17's exact sentence;
  - A13's percentage rule;
  - a split only if still over 800.

  The leg is `ready`.
- **Leg 03b landed** (`[LAND:leg]`). The allowance went from 21 rows / 30 uses to 8 / 14. 42 contract cases failed first. The captures across 25 surfaces × 4 differ only at A9's long-meta rows (and one MCP timestamp). `--parallel 3`: 1661 s, every lane passing after the Developer's own test bug was fixed (`test_flow_jump_to.py` re-ran 24 passed). Unit 7786 / 15.
  - **FD accepts both deviations:**
    - the picker field stays 34px, since its 40px rule was dead CSS and keeping it is no visible change. A real 40px field is a **debrief candidate**, not a squawk yet;
    - A9's flex values differ from the review's (`flex: 1 0 auto` overflowed a 200-character label), and a test covers the very long label.
  - **Note:** the leg's `shared` re-run covered only `test_flow_jump_to.py`. The batch B2 end runs `shared` whole.
  - Leg 03c's Developer was spawned.
- **Leg 03c landed** (`[LAND:leg]`). The squawk 0269 and 0270 contract tests were seen failing first.
  - **FD accepts the 0270 deviation:** after an empty save under a renamed key, the row is an ordinary empty secret cell, whose eye is normal (a new sensitive row has one). The stale hint was the defect, and it is fixed. The squawk's "Show button persists" clause described expected behaviour.
  - **Batch B2 whole-suite evidence:** `PARALLEL_RESULT rc=0 total=1573s lanes=15 failed=-` (the full `shared` lane included); unit 7786 / 15.
- **Batch B2 end (legs 03a-03c).**
  - **The deleted-selector grep:** each leg grepped and ran the owning lanes for the `chat.css` / `studio.css` rules it deleted, and the full run covers every lane.
  - **Reviewers spawned in parallel:** a **Sonnet** Reviewer (03c touches the key-value table's secret-cell hint handling, and the batch is broad) and an **Accessibility Reviewer** (Sonnet), since B2 has visible UI changes (A9, the chip remove button, the copy confirmation, sentence case and the flash region).
- **Batch B2 review: code Reviewer (Sonnet) and Accessibility Reviewer (Sonnet) both `[HANDOFF:confirmed]`, no blocking issues.**
  - **Code review:** the guard set passed (448); the D4 pin rewrites are deliberate contract changes; the 0269/0270 fixes touch no secret value or mask. Its nit (0269/0270 still `open`) is fixed: both are `in-progress` until the flight commit.
  - **Accessibility notes carried forward:**
    1. If a status toast replaces an error toast within a few hundred ms, the alert may not be announced. This is a risk of the operator's newest-replaces rule (ledger row 38) and goes on the **HAT walk**; a mitigation (an error holds until it has announced) is a fix-vs-feature call there.
    2. The new chip remove button is 22×22px, under WCAG 2.2's 24px target size. **Leg 05a's design** decides 24px (a ledger row) when the chips get their consumers.
    3. The truncated search-list meta has no `title` tooltip (a debrief candidate).
  - The re-announce-on-re-home and the toast-behind-modal notes are recorded and accepted as rare.
  - Legs 03a-03c are `completed`, with checkpoint commit B2.
- **Leg 04 design review, cycle 2** (Sonnet, against the landed B2 library): approve with changes, applied. The Outputs were rewritten to fold in the amendments; the Copy reply uses `copyButton` with one shared `liveEl` (FD answer); the script order, the trace not reusing `disclosure`, and the concrete lane bookkeeping. This was the final cycle. The leg is `ready`; batch B3 starts once 05a-05c are designed.
- **Legs 05a, 05b and 05c designed** (all tier high per the flight spec). Their Developer design reviews are deferred until leg 04 lands, so they check against the landed controls rather than the spec. A16 moved from 05c to 05b, since its badge is built in `chats-list.js`; 05b names it. The B2 accessibility note on the 22px chip remove button is decided in 05a: the library button becomes 24px (a ledger row).
- **Leg 04 landed** (`[LAND:leg]`). Six controls, 144 contract tests in `contracts-chat` (both engines), and the parity check green; no consumer or `chat.css` change.
  - **Ledger row 39 added:** the one intended parity difference, the tool message in a trace capped at the trace width.
  - The telemetry percentage stays non-mono, as drawn today (its old mono rule never matched); 05c may choose otherwise only as a ledger row.
  - Guards 487, unit 7805 / 15.
  - The design reviews of 05a, 05b and 05c were spawned in parallel, read-only, against the landed controls.
- **Design reviews for 05a and 05b: both approve with changes, applied as amendments.**
  - **05a:** an AC grep that could never pass (it collided with `ui-composer-*`); a cache-busting fixture pointing at the deleted file; the eight `sessionBannerEl` guards folded into one `computeBlocked()`; a persistent live banner; one-shot 0.1 focus.
    - **Small library additions:** `composer.fileInput`, a live queued slot, chip `labelHidden` / `truncate`, and the 24px remove button. Staged chips keep their names (FD answer).
  - **05b:** the delete label derived from the title, never read back (a second-click trap); the sign-in button keeping its `data-*` and class hooks; no new testid; the Discord badge test retargeted; unknown slugs title-cased.
  - Leg 05a's Developer was spawned. The 05c review is pending.
- **Leg 05c design review: approve with changes, applied as amendments.**
  - B2 anchored per iteration (no frame carries a message id; stream order with no anchor);
  - B9's trigger moved to the Stop click (the held message is gone by `cancelled`), Stop only;
  - A4's error from a closed-port provider, keeping the `"Agent error: "` prefix (now a recorded contract in leg 06);
  - F1 for a Stopped reply copies the received text;
  - 0.3 checks `status` plus a loaded store;
  - one `clearLog()` for DD11 4;
  - the parity test deleted first;
  - the labels "Thinking" and "Loading model";
  - a locator helper for about 55 role locators, with the `routing` and `shared` lanes added;
  - the `ui_capture.py` retargets;
  - an anchored AC grep.

  The leg is `ready`.
- **Leg 05a landed** (`[LAND:leg]`). The allowance went from 8 rows / 14 uses to 7 / 13; 10 failing-first cases were recorded; the captures match the ledger.
  - **FD accepts:** the `blocked || busy` Send fix could not be shown failing first (the old defect was latent: no real flow clears the banner while busy). It is pinned by the contract test and an area test (ledger row 41).
  - **Ledger row 42 added:** the short queued chip now hugs its text.
  - **A slip in the report:** it said the sinks were "unchanged at 5"; the FD checked, and `HTML_SINK_ALLOWANCE` is `{}` with `SINK_TOTAL = 0`.
  - **Flake:** one `test_flow_chat_list.py` delete-focus test failed once under concurrent load and passed in isolation and on the full lane. It is recorded; it recurs only if it reappears.
  - Unit 7805 / 15. Leg 05b's Developer was spawned.
- **Leg 05b landed** (`[LAND:leg]`). Chat sign-in and the Chats list delete are on the library; the chat area holds no ownership row.
  - **Sign-in:** "Sign-in needed" above a library primary button "Sign in to {server}" (keeps the `login-required-btn` class and `data-*` hooks, no new testid); `App.ui.consentLink` direct; the group keeps `_btn` / `_consentBlock` references (no class queries). **Squawk 0215:** `abandon()` calls `resetLoginGroups`; recorded in the squawk (in-progress, closes at the flight commit).
  - **Chats list:** `App.ui.confirm` with `onArmChange` (label derived from the row title passed into `onDelete`, MutationObserver gone); DD11 6 offline delete reverts the arm and flashes "Not connected, so the chat wasn't deleted. Try again in a moment."; A16 `App.chat.chatsList.platformName` (Discord, Telegram, Slack, Stub; unknown title-cased).
  - **Failing first (seen failing before the fix):** 0215 http-500 and network-error (POST held until the consent frame was injected; block still present), DD11 6 offline (no toast), A16 badge ("discord" vs "Discord"). The arming-label and online-no-toast tests passed already (regression pins, as the leg expected).
  - **Retargeted:** `test_oauth_modal_flow.py` strings ("Log in to" to "Sign in to", comments); `test_flow_chat_list.py` badge to "Discord".
  - **Allowance:** the 5 chat.js/sign-in.js rows and 3 MOVES entries deleted; `TOTAL_USES` down to `api:App.icon(` 1 and `api:App.showFlash(` 3 (markdown.js only, leg 07). `MOVES` is empty. Ledger rows 3, 16, 34, 35 confirmed.
  - **Docs:** CLAUDE.md "Honest sign-in", `agents.md` sign-in and Chats list notes. `start-a-chat.md` step 14 needed no change.
  - **Verification:** guards (ownership, consent-link static, ui_guards, tokens, a11y) 373 passed; lanes chats, chats-transcript, shared green (43 / 159 / 271 passed across the three); `make test-unit` 7805 passed, 15 skipped; ruff clean.
- **Legs 09a and 09b drafted** (`planning`), from DD14 and DD15. They go `ready` after batch B4 lands and their citations are re-run against that tree. Tiering: 09a is low-to-medium (deletions with no remaining callers, verified by grep, plus docs); 09b is a verification leg. Both get a design review at that point, since they depend on everything before them. The HAT leg (10) is written when it is next.
- **Leg 05b landed** (`[LAND:leg]`). The 0215 (both branches), DD11 6 and A16 tests were seen failing first; two regression pins passed before (expected).
  - **The allowance:** 5 rows removed, `MOVES` empty; `TOTAL_USES` now holds only `markdown.js`'s `api:App.icon(` 1 and `api:App.showFlash(` 3 (leg 07). The chat area holds no ownership row.
  - Unit 7805 / 15. Leg 05c's Developer was spawned.
- **Leg 05c landed** (`[LAND:leg]`). The full gate (the batch B3 end): unit 7810 / 15; `PARALLEL_RESULT rc=0 total=1795s lanes=16 failed=-`. Only `markdown.js`'s 2 rows (4 uses) remain in the allowance, for leg 07.
  - **FD notes:**
    - DD11 4, DD11 5 and 0.3 were shown failing behaviourally first; the other 15 new cases failed on missing selectors only (not behavioural evidence, accepted given the behavioural three and the leg's scope);
    - the `App.ui.message.visibilityStyles` addition is accepted (it keeps the area free of allowance rows, with no contract change);
    - the rich-chat surfaces grow about 22px per reply from Copy reply (row 30) and go on the HAT walk;
    - ledger row 43 was added.
  - **Untested, recorded:** a `refreshAfterTurn` re-join landing right after `cancelled`, and A18 checked through the rule rather than a real keyboard focus.
- **Batch B3 end (legs 04, 05a, 05b, 05c).** Reviewers were spawned in parallel: a **Sonnet** code Reviewer (the sign-in flow and consent-URL gating changed, and the batch is large) and an **Accessibility Reviewer** (Sonnet).
- **Batch B3 reviews, first pass.**
  - **Accessibility Reviewer:** `[HANDOFF:confirmed]`, no blocking issues, with three non-blocking findings the FD takes into the fix pass:
    1. focus falls to `body` after a chip removes itself (`attachments.js`, `hold-queue.js`);
    2. the queued slot is unhidden in the same step its chip is inserted, which can defeat its live region;
    3. the spinner glyphs are not `aria-hidden`.
  - **Code Reviewer:** `[HANDOFF:confirmed]`, but self-described as a spot-check that left the sign-in security gating, the transcript behaviour, locator fidelity and the lane bookkeeping unverified. **The FD did not accept a spot-check for the largest batch with a security-sensitive path,** and sent the same Reviewer back (`SendMessage`) to verify those areas explicitly. Its stale-comment findings (references to the deleted renderer files) go into the fix pass.
- **Batch B3 code review, deepened pass (Sonnet, the same Reviewer): `[HANDOFF:confirmed]`.**
  - **Verified explicitly:**
    - the sign-in security gating, unchanged apart from the alias rename (`test_oauth_modal_flow.py`: 20 passed);
    - the transcript behaviours: F1 source, B2 anchor, B9, DD11 4, DD11 5 and 0.3 (`test_flow_chat_transcript_library.py`: 18; `test_flow_streaming.py`: 2);
    - the retarget fidelity across about 15 files (no weakened assertion; the deliberate changes match the ledger);
    - the offline delete;
    - the `contracts-chat` bookkeeping.
  - **Its question answered by the FD:** B9's "Stopped." in a tab that did not click Stop (a Stop from another tab) is intended, as leg 05c specified.
  - **A fix pass was spawned** for the three accessibility findings, the stale comment references to deleted files, and CLAUDE.md's `--lane` selector list. Per the F5 debrief's rule, it runs the unit tier plus its owning lanes.
- **Batch B3 fix pass verified.**
  - The FD re-ran the static guards after the pass's final edits: 471 passed.
  - The Accessibility Reviewer re-reviewed its three findings: `[HANDOFF:confirmed]`, all fixed.
  - The fix pass's own run: `contracts-chat` 146, `chats-transcript` 63, `chats` 159, unit 7810 / 15.
  - Legs 04, 05a, 05b and 05c are `completed`, with checkpoint commit B3.
- **Leg 06 landed** (`[LAND:leg]`). The flag lifecycle (13 tests), the web frame and REST key, the connector line (after the persist, never raising), the CLI line and 0.2's wording are in. The 0.2 audit found only the two known probes, so no divert.
  - The core, web, 0.2 and browser tests were seen failing first; the connector and CLI tests were not (written alongside), which the FD accepts given the batch review to come.
  - No eval run was needed (no platform prompt text changed; the notice never reaches the model).
  - Unit 7842 / 15. Leg 07's Developer was spawned.
- **Leg 07 landed** (`[LAND:leg]`). Against the untouched renderer, 27 negative and feature tests failed first (the link escape, the fence class, the nested link and `` [`]`](u) `` among them); the attribute-injection and encoded-scheme cases passed as regression guards.
  - **`OWNERSHIP_ALLOWANCE` and `TOTAL_USES` are now `{}`:** the mission's reuse-check exception list is empty.
  - Ledger rows 44 (the code-copy button's size and look) and 45 (the task checkbox, the table region) were added.
  - The leg ran no captures (leg 09b's after set covers them).
  - Unit 7845 / 12 (run outside netns).
  - Leg 08's Developer was spawned.

- **Leg 08 landed** (`[LAND:leg]`). `App.ui.modelList` (`js/ui/model-list.js`) replaces the hand-built rows of both provider model panels.
  - **Control API as built:** `modelList({label, testid, rowTestid, density: 'compact', actions: ['unload','load','delete'], confirmLabel, onAction(name, action), onFocusLost})` returns `{el, reconcile(sections), setRowBusy(name, action | 'done' | null), setRowError(name, msg | null), focusRow(name), destroy()}`; static `modelList.capabilityChips(caps)` (`App.studio.renderCapabilityChips` is deleted; `agent-model-picker.js` calls the control's). The control owns the row state machine: a click records held focus, sets the row busy and calls `onAction`; `'done'` ends on the next reconcile; `null` is the failure path (label restored, an armed Delete reverted through the stored `revert`, focus returned); an armed Delete survives a reconcile on the same node and is disarmed when it hides. Focus order: the focused control, the row's first action (Unload, Load, Delete), the next row's, the previous row's, `onFocusLost`. Rows carry `data-name`, `data-section` and a `title`. Owned classes: `ui-model-list`, `--compact`, `ui-model-section-label`, `ui-model-row`, `ui-model-name`, `ui-model-caps`, `ui-model-size`, `ui-model-actions`, `ui-model-led`, `ui-model-error`, `cap-chip-row`.
  - **Area:** the loading, error and empty lines and the control's list sit in `div.provider-models-region[aria-live=polite]` (renamed from `admin-pf-models-list`); fetch, Pull, VRAM and the size confirm stay in `provider-models.js`. A10 mono (compact density keeps the old look), A11 VRAM plain text (the span and rule dropped), A12 "Use Pull to download one.", A13 "Pulling {model}… {pct}%" (floor, 0% first, never the raw status), A17 "Each of your Agents chooses one of these in its Model section." edited in place.
  - **Split decision:** none. `provider-models.js` 996 -> 719 lines (its `test_area_module_size.py` entry removed); `provider-editor.js` 895 (ceiling 896 kept); `model-list.js` is a `js/ui` file.
  - **Failing first:** the contract file's WebKit run failed `test_focus_stays_on_load_then_moves_to_unload_as_the_row_runs` (WebKit keeps a hidden button as the active element, so the early return skipped the move); fixed by testing the button's usability before the identity check. The A10-A13 and A17 assertions were written against the visible differences (the old text, accent and sans font) but not run against a stash: the area files changed together with the retargeted selectors, so the old code could not satisfy them either way. The FD should note that.
  - **Retargets:** `admin-pf-model-row|item` -> `.ui-model-row`, `admin-pf-section-label` -> `.ui-model-section-label`, `admin-pf-models-list` -> `.provider-models-region` in `test_flow_provider_models_patch.py` and `test_flow_provider_visible_fixes.py` (the cursor assertion now reads `.ui-model-row`); `scripts/ui_capture.py` waits on `.ui-model-row`; `tests/behavior/system-provider-config.md` step 5 names the new sentence. `test_ui_editor_contract.py` needed none. New assertions: A10, A11, A12, A13, A17. The providers files run together: 65 passed. New `test_ui_model_list_contract.py` (32 cases, Chromium and WebKit; lane `contracts-controls`).
  - **Captures** (`$HOME/.cache/the-one-ui-capture/m31-f6-l08-after` against `m31-f6-before`, PIL threshold 8, 3 surfaces x light/dark x 1280/1024): all 12 differ, only where a row says so: `ollama-models-panel` (the VRAM text, row 11), `ollama-pull-progress` (the intro sentence, row 17; the progress text "Pulling llama3.2:1b… 42%", row 13; the VRAM text, row 11; plus the label changes of earlier legs in the same editor), `provider-models-generic` (the intro sentence, row 17; mono names, row 10). Row geometry is unchanged.
  - **Ledger:** rows 10-13 and 17 confirmed; row 46 added (the id tooltip).
- **Leg 08 landed** (`[LAND:leg]`). `App.ui.modelList` has 32 contract cases in both engines; `provider-models.js` went from 996 to 719 lines (no split; its line-guard entry removed). Ledger row 46 added (the model-id tooltip).
  - **The batch B4 whole-suite evidence:** `PARALLEL_RESULT rc=0 total=1640s lanes=16 failed=-`; unit 7845 / 15 (netns).
  - A10-A13 and A17 were not stash-tested; the FD accepts this, since the retargeted selectors could not pass on the old code either way.
- **Batch B4 end (legs 06, 07, 08).** Reviewers were spawned in parallel:
  - a **Sonnet** code Reviewer (the agent loop, the WebSocket protocol, connectors, markdown link security), briefed up front for a **full** verification of the security- and protocol-critical paths, not a spot-check (the B3 lesson);
  - an **Accessibility Reviewer** (the step-limit notice, the markdown task lists and table region, the code-copy button, the model list's focus and live region).
- **Batch B4 reviews.**
  - **Code Reviewer (Sonnet):** `[HANDOFF:confirmed]`, a **full** verification with no issues. It covered the flag lifecycle (core.py), the frame placement and broadcast-only send (app.py), the connector line after the persist (never raising), the `safeHref` / fence / autolink rules, no weakened boundary case (the `:948` pin is stricter), the model list's state machine, and the empty allowances. Its runs: the leg 06 set 122, guards 474, `test_markdown.py` 181, the model-list contract 32 (both engines), the provider flows 25, the transcript library 21.
  - **Accessibility Reviewer:** `[HANDOFF:confirmed]`. Two notes went to a fix pass: (1) the code-block copy status inside the `role=log` may double-announce, so it moves to the shared copy live node through a `render(text, {copyLiveEl})` option; (2) the model-row actions are named with the model. Three more are **debrief candidates**: truncated names only in `title`, no list semantics on the model rows, and table regions all named "Table".

- **Batch B4 review fixes.**
  - **Item 1 (WCAG 4.1.3):** `App.markdown.render(text, {copyLiveEl})` takes an optional shared live node; `renderCodeBlock` hands it to the copy button and makes no per-block `role=status` span (without the option the span stays, so callers outside chat are unchanged). Every chat render call (commit, finalize, replay) passes `ctx.copyLiveEl` through `mdOpts()` in `transcript.js`. Tests: `test_markdown.py` (span without the option, none with it), `test_flow_chat_transcript_library.py` (live and replayed code-copy writes "Copied" to `chat-copy-status` outside `.messages`, no `role=status` inside it), and `test_flow_markdown_chat.py` retargeted to the shared node.
  - **Item 2 (WCAG 2.4.6 / 4.1.2):** `js/ui/model-list.js` row actions carry `aria-label` "{Label} {model}" ("Load a", "Unload a", "Delete a"); armed "Confirm delete? a" (through `onArmChange`, and reset in `disarm`), busy "Deleting… a". Contract test `test_row_actions_are_named_for_their_model` (both engines). The provider flows needed no change (name matching is by substring).
  - **Debrief candidates (recorded only):** (3) truncated model names expose the full name only through `title`; (4) the model rows lack list semantics; (5) markdown table regions are all named "Table".
  - **Evidence:** static guards 470 passed; lanes shared 333, chats-transcript 67, providers 138, contracts-controls 1036 (4 skipped), contracts-chat 146; unit 7845 passed / 15 skipped (netns); ruff clean. No ledger row (accessible names are not visible).
- **Batch B4 fix pass verified.** Its run: guards 470, `shared` 333, `chats-transcript` 67, `providers` 138, `contracts-controls` 1036 / 4 skipped, `contracts-chat` 146, unit 7845 / 15. The Accessibility Reviewer re-reviewed both fixes: `[HANDOFF:confirmed]`. Legs 06, 07 and 08 are `completed`, with checkpoint commit B4.

---

## Session Notes
