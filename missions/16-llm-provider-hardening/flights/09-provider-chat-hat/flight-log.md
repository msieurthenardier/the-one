# Flight Log: Human Acceptance Testing — Provider Chat Sweep

**Flight**: [HAT — Provider Chat Sweep](./flight.md)

> Running ledger of HAT findings. One entry per defect/rough-edge observed while
> exercising chat on the installed app. Capture enough to act:
>
> - **Provider / model** (verify the model id is live before relying on it)
> - **Version/commit under test** (installed app build)
> - **Repro** (steps)
> - **Observed vs. expected**
> - **Evidence** (screenshot, log excerpt, WS frame — anonymize paths)
> - **Disposition** (DD4): leg `{NN}-{slug}` here / spun-out flight / mission Known Issue

## Environment Under Test
- App: installed GleepGlorp app (web UI `http://localhost:8484` or desktop `the-one app`)
- Baseline version: 0.2.9 (record actual commit per session)
- Providers in scope: Anthropic, Ollama (native `/api/chat`), OpenRouter

---

## Findings

### F09-03 — "Stop" during a queued state cancels the queued message, not the running turn

- **Version under test**: 0.2.10 (installed packaged app).
- **Feature**: F07 cancel/interrupt + F07 DD4 one-slot queue, interacting.
- **Repro (analysis-confirmed; live repro pending)**: Start a turn; while it runs, queue a
  second message; then click **Stop**. Expected: the running turn halts (DD4: "stop = stop
  everything"). Actual: the *queued* message's task is cancelled and the **running turn
  keeps going** to normal completion.
- **Root cause (backend)**: the WS receive loop is intentionally non-blocking
  (`app.py:2133-2139`), so a queued message is spawned as a task immediately and
  `_session_inflight[session.id] = task` (`app.py:2148`) **overwrites** the running turn's
  task with the queued task (which is merely blocked on `session_locks[session.id]`). The
  cancel action reads `_session_inflight.get(session.id)` (`app.py:2102`) → gets the
  **queued** task and cancels it; the running task (holding the lock) is untouched. The
  authors anticipated the overwrite for the done-callback (identity guard, `:2151-2153`)
  but the cancel action still targets the single latest task.
- **Fix (backend)**: track in-flight tasks **per session as a set**
  (`_session_inflight: dict[str, set[Task]]`); on a `cancel` action, cancel **every**
  not-done task for the session (running + queued) — matching DD4. Update the spawn site
  (add to set), the done-callback (discard from set, drop empty), and the cancel handler.
- **Disposition (DD4)**: folded into leg `02-queued-message-render` (operator: investigate
  now, fix if real). Backend change; pairs with the F09-02 frontend render fix.
- **Status**: diagnosed; fix pending. *(Bundled with F09-02 — both are send-while-thinking
  UX defects in the same chat surface; one leg, one 0.2.11 build.)*

### F09-02 — Queued (send-while-thinking) message never renders as a bubble in the live transcript

- **Version under test**: 0.2.10 (installed packaged app, `C:\Users\…\AppData\Local\the-one\the-one.db`).
- **Feature**: F07 DD4 one-slot "send while thinking" queue.
- **Repro**: While a turn is running, type + send a second message (it shows "<text>
  (queued)"). When the first turn finishes, the queued message is dequeued and the
  agent acts on it — but the operator's queued message **bubble never appears** in the
  conversation.
- **Observed**: Agent processes the queued message (its response appears), but the
  user's queued message text is gone from the live transcript.
- **Expected**: The queued message should appear as a normal user bubble, in order
  (after the first turn's response, before the queued turn's response).
- **Persistence is NOT affected.** `_save_session_to_db` (`app.py:1011-1029`) persists
  `session.agent.messages` **wholesale**, and `agent.step` appends BOTH the user message
  and the assistant response to that one list — so the user message cannot be lost from
  the DB while the response survives. Verified: every stored session in the live DB has
  clean, complete user/assistant message arrays. A reload re-renders the queued message
  from the DB; it is only missing from the **live** view. ("Lost in chat history" =
  lost from the live scrollback, not from storage.)
- **Root cause (frontend-only)**: `chat.js`
  - Normal send optimistically renders the user bubble (`addMsg('user', …)` `chat.js:782`).
  - Queued send renders only a "(queued)" indicator (`showPendingQueued` `chat.js:50-59`,
    called at `:776`), then `ws.send` (`:778`).
  - Backend broadcasts the user echo with `exclude=<sender ws>` for BOTH paths
    (`_process_and_broadcast` `app.py:1430`, via `_spawn_message_processing` `:462`), so
    the sender never receives its own message back.
  - On turn-1 `done`, the handler does `delete pendingQueuedMessages[sid]` +
    `clearPendingQueued()` (`chat.js:1234-1240`) — wiping the indicator **without** ever
    rendering the real bubble. Net: the queued message has no optimistic render and no
    echo-render → it disappears from the live view.
- **Fix (frontend-only)**: in the `done` handler, when a pending queued message exists,
  render it as a real user bubble (`addMsg('user', text, 'You')`) at dequeue time (correct
  order) and keep the session in-flight (re-arm `inFlightSessions` + `showThinking`,
  disable Send) since the queued turn is now starting. No backend / persistence change.
- **Related**: investigating the cancel interaction surfaced **F09-03** (Stop targets the
  queued task, not the running turn) — confirmed real, fixed in the same leg.
- **Disposition (DD4)**: in-flight leg `02-queued-message-render` (frontend render fix here
  + the F09-03 backend cancel-set fix).
- **Status**: diagnosed; fix pending.

---

### F09-01 — `search_tools` silently caps at 8 results; tools beyond the top 8 become invisible

- **Provider / model**: Ollama — `ministral-3:8b` (agent "Sonos Agent", provider config `ec0d0a56cbf0`).
- **Version under test**: 0.2.9 (installed app, `http://localhost:8484`).
- **MCP source**: Sonos (`e7c2e3106487`) — exposes **37 tools**, all enabled (no
  `enabled_tools`/`disabled_tools` restriction on the agent).
- **Repro**: In a Sonos Agent chat, ask it to change a speaker's volume ("turn the
  column on the kitchen down to 20"), then "isnt there a set_volume tool?" / "how many
  sonos tools do you have available?". Session `a15d1d79aa8f`.
- **Observed**: Agent reports exactly **8 tools** (`list_speakers`, `list_groups`,
  `refresh_speakers`, `now_playing`, `play_url`, `play_file`, `pause`, `resume`) and
  states there is **no `set_volume` tool** — then tries pause/resume workarounds.
- **Expected**: `set_volume` exists on the Sonos MCP server (verified via
  `/api/mcp-sources`), along with ~28 others the agent never saw (`mute`, `unmute`,
  `stop`, `next_track`, `previous_track`, `group`, `ungroup`, `partymode`, `say`,
  `dissolve_all_groups`, and the full `playlist_*` family).
- **Root cause**: Lazy tool-discovery protocol — the model is shown only
  `search_tools` + `continue` and must search to load tools
  (`the_one/agent/core.py` `_compute_visible_schemas`). `search_tools` hard-caps
  non-empty queries at **8** (`the_one/tools/_search_tools.py:51`
  `_MAX_SEARCH_RESULTS = 8`, applied at ~`:217`). With 37 candidate tools, ranking is
  token-overlap (`:135-143`) with ties broken by registration order, so a query like
  "volume"/"sonos" returns 8 tools and `set_volume` falls outside the cut and is
  **silently dropped**. The result carries **no truncation signal**, so the model
  concludes the tool does not exist. *(Mechanism is provider-agnostic — any agent on
  an MCP source with >8 tools is exposed — but surfaces hardest on small Ollama models
  that issue one narrow search and give up.)*
- **Evidence**: chrome-devtools snapshot of session `a15d1d79aa8f` (agent claims "8
  tools", no `set_volume`); `/api/mcp-sources` cache showing the 37-tool Sonos catalog
  incl. `set_volume`; code citations above.
- **Disposition (DD4)**: in-flight leg — fix in `the_one/tools/_search_tools.py`
  (+ possibly the `search_tools` result shape and core wiring). Contained to the
  tool-search mechanism; no `LLMProvider`-contract impact. → leg `01-search-tools-truncation`.
- **Resolved (2026-06-26, 0.2.10).** Live-verified on the installed 0.2.10 app: a Sonos
  Agent search now surfaces the full Sonos catalog incl. `set_volume` (was hidden at 8).
  **Operator decision — "leave it as is":** a query containing the server name (e.g.
  "sonos") returns all 32 Sonos tools, because the name-match guarantee is judged on the
  tool's **full prefixed name** (`mcp__Sonos__…`), so the server name is a substring of
  every tool. The focused alternative (match the short name → "8 of 32 + narrow-query
  signal") was offered and **declined**; the broad return is accepted behavior, not a
  bug. Do NOT "fix" the prefixed-name match without re-confirming — it is intentional as
  of this decision. The `set_volume`-by-name guarantee and the honest "N of M" signal
  remain in effect for queries that do not name the server.
- **Status**: ~~fix implemented~~ → **RESOLVED / leg landed→completed.** `_filter_candidates`
  returns the pre-cap total; name-token matches are guaranteed and ranked above
  description-only matches; truncated results report the honest "N of M" total + a
  recovery hint. Unit tests green (`tests/test_search_tools.py` 54/54 in `.venv`).
  **Pending live re-verify** — operator tests against the packaged installer, not the
  editable dev install, so this rides into release **0.2.10**: bump + fix committed on
  branch `fix/search-tools-truncation` → PR → merge to `main` → Concourse `the-one`
  pipeline (`ci` → `build-windows-installer`) publishes `the-one-setup-0.2.10.exe` to
  the MinIO `the-one-installers` bucket. Operator installs 0.2.10, then a fresh Sonos
  Agent chat must find & call `set_volume` to close F09-01 / the leg.
