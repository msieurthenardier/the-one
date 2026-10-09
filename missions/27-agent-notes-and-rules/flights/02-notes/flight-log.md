# Flight Log: Notes

**Flight**: [Notes](flight.md)

## Summary

Planned 2026-10-09 while the operator was away overnight (authorized to plan
and execute up to the mission HAT). The research was done during Flight 1. The
key finding is that the untrusted flag can be computed without touching the
frozen loop, from a per-turn context variable that callers set around
`agent.step` (DD5, DD6). That removes the mission's pre-declared split risk.

---

## Leg Progress

---

## Decisions

### Autonomous judgement calls (for HAT review)

- **DD1:** the notes table's columns, and the per-agent number counter on
  `agents`.
- **DD3:** the tool names `save_note`, `update_note` and `forget_note`. The
  tools are seeded into the baseline and are not built-ins, so they do not
  appear in either Built-in Tools surface.
- **DD6:** the trusted-tool set is the notes tools plus `search_tools`; every
  other tool is untrusted, fail-closed. Every connector-peer message counts as
  untrusted.
- **DD8:** limits of 400 characters per note, 4,000 characters in total, and 5
  writes per turn. Duplicate detection uses normalised exact match.
- **DD9:** the prompt wording, the `<saved_notes>` delimiters, and the
  "(unverified)" marker.
- **DD10:** layout and copy: the "Check this" badge; text editing in the tab
  only, while the drawer prunes.
- **DD11:** there is no operator create route.

---

## Deviations

---

## Anomalies

---

## Session Notes

### Flight Director Notes
- Flight 1's debrief is deferred until after the mission HAT, by Flight Director
  judgement while the operator is away. The debrief benefits from operator
  input.
- **Design review, cycle 1** (Architect, Opus): approve with changes, 2 high
  findings. All were applied by rewriting DD1-DD13 in place, since the flight
  is still in planning.
  - **High:**
    - Ollama tool-call ids repeat across turns, so the anchor search runs
      backwards and results are attributed by position (DD6).
    - Newline injection could forge a `[n]` line, so text is collapsed to one
      line at write, with case-insensitive delimiter neutralisation (DD8,
      DD9).
  - **Medium:**
    - the signature becomes `notes=None` (None means off), with
      `RenderedNote`;
    - `build_system_prompt` loads notes itself, so `next_turn` keeps them;
    - an execute-time switch re-check stops writes from already-built agents;
    - `continue` is trusted;
    - the origin label is the live title through a LEFT JOIN;
    - the tools bind to their `Agent` instead of a list reference.
  - **Low:**
    - `notes_next_number` stays out of `AgentConfig` and the upsert;
    - route order;
    - DD2 wording;
    - `peer_name is not None`;
    - fixes to behavior-spec steps 2 and 7 and its preconditions.
  - **Questions answered:**
    - a resumed turn gets a fresh write budget;
    - `forget_note` also refuses while notes are off;
    - a `next_turn` recompose showing earlier notes in an open conversation is
      accepted.
  - A second cycle is run because the changes are substantive.
- **Design review, cycle 2** (Architect, Opus): approve with changes. The
  cycle 1 fixes were confirmed, with no contradictions between DDs. Applied:
  - **Medium:** an agent `update_note` ORs the taint flag and merges sources,
    and the origin stays the creating conversation.
  - **Low:**
    - the "any rules above" wording;
    - `render_rules_block(notes_present=False)` by default;
    - `" ".join(text.split())` as the normalisation mechanism;
    - binding details (`agent = Agent(...)`, `bind_agent` on the notes class,
      an unbound tool fails closed, `agent_name` plumbing);
    - one shared fallback counter;
    - corrected set-site wording;
    - DD12 cases split out (restored clean versus tainted history, Ollama
      bare-name ids, the update-stays-flagged case, Unicode line separators);
    - `textContent`-only rendering.
  - **Open for the HAT:** whether the operator can clear a reviewed "Check
    this" flag (no such action is built).
  - The 2-cycle maximum is reached, the remaining changes are clarifications,
    and the flight is marked `ready`.
