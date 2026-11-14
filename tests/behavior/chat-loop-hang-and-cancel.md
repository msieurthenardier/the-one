# Behavior Test: Chat-loop hang-proofing, interrupt, and queued send

**Slug**: `chat-loop-hang-and-cancel`
**Status**: draft
**Created**: 2026-06-21
**Last Run**: never
**Updated**: 2026-11-14 (sortie 16: steps 2-4 read the turn's work line (`turn-work`: "Working", "Work · N tool calls", "Stopped") instead of the "Thinking…" indicator and streamed text); 2026-10-27 (M31 F6 L05c: step 2's indicator reads "Thinking…"; step 4's cancelled indication is the muted "Stopped." line); 2026-10-05 (M25 F4 leg 8: step 1 starts the chat through New chat and the agent picker, as a pending chat)

## Intent
Verifies the three operator-facing guarantees added by Flight 07: (1) a chat turn
that fetches a continuous-stream URL via the web tools **terminates** instead of
hanging indefinitely; (2) the operator can **interrupt** an in-flight turn and the
UI recovers with partial output preserved; (3) the operator can **queue one
message** while a turn is running. These are real-environment behaviors spanning the
WebSocket protocol, the hand-rolled agent loop, the web tools, and the Chat UI —
they cannot be observed by unit tests, which is why the Witnessed paradigm fits:
the hang and the recovery are only visible by driving a live chat to completion and
watching the UI/event stream.

## Preconditions
- A dev instance of the-one is serving on `http://localhost:8485` with the Flight-07
  changes applied.
- An agent exists that has the web tools enabled (e.g. `sonnet-loop-test`:
  claude-sonnet-4-6 + `http_request`/`fetch_url`), and its provider key is valid.
- Outbound network is reachable (the stream URL must actually connect).
- `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS` is at its default (120) or a known value.

## Observables Required
- browser (Chat UI state: the turn's work line (`turn-work`) and its state, the stop control, the
  queued-message pending indicator, input enabled/disabled — measured via
  chrome-devtools).
- http/ws (optional cross-check: the WS event stream — `done` / `cancelled` events —
  measured via a shell WS client if browser observation is ambiguous).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open browser to `http://localhost:8485`. On Chats, start a new chat with the web-tool agent (e.g. `sonnet-loop-test`): click the Chats list's **New chat** (`chats-new-btn`), type the agent's name in the agent picker's search (`agent-picker-search`), and press Enter. | A pending new chat with that agent: the chat header (`chat-header`) reads "New chat" with "with {agent}"; the message box (`chat-input`) is enabled. Step 2's first send creates the session. |
| 2 | Send: "Use http_request to GET `https://stream.radioparadise.com/aac-320` and tell me exactly what the tool returned." | A work line (`turn-work`, `data-state="working"`) reading "Working" with its dots appears under the sent message; a stop control is visible while the turn runs. |
| 3 | (Wait point) | Within 150s the turn **completes** (the work line leaves "Working": it reads "Work · N tool calls" with a chevron, collapsed, and a final assistant message renders after it as one bubble). The tool returns a bounded result — a media-content short-circuit message (e.g. "looks like a media stream") or a cap/timeout error — **not** an indefinite hang and not a frozen UI. |
| 4 | Send a message that triggers a longer turn (e.g. "Search the web and fetch three pages about internet radio formats, then summarize."). While it is still running, click the **stop/interrupt** control. | The turn aborts promptly; the work line reads "Stopped" (`data-state="stopped"`, with its tool-call count) and no reply bubble is built, and a muted **"Stopped."** line (`chat-stopped`) follows the group (and "Queued message discarded." (`chat-discarded`) as well if a message was held when Stop was clicked; neither line survives a reload); the input is re-enabled; the partial output is preserved, not erased: expanding the work line shows the text the turn had written so far as narration (after a reload the same turn renders as a finished one, its last text as a reply bubble). |
| 5 | Send message A ("Count slowly from 1 to 20."). While A is still running, send message B ("Now say the alphabet."). | B is accepted while A runs and shown as a **queued** chip (input not silently dropped). A completes first, then B runs and completes. The conversation shows A's answer then B's answer in order. |
| 6 | While A is running, send B and then a third message C ("Name three colours."). | Both are held as chips in send order ("Queued" lead, each with its own cancel). A completes, then B runs, then C runs; the conversation shows the answers in order and each message is sent only when the previous turn ends. (The queue holds up to 10; an eleventh Send stays in the message box with a "Queue is full (10)" note.) |

**Row conventions:** rows 1 and (the send half of) 5 are setup; the judged
checkpoints are 3 (no-hang), 4 (interrupt + partial preserved), 5 (one queued runs
after), 6 (several queued run in order, one per turn).

## Out of Scope
- The web_search backend configuration ("No results found" on the installed
  instance) — tracked separately as a Flight-07 open question.
- Provider-specific tool-call recovery (covered by M16 F03's gemma behavior tests).
- Sonos MCP playback correctness — this test uses the generic web-tool agent to keep
  the hang/cancel/queue behavior provider- and MCP-agnostic.

## Variants (optional)
- Run step 2-3 against a ministral-3:8b web-tool agent to confirm the no-hang
  guarantee is provider-agnostic.
