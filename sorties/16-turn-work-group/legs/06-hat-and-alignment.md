# Leg: hat-and-alignment

**Status**: completed
**Flight**: [One work line per chat turn](../flight.md)

## Objective
The operator walks the new turn shape on a dev instance with real models, one step at a time, and the Flight Director fixes what they find until they sign off.

## Context
- An interactive leg: no autonomous implementation. The Flight Director presents one step, waits for the operator's result, and moves on. A failure is diagnosed and fixed (a Developer does any code change) and that step is walked again.
- Fix or feature: a look-and-feel fix rides inline. A request that adds behaviour is a feature and gets a scoped design review first; the Flight Director makes that call out loud. A fix that spans more than one surface gets a short Developer design pass before it is implemented.
- The contract the tests and behavior specs read is flight DD11 (the testids `turn-work`, `turn-work-preview`, `data-state`, and the kept notice ids). A HAT change to it is a spec re-author, not an inline fix.
- Things the flight deliberately flagged for the operator's judgement here:
  1. The app's spinner stands in for the mockup's three dots.
  2. The preview follows the **latest** text (the mockup clipped from the start).
  3. With the group open while a turn runs, the newest narration shows as plain source until the next text arrives (DD4).
  4. After a chart or widget block nested in a quote or list, the rest of that pass's preview shows only the phrase (deliberate over-hiding).
  5. While the socket is down the work line keeps its dots until the re-join (today the "Thinking" line is dropped at once).
  6. The "Resuming…" line after a sign-in sits below the group while the resumed work lands inside it.
  7. Known, out of scope (pre-existing): a second window that is only watching can still send mid-turn.

## Inputs
- Commit `122158bf` on `sortie/16-turn-work-group`; draft PR #371.
- The HAT instance (set up 2026-11-14, serving the branch from the repo's venv):
  - port **8487**, data directory `~/the-one-hat-sortie16/data`, working directory `~/the-one-hat-sortie16/cwd`, PID in `~/the-one-hat-sortie16/cwd/serve.pid`, log `serve.log` beside it;
  - `THE_ONE_DEV_MODE=true`, `THE_ONE_STUB_TEST_ENDPOINT=1`;
  - never port 8484 or 8485, never the default data directory (`~/.local/share/the-one`).
- Seeded: provider "Local Ollama" (the host's Ollama); agents **Researcher** (`gpt-oss:20b`, tools, emits thinking), **Quick** (`qwen3:4b-instruct`), **Step limit** (mock: a tool call every pass, limit 3), **Plain** (mock: a streamed reply, no tools); a stub connector whose default agent is Quick.
- Not seeded, and each needs the operator: a Claude provider (their plan token or sign-in), if they want to see it on Claude; an MCP server that asks for an OAuth sign-in (step 7).
- A static-file edit under `static/js` or `static/css` is live on the next page load (dev mode rebuilds `index.html` per request); no restart is needed for JS or CSS.

## Steps
Each step names the state change and what must and must not be on screen.

1. **[idle] → [working]** — Researcher, a prompt that needs several tools.
   - One "Working" line with the spinner; the count rises; the running tool's name shows; a muted preview moves under the line.
   - No reply bubble yet. No error line. Stop is shown, Send is disabled.
2. **[working] → [done]**
   - The reply lands whole as one bubble; the line reads "Work · N tool calls"; the preview is gone.
   - Exactly one reply bubble. Copy copies the reply only.
3. **[done] → [expanded] → [collapsed]**
   - Thinking, narration and tool rows in order. Then, on a second turn, open the group **while it runs**: the newest narration is plain source until the next text arrives. Acceptable?
4. **[done] → [reloaded]**
   - The same shape after a reload. No duplicate group, no second reply.
5. **[working] → [stopped]** — Stop mid-pass.
   - "Stopped · N", the partial text inside the group, "Stopped." below, no reply bubble.
6. **[working] → [step limit] → Continue** — the Step limit agent.
   - "Paused at the step limit · 3 tool calls", the notice with Continue; Continue starts a new turn with its own group.
7. **[working] → [sign-in] → [working]** — needs an OAuth MCP server; skipped by agreement if none is at hand.
   - The sign-in block sits after the group, never inside it; after signing in the same group continues and the turn ends with one reply.
8. **Other shapes** — the Plain agent (no work line at all); a thinking-only turn; a chart and a widget in a reply (they draw when the reply lands; while they stream the preview reads "Drawing a chart" / "Building a widget").
9. **Shared state** — a connector chat (inject a stub message; the group carries "Operator only"), and the same chat open in a second window: both show the same shape.
10. **Both themes**, and the desktop webview if the operator wants it.

## Acceptance Criteria
- [x] Each step walked, or skipped by the operator's explicit choice, with the result recorded in the flight log. (Steps 1 to 6, 8A, 8B, 9A, 9B and 10 pass. Step 7 skipped by the operator. Step 8C could not be walked: no available model thinks. The desktop webview was not walked, by the operator's choice.)
- [x] Every failure fixed and its step walked again, or logged as a squawk or a follow-up with the operator's agreement. (Two fixes: the chevron while working, and the indicator redrawn as CSS dots after a glyph could not be aligned; the operator accepted both on their own browser. Squawk 0361 logged for a problem outside the flight.)
- [ ] The seven judgement items above each have the operator's answer recorded. **Partly.** Answered: 1 (the indicator: the mockup's dots, accepted), 2 (the preview follows the latest text: no objection), 3 (plain newest narration: "acceptable"), 4 (the phrase after a nested block: no objection at step 8B, which used top-level blocks only). Not answered, because the step was not walked or the case was not exercised: 5 (the dots while the socket is down), 6 (the "Resuming…" line), 7 (the second-window send, known and out of scope).
- [x] After any code change: the unit tier and the owning lanes pass before the HAT's commit. (Unit 10137 passed, 15 skipped; `contracts-chat` 330, `chats-transcript` 152, `chats-widgets` 32, `chats` 176, `shared` 364.)
- [x] The operator signs off. ("signed off", 2026-11-14, with the unwalked items listed to them as open.)

## Verification Steps
- The operator's own observation at each step, relayed to the Flight Director.
- For a fix: the Developer's falsified test, `THE_ONE_TEST_NETNS=1 make test-unit`, and the owning browser lane of every file touched.

## Teardown
- Stop the instance by its recorded PID: `kill $(cat ~/the-one-hat-sortie16/cwd/serve.pid)`.
- The scratch directory `~/the-one-hat-sortie16` and the captures in `~/the-one-capture-sortie16` are outside the repo and are the operator's to delete.

## Citation Audit
- `CLAUDE.md` "Behavior-test credential convention" - a dev instance uses a non-default port and a scratch data directory together, is started from a scratch working directory, and a browser signs in through `POST /api/session/handoff` - followed for the instance above
- `the_one/config.py::settings.data_dir` - printed `~/.local/share/the-one` on this host; the HAT instance's own `/proc/<pid>/environ` shows `THE_ONE_DATA_DIR=~/the-one-hat-sortie16/data` and `THE_ONE_PORT=8487` - verified 2026-11-14

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
