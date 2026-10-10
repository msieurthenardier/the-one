# Behavior Test: Agent Rules Round Trip

**Slug**: `agent-rules-round-trip`
**Status**: draft
**Created**: 2026-10-09 (Mission 27 Flight 1)
**Updated**: 2026-10-10 (Mission 27 Flight 3 HAT: the panel is read-only and bulleted; step 4 is re-authored for the removed Edit rules link)
**Last Run**: 2026-10-10 (post-HAT re-run): pass, 9/9 ([run log](agent-rules-round-trip/runs/2026-10-10-21-05-09.md)). Earlier: 2026-10-09 pass, 9/9 ([run log](agent-rules-round-trip/runs/2026-10-09-22-40-11.md)).

## Intent

Verifies that operator-authored rules reach an agent's next build and change
what it does, in the app and in a connector conversation. It also checks that
disabled rules have no effect, that order is kept, and that rules follow an
agent through rename and delete.

Unit tests can prove the composer's output. They cannot prove that a newly
built agent in a running instance carries the rules, or that a real model obeys
them. No API returns a running agent's prompt, so this spec uses two independent
observables:

1. **The first reply of a fresh conversation, carrying a sentinel.** This is the
   adherence signal. The `agent-self-revision-propagation` run of 2026-08-25
   established that a sentinel is a reliable observable only on the **first turn
   of a fresh conversation**. Inside a conversation that already has turns, the
   model anchors on its own earlier replies. Never assert a sentinel change
   inside a conversation that already existed.
2. **The persisted session's system message.** This is the composition signal.
   Every web and connector session stores `agent.messages`, system message
   included, in `chat_sessions.messages` (a JSON list whose first element has
   `"role": "system"`). Read it with `sqlite3` from the scratch data directory's
   database. It shows rule order, disabled-rule absence and the base-prompt
   prefix without relying on the model.

## Preconditions

- A dev instance built from the flight branch, on a port of 8490 or higher (never
  8484 or 8485), with a **scratch data directory**. Start it with
  `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`. Follow CLAUDE.md
  "Behavior-test credential convention" for the credential and the browser
  handoff.
- The operator's local Ollama answers at `http://localhost:11434` with a
  tool-capable model (`gpt-oss:20b` or `qwen3:30b`). Re-check it with
  `curl -s localhost:11434/api/tags` before step 1.
- An `ollama` provider pointing at it exists in the scratch instance, and an
  agent `rules-probe` uses it, with:
  - persona: "You are a terse assistant.";
  - no rules;
  - notes off (Flight 2), if present.
- A stub connector `bt-stub` exists, with `default_agent` set to `rules-probe`
  and peer `peer-1` admitted. Set it up as `stub-connector-round-trip.md` steps
  1-4 do, with these changes:
  - select `rules-probe` where that spec selects `test-agent`;
  - keep **this** spec's port (8490 or higher), not the 8485 that spec names;
  - the peer-2 replay in its step 4 is optional.

  Pairing creates no session (`inbound.py:385-390`), so step 5 below is the
  first turn of a fresh conversation.
- A browser apparatus can reach the dev instance.
- The database path is `{data_dir}/the-one.db` (`config.py:107`).

## Observables Required

- **browser**: the Rules and notes tab, the chat transcript and the chat agent
  panel.
- **http**: `GET /api/agents/{name}/rules`, `GET /api/chat/sessions`, and the
  stub seam routes `POST /api/_test/stub/inbound` and
  `GET /api/_test/stub/outbound`.
- **shell**: `sqlite3 {data_dir}/<db> "SELECT messages FROM chat_sessions WHERE id='{SESSION}'"`,
  then parse the JSON and take element 0's `content`.

## Steps

