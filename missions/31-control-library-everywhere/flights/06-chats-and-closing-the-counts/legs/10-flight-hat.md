# Leg: flight-hat

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)
**Interactive**: yes (HAT; the operator verifies, the Flight Director guides one step at a time)

## Objective
The operator walks the flight's visible changes (Visible-Differences Ledger rows 1-46) and its two added features. The walk uses a seeded dev instance in both themes, at 1280 and 1024. It includes states the operator is not looking at: a connector chat that updates while another chat is open, and the step-limit line on the stub connector. Look-and-feel fixes found here ride inline. Anything that adds behaviour goes through the fix-vs-feature gate. The operator then approves the before and after captures.

## Context
- **Instance.** `scripts/ui_capture.py --keep-running` started a dedicated dev instance (port 56764, scratch data under `$HOME/.cache/the-one-ui-capture/20261027-225636-4051741/`; not 8484 or 8485, not the default data dir). The FD stops it by its PID, 4051743.
  - It holds the capture seed: providers, agents, the Library and Settings, and the chat seed with the rich, streaming, slow, broken and long-name agents and eight dated sessions.
  - `hat_seed.py` in the FD scratchpad added `limit-agent` (`max_iterations` 2, a mock that always calls `current_time`), `connector-agent`, and the stub connector `hat-stub` with `peer-1` admitted.
- **Ledger.** The flight log's "Visible-Differences Ledger", rows 1-46.
- **Watch items** carried in from leg 09b and the earlier batches:
  - the replacing toast is announced (newest replaces);
  - Copy reply adds about 22px to each reply;
  - a Stopped partial reply shows Copy;
  - the short queued chip (row 42);
  - "Tool activity · N" counts both the call and its result;
  - the "Agent created" toast lingered in the Dark run;
  - the Dark pending-row wash is faint.
- **Captures.** Before: `$HOME/.cache/the-one-ui-capture/m31-f6-before`. After: `.../m31-f6-after`, with `comparison.md`. They are never committed.

## Steps (state-transition sequences; the FD presents one at a time)
1. **[Chats list] → [picker] → [pending chat].** Rows 9, 32 and 27, plus the Discord badge (row 16).
2. **[Rich chat, settled].** Rows 1, 2, 44, 19, 45, 29, 33, 15, 20, 21, 22 and 30, plus the trace count and Copy reply watch items.
3. **[Live turn].** Streaming, then "Thinking…" (row 8), then Stop (row 24, Copy on the partial reply). A queued short and long message (rows 7 and 42) with remove (row 40). Staged images (rows 6 and 40).
4. **[Turn-end states].** An agent error (row 4). The unreachable OpenAI-compatible provider names its type (row 28). The deleted-agent chat: banner, blocked composer, Attach disabled (rows 5, 25 and 43).
5. **[Step limit, web] and [connector, unseen].** `limit-agent` in the web chat shows the notice and its settings link (row 31). With another chat open, the stub connector's inbound arrives: the Chats list updates, and the connector gets one neutral line. Opening that chat shows no notice.
6. **[Editors and toasts].** Sentence-case labels (row 26). "Agent saved" and toast replacement (rows 14, 37 and 38, plus the lingering-toast watch). The MCP Headers rename (row 36). The provider model lists and the Ollama panel (rows 10-13, 17 and 46).
7. **[Theme and width].** A walk of the main states in Dark and at 1024. Readability, the pending-row wash, focus rings.
8. **[Captures].** The operator reviews the before and after set and approves it.

## Acceptance Criteria
- [ ] Every ledger row the operator walked matches what it promised, or is fixed and re-verified.
- [ ] The unseen-state checks hold: the connector update while another chat is open, and the step-limit line on the connector.
- [ ] The operator approves the before and after captures.
- [ ] After any HAT code change, the affected lanes and the unit tier re-run green, and the close checks (counts, docs) still hold.

## Edge Cases
- Rows with no live trigger on this seed are confirmed by their tests and the captures; the FD says which ones when they come up. These are: 34 (offline delete), 35 (a failed sign-in start), 3 (sign-in needs an OAuth-backed MCP source), and 41 (latent).
- A HAT change to a behavior spec's contract (testids, routes, copy) is a deliberate spec re-author, not an inline edit.
