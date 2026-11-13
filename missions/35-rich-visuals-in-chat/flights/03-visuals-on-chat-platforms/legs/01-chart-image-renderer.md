# Leg: chart-image-renderer

**Status**: completed
**Flight**: [Visuals on Chat Platforms](../flight.md)

## Objective
The server can draw every valid chart as a light-theme PNG with a bundled, SHA-pinned font whose text widths are the same on every host. A thirteenth `the-one doctor` gate, `chart images`, proves this, and the operator approves a sample sheet before any send path uses the renderer.

## Context
- **Flight design decisions:** DD4 (font, `Layout.BASIC`, design-unit measurement, glyph residual, lock), DD5 (light palette pinned to `tokens.css`, sizes, content, shared y-tick corpus, decoded-pixel comparisons, sample sheet), DD10 (at-limit drawing time, 8 MB cap) and DD12 (the doctor gate and every gate list).
- This is the first leg. Nothing in Flight 3 is built yet. Leg 2 runs this leg's doctor gate in the packaged builds. Leg 3 is the renderer's first caller, through `OutboundImage`, which Leg 3 defines. This leg returns raw PNG bytes and the pixel size only.
- **No committed pixel baselines** (operator's standing rule: golden files are never committed). DD5's "decoded-pixel hash" therefore means:
  - in-process determinism: two draws of one spec give the same `Image.tobytes()` hash;
  - structural assertions: the size, card colour, edge colour and the series colours present.
  
  Never a hash stored in the repository. The doctor gate's reference *width* is a property of the font file, not a rendering, so pinning it is allowed.
- **Pillow is already in every packaged build:** `pystray` depends on it, and the `[gui]` extra carries `pillow>=13.0` (`pyproject.toml:164`). Moving it to the base dependencies changes the dependency declaration and the lock, not what the bundles contain.
- **Host facts** (measured at planning): Pillow 13.0.0, FreeType 2.14.3. RAQM loads here only because the host has `libfribidi.so.0`. BASIC must be pinned explicitly.
- **Font facts** (Flight Director, 2026-11-12, from `geist-font-1.8.0.zip`, the 1.8.0 release asset):
  - The release's `fonts/Geist/ttf/` holds the static files.
  - `unitsPerEm` is 1000 for both weights.
  - The fonts have no `kern` table, only GPOS.
  - Advances at `size=1000` with BASIC: Regular `"0"` 663, `"A"` 668, `"V"` 667, `"AV"` 1335; SemiBold `"0"` 683.
  - SHA-256: `Geist-Regular.ttf` `bde046ddd9f20be35b0bd56cc79eb752b967fb6661a3fe76cb067bb09f871d76`, `Geist-SemiBold.ttf` `097409e9fabf676be0764b47297c2cdab3750e84dc0f575298c7fbd45f3b3819`, `OFL.txt` `1781d2806a07d91c4edf4740b88449fab7d0eadad53f7c351b94cd4d4eb8c00f`.
- **Measuring by per-character advance sums** (design review): BASIC still applies a legacy `kern` table when a font has one. With DejaVuSans, `"AV"` measured 2799.953 against 2802. Geist has no `kern` table, so its sums happen to be exact, but layout must not rely on that. `measure()` sums each character's own advance, and text is drawn one character at a time at the accumulated positions. A width is then a property of the font file by construction, whatever tables the font carries.
- **Font placement:** the shell-write hook blocks `cp` into `the_one/`, and the Edit and Write tools cannot write binary files. So the operator places the three font files before this leg starts (see Inputs). The Developer verifies them and does not copy anything.

## Inputs
- `the_one/visuals/chart_spec.py`: `parse_chart`, `format_tick`, `format_full`, and the `ChartSpec`/`Axis`/`Series`/`Annotation` dataclasses. Standard library only.
- The browser chart control, which is the layout reference:
  - `static/js/ui/chart-scale.js` (`HEIGHT = 240`, `niceStep`, `buildAxis`, `computeStacks`, `addGridAndTicks`, `tickWidth`, `axisLabels`, `SPARK_W`/`SPARK_H`);
  - `static/js/ui/chart-layout.js` (margins, x-label thinning, `fitText`, per-type drawing);
  - `static/js/ui/chart.js`;
  - `components.css:2956-2991` (`.ui-chart-*`: ticks and axis labels at 11 px in `--fg-tertiary`, title semibold at `--font-size-body`).
- `tests/fixtures/charts/valid/*.json` (23 specs) and `number-format.json`.
- `the_one/diagnostics.py` (12 gates, `run_doctor` at `:1172`, `gates = [` at `:1268`, `ProbeResult(name, ok, detail)`).
- `the_one/interfaces/web/static/fonts/LICENSE.txt` (the Geist OFL text for the bundled `.woff2`, vercel/geist-font 1.8.0).
- `the_one/visuals/fonts/Geist-Regular.ttf`, `Geist-SemiBold.ttf` and `OFL.txt`, placed by the operator from the 1.8.0 release zip. Their hashes are given in Context.

## Outputs
- **`pyproject.toml`:**
  - `pillow>=13.0` is a base dependency. The CVE-floor comment moves with it.
  - The `[gui]` and `[dev]` entries are removed. Pillow comes from the base now; `pystray` still pulls it in for `[gui]`. A note says why.
  - `[tool.setuptools.package-data]` gains `visuals/fonts/*`.
- **`uv.lock`:** re-locked (`uv lock`), then `uv sync --all-extras --frozen`.
- **`.github/workflows/pr-lint.yml`:** the comment about pillow entering only through `[gui]` (`:69-71`) is corrected. Comment only.
- **`the_one/visuals/fonts/`:** `Geist-Regular.ttf`, `Geist-SemiBold.ttf` and `OFL.txt` (the licence copy).
- **`the_one/visuals/chart_image.py`** (new). The renderer: `render_png(spec: ChartSpec) -> RenderedChart` (a frozen dataclass of `data: bytes`, `width: int`, `height: int`, the pixel size at 2×). It also holds:
  - the palette constants;
  - the font loader and design-unit measurement;
  - the scale code mirroring `buildAxis`/`niceStep`/`computeStacks`;
  - the module lock.
- **`the_one/visuals/__init__.py`:** docstring updated. `chart_spec.py` (and Leg 3's `blocks.py`/`outbound.py`) are standard library only; `chart_image.py` imports Pillow lazily.
- **`the_one/diagnostics.py`:** `_probe_chart_images` and the `chart images` gate, thirteenth in the `gates` list.
- **The gate lists** (DD12): see Implementation Guidance step 7.
- **`tests/fixtures/charts/ticks.json`** (new): for every valid **cartesian** spec (not pie or sparkline), the expected `y` ticks and, when the chart has a right axis, the `y2` ticks, as numbers.
- **Tests:**
  - `tests/test_chart_image.py` (new);
  - additions to `tests/test_chart_spec.py` (the AST guard covers the whole package);
  - `tests/test_doctor.py`;
  - a tick-corpus test in `tests/browser/test_ui_chart_contract.py`.
- **`scripts/chart_sample_sheet.py`** (new, a developer tool). It writes one PNG per valid corpus spec, plus the at-limit and CJK-title specs, and an `index.html` that shows them all, to `--out DIR`. It refuses an `--out` inside the repository, like `scripts/ui_capture.py`.
- **`docs/chart-format.md`:** a new "Images" section.
- **Docs:**
  - the `the_one/agents.md` gate table and its prose counts;
  - CLAUDE.md's gate sentence ("a thirteenth, `chart images` (M35 F3 L1) …").

## Acceptance Criteria
- [ ] **AC1:** `pillow>=13.0` is a base dependency in `pyproject.toml`.
  - It is no longer listed in `[gui]` or `[dev]`, and the CVE-floor comment sits beside the base entry.
  - `uv.lock` is re-locked, and `uv sync --all-extras --frozen` succeeds.
  - `uv lock --check` passes.
- [ ] **AC2:** `the_one/visuals/fonts/` holds `Geist-Regular.ttf`, `Geist-SemiBold.ttf` and `OFL.txt`, with exactly the SHA-256 values in Context.
  - A test pins both TTF hashes and each TTF's `head.unitsPerEm` (1000).
  - The source (`https://github.com/vercel/geist-font/releases/download/1.8.0/geist-font-1.8.0.zip`, path `fonts/Geist/ttf/`) is recorded in the flight log.
- [ ] **AC3:** the fonts reach every package. `pyproject.toml` package-data covers `visuals/fonts/*`. Each of `packaging/windows/the-one.spec`, `packaging/linux/the-one.spec` and `packaging/macos/the-one.spec` collects `visuals/fonts/*` with `collect_data_files("the_one", includes=[…])`, beside the existing calls. A unit test reads the three spec files and fails if any of them lacks the include.
- [ ] **AC4:** `chart_image.py` follows these rules, each pinned by a test:
  - It imports Pillow only inside functions; importing the module does not import `PIL`.
  - Every font is loaded with `layout_engine=ImageFont.Layout.BASIC`.
  - All drawing runs under one module-level `threading.Lock`.
  - Layout widths come from design units. Each character is measured on its own (`getlength(ch)`) with a font loaded at `size = unitsPerEm`, read from the TTF `head` table; the advances are summed and scaled to the logical size.
  - Text is drawn one character at a time at the accumulated positions, so what is drawn matches what was measured.
  - Tests assert:
    - `measure("0", 1000, regular)` == 663;
    - `measure("AV", …)` == `measure("A", …) + measure("V", …)`;
    - the per-character path is used even for a font that has a `kern` table (a test with a stub `getlength` that kerns pairs).
- [ ] **AC5:** the AST guard in `tests/test_chart_spec.py` covers every module in `the_one/visuals/`. Only `chart_image.py` may import `PIL`, and no module imports anything from `the_one.` outside `the_one.visuals`. The existing `chart_spec.py` allowlist is unchanged.
- [ ] **AC6:** every valid corpus spec draws (`tests/fixtures/charts/valid/*.json`, all 23).
  - The image is an RGB PNG with no alpha and no text chunks.
  - Size, in pixels (logical × 2):
    - Cartesian and pie charts are 1280 wide and `(240 + 20·title_rows + 20·legend_rows) × 2` high.
      - `title_rows` is 1 when there is a title, else 0. The title is one line, cut with an ellipsis to the width by `fitText` and measured in design units.
      - `legend_rows` is 0 when the browser shows no legend (one series and not a pie), else the number of rows the legend wraps into at 640 logical width. Entries flow left to right like the browser's `flex-wrap`, so `pie-twelve-slices.json` takes more than one row.
    - Sparklines are 640 wide and `(64 + 20·title_rows) × 2` high.
      - The browser's 140 × 32 geometry (`SPARK_W`/`SPARK_H`, with its insets and its 1.5 px stroke) is scaled to 320 × 64.
      - A titled sparkline (`sparkline-titled-unit.json`) gets the title row above it, because the image stands alone.
    - A test pins the formula for each corpus spec.
  - Corner pixels are `--surface` light `#fafafa`, and the 1-logical-px edge is `--border` light `#e4e4e7`.
  - Each drawn series' palette colour (`--chart-1` …, repeating after 8) appears in the image.
  - Two draws of the same spec give identical `Image.tobytes()`.
- [ ] **AC7:** the light palette and card constants in `chart_image.py` equal the light `[data-theme="light"]` values in `css/tokens.css`, parsed by the test:
  - `--chart-1` … `--chart-8`, `--chart-ref`;
  - `--surface`, `--border`, `--border-strong`, `--fg`, `--fg-secondary`, `--fg-tertiary`.
  
  No runtime CSS read.
- [ ] **AC8:** `tests/fixtures/charts/ticks.json` lists every valid cartesian spec and no others: 18 of the 23, leaving out the 3 pie and 2 sparkline specs. Scatter specs' numeric x ticks are not in the corpus, and each renderer pins them itself, like x thinning.
  - Python asserts `chart_image`'s axis ticks against it, exactly, as floats.
  - `tests/browser/test_ui_chart_contract.py` asserts the browser's drawn y (and y2) tick labels against it in Chromium and WebKit: each corpus value formatted with `format_tick` and the axis unit, in order.
  - The corpus values come from the browser, which is the existing reference. Python is made to match it, never the other way round.
- [ ] **AC9:** the content follows `docs/chart-format.md`, each pinned by at least one structural test:
  - bars include 0;
  - log axes tick at powers of 10;
  - colours repeat after 8 series;
  - line series 5 and up are dashed;
  - reference lines use a `4 3` dash;
  - a zero pie slice is not drawn;
  - null gaps break a line.
- [ ] **AC10:** a synthetic at-limit spec (2000 values over 8 series, a log y axis and 5 annotations) parses and draws in under 500 ms on this host. The bound can be overridden by `THE_ONE_CHART_DRAW_BOUND_MS` (test-only), and the test measures the median of 3 draws. A PNG over 8 MB raises `ChartImageError`, a module exception whose message never includes chart data; this is tested with a monkeypatched cap.
- [ ] **AC11:** `the-one doctor` prints `chart images: OK — …` as its thirteenth gate, on every host and not frozen-only.
  - The probe loads both TTFs with BASIC.
  - It requires the exact design-unit width of a fixed ASCII reference string (a constant in `diagnostics.py`), measured through `chart_image`'s own `measure()`, so the gate tests the code layout uses.
  - It draws a fixed reference chart and requires its exact pixel size.
  - Its detail is ASCII-only: `width <W> du, layout basic, pillow <v>, freetype <v>`.
  - It never raises; a missing font file fails the gate with a plain detail.
  - `tests/test_doctor.py` covers pass, a missing font (monkeypatched path), a wrong width (monkeypatched constant), the gate's order (thirteenth, after `mcp sdk`), and that the detail is ASCII.
  - `test_gates_list_has_twelve_names_ending_with_mcp_sdk` (`test_doctor.py:867`) is renamed (not deleted and re-added) to `test_gates_list_has_thirteen_names_ending_with_chart_images`, and updated.
  - The `run_doctor` docstring (`diagnostics.py:1177-1191`, "twelve" and the list of unconditional gates) is updated.
- [ ] **AC12:** every gate list names `chart images`:
  - `packaging/windows/build.ps1` (both lists, `:52` and `:365`);
  - `packaging/windows/README.md:53`;
  - `scripts/windows_test_copy.py:101`;
  - `tests/test_windows_build_recipe.py:161`;
  - `tests/test_windows_test_copy.py:452`;
  - `packaging/macos/checks.sh:85` and its comment at `:73`;
  - the `run_doctor` docstring;
  - the `the_one/agents.md` gate table (`:1923-1925`), its `:1908` build-recipe sentence and the "twelve gates" counts;
  - CLAUDE.md (`:95`, and `:252` if it counts gates).
  
  `packaging/linux/checks/score.py` reads the doctor output generically and is unchanged. `docs/releases/*` is history and is unchanged.
  
  `grep -rn "mcp sdk" --include=* .` shows no gate list that lacks `chart images`, apart from history (mission and flight artifacts, squawks).
- [ ] **AC13:** `scripts/chart_sample_sheet.py --out <dir outside repo>` writes 25 PNGs (23 corpus specs, the at-limit spec and a CJK-title spec) and an `index.html`. It exits 2 for an `--out` inside the repository, and a unit test covers that refusal.
- [ ] **AC14:** `docs/chart-format.md` has an "Images" section stating:
  - the light theme, sizes and 2× density;
  - the bundled Geist TTFs under BASIC, with layout widths measured as per-character design-unit advance sums and text drawn per character (so server text sits slightly wider than the browser's kerned text);
  - that the missing-glyph box is drawn for characters Geist lacks (CJK, emoji), and that the title also goes out as platform text;
  - that the y-tick corpus is shared by both renderers and x-label thinning is per renderer.
  
  The "Text width" section points to it.
- [ ] **AC15:** `make test-unit` passes, with the expected skip count. `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat` passes. `ruff check` and `ruff format --check` are clean.
- [ ] **AC16 (Flight Director gate, after landing):** the operator approves the sample sheet. The leg is not `completed`, and Leg 3 does not start, until then. Revisions the operator asks for land in this leg's code through a fix pass. After two revision rounds, an unresolved look becomes a Flight 4 alignment item (flight Adaptation Criteria).

## Verification Steps
- AC1: `grep -n pillow pyproject.toml`; `uv lock --check`; `uv sync --all-extras --frozen`.
- AC2, AC3, AC4, AC5, AC6, AC7, AC9, AC10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_chart_image.py tests/test_chart_spec.py -x --timeout 60`.
- AC8: the Python test as above, then `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat`.
- AC11: `.venv/bin/the-one doctor`, run from a scratch cwd with `THE_ONE_DATA_DIR` set to a scratch directory under `$HOME` (never the default data dir; `doctor` reads settings). Read the `chart images:` line. Then `scripts/run-tests.sh tests/test_doctor.py -x --timeout 60`.
- AC12: `grep -rn "mcp sdk" packaging scripts tests the_one CLAUDE.md` and compare.
- AC13: `.venv/bin/python scripts/chart_sample_sheet.py --out $HOME/m35f3-sample-sheet`; list the files; then the refusal test.
- AC15: `THE_ONE_TEST_NETNS=1 make test-unit`; the lane above; `ruff check the_one/ tests/ scripts/ evals/` and `ruff format --check …`.

## Implementation Guidance

1. **Fonts first (AC2).**
   - Check that the three operator-placed files exist and match the hashes in Context (`sha256sum`).
   - If any file is missing or differs, stop and signal `[BLOCKED:fonts-not-placed]`. Never copy or download fonts into the repo yourself; the shell-write hook refuses it.
   - Read `unitsPerEm` from the `head` table with `struct`: find the `head` entry in the table directory, then read offset 18 within the table, a big-endian uint16.

2. **Dependency move (AC1).**
   - Edit `pyproject.toml` by hand, then `uv lock` and `uv sync --all-extras --frozen` (CLAUDE.md: never `uv run --python <other>` against the project).
   - Reword the CVE-floor comment for its new home beside the base block's "dual-binding" CVE comment: it now binds every install, not only the Windows installer's `[gui]` extra.
   - Every packaging recipe exports the locked closure with `--extra gui --extra all-llms`: `build.ps1:215`, `linux/build.sh:88`, `macos-packages.yml:153`, `release.yml:76` and `pr-lint.yml:72`. So bundle contents do not change; only the `pr-lint.yml:69-71` comment does.
   - The lock diff should only move pillow's marker or extra and touch no other version. If other versions change, stop and report.
   - If the frozen build's PIL hook misses `PIL._imagingft` (the font module is imported lazily), the fallback is a `hiddenimports` entry. Leg 2's packaged doctor run is what decides; do not add it pre-emptively.

3. **Measurement and fonts in `chart_image.py` (AC4).**
   - `_fonts()` lazily imports `PIL.ImageFont` and caches, per weight, a design-unit font (`size=units_per_em`) and the drawing fonts at the 2× pixel sizes, all with `layout_engine=ImageFont.Layout.BASIC`.
   - `measure(text, size_px, weight) -> float` is `sum(advance(ch)) * size_px / units_per_em`, where `advance(ch)` is `design_font.getlength(ch)`, cached per character. It is the only width source for layout.
   - Draw text with the 2× font one character at a time, at x positions accumulated from the same advances (scaled to 2×), rounded only at draw time.

4. **Scale and layout (AC6, AC8, AC9).**
   - Port `niceStep`, `buildAxis` (including `roundClean` = `float(f"{v:.12g}")`, the 1e-9/1e-12 epsilons and the log stride), `computeStacks`, the extent rules and the margin rules from `chart-scale.js` and `chart-layout.js`, keeping names close to the JS so a later reader can diff them.
   - Logical width 640; the drawing area is `HEIGHT = 240` (`chart.js:105` sets the SVG to 240, or 32 for a sparkline).
   - The title and legend rows sit outside the 240, as the browser's `.ui-chart-caption` (a `div.ui-chart-title` and a `ul` legend) sits outside its SVG.
     - The title row is 20 logical px, semibold at 13 px.
     - Each legend row is 20 logical px, 11 px text with a colour swatch.
     - Record both heights in `docs/chart-format.md`.
   - Tick text is `format_tick(value, unit)` from `chart_spec.py`.
   - X-label thinning uses `measure`, not the browser's numbers, and is pinned by its own Python test (DD5: thinning is per renderer).
   - Pie: slices plus the wrapped legend; a zero slice is skipped.
   - Sparkline: the browser's 140 × 32 geometry scaled to 320 × 64 logical, a single line with no axes, plus the title row when titled.

5. **The tick corpus (AC8).**
   - In the browser contract test, draw each valid cartesian spec with the existing harness, collect the `ui-chart-tick` text elements, and split them by `text-anchor` (`end` = left axis, `start` = right axis).
   - To create `ticks.json`, print the browser's numeric ticks for every spec (calling `App.ui.util.chartParts.buildAxis` through `page.evaluate` with the same extent logic the drawing uses, or from a temporary debug print), then write the JSON with the Write tool. Never write it from a script.
   - The committed test compares the drawn labels to `format_tick(corpus value, unit)`. The JS formatter's output is pinned equal to Python's by `number-format.json` already.

6. **The doctor gate (AC11).** Follow `_probe_mcp_sdk`'s shape (`name = "chart images"`, try/except, never raises, `ProbeResult`). The reference string and its expected width are module constants; measure the width once and hard-code it. The reference chart is a small inline spec, and its size is a constant.

7. **Gate lists (AC12).** Search `grep -rn "mcp sdk"` across `packaging/`, `scripts/`, `tests/`, `the_one/`, `.github/` and CLAUDE.md, and add `chart images` wherever the twelve gates are listed or counted ("twelve" → "thirteen", where it counts gates). Keep the Windows PowerShell exact `"chart images: OK"` form. The Windows lists are not run by `make test-unit` (`agents.md:1908`), so check each by eye.

8. **Sample sheet script (AC13).**
   - Model the repository refusal on `scripts/ui_capture.py`'s `--out` check.
   - The at-limit and CJK specs are built in code; the CJK title is `"季度收入 Revenue"`.
   - `index.html` shows each PNG at its natural size, with the spec's file name above it, on a plain white page. The operator sees what the platform shows.

9. **Docs (AC14)** and the `visuals/__init__.py` docstring.

10. **Run the gates (AC15).**
    - Run `make test-unit` once at the end, in the background, and wait for its notification.
    - Run the `contracts-chat` lane with WebKit required and `THE_ONE_TEST_NETNS=1`.
    - Then write the sample sheet to `$HOME/m35f3-sample-sheet` (outside the repo) and report the path. The Flight Director shows it to the operator.

## Edge Cases
- **No title:** no title row; the image is 480 px high plus the legend row, if any.
- **One series:** no legend row (browser legend rules, `test_legend_rules`).
- **A spec with `y2`:** right-axis ticks are drawn at the plot's right, and `ticks.json` carries `y2`.
- **Log axis with fixed `min`/`max`:** `buildAxis` log branch (`d1 <= d0` → `d1 = d0 * 10`).
- **Label at the 60-character limit with emoji** (`label-at-limit-emoji.json`): an emoji draws as the missing-glyph box, and `fitText` truncation measures with design units.
- **A font file missing at runtime:** `render_png` raises `ChartImageError` (Leg 3 treats that as "not drawn"); the doctor gate fails with a plain detail.
- **Concurrent callers:** the lock serialises them; a test runs two threads and checks both results equal the serial draw. The lock is process-wide and is held through the PNG encode, so one slow draw delays every other caller. The format limits keep that under DD10's bound.
- **Title at its limit** (`title-and-unit-at-limit.json`, 130 characters): cut with an ellipsis to one line.
- **CJK title** (sample sheet only): drawn as missing-glyph boxes, and cut like any title.
- **Unmeasured hosts:** AC10's 500 ms bound is measured on this host only. The Windows and macOS hosts are not timed.

## Files Affected
- `pyproject.toml`, `uv.lock`, `.github/workflows/pr-lint.yml` (comment)
- `the_one/visuals/__init__.py`, `the_one/visuals/chart_image.py` (new), `the_one/visuals/fonts/*` (new)
- `the_one/diagnostics.py` (the probe, the gates list, the `run_doctor` docstring)
- `packaging/windows/the-one.spec`, `packaging/linux/the-one.spec`, `packaging/macos/the-one.spec`, `packaging/windows/build.ps1`, `packaging/windows/README.md`, `packaging/macos/checks.sh`
- `scripts/windows_test_copy.py`, `scripts/chart_sample_sheet.py` (new)
- `tests/test_chart_image.py` (new), `tests/test_chart_spec.py`, `tests/test_doctor.py`, `tests/test_windows_build_recipe.py`, `tests/test_windows_test_copy.py`, `tests/browser/test_ui_chart_contract.py`, `tests/fixtures/charts/ticks.json` (new)
- `docs/chart-format.md`, `the_one/agents.md`, `CLAUDE.md`

## Citation Audit
Checked against the working tree at `2d1e6860` (2026-11-12).
- `pyproject.toml:150-165` — `gui` extra holds `pillow>=13.0` with the CVE-floor comment at `:158-163`; `:169` `dev` holds `pillow>=13.0`; `:188-196` package-data globs on the `the_one` key — verified
- `.github/workflows/pr-lint.yml:69-71` — the "pillow only enters via the gui extra" comment — verified
- `the_one/visuals/__init__.py:1` — "Standard library only; no web, agent or Pillow imports." — verified
- `the_one/visuals/chart_spec.py:36-80` — frozen dataclasses `ChartError`, `Axis`, `Series`, `Annotation`, `ChartSpec`; `:19-24` limits; `:134` `format_tick(value, unit="")` — verified
- `tests/test_chart_spec.py` `test_module_imports_nothing_from_the_app_or_pillow` — parses only `chart_spec.py`; allowlist `{"__future__", "json", "math", "dataclasses", "decimal"}` — verified
- `static/js/ui/chart-scale.js:25` `HEIGHT = 240`; `:168` `niceStep`; `:184` `buildAxis` (log stride, `roundClean`); `:251` `computeStacks`; `:285` `addGridAndTicks` (left ticks `text-anchor` `end`, right `start`); `:330-353` exports on `App.ui.util.chartParts` — verified
- `css/tokens.css` light block from `:233`: `--surface #fafafa` `:240`, `--border #e4e4e7` `:246`, `--border-strong #a1a1aa` `:248`, `--fg #18181b` `:253`, `--fg-secondary #52525b` `:254`, `--fg-tertiary #5f5f68` `:255`; chart palette `:313-321` — verified
- `css/components.css:2956`, `:2978-2979`, `:2991` — chart title, tick/axis-label 11 px `--fg-tertiary`, ref label — verified
- `the_one/diagnostics.py:53` `ProbeResult(name, ok, detail)`; `:744` `_probe_mcp_sdk`; `:1172` `run_doctor`; `:1268-1281` the 12-gate list ending `mcp_sdk_probe` — verified
- Gate lists: `packaging/windows/build.ps1:52`, `:365`; `packaging/windows/README.md:53`; `scripts/windows_test_copy.py:101`; `tests/test_windows_build_recipe.py:161`; `tests/test_windows_test_copy.py:452`; `packaging/macos/checks.sh:85`; `tests/test_doctor.py:886`, `:1232`; `the_one/agents.md:1908`, `:1925`, `:1927` — verified
- Freeze specs: `packaging/linux/the-one.spec:63-66`, `packaging/macos/the-one.spec:81-83`, `packaging/windows/the-one.spec:156-157`, `:170`, `:202` — `collect_data_files("the_one", includes=[…])` — verified
- `tests/browser/test_ui_chart_contract.py:23` `CORPUS` path; `engine_page` + `load_harness`; lane `contracts-chat` — verified
- Pillow 13.0.0, FreeType 2.14.3, `features.check("raqm")` True on this host; `/home/cprch/.local/bin/uv` present — verified (measured)
- Design review cycle 1 (Developer, Sonnet, 2026-11-12) also verified:
  - `chart.js:105` (SVG height 240, or 32 for a sparkline) and `chart-scale.js:26-27` (`SPARK_W` 140, `SPARK_H` 32);
  - `test_doctor.py:867`, `diagnostics.py:1177-1191` and `checks.sh:73`;
  - the recipes' `--extra gui` exports (`build.ps1:215`, `linux/build.sh:88`, `macos-packages.yml:153`, `release.yml:76`, `pr-lint.yml:72`);
  - that the hook blocks `cp` into `the_one/`;
  - that `doctor` creates `data_dir` through `config.py`, so a scratch `THE_ONE_DATA_DIR` is required.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
