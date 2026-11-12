# Chart format, version 1

This document is the single, language-neutral specification of the ```` ```chart ```` block that agents write and the app draws. Two programs implement it: the browser control `App.ui.chart` (`the_one/interfaces/web/static/js/ui/chart.js`) and the Python validator `the_one/visuals/chart_spec.py` (which the eval check and the connector image renderer use). They are kept equal by one shared corpus, `tests/fixtures/charts/`:

- `valid/*.json`: every file must be accepted.
- `invalid/*.json` and `invalid/expected.json`: every file must be refused with exactly the sentence `expected.json` gives it.
- `number-format.json`: `[value, unit, tick text, full text]` rows both formatters must reproduce.

A new rule lands in this document, the corpus and both implementations in the same change. The sentences in "Error sentences" below are the only source of the wording: `tests/test_chart_spec.py` fails if the corpus and this section disagree.

## The block

A chart is a fenced code block whose info string's first word is exactly `chart` (lowercase). Its body is one JSON object. By convention `type` is the first key: the streaming placeholder reads the type from the start of the object, and an object that puts `type` later is drawn correctly but its placeholder stays generic.

````
```chart
{"type": "bar", "x": {"values": ["Q1", "Q2", "Q3"]}, "series": [{"values": [12, 19, 7]}]}
```
````

Any other language, including `json`, is an ordinary code block.

## Keys

Unknown keys are ignored at every level. Every known key is checked strictly. Strings are measured in Unicode code points (one emoji is one character, however a language stores it). Numbers are JSON numbers: `true` and `false` are not numbers, and `NaN`, `Infinity`, `-Infinity` and a number too large to be finite (such as `1e999`) are refused.

| Key | Meaning |
|---|---|
| `type` (required) | `bar`, `line`, `area`, `scatter`, `pie` or `sparkline`. |
| `title` | Text, at most 120 characters. |
| `x` | Object with `label` (text), `values` and `scale` (`linear`, the default, or `log`). `values` are the categories or x positions, strings or numbers, at least one, none repeated; required for every type except `scatter` (where they are ignored) and `sparkline` (which ignores `x` entirely). `scale: "log"` is for `scatter` only. |
| `y` | Optional object with `label` (text), `unit` (text, at most 12 characters), `scale`, `min` and `max` (numbers, `min` below `max`; with a log scale `min` must be above 0). |
| `y2` | A right-hand axis with the same keys as `y`. Only `bar`, `line` and `area` read it; on other types it is ignored. |
| `series` (required) | One to eight objects. `name` (text; required when there are two or more series, optional for one), `values`, optional `axis` (`left`, the default, or `right`, which needs `y2`) and optional `type` (`bar` or `line`, only in a `bar` or `line` chart, to mix bars and a line). |
| `stacked` | Boolean. Stacks bar series and area series per category. Ignored by other types. |
| `annotations` | At most five reference lines: `{"axis": "y" or "y2" or "x", "value": ..., "label": "..."}`. For `y` and `y2` the value is a number; for `x` it is one of `x.values` (a number for a `scatter`). `label` is optional text. Ignored by `pie` and `sparkline`. |

`series[].values`:

- `bar`, `line`, `area`: one number or `null` per `x.values` entry. `null` is a gap: a line or area breaks, a bar is absent, the table cell is empty.
- `scatter`: `[x, y]` pairs of numbers, any count. No `null`.
- `pie`: exactly one series with one non-negative number per slice (`x.values` names the slices); the total must be above 0, at most 12 slices. A `0` slice is valid: it is drawn with zero width and kept in the table.
- `sparkline`: one series, numbers or `null`, drawn as a compact row without axes, legend or "Show data". `x`, `y2`, `stacked` and `annotations` are ignored; `title` and `y.unit` are read.

Limits: 8 series; 2,000 values in all (a `null` counts as a value; a scatter point counts as one); 200 categories; 12 pie slices; 5 annotations; a label (a category, an axis label, a series name or an annotation label) at most 60 characters.

Axis rules the renderers share:

- Bars include 0 on the axis they are drawn against (the left axis, or `y2` for a bar series with `"axis": "right"`). On a log axis a bar starts at the bottom of the axis. An axis with only line or point series is fitted to its data with padding; if every value is equal the domain still gets a non-zero span.
- A log scale draws ticks at powers of ten and needs every value on it above 0. A stacked chart cannot use one.
- Normalisation: `scale` is `linear`, `axis` is `left` and `stacked` is `false` unless given. A key a type does not read is dropped before any check, so it can never cause an error.

## Examples

One minimal spec per type, `type` first:

```json
{"type": "bar", "x": {"values": ["Q1", "Q2", "Q3"]}, "series": [{"values": [12, 19, 7]}]}
{"type": "line", "x": {"values": [1, 2, 3, 4, 5]}, "series": [{"values": [3, 5, 4, 8, 6]}]}
{"type": "area", "x": {"values": ["Jan", "Feb", "Mar"]}, "series": [{"name": "Sessions", "values": [100, 140, 120]}]}
{"type": "scatter", "series": [{"values": [[1, 2], [2, 3.5], [3, 3]]}]}
{"type": "pie", "x": {"values": ["Chrome", "Firefox", "Safari"]}, "series": [{"values": [62, 18, 15]}]}
{"type": "sparkline", "series": [{"values": [3, 5, 4, 8, 6, 9, 7]}]}
```

One spec using every optional key (`tests/fixtures/charts/valid/bar-all-keys.json`):

```json
{
  "type": "bar",
  "title": "Revenue and margin by quarter",
  "x": {"label": "Quarter", "values": ["Q1", "Q2", "Q3", "Q4"]},
  "y": {"label": "Revenue", "unit": "$", "scale": "linear", "min": 0, "max": 200000},
  "y2": {"label": "Margin", "unit": "%", "scale": "linear", "min": 0, "max": 100},
  "series": [
    {"name": "Revenue", "values": [120000, 135000, 150000, 180000]},
    {"name": "Margin", "values": [31, 34.5, null, 40], "axis": "right", "type": "line"}
  ],
  "stacked": false,
  "annotations": [
    {"axis": "y", "value": 150000, "label": "Target"},
    {"axis": "y2", "value": 35, "label": "Margin goal"},
    {"axis": "x", "value": "Q3", "label": "Launch"}
  ]
}
```

## Number display

Display is locale-neutral and defined here, never by the system locale (the desktop engine on Linux follows it).

- **Tick text** (axis ticks, log ticks at powers of ten): a compact form with at most three significant digits, rounded half up on the exact value. From 1,000 the suffixes `k` (thousand), `M` (million) and `B` (billion) are used; above 999 billion the number stays in `B`. Trailing zeros are dropped: `1k`, `1.23k`, `12.3k`, `123k`, `3.4M`, `2.5B`. A value below 1 keeps its digits (`0.5`, `0.01`, `0.00012`). A value below `0.000001` or from `1e15` up is written `1.2e-7` or `1e15`. Zero is `0`. A negative value starts with `-`.
- **Full text** (tooltip and table): the whole value with `,` grouping of the integer part and `.` decimals, at most six decimals, trailing zeros dropped (`1,234,567.891`). The same exponent form applies at the same extremes. A value that rounds to zero is `0`.
- **Units**: `$`, `€`, `£` and `¥` are prefixes (`$150k`, `-$2.5k`, with the sign before the unit). Any other unit is a suffix after a thin space, U+2009 (`45 %`, `1.5k ms`).

`number-format.json` holds the examples both formatters must reproduce.

## Text width

Axis text (tick labels, the margin they need, how far a category label is cut before its ellipsis) is sized by the width the text really has. The browser control **measures** it: it appends a probe `<text>` with the label's own class to the chart's live `<svg>`, reads `getComputedTextLength()` and removes it, caching the result by class and string and clearing that cache when the web fonts finish loading. A fixed 6.4 px per code point is only the fallback when measuring is impossible (a detached chart, an error, or a length of 0 for a non-empty string). A server-side renderer has no browser to ask, so it sizes text from the font's own metrics (advance widths for the font it draws with), not from a per-character estimate; see "Images" below.

## Images

`the_one/visuals/chart_image.py` (M35 Flight 3) draws any valid chart as a PNG for a chat platform that cannot run the browser control.

- **Look.** Always the light theme (the palette constants equal the `[data-theme="light"]` values in `css/tokens.css`, pinned by a test), on a `--surface` card with a 1-logical-px `--border` edge and rounded corners. Density is 2x: every logical pixel is two image pixels. Shapes are drawn at 4x and reduced, so edges are smooth.
- **Sizes (logical pixels; the file is twice that).** A cartesian chart or a pie is 640 wide and `240 + 20 * title_rows + 20 * legend_rows` high, so 1280 pixels wide. `title_rows` is 1 when there is a title (one line, semibold 13 px, cut with an ellipsis to the width), else 0. `legend_rows` is 0 when the browser shows no legend (one unnamed series, not a pie), else the number of rows the legend (11 px text, a colour swatch) wraps into at 640; entries flow left to right like `flex-wrap`. A sparkline is 320 wide and `64 + 20 * title_rows` high (the browser's 140 x 32 geometry scaled up), so 640 pixels wide; a titled sparkline gets the title row above it because the image stands alone. The title and legend rows sit outside the 240 of the drawing area, as the browser's caption sits outside its SVG.
- **Font and text width.** The bundled Geist Regular and SemiBold TTFs (`the_one/visuals/fonts/`, SIL OFL, Geist 1.8.0, SHA-256 pinned by a test) are loaded with Pillow's `BASIC` layout engine, never RAQM, so no host library can change a width. A string's width is the sum of each character's own advance read at `size = unitsPerEm` (the design units) and scaled to the size, and text is drawn one character at a time at the accumulated positions. Widths are therefore a property of the font file on every host, and server text sits slightly wider than the browser's kerned text. The doctor gate `chart images` requires the exact design-unit width of a fixed ASCII string. The thin space before a suffix unit is drawn as an ordinary space (Geist has no glyph for it).
- **Missing glyphs.** A character Geist lacks (CJK, emoji) draws as the font's missing-glyph box. Because of that, a title also goes out as platform text beside the image.
- **Ticks and thinning.** The y (and y2) tick values come from the one shared corpus `tests/fixtures/charts/ticks.json`, which both the browser control and the server renderer are tested against. X-label thinning is per renderer: each thins with its own measured widths, so the two may keep different labels.
- **Limits.** A chart at the format limits (2000 values over 8 series, a log y axis, 5 annotations) draws in well under half a second, and a PNG over 8 MB is refused with `ChartImageError`.

## Error sentences

A text that breaks a rule is refused with one plain sentence, naming the series or key when there is one. The first error found wins, checking in this order: JSON syntax; object shape; `type`; `title`; `stacked`; the axes `x`, `y`, `y2` (inside an axis: `label`, `unit`, `scale`, `min`, `max`, then `x.values`); each series in turn; the cross-series checks (pie series count, duplicate names, length against `x`, nothing to draw, pie values, log-scale values, stacking on a log scale); `annotations`; and last the limits (values, categories, series, slices, annotations). The examples below are the exact sentences the corpus pins; `{n}`-style numbers, series names and axis names vary with the input, and a series without a name is called `Series 1`, `Series 2` and so on.

| Rule | Sentence |
|---|---|
| Not valid JSON, including `NaN`, `Infinity` and a number too large to be finite | `The chart text isn't valid JSON.` |
| Valid JSON that is not an object | `The chart must be one JSON object.` |
| No `type` | `The chart needs a "type".` |
| `type` is not one of the six | `The chart "type" must be one of bar, line, area, scatter, pie or sparkline.` |
| `title` is not text | `The "title" must be text.` |
| `title` is over 120 characters | `The title is 121 characters; the limit is 120.` |
| `stacked` is not true or false | `The "stacked" setting must be true or false.` |
| An axis is not an object | `Axis "x" must be an object.` |
| An axis `label` is not text | `Axis "x" has a "label" that isn't text.` |
| A label (category, axis, series or annotation) is over 60 characters | `A label is 61 characters; the limit is 60.` |
| A `unit` is not text | `Axis "y" has a "unit" that isn't text.` |
| A `unit` is over 12 characters | `A unit is 13 characters; the limit is 12.` |
| `scale` is not `linear` or `log` | `Axis "y" has a "scale" that isn't linear or log.` |
| `x.scale` is `log` on a chart that is not a scatter | `A log scale on axis "x" only works on a scatter chart.` |
| `min` is not a number | `Axis "y" has a "min" that isn't a number.` |
| `max` is not a number | `Axis "y2" has a "max" that isn't a number.` |
| `min` is not below `max` | `Axis "y" needs "min" to be below "max".` |
| A log axis has a `min` of 0 or less | `Axis "y" has a log scale, so "min" must be above 0.` |
| `x.values` is missing, not a list or empty | `Axis "x" needs a list of "values" with at least one entry.` |
| An `x.values` entry is neither text nor a number | `Axis "x" has a value that is neither text nor a number.` |
| `x.values` repeats an entry | `Axis "x" lists the same value twice.` |
| `series` is missing, not a list or empty | `The chart needs a "series" list with at least one entry.` |
| A series is not an object | `Series 1 isn't an object.` |
| A series has no usable `name` while there are two or more | `Series 2 needs a "name".` |
| A series `type` is not `bar` or `line` | `Series "S" has a "type" that isn't bar or line.` |
| A series `type` on a chart that is not a bar or line chart | `Series "S" has its own "type", which only bar and line charts allow.` |
| A series `axis` is not `left` or `right` | `Series "S" has an "axis" that isn't left or right.` |
| A series is on the right axis and there is no `y2` | `Series "Visits" is on the right axis, but the chart has no "y2".` |
| A series has no `values` list | `Series "S" needs a list of "values".` |
| A value is not a number or `null` (a boolean, text, a non-finite number) | `Series "S" has a value that isn't a number or null.` |
| A pie value is not a number (a `null` too) | `Series "Share" has a value that isn't a number.` |
| A scatter point is not an `[x, y]` pair of numbers | `Series "Runs" has a point that isn't an [x, y] pair of numbers.` |
| A pie has other than one series | `A pie chart takes one series; this one has 2.` |
| Two series share a name | `Two series are both named "Sales".` |
| A series length differs from `x.values` | `Series "2024" has 11 values, but the x axis has 12.` |
| A series has nothing to draw (empty or all `null`) | `Series "Empty" has no values to draw.` or, for a series without a name, `Series 1 has no values to draw.` |
| A pie value is negative | `Series "Share" has a negative value; a pie needs every slice at 0 or more.` |
| A pie total is not above 0 | `A pie chart needs a total above 0.` |
| A log y axis has a value of 0 or less | `Series "Latency" has a value of 0 or less; a log scale needs every value above 0.` |
| A log x axis has an x of 0 or less | `Series "Runs" has an x value of 0 or less; a log scale needs every x above 0.` |
| A stacked chart has a log axis | `A stacked chart can't use a log scale.` |
| `annotations` is not a list | `The "annotations" must be a list.` |
| An annotation is not an object | `Annotation 2 isn't an object.` |
| An annotation `axis` is not `y`, `y2` or `x` | `Annotation 1 needs an "axis" of y, y2 or x.` |
| An annotation is on `y2` and there is no `y2` | `Annotation 1 is on "y2", but the chart has no "y2".` |
| A `y`, `y2` or scatter-`x` annotation value is not a number | `Annotation 1 needs a numeric "value".` |
| An `x` annotation is not one of `x.values` | `Annotation 1 is at a category that isn't in the x values.` |
| An annotation `label` is not text | `Annotation 1 has a "label" that isn't text.` |
| An annotation sits at 0 or less on a log axis | `Annotation 1 is on a log axis, so its value must be above 0.` |
| More than 2,000 values (counted before the other limits) | `This chart has 2046 values; the limit is 2000.` |
| More than 200 categories | `This chart has 201 categories; the limit is 200.` |
| More than 8 series | `This chart has 9 series; the limit is 8.` |
| More than 12 pie slices | `This pie chart has 13 slices; the limit is 12.` |
| More than 5 annotations | `This chart has 6 annotations; the limit is 5.` |

## Palette appendix

The server renderer (Flight 3) reads its colours from here instead of deriving them again. The tokens live in `the_one/interfaces/web/static/css/tokens.css` (mirrored in `tests/browser/design_tokens.py`); series *N* uses `--chart-N`, the 9th series would repeat from 1 (a chart never has more than 8 series; a pie of up to 12 slices repeats the colours and relies on the legend, the tooltip and the table). Every colour is at least 3.0:1 (WCAG 1.4.11, non-text) against the page (`--bg`), the chart card (`--surface`) and the assistant bubble (`--surface-translucent` composited over `--bg`), in both themes (gated in `tests/test_design_tokens_a11y.py`).

| Token | Role | Dark | Light |
|---|---|---|---|
| `--chart-1` | series 1 (violet) | `#a78bfa` | `#6d28d9` |
| `--chart-2` | series 2 (cyan) | `#22d3ee` | `#0e7490` |
| `--chart-3` | series 3 (amber) | `#fbbf24` | `#b45309` |
| `--chart-4` | series 4 (pink) | `#f472b6` | `#be185d` |
| `--chart-5` | series 5 (green) | `#4ade80` | `#15803d` |
| `--chart-6` | series 6 (orange) | `#fb923c` | `#c2410c` |
| `--chart-7` | series 7 (blue) | `#60a5fa` | `#1d4ed8` |
| `--chart-8` | series 8 (slate) | `#94a3b8` | `#475569` |
| `--chart-ref` | reference lines and their labels | `#fbbf24` | `#b45309` |

Grid, axis and text reuse existing tokens: gridlines `--border` (dark `#26272c`, light `#e4e4e7`), the baseline `--border-strong` (`#4a4b55`, `#a1a1aa`), tick text `--fg-tertiary` (`#9a9ca4`, `#5f5f68`), axis labels `--fg-secondary` (`#adafb7`, `#52525b`), the card fill `--surface` (`#17181c`, `#fafafa`). Line series from the fifth on are also dashed (`6 3`, `2 3`, `8 3 2 3`, `1 4`), so series are never told apart by colour alone. Reference lines are dashed `4 3`, 1.5 px, in `--chart-ref`.
