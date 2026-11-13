# Squawk 0349: README out of date

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: 2026-11-13

## Report
The README has not kept pace with features shipped since about Mission 25 (operator, at the Mission 35 Flight 3 debrief). A review on 2026-11-13 found 12 inaccuracies:
1. "Settings holds your Providers". Model providers moved to Library in sortie 02.
2. The Library section omits Model providers and Secrets (sortie 10).
3. The tool note says agents always look tools up with `search_tools`. Since sortie 11, all tools are exposed up front when the context window is known and the toolset fits.
4. The desktop window is described as tray-only. macOS has no tray: the app lives in the Dock (M32 F3).
5. The build record table is frozen at "25+ missions, 140+ flights, 780+ legs, 160+ squawks, 35+ behavior tests, 6,000+ test functions".
6. Rich visuals (charts and widgets in chat, the per-agent switch, and charts on Discord and Telegram, M35) are not mentioned.
7. Secrets (sortie 10) are not mentioned, including in the diagram and in "Why it's different".
8. The built-in tools list misses the notes tools, the routine tools and `current_time`.
9. The "Every command" table misses `the-one quit`.
10. The example version is `0.12.0`; the current release is `0.15.1`.
11. "This README rebuild is squawk 0170" no longer describes the README.
12. The `gui` extra paragraph predates Pillow becoming a base dependency (M35 F3).

## Evidence
- `README.md:96`, providers in Settings; CLAUDE.md "Settings item pages": "providers moved to Library, sortie 02".
- `README.md:82`, `search_tools`; CLAUDE.md "Tool exposure for small models (sortie 11)".
- `README.md:104`, tray; CLAUDE.md "On macOS (M32 F3 L4) there is no tray".
- `README.md:203`; the repo on 2026-11-13 holds 35 missions plus 14 sorties, 175 flights, 1,007 legs, 347 squawks, 52 behavior tests and about 10,380 test functions.
- `the_one/main.py`, the `quit` command; `the_one/__init__.py` `__version__ = "0.15.1"`.
- Still correct: the install table and guides, the providers table, data paths, 30-day chat expiry (`agent/config.py:143`), the DuckDuckGo default, `docs/connector-setup.md`, the WCAG note, Developing.

## Corrective Action
All in `README.md`:
1. Settings paragraph no longer lists Providers; it names the six current pages (Appearance, Date and time, Prompts, Encryption, Built-in tools, Knowledge indexing; matches `settings-pages.js`).
2. Library intro and list now cover all five groups: Model providers (new bullet), Knowledge bases, MCP servers, Connectors, Secrets (new bullet).
3. `search_tools` note rewritten: all enabled tools are given up front when the provider reports the context window and they fit; otherwise `search_tools` lookup.
4. Desktop window: Windows/Linux tray behaviour kept; added macOS (no tray, Dock, Quit from app menu or Dock).
5. Build record recounted on 2026-11-13: missions 35; flights 175 in missions plus 14 sorties = 189; legs 1,007 in missions plus 36 in sorties = 1,043; squawk files 351; behavior test specs 52 (`tests/behavior/*.md`); `def test_` 10,386. Table now `35+ | 185+ | 1,040+ | 350+ | 50+ | 10,000+` (same "N+" rounding, sorties folded into flights and legs); prose notes sorties and links `sorties/`.
6. Rich visuals: new "Why it's different" bullet (charts, live widgets, Rich visuals switch, charts as images on Discord/Telegram, widget replaced by a note), links to `docs/chart-format.md` and `docs/widget-format.md`; Chats tour mentions charts and widgets.
7. Secrets: new "Why it's different" bullet, Library bullet, and a "Secrets" box in the mermaid diagram.
8. Built-in tools list: added Time (`current_time`) and Notes and routines bullets, with a note that those tools appear when notes or routine-making are switched on for the agent.
9. Command table: added `the-one quit` (`--wait` default on a terminal, `--no-wait`), per `the_one/main.py`.
10. Example version `0.12.0` -> `0.16.0` (`__version__` is 0.16.0, not the 0.15.1 the report cited).
11. "This README rebuild is squawk 0170" replaced by a line pointing at squawk 0349.
12. `gui` paragraph: added that Pillow is a base dependency for chart images; PyGObject/pycairo/WebKitGTK notes unchanged (still match `pyproject.toml`).
Extra factual errors found: none beyond the above.

## Verification
Every link in README.md resolves to an existing file (checked by script, including the new `docs/chart-format.md`, `docs/widget-format.md`, `sorties/`). No test covers the README (grep of tests/ found only unrelated mentions). Facts checked against CLAUDE.md, `settings-pages.js`, `the_one/main.py`, `pyproject.toml`, `__init__.py` and docs/releases v0.15.0 and v0.16.0.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku), independent of the implementers.
- Every relative link resolves.
- Spot-checks confirmed:
  - the Settings pages match `settings-pages.js`;
  - Library lists five groups;
  - `the-one quit` matches `main.py`;
  - `__version__` is 0.16.0;
  - the build-record counts match the tree;
  - the mermaid block is valid;
  - the Pillow claim matches `pyproject.toml`.
- Record note: the Reviewer counts 10,428 `def test_`, not 10,386. The README's "10,000+" stands.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13`
