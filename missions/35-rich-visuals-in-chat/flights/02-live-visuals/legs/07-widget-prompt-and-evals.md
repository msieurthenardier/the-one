# Leg: widget-prompt-and-evals

**Status**: completed (commits C1 `35842128`, B1 `126e5f64`, C2 `2a7150c5`, C3 `48ab1bb7`; baselines `m35f2b-*`, 2026-11-11)
**Flight**: [Live Visuals](../flight.md)

## Objective
Teach agents with Rich visuals on to write widgets, and measure the cost:
1. fix the chart log-scale wording and re-record same-prompt baselines on the shipped prompt (closing squawk 0337 and Flight 1's stale m35 baselines);
2. widen the `visuals` prompt section with the widget text (the DD15 must-mention list) and widen the switch's hint;
3. add `reply_has_valid_widget` and an `evals/widgets/` scenario set;
4. run the comparisons, and stop for the operator's size decision.

## Context
- **Flight DDs:** DD15 (the must-mention list), DD16 (the A1 → B1 → A2 → B2 order, fixed at design review cycle 2), and the operator's choice "re-baseline first".
- **CLAUDE.md "Prompt evals":**
  - platform prompt text lands with an eval run;
  - same-prompt baselines;
  - never compare across scenario sets;
  - the `m35` size targets use ratio 1.0;
  - evals stay out of CI.
- **`evals/README.md`:** usage, gates, `measure-prompt`, `compare`, `baseline`, `derive-bars`.
- **Flight 1 leg 4 precedent** (Flight 1 flight log): a mid-flight review and commit before quota; n=5 sentinels, then n=20; the operator's decision at the end. Debrief lesson: a trimmed prompt must keep every approved item, so the reviewer checks the must-mention list.
- **Current state:**
  - `the_one/agent/platform_prompt.py:142-153` is `_VISUALS` (203 tokens at Flight 1's end). Its log clause reads `` `"scale": "log"` on an axis `` (loose: x log is scatter-only).
  - Baselines: `evals/baselines/m35-platform.json`, `m35-routines.json` and `m35-visuals.json`, which are **stale**: prompt fingerprint `99842c3f` against the shipped `9f213ed2`.
  - Visuals set: `evals/visuals/scenarios/` with `chart-fits-shares`, `chart-fits-timeseries`, `chart-when-asked` and `no-chart-unasked`.
  - `evals/checks.py:310-338` `_chart_blocks` is a chart-only top-level fence scanner; `:341-360` is `reply_has_valid_chart`; `:609-611` is the registry.
  - `tests/test_evals_freeze.py:32` holds `SCORING_DIGESTS` (pins `evals/checks.py` among others; changing it needs operator approval).
  - `evals/fingerprint.py:48-59`: `scenarios_fingerprint` hashes every `*.toml` in the set directory and its sibling `fixtures/`.
  - Default eval models: haiku (plan token), qwen3-4b, lfm3 (Ollama).
  - Sortie 12 is in `planning`; squawk 0337 is open.
- **The switch hint** lives in the General tab (`areas/studio/general-tab.js:201-202`, the Rich visuals toggle `hint`). **No test pins its text today** (design review: a grep of `tests/`, `docs/` and `the_one/` finds only that file). `tests/browser/test_flow_agent_rich_visuals.py` (`agents` lane) has four tests, at `:36`, `:43`, `:69` and `:80`, none of which reads the hint. AC5 adds the pin.
- **Old log clause:** the only copies are `platform_prompt.py:152` and `tests/_platform_prompt_pins.py:19`. The parse rules are in `ui/chart-parse.js:158-159`: x log is scatter-only, and a log axis needs positive values and is not stacked.
- **Scenario set discovery** is `--scenarios-dir` only: there is no registry and no `Makefile` or `fingerprint.py` change. The fixtures default to a sibling `fixtures/` directory, which may be absent (the visuals set has none). `tests/test_evals_scenarios.py:633-640` (`test_the_scenario_files_hold_no_loopback_address`) globs the `SCENARIOS`, `ROUTINES_SCENARIOS` and `VISUALS_SCENARIOS` sets.
- **`SCORING_DIGESTS`** (`tests/test_evals_freeze.py:32-50`) pins `checks.py`, `outcomes.py`, `judge.py` and `harness.py`. Only `checks.py` changes, in A1 and again in A2. Files under `evals/widgets/` need no digest.
- **Size gates:** no unit-tier test pins a `_VISUALS` token count. The byte-for-byte pins in `tests/test_platform_prompt.py` and `tests/_platform_prompt_pins.py` must be rewritten in A2. The size gates live only in `compare`.
- **The widget limit** is UTF-8 bytes ≤ 65536 (`ui/widget.js:32` `MAX_BYTES`), shown to people as "64 KB" (`widget.js:92`). The frame allows `img-src data: blob:`, so local images are fine; remote ones are not.

## Parts and gates
The leg runs in order, with the Flight Director owning the gates:

| Part | Who | What | Ends with |
|---|---|---|---|
| A1 | Developer | log-scale clause fix; `_chart_blocks` → tag-parametrised scanner (no behaviour change); prompt pins; `SCORING_DIGESTS` | **Operator gate 1**: approve the digest update; then the **flight review** (legs 1-6 + A1) and commit `C1` |
| B1 | Developer (quota) | `measure-prompt`; n=20 platform, routines, visuals on haiku, qwen3-4b, lfm3; different-prompt `compare` vs the m35 baselines. **If any pass-rate gate fails, stop and report** (operator gate 1b: the operator accepts or not before any baseline is recorded). Then record `m35f2-*` same-prompt baselines; point the docs at them; close squawk 0337 | commit |
| A2 | Developer | the widened `visuals` text (must-mention list); the hint; `reply_has_valid_widget`; `evals/widgets/scenarios/` (3 scenarios); pins; `SCORING_DIGESTS` | **Operator gate 2**: approve the digest update; review of the A2 diff; commit `C2` |
| B2 | Developer (quota) | n=5 sentinel → n=20; `measure-prompt`; `compare` vs `m35f2-platform`/`-routines` (pass-rate gates hold; size gates fail by construction); different-prompt `compare` of the visuals set vs `m35f2-visuals`; n=20 widgets set | **Operator gate 3**: the size decision |
| After gate 3 | Developer | if accepted, record `m35f2w-platform`, `-routines`, `-visuals`, `-widgets`, and point CLAUDE.md and `evals/README.md` at them; if cut, return to A2 with a shorter text that keeps the list | commit |

## Acceptance Criteria
- [ ] **AC1 (A1) — The log clause.** `_VISUALS` says log scale is for `y`/`y2` and, on `x`, scatter only. Suggested wording: `` log scale: `"scale": "log"` on `y` (on `x`, scatter only) ``. The exact wording is the Developer's, at no more than +6 tokens, spent on the x/scatter point. `tests/_platform_prompt_pins.py` and the byte-for-byte tests are updated. A grep finds no other copy of the old clause.
- [ ] **AC2 (A1) — The scanner.** `_chart_blocks(reply)` becomes `_top_level_blocks(reply, tag='chart')`, returning `(body, closed)` pairs, where `closed` is whether a closing fence was found (in the loop, `i < len(lines)` before the closer is skipped).
  - `_reply_has_valid_chart` ignores `closed` and stays unchanged in behaviour. The unterminated-chart cases at `tests/test_evals_checks.py:201-202` still count, and the existing cases at `:197-216` pass untouched.
  - New parametrized `tag='widget'` cases: backtick and `~~~widget` fences, nested in a list (not top-level), quoted inside JSON (not a block), and an unclosed widget (`closed` False). A test pins `tag='chart'` as the default.
  - Falsification: mutate the tag comparison (`tokens[0] == tag`) and show the existing chart cases fail. `SCORING_DIGESTS` is updated with a dated comment; **the Flight Director gets the operator's approval before `C1`**.
- [ ] **AC3 (B1) — The re-baseline.** On commit `C1`, every external session is re-verified at the start: the plan token, `ollama list` showing `qwen3-4b` and `lfm3`, `.[evals]` installed, and sortie 12's status. Then:
  - `measure-prompt` shows a fingerprint different from `9f213ed2`;
  - n=20 runs of the platform, routines and visuals sets on the three default models;
  - a plain `compare` (different-prompt) against `m35-platform`, `m35-routines` and `m35-visuals`, where the pass-rate gates hold;
  - `baseline` writes `evals/baselines/m35f2-platform.json`, `m35f2-routines.json` and `m35f2-visuals.json`;
  - CLAUDE.md "Prompt evals" and `evals/README.md` name them as current;
  - squawk 0337 is completed against them, through the squawk protocol: the Flight Director records the corrective action, and the review sign-off is this leg's review.
  
  The run directories stay gitignored; the baselines are committed.
- [ ] **AC4 (A2) — The widget text.**
  - The `visuals` section text contains every DD15 must-mention item:
    1. the tag `widget`;
    2. one self-contained HTML document or fragment with inline `<style>` and `<script>`;
    3. no network or external resources;
    4. the theme variables by name (`--bg`, `--fg`, `--accent`, `--chart-1` …);
    5. `requestAnimationFrame`, never an endless loop;
    6. the 64 KB limit;
    7. a widget for animation or interaction, a chart for plain data.
  - A unit test asserts each item's presence by these exact substrings: `` `widget` ``, `<style>`, `<script>`, `--bg`, `--fg`, `--accent`, `--chart-1`, `requestAnimationFrame`, `64 KB`, `animation or interaction`, `chart for plain data`. It also asserts one "no network" phrase the Developer picks and names in the test.
  - **Starting draft** (trim by measurement, keep the list): "To show something moving or interactive, write a fenced block with the language `widget`: one self-contained HTML document or fragment with inline `<style>` and `<script>`. It runs sandboxed with no network, so use no URLs, CDNs, web fonts or remote images. Colours: `var(--bg)`, `var(--fg)`, `var(--accent)`, `var(--chart-1)` to `var(--chart-8)`. Animate with `requestAnimationFrame`; never loop forever. Keep it under 64 KB. Use a widget for animation or interaction, a chart for plain data."
  - The draft agrees with `docs/widget-format.md`: the tag (case-sensitive), a fragment or a whole document, the theme names, 64 KiB shown as "64 KB", and no network. It leaves out `themechange`, `--surface`, `--fg-muted`, `--border` and `--danger` on purpose, for the token budget.
  - A2 greps the Settings › Prompts tests (`test_flow_admin_settings_nav.py`, `test_prompt_layers.py`, and any other hit for the section title or text) and updates every pin, per squawk 0334.
  - The section keeps its id, title and condition. Settings › Prompts shows it unchanged in structure. The pins move.
- [ ] **AC5 (A2) — The hint.** The General tab Rich visuals hint reads: "Tell this agent it can answer with charts and widgets. When it's off, the agent isn't told, but any chart or widget in its replies is still shown." No test pins the hint today, so A2 **adds** an assertion of the exact hint text to `tests/browser/test_flow_agent_rich_visuals.py`, scoped to the Rich visuals toggle (falsify it against the old text). The `agents` lane passes.
- [ ] **AC6 (A2) — The check and the set.**
  - `reply_has_valid_widget(turn=)` passes when the reply holds a **closed** top-level ```` ```widget ```` block (closed-only, matching DD12: the chat never runs an unclosed block; unlike the chart check's precedent) that:
    - is at most 65536 bytes in UTF-8 (`widget.js` `MAX_BYTES`);
    - contains `<script`, `<canvas` or `<svg`;
    - has no external URL. The heuristic is a regex the Developer pins in the docstring and tests: an `http:`, `https:` or protocol-relative `//` value as the argument of `src=`, `href=` (including `xlink:href`), `url(`, `@import`, `fetch(` or an `import … from` / `import(`. `xmlns="http://www.w3.org/…"` is **not** a reference and passes. WebSocket, XHR and EventSource URLs are out of scope (the frame blocks them), and the docstring says so and that it is a heuristic.
  - It is registered with `{"turn": "int"}` and documented in `evals/README.md`'s check vocabulary table. `evals/README.md`'s visuals paragraph (around lines 162-178) gains the widgets set and its `--scenarios-dir evals/widgets/scenarios` command.
  - `evals/widgets/scenarios/` holds (each TOML with a `class`):
    - `widget-when-asked` (`improve`): phrasings × facts asking for an animation or an interactive thing; check `reply_has_valid_widget`;
    - `widget-not-for-data` (`hold`): a plain table of numbers to visualise; checks `reply_has_valid_chart` and `reply_not_matches` a widget fence;
    - `no-widget-unasked` (`hold`): a prose question; `reply_not_matches` `(?m)^```\s*widget\b`.
  - Offline unit tests cover the check: valid; exactly 65536 bytes (pass) and 65537 (fail); a multibyte body under 64 Ki characters but over 65536 bytes (fail); `src="//cdn…"`, `url(https://…)`, `fetch("https://…")`, `import x from "https://…"` and `@import url(…)` (each fail); `xmlns` and `href="#frag"` (pass); no script, canvas or svg (fail); unclosed (fail); nested in a list (not top-level, fail).
  - A new `tests/test_evals_widgets.py`, modelled on `tests/test_evals_visuals.py`, covers scenario parsing, check names and scripted pass and fail runs. A `WIDGETS_SCENARIOS` glob is added to `tests/test_evals_scenarios.py::test_the_scenario_files_hold_no_loopback_address`.
  - `SCORING_DIGESTS` is updated after the final `checks.py` edit and `ruff format`, with a dated comment; **the operator approves before `C2`**.
  - The visuals set directory is **unchanged**.
- [ ] **AC7 (B2) — The widget-prompt runs.** On `C2`, with the external sessions re-verified:
  - an n=5 sentinel on haiku `widget-when-asked` and the visuals set;
  - n=20 platform, routines and visuals sets plus the widgets set;
  - `measure-prompt` (the section's token count, and the bare and all-on totals);
  - `compare --baseline evals/baselines/m35f2-platform.json` and `m35f2-routines.json` (`--same-prompt` does not apply; the prompt changed). Pass-rate gates must hold; the size gates fail by construction;
  - a plain `compare` of the visuals set against `m35f2-visuals.json`.
  
  The flight log records a table per set and model, with Wilson intervals and token deltas. As a diagnostic beside the pass rates, it also records the count of widget fences in each visuals scenario's replies and, for the widgets set, unclosed-widget counts kept separate from invalid ones (truncation on the local models).
- [ ] **AC8 — Operator gate 3.** The Flight Director brings the operator the token cost, the pass rates and any regressions. **Divert criterion:** haiku `widget-when-asked` below about 0.5, or a visuals-set regression on the widget prompt. The operator either accepts (record the `m35f2w-*` baselines and point the docs at them) or cuts (return to A2 with a shorter text that keeps the list).

## Verification Steps
- **A1/A2 unit:** `.venv/bin/python -m pytest tests/test_platform_prompt.py tests/test_evals_*.py -x -q`, then `THE_ONE_TEST_NETNS=1 make test-unit`. The `settings` lane covers the Prompts pins (squawk 0334: grep the section title and count pins). The `agents` lane covers the hint.
- **B1/B2:** the exact `make eval ARGS="…"` commands and the run directory names go in the flight log.

## Implementation Guidance
1. **Read `evals/README.md` fully, and Flight 1's leg 4 flight-log entries** for the exact commands, flags and run-directory conventions. Reuse them.
2. **Quota spend runs only after its commit.** Never run B1 or B2 on an uncommitted tree; the fingerprints must match committed code.
3. **Run Ollama models sequentially;** do not overlap them with browser lanes (the quiet-host rule).
4. **Keep the widget text** in the same `_VISUALS` constant, after the chart text, so one section serves both.

## Edge Cases
- **B1's different-prompt compare fails a pass-rate gate against the stale m35 baselines:** stop and report to the Flight Director, with the failing cells and Wilson intervals. `baseline` does not require `compare` to pass (`evals/baseline.py`), but no `m35f2-*` baseline is recorded until the operator accepts (operator gate 1b).
- **The commits:** `env.sh` (untracked, repo root) is not part of the flight and must not be committed.
- **Sortie 12 has landed by leg start:** compare against its baselines instead, and record it (DD13 of Flight 1 precedent).
- **Ollama lacks a model:** stop and ask the operator, do not substitute.
- **The plan token has expired:** stop and ask the operator.

## Files Affected
- `the_one/agent/platform_prompt.py`, `tests/_platform_prompt_pins.py`, `tests/test_platform_prompt.py`
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` (the hint), `tests/browser/test_flow_agent_rich_visuals.py` (a new hint pin)
- `evals/checks.py`, `evals/README.md`, `evals/widgets/scenarios/*.toml` (new), `tests/test_evals_checks.py`, `tests/test_evals_widgets.py` (new), `tests/test_evals_scenarios.py`, `tests/test_evals_freeze.py`
- Settings › Prompts pins found by the A2 grep (`tests/browser/test_flow_admin_settings_nav.py`, `tests/test_prompt_layers.py` or wherever they are)
- `evals/baselines/m35f2-*.json`, `m35f2w-*.json` (new)
- `CLAUDE.md` ("Prompt evals")
- `squawks/0337-platform-eval-same-prompt-rebaseline.md`
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md`

## Citation Audit
Verified on 2026-11-09:
- `the_one/agent/platform_prompt.py:142-153` - `_VISUALS`, with the clause `` `"scale": "log"` on an axis `` - verified
- `evals/baselines/` - `m35-platform.json`, `m35-routines.json`, `m35-visuals.json` (plus history files) - verified
- `evals/visuals/scenarios/*.toml` - four files; TOML shape `id`, `class`, `description`, `[variants]` (`phrasings`, `facts`), `[[conversations]]`, `[[checks]]` - verified
- `tests/test_evals_freeze.py:32` `SCORING_DIGESTS` - verified
- `evals/fingerprint.py:48-59` - the set fingerprint covers `*.toml` and the sibling `fixtures/` - verified
- `evals/checks.py:310-338`, `:341-360`, `:609-611` - verified (flight citation audit)
- `squawks/0337-platform-eval-same-prompt-rebaseline.md` - open - verified

Re-verified 2026-11-10 by the Flight Director and the design review: every citation above still holds. Added `general-tab.js:201-202`, `tests/_platform_prompt_pins.py:19`, `ui/chart-parse.js:158-159`, `ui/widget.js:32`/`:92`, `tests/test_evals_checks.py:197-216`, `tests/test_evals_scenarios.py:633-640` and `tests/test_evals_freeze.py:32-50`, each checked by the review.
