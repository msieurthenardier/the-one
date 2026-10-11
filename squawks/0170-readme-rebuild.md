# Squawk 0170: README misdescribes the system and undersells it

**Status**: in-progress
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: —

## Report
`README.md` is the project's front door. It is inaccurate in places and flat
throughout.

- **Wrong frame.** It opens by calling the app "a personal AI agent". The app
  is not an agent. It is where you build, run and oversee many agents, each
  with its own model, instructions, tools, knowledge, rules and notes
  (operator, 2026-10-10).
- **Stale and overclaiming.** Mission 27's rules and notes are missing, and so
  is the Ctrl K palette. "Your data and settings stay on your machine" is not
  true of chats sent to a cloud model provider.
- **Undersold.** The distinctive parts get one equal-weight bullet each, or no
  mention at all: a Claude subscription by sign-in, box-by-default execution,
  local hybrid knowledge search, and agents that rewrite themselves only when
  allowed, with optional approval (off by default) and a revision log. Nothing says how the project was built.

The operator asked for an "extremely compelling" rebuild with creative
latitude. The direction is settled:
- reframe it as a workbench for your own agents;
- lead with what is distinctive;
- tell the build story: missions, flights, legs and squawks, flown by AI
  crews.

## Evidence
- `README.md:13` — "GleepGlorp AI is a personal AI agent that runs on your own computer."
- `README.md:13` — "Your data and settings stay on your machine."
- `README.md:15-24` — no rules or notes (CLAUDE.md "Rules and notes tab (M27 F1 L2)").
- `README.md:19` — an exact count ("22 tools") that goes stale whenever a tool is added.

## Corrective Action
The change is README-only.

`README.md` is rebuilt in reader order:
- the hero and the workbench frame;
- What it is: a diagram, plus a paragraph carrying the same content;
- Why it's different: seven verified facts;
- A tour of Chats, Agents, Library, Settings, Jump to and the desktop window;
- Install, Your first five minutes, Providers;
- Privacy and security, Accessibility;
- How it was built: the witnessed notes run, and a flight record of round-down
  floors;
- Developing.

It also corrects the old page in two ways:
- Since Mission 20, a browser that opens a bare `the-one serve` gets a 401. Install
  now leads with `the-one app`, which signs you in.
- It discloses the daily models.dev catalog download and the Ollama library read.

The operator made two changes mid-squawk (2026-10-10):
- No exact built-in tool count. The README says "20+" and describes the tools by
  family.
- The planned guard test, `tests/test_readme_claims.py`, was dropped as
  over-engineered.

## Verification
- No code changed, so no tests or linters ran.
- (a) A one-off shell check, not committed, resolved every relative link, image
  path and in-page anchor: 14 of 14 (3 anchors and 11 paths). External links were
  not checked.
- (b) Every factual claim in the README was checked against the code. The key
  sources: the sandbox factory, `tools/shell.py`, `knowledge/retrieval.py`,
  `self_configuration/surface.py`, `notes/tools.py`, `middleware.py::EXEMPT_PATHS`
  and `llm/model_catalog.py`. The flight-record floors were checked against
  on-disk counts: 27 missions, 150 flights, 790 legs and 170 squawks.
  The independent review caught and fixed four claims: Telegram history, default-enabled
  built-ins, the Linux GUI install, and `the-one chat`'s default agent.
- (c) `git -C <worktree> status --short` lists exactly ` M README.md` and
  `?? squawks/0170-readme-rebuild.md`.

## Sign-Off
*(written at completion)*
