# Leg: ingestion-and-vision-hat

**Status**: completed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Build a **minimal image-ingestion producer** — attach/paste an image in the chat,
it reaches the model as a `list[ContentBlock]` user turn — plus the
`content_to_text` event projection that hardens the two latent break sites the
recon found; then run a live **Anthropic vision HAT** (operator drops an image →
Claude answers about it). Own-image thumbnail rendering is a deferred follow-up.

## Context

- **Promoted from optional** (operator, 2026-07-09) — the operator wants to send an
  image and see vision work. Flight 12 L01–L07 landed the capability (wire-proven
  hermetically); L08 adds the producer + a live proof.
- **Recon (2026-07-09) mapped the send path** and found the producer touches exactly
  four spots + one shared fix:
  1. **Frontend** (`chat.js`): a paste (and/or file-attach) handler yielding
     `{data: base64, media_type}`, threaded into the `ws.send` payload as an
     `images` field. The composer is `chat.js:167` (`data-testid="chat-input"`);
     send is `performSend` (`chat.js:849-856`, currently `ws.send(JSON.stringify({
     message: text }))`). No file/paste handling exists today. Editing `chat.js`
     directly (no new JS file) avoids an `index.html` script-registration change.
  2. **WS handler** (`app.py`): the message branch reads `payload.get("message","")`
     (`app.py:2163`) and the `if not user_input: continue` guard (`app.py:2164`).
     When `images` present, build `content = [TextContent(text=user_input),
     *[ImageContent(**img) for img in images]]` and pass it as the `user_input`-shaped
     arg through `_spawn_message_processing`/`_process_and_broadcast` (widen their
     `user_input: str` hints to `str | list[ContentBlock]`); the guard becomes
     "text OR images present".
  3. **`Agent.step`** (`core.py:197`): widen the `user_input` type hint to
     `str | list[ContentBlock]` — **body unchanged**; `Message.user()` (`base.py`)
     is already polymorphic over the union, and `step` is the single choke point
     that appends `Message.user(user_input)` (`core.py:222`). Other callers
     (`_inbound.py:963`, `cli.py:75`, self-test) pass `str`, unaffected.
  4. **Event projection** (the shared fix): `content_to_text(msg.content)` (L03,
     `base.py`) at the **live-broadcast** site (`app.py:1444`,
     `user_event["content"] = user_input`) and the **replay** site
     (`codec.py:358`, `messages_to_ui_events` USER branch). This closes **two latent
     bugs** any image message would trigger:
     - **[high] JSON-serialization break on BOTH the live send AND replay/join**:
       `message_from_dict` decodes list content into `TextContent`/`ImageContent`
       dataclass instances; both `messages_to_ui_events` (replay) and the live
       `user_event` put them raw into `content`; both go through `ws.send_json` →
       stdlib `json.dumps` (no custom encoder) → `TypeError`. On **replay/join** it's
       unhandled → **kills the WS**. On the **live send** (`_send_to_session`,
       `app.py:1179`) it's swallowed by try/except that silently drops the sender's
       own socket as "dead" → the sender **desyncs from their own session on the very
       first image send** (never sees the assistant reply). So this bites immediately,
       not just on rejoin. (Review [low] correction to the recon framing.)
     - **[medium] title corruption**: `Session.add_event` (`app.py:405-409`) derives
       `session.title = event["content"][:50]`; on a list that slices to a **list**,
       silently persisted into the `str`-typed `ChatSession.title` (Pydantic
       `model_copy` doesn't revalidate) → corrupts the history sidebar.
     Projecting once at the `user_event` construction (before `add_event`) + at the
     codec replay site fixes both for free — reusing the established
     `content_to_text` pattern (already used at `_inference.py:135`, L03).
- **Persistence already safe** (L02 `message_to_dict` handles list content).
- **`/api/chat` REST endpoint inherits the fix free** — it shares
  `_process_and_broadcast` (`app.py:~1954`), so the projection at `:1444` covers it
  too; no extra touch-point.
- **Deferred (recorded)**: rendering the user's own image thumbnail in the bubble
  (the message shows text + an `[image]` indicator via `content_to_text`; Claude's
  reply is the proof). **Attach-while-a-turn-is-running** — the F09-04 one-slot hold
  queue (`pendingQueuedMessages`) holds only text; staging an image while busy is
  explicitly **out of scope** for L08 (disable/ignore attach while a turn runs, or
  defer). Documents/PDF. Multi-image UX polish.

## Prerequisites

- Live Anthropic API key; the Anthropic provider on a vision-capable model
  (`claude-sonnet-4-6`, the default — no vision feature-flag exists, it's implicit).
- Dev backend rebuilt from this branch: `make restart THE_ONE_PORT=8485` +
  `make verify-serving`; browser hard-refresh (JS is cached; `verify-serving` does
  NOT cover chat submodules — curl-verify the served `chat.js` contains the new
  handler).

## Acceptance Criteria (build)

- [x] **Frontend attach — a file-attach control is the PRIMARY mechanism** (review
      [high]): `chat.js` gains a hidden `<input type="file" accept="image/*">` + a
      trigger button in `.input-area`, reading the file via `FileReader.readAsDataURL`,
      stripping the `data:...;base64,` prefix → `{data, media_type}`. (A `paste`
      handler MAY be added too, but the file input is the one that's **testable via
      Playwright `set_input_files`** — see the test criterion.) When an image is
      staged, `performSend` includes `images: [{data, media_type}]` in the `ws.send`
      payload. Text-only sends are **unchanged** (no `images` key).
- [x] **WS handler builds list content**: when the payload carries `images`,
      `app.py` builds the content list; the empty-guard accepts text-OR-images; type
      hints widened; text-only path byte-identical.
- [x] **Image-only (no text) MUST omit the empty `TextContent`** (review
      [medium-high]): when `user_input` is empty, build `[ImageContent(...), …]` with
      **no** `TextContent` (Anthropic 400s on an empty-text block —
      `"text content blocks must contain non-whitespace text"`). With text present,
      build `[TextContent(text), *ImageContent(...)]`. Hermetic test for both; a HAT
      step exercises image-with-no-text.
- [x] **`Agent.step` widened** to `str | list[ContentBlock]` (hint only; body
      unchanged); the plain-str callers still work.
- [x] **Event projection fixes both bugs**: `content_to_text` applied at
      `app.py:1444` (live) and `codec.py:358` (replay) — an image-bearing user turn
      no longer (a) crashes `json.dumps` on session join, nor (b) corrupts
      `session.title`. Tests assert a list-content user message projects to a string
      in both a `messages_to_ui_events` event and via the title-derivation path.
- [x] **Tests**: (a) **hermetic** — the `content_to_text` projection at both sites
      (a list-content `Message` → string `content` in a `messages_to_ui_events`
      event; `Session.add_event` title-derivation yields a `str`); the `app.py`
      content-building (text+images vs image-only) via a focused unit test on the
      builder. (b) **browser** — a real `tests/browser/test_flow_chat_image_attach.py`
      (the repo HAS a Playwright suite: `tests/browser/`, `make test-browser`, the
      `browser` marker + `SeededApp`/mock-provider fixtures — the recon missed it)
      driving the file input via `set_input_files`, asserting the `images` field
      reaches the (mock-provider) request and the user bubble renders text+`[image]`
      without a crash. **Functional/DOM assertions only — NOT a pixel snapshot**
      (snapshot baselines are gitignored, not committed).
- [x] **Scope**: `git diff --stat` = `chat.js`, `app.py`, `core.py`, `codec.py`
      (projection), + test files (+ flight artifacts). No provider/projection change
      (L04–L06 already done).
- [x] Targeted + regression green: the touched unit test files + the new
      `tests/browser/test_flow_chat_image_attach.py` (`make test-browser`, or the
      focused invocation), then `make test-unit` shows no regression.

## HAT (operator-guided, after build)

Run `/behavior-test`-style guided steps (FD presents one at a time):
1. **Backend currency**: `make restart THE_ONE_PORT=8485` from this branch; curl the
   served `chat.js` for the new handler; hard-refresh the browser.
2. **Attach path**: paste (or attach) an image into the chat composer — confirm the
   optimistic user bubble shows the text + an `[image]` indicator (not a crash / not
   `[object Object]`).
3. **Vision round-trip (with text)**: send "what is in this image?" with an image
   attached → **Claude's reply is grounded in the image content** (describes what's
   actually in it). This is the live vision proof.
4. **Image-only (no text)**: attach an image and send with an **empty** text box →
   the request goes out (no empty-text-block 400) and Claude still describes the
   image (exercises the omit-empty-`TextContent` path).
5. **Session rejoin**: reload / rejoin the session → it loads without a WS crash and
   the user turn renders as text + `[image]` (the replay-projection fix).
5. **Fix inline** any wire-format surprise (e.g. a media_type/base64 issue) — the A4
   HAT pattern.

## Edge Cases

- **Image with no text** → `user_input` empty; build `[ImageContent(...)]` (no
  `TextContent`) OR a minimal text block — decide at build (Anthropic accepts an
  image-only user turn; the empty-guard must allow it).
- **Non-image paste** → ignored (only `image/*` staged); normal text paste unaffected.
- **Large image** → base64 size; no client-side limit this leg (provider's own limit
  is the guard; note as a follow-up).
- **`content_to_text` for a multi-image turn** → `"text [image] [image]"` — sane
  indicator, deferred real rendering.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — paste/attach handler + payload.
- `the_one/interfaces/web/app.py` — image-message construction + hint widening +
  `content_to_text` at the live-broadcast site.
- `the_one/agent/core.py` — `step` type-hint widening.
- `the_one/db/codec.py` — `content_to_text` at the `messages_to_ui_events` USER site.
- Test files + a JS source-scan guard.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] Build acceptance criteria verified (hermetic + regression)
- [x] HAT steps 1–5 adjudicated (pass / fixed-inline / noted)
- [x] Update flight-log.md (Leg Progress + HAT run record + the two-bug-fix note)
- [x] Set this leg's status to `completed`
- [x] Check off this leg in flight.md
- [x] **Final leg** — after this: batch-review the L08 build, then it joins the
      flight's commit/PR (a follow-up commit on the same branch — no amend)
