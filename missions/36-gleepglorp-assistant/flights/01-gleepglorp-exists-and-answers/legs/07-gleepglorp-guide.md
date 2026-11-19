# Leg: gleepglorp-guide

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Ship the app guide as plain help topics GleepGlorp looks up with
`get_app_guide(topic)`, packaged in every installer, with a drift test that
fails when the guide links to a page that no longer exists or breaks its own
format.

## Context
- Flight DD6 (the guide part), the mission's knowledge-sources and
  help-docs decisions (the guide is written for people too; in-app Help pages
  are a follow-on). Split from the planned Leg 6 (flight log).
- Design-review facts (the superseded `06-gleepglorp-guide-memory-web.md`):
  - Load the topics with `Path(__file__).parent / "guide"`, the pattern the
    existing bundled data uses (fonts, seeds), not `importlib.resources`,
    which depends on the frozen reader.
  - Package data: `pyproject.toml` ~:206; the three specs'
    `collect_data_files("the_one", includes=[...])`
    (`packaging/linux/the-one.spec` ~:63-67, `packaging/macos/the-one.spec`
    ~:81-85, `packaging/windows/the-one.spec` ~:156-204). The packaging test
    pattern `tests/test_chart_image.py` ~:96 regex is anchored to a
    one-element `includes` list: add a separate `collect_data_files` line per
    spec, or loosen the pattern.
  - The drift test needs parsers for the router's `SECTIONS` Library rows
    (`router.js` ~:87-102, `dest: 'library'`) as well as the settings rows
    `tests/test_settings_pages_static.py` ~:22-25 already parses, the agent
    tab ids in `TAB_ITEMS` (`studio/agent-editor.js` ~:42-49, `{ id: '...' }`),
    and explicit handling of `tools/{name}` and `~new`. Aliases that redirect:
    bare `#library/{group}`, bare `#settings`, `#settings/general…`,
    `#agents/{n}/mcps…`, bare `#chats/~new`, legacy `#chat`/`#studio`/`#admin`
    (`router.js` resolve ~:275-375).
  - `get_app_guide` joins `TRUSTED_TOOL_NAMES` (`agent/taint.py` ~:33): shipped
    text, so a note saved after a guide lookup is not flagged.

## Inputs
- Leg 6 landed (both touch the GleepGlorp build and its allowlist test).

## Outputs
- `the_one/gleepglorp/guide/*.md`, `the_one/gleepglorp/guide_tool.py`
  (`get_app_guide`), registered in the GleepGlorp build.
- One shared constant module for valid route patterns and aliases (used by the
  drift test now and the prompt check in Leg 8), for example
  `tests/_app_routes.py`.
- `tests/test_gleepglorp_guide.py` (tool, format, drift), the packaging test,
  package data in `pyproject.toml` and the three specs.

## Acceptance Criteria
- [ ] One markdown file per topic, each starting with `# Title` then a
      one-sentence summary paragraph, written as plain help text for a person
      (second person, sentence case, no internal names, no code paths, no
      testids), accurate to the app in this branch (written by reading the UI
      modules, the routes and CLAUDE.md, and checked against them). Topics at
      least: `overview` (the four destinations and what lives where),
      `agents`, `agent-tools` (built-in tools, overrides, MCP and knowledge
      attachments), `rules-and-notes`, `routines`, `self-configuration`,
      `mcp-servers` (local command vs HTTP, arguments one per row, headers and
      environment variables, sign-in, per-agent credentials, Test, Forget),
      `model-providers` (types, the two Claude plan sign-ins, Ollama and
      pulling models), `knowledge-bases`, `connectors`, `secrets`
      (`{{secret:key}}`, allowed tools, grants), `settings` (each Settings
      page), `gleepglorp` (what it can and cannot do, its settings). Each topic
      is at most 600 words.
- [ ] `get_app_guide(topic)` returns the topic's text; an unknown or empty
      topic returns the topic list with each summary; matching is exact,
      case-insensitive. The topic ids and a one-line purpose are in the tool
      description. No network, no write. It is in `TRUSTED_TOOL_NAMES`.
- [ ] The allowlist test's base set becomes `{search_tools, current_time,
      read_app_config, get_app_guide}` across every combination Leg 6 pins.
- [ ] The drift and format test fails, falsified with a planted case each,
      when: a guide link `](#…)` names a route the router does not serve, an
      alias that redirects, a Settings section missing from
      `settings-pages.js`, a Library group missing from the router `SECTIONS`,
      an agent tab not in `TAB_ITEMS`, or a guide topic id with no file; a
      topic lacks its `# Title` or summary; a topic exceeds 600 words; a topic
      contains an internal name (a code path like `the_one/`, a `testid`, a
      `.js`/`.py` file name).
- [ ] The guide files are package data in `pyproject.toml` and all three freeze
      specs; the packaging test fails if either is missing; `get_app_guide`
      lists the topics from the installed package layout (a test that loads
      through the same `Path(__file__)` path the tool uses).
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; ruff clean.
- [ ] Docs: CLAUDE.md (the guide, its drift test, and the project convention
      from the mission: a change to a page or form updates the guide in the
      same flight), `the_one/agents.md` ("GleepGlorp (M36)": the guide and its
      format rules).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_guide.py tests/test_gleepglorp_build.py <packaging test> -x --timeout 60`.
- Falsification report per planted case.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- A word count per topic, recorded in the flight log.

## Implementation Guidance
1. Write `tests/_app_routes.py` (route patterns and the alias list, built by
   parsing `router.js`, `settings-pages.js` and `agent-editor.js`) and the
   drift/format test first, against an empty guide.
2. Write the topics, one at a time, reading the relevant UI module and routes
   for each; keep each under 600 words; links only to routes that land on a
   page (`#library/mcp/~new`, `#settings/gleepglorp`, `#agents/~new`, …).
3. `guide_tool.py`: load with `Path(__file__).parent / "guide"`; register it
   in the GleepGlorp branch; add it to `TRUSTED_TOOL_NAMES`.
4. Package data and the packaging test.
5. Docs.

## Edge Cases
- **A topic that needs a per-item link** (an agent's Tools tab): describe the
  path in words ("open the agent, then its Tools tab") rather than a link with
  a placeholder name.
- **A future rename of a page**: the drift test is the alarm; the convention
  says the same flight updates the guide.

## Files Affected
- New: `the_one/gleepglorp/guide/*.md`, `the_one/gleepglorp/guide_tool.py`,
  `tests/_app_routes.py`, `tests/test_gleepglorp_guide.py`.
- Changed: `the_one/agent/taint.py`, `the_one/agent/factory.py`,
  `tests/test_gleepglorp_build.py`, `pyproject.toml`, the three
  `packaging/*/the-one.spec`, a packaging test, CLAUDE.md, `the_one/agents.md`.

## Citation Audit
See the superseded `06-gleepglorp-guide-memory-web.md` audit and its design
review in the flight log (router `SECTIONS` ~:87-102, `TAB_ITEMS` ~:42-49,
`test_settings_pages_static.py` ~:22-25, the specs and `test_chart_image.py`
~:96, the `Path(__file__)` pattern) - verified (review).
