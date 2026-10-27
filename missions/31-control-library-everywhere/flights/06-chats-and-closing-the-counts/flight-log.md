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
| 4 | 05c | Chat | An agent error is a danger-tone headline with the raw text under "Technical details" | A4 |
| 5 | 05a | Chat | The deleted-agent warning is the library warning banner | A5 |
| 6 | 05a | Composer | A staged image's remove is the library icon-only remove button | A6 |
| 7 | 05a | Composer | The queued message's cancel is a library icon button; the label is "Queued" | A7 |
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
| 23 | 05a | Chats empty state | The text column is centred under the mascot | B6 |
| 24 | 05c | Chat | After Stop: a muted "Stopped." line, plus "Queued message discarded." when one was held | B9 |
| 25 | 05a | Composer | Blocked: the box is dimmed with the disabled tokens, and Attach is disabled | B13, 0.3 |
| 26 | 03c | Agent and provider editors | Sentence-case labels ("LLM configuration", "System prompt", "Max iterations", "Context window", "Reasoning effort", "OpenAI-compatible", …) | D7 |
| 27 | 05a | Chat | After an agent pick, focus is in the message box | 0.1 |
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

---

## Session Notes