Sentinels: `NAUTILUS` (rule A), `WOMBAT` (rule B, disabled), `MARLIN` (rule A
after its edit).

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | In the browser, open Agents, then `rules-probe`, then the rules tab (`tab-rules-and-notes`, labelled "Rules and notes", or "Rules" if Flight 1 took the width fallback). | The tab shows a **Rules** section with an empty state and an "Add rule" control. A line says changes apply to new and reopened chats, and to the next message in connector channels. No error is shown. |
| 2 | Add three rules in this order: A "Begin every reply with the single word NAUTILUS.", B "End every reply with the single word WOMBAT.", C "Keep every reply under 25 words." Turn B **off**. Move C to the top. Reload the page and reopen the tab. | After the reload the list reads C, A, B, top to bottom, with B shown off and A and C on. `GET /api/agents/rules-probe/rules` returns the same order (`position` ascending) with `enabled: false` only on B. No error is shown. |
| 3 | Start a **new** web chat with `rules-probe` (Chats, New chat, then pick it) and send "Say hello." Record the session id as `{WEB1}`. Read `{WEB1}`'s stored system message through the shell. | The reply's first word is `NAUTILUS`, and it does **not** end with `WOMBAT`. The stored system message starts with the base prompt: it begins "You are an AI agent with access to a set of tools". The persona appears after it, then a rules block with C as rule 1 and A as rule 2. The text `WOMBAT` does **not** appear anywhere in it. |
| 4 | With `{WEB1}` open, make sure the chat agent panel is open. It is open by default at 1280 px and wider, so click `chat-drawer-toggle` only if it is closed (clicking an open panel closes it). | The panel has a **Rules** group listing C then A as a bulleted list (no numbers), plus "1 off". The panel has **no** "Edit rules" link (removed in Mission 27 Flight 3). Its footer's **Open agent settings** is present. |
| 5 | Through the stub seam, inject a DM from `peer-1`: "Say hello." Poll the outbound records for up to 90 s. Find the resulting session (`DM: peer-1`), record its id as `{DM1}`, and read its stored system message. | One outbound reply arrives whose first word is `NAUTILUS`. `{DM1}`'s stored system message holds the same rules block as `{WEB1}`'s (C, then A, no `WOMBAT`). |
| 6 | Edit rule A to "Begin every reply with the single word MARLIN." Then start a **new** web chat with `rules-probe` and send "Say hello." Record it as `{WEB2}`. | `{WEB2}`'s reply begins with `MARLIN`, not `NAUTILUS`. Its stored system message contains `MARLIN` and not `NAUTILUS`. |
| 7 | Through the stub seam, inject another DM from `peer-1`: "Say hi again." Wait for the reply, then re-read `{DM1}`'s stored system message. | The stored system message now contains `MARLIN` and not `NAUTILUS`: the connector conversation was rebuilt for the next message. The reply's wording is **not** asserted, because the conversation already has turns. |
| 8 | Rename `rules-probe` to `rules-probe-2` through the General tab. Open the Rules and notes tab again. | The rename succeeds with no error. The tab lists the same three rules in the same order and states (C, A edited, B off). `GET /api/agents/rules-probe-2/rules` matches, and `GET /api/agents/rules-probe/rules` is 404. |
| 9 | Delete `rules-probe-2` from its General tab's Danger Zone. Then run `sqlite3 {db} "SELECT COUNT(*) FROM agent_rules WHERE agent_name IN ('rules-probe','rules-probe-2')"` and the same count on `agent_revisions`. | The delete succeeds. Both counts are `0`. |

## Out of Scope

- Notes, and the precedence of rules over notes. Flight 2 extends this spec or
  adds its own.
- Whether a conversation that was open during an edit changes its replies.
  Replies in an existing conversation are confounded by history anchoring (see
  Intent). Step 7 asserts the rebuild through the stored prompt instead.
- Renaming an agent that has self-configuration revision history. That is
  covered at unit level, because producing revisions needs a scripted
  self-revision.
- That no agent capability can write rules. No tool addresses rules, which is a
  unit-level assertion on the tool catalog.
