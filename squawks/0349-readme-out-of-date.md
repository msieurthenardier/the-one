# Squawk 0349: README out of date

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: —

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
*(written at completion)*

## Verification
Re-read each changed section against CLAUDE.md and the code. Check every link resolves, recount the build record, and match the command table against `the_one/main.py`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
