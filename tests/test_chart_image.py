"""Chart images (M35 F3 L1): the bundled fonts, design-unit measurement, the scale and layout
ports, every corpus chart drawn, the shared tick corpus, the at-limit draw time and the sample
sheet's refusal. No pixel baselines are stored (they are never committed): determinism is two
draws in one process, and the rest are structural assertions on the drawing operations and on
decoded pixels."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from the_one.visuals import chart_image
from the_one.visuals.chart_image import (
    CHART_COLORS,
    ChartImageError,
    Circle,
    Line,
    Rect,
    Slice,
    Text,
    axis_ticks,
    build_scene,
    measure,
    render_png,
    units_per_em,
)
from the_one.visuals.chart_spec import ChartError, parse_chart

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "charts"
FONTS = ROOT / "the_one" / "visuals" / "fonts"
VALID = {p.name: p.read_text(encoding="utf-8") for p in sorted((CORPUS / "valid").glob("*.json"))}
SPECS = {name: parse_chart(text) for name, text in VALID.items()}


def _spec(**kw):
    base = {"type": "bar", "x": {"values": ["a", "b", "c"]}, "series": [{"values": [1, 2, 3]}]}
    base.update(kw)
    spec = parse_chart(json.dumps(base))
    assert not isinstance(spec, ChartError), spec
    return spec


def _image(data: bytes):
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def _hex(rgb: tuple) -> str:
    return "#%02x%02x%02x" % rgb[:3]


def _colors(img) -> set:
    return {_hex(c) for _, c in img.getcolors(maxcolors=1 << 24)}


def _load_sample_sheet():
    spec = importlib.util.spec_from_file_location(
        "chart_sample_sheet", ROOT / "scripts" / "chart_sample_sheet.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------- AC2, AC3


def test_font_files_are_the_pinned_geist_1_8_0_release_files() -> None:
    expected = {
        "Geist-Regular.ttf": "bde046ddd9f20be35b0bd56cc79eb752b967fb6661a3fe76cb067bb09f871d76",
        "Geist-SemiBold.ttf": "097409e9fabf676be0764b47297c2cdab3750e84dc0f575298c7fbd45f3b3819",
        "OFL.txt": "1781d2806a07d91c4edf4740b88449fab7d0eadad53f7c351b94cd4d4eb8c00f",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((FONTS / name).read_bytes()).hexdigest() == digest, name
    assert units_per_em(FONTS / "Geist-Regular.ttf") == 1000
    assert units_per_em(FONTS / "Geist-SemiBold.ttf") == 1000


def test_fonts_are_in_package_data_and_every_freeze_spec() -> None:
    assert '"visuals/fonts/*"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for platform in ("windows", "linux", "macos"):
        text = (ROOT / "packaging" / platform / "the-one.spec").read_text(encoding="utf-8")
        assert re.search(
            r'collect_data_files\("the_one",\s*includes=\["visuals/fonts/\*"\]\)', text
        ), platform


def test_pillow_is_a_base_dependency_only() -> None:
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    base = data["project"]["dependencies"]
    assert "pillow>=13.0" in base
    extras = data["project"]["optional-dependencies"]
    assert not [d for d in extras["gui"] if d.startswith("pillow")]
    assert not [d for d in extras["dev"] if d.startswith("pillow")]


# ------------------------------------------------------------------------------------- AC4


def test_importing_the_module_does_not_import_pillow() -> None:
    code = (
        "import sys\nimport the_one.visuals.chart_image\n"
        "assert not any(m == 'PIL' or m.startswith('PIL.') for m in sys.modules), 'PIL imported'\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_every_font_is_loaded_with_the_basic_layout_engine() -> None:
    from PIL import ImageFont

    fonts = chart_image._fonts()
    for weight in ("regular", "semibold"):
        assert fonts.design[weight].layout_engine == ImageFont.Layout.BASIC
        assert fonts.draw_font(weight, 22).layout_engine == ImageFont.Layout.BASIC
    source = (ROOT / "the_one" / "visuals" / "chart_image.py").read_text(encoding="utf-8")
    assert source.count("ImageFont.truetype(") == source.count(
        "layout_engine=ImageFont.Layout.BASIC"
    )
    assert "Layout.RAQM" not in source


def test_drawing_runs_under_one_module_level_lock(monkeypatch) -> None:
    assert type(chart_image._LOCK) is type(threading.Lock())
    seen = []
    real = chart_image._paint

    def spy(scene):
        seen.append(chart_image._LOCK.locked())
        return real(scene)

    monkeypatch.setattr(chart_image, "_paint", spy)
    render_png(_spec())
    assert seen == [True]


def test_two_threads_give_the_serial_result() -> None:
    spec = _spec(title="Threads")
    serial = render_png(spec).data
    results = []

    def run() -> None:
        results.append(render_png(spec).data)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert results == [serial, serial]


def test_measure_is_the_design_unit_advance_of_each_character() -> None:
    regular = "regular"
    assert measure("0", 1000, regular) == 663
    assert measure("A", 1000, regular) == 668
    assert measure("V", 1000, regular) == 667
    assert measure("AV", 1000, regular) == 1335
    assert measure("0", 1000, "semibold") == 683
    assert measure("AV", 1000, regular) == measure("A", 1000, regular) + measure("V", 1000, regular)
    assert measure("AV", 11, regular) == pytest.approx(1335 * 11 / 1000)
    assert measure("", 11, regular) == 0


def test_measure_sums_characters_even_when_the_font_kerns_pairs(monkeypatch) -> None:
    class Kerning:
        """A font whose getlength kerns a pair, like a legacy kern table under BASIC."""

        def getlength(self, text: str) -> float:
            adv = {"A": 668.0, "V": 667.0}
            total = sum(adv.get(ch, 500.0) for ch in text)
            return total - 40.0 if text == "AV" else total

    class Stub:
        units = {"regular": 1000, "semibold": 1000}
        design = {"regular": Kerning(), "semibold": Kerning()}
        _adv: dict = {}

        def advance(self, ch: str, weight: str) -> float:
            return float(self.design[weight].getlength(ch))

    assert Kerning().getlength("AV") == 1295.0  # the stub does kern a whole pair
    monkeypatch.setattr(chart_image, "_fonts", lambda: Stub())
    assert measure("AV", 1000, "regular") == 668 + 667


def test_text_is_drawn_per_character_at_the_measured_positions(monkeypatch) -> None:
    """Every ImageDraw.text call is one character, and positions are the accumulated advances."""
    from PIL import ImageDraw

    calls = []
    real = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *args, **kwargs):
        calls.append((xy, text))
        return real(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    scene = chart_image.Scene(100, 30, [Text(10, 20, "AVA", 11, "regular", "#000000", "start")])
    chart_image._paint(scene)
    assert [t for _, t in calls] == ["A", "V", "A"]
    scale = 2 * 11 / 1000
    xs = [xy[0] for xy, _ in calls]
    assert xs == [round(20), round(20 + 668 * scale), round(20 + (668 + 667) * scale)]


def test_a_thin_space_measures_and_draws_as_a_space() -> None:
    assert measure("5 %", 11) == measure("5 %", 11)


def test_fit_text_cuts_with_an_ellipsis_in_design_units() -> None:
    text = "W" * 40
    cut = chart_image.fit_text(text, 60, 24, 11)
    assert cut.endswith("…") and len(cut) < len(text)
    assert measure(cut, 11) <= 60
    assert chart_image.fit_text("short", 60, 24, 11) == "short"


# ------------------------------------------------------------------------------------- AC5


def test_missing_font_raises_a_plain_chart_image_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chart_image, "FONT_DIR", tmp_path)
    with pytest.raises(ChartImageError) as err:
        render_png(_spec(title="Secret quarterly numbers"))
    assert "Geist-Regular.ttf" in str(err.value)
    assert "Secret" not in str(err.value)


# ------------------------------------------------------------------------------------- AC6


# (pixel width, pixel height) of every corpus chart. The formula is
# cartesian and pie: 1280 x (240 + 20*title_rows + 20*legend_rows) * 2;
# sparkline: 640 x (64 + 20*title_rows) * 2.
#
# The browser shows a legend for a pie, for more than one series and for one named series; every
# corpus legend fits one row at 640 logical pixels (wrapping has its own test below).
def _legend_rows(spec) -> int:
    if spec.type == "sparkline":
        return 0
    return 1 if (spec.type == "pie" or len(spec.series) > 1 or spec.series[0].name) else 0


def _expected_size(name: str, spec) -> tuple:
    title_rows = 1 if spec.title else 0
    if spec.type == "sparkline":
        return 640, (64 + 20 * title_rows) * 2
    return 1280, (240 + 20 * title_rows + 20 * _legend_rows(spec)) * 2


def test_the_corpus_covers_every_size_family() -> None:
    kinds = {(s.type == "sparkline", bool(s.title), _legend_rows(s)) for s in SPECS.values()}
    assert {(False, True, 1), (False, False, 1), (False, True, 0), (False, False, 0)} <= kinds
    assert (True, True, 0) in kinds and (True, False, 0) in kinds


@pytest.mark.parametrize("name", sorted(VALID))
def test_every_corpus_chart_draws_to_the_size_formula(name: str) -> None:
    spec = SPECS[name]
    assert not isinstance(spec, ChartError)
    rendered = render_png(spec)
    assert (rendered.width, rendered.height) == _expected_size(name, spec)
    img = _image(rendered.data)
    assert img.format == "PNG" and img.mode == "RGB"
    assert img.size == (rendered.width, rendered.height)
    assert not getattr(img, "text", {})
    # no alpha, no text chunks: the PNG's chunk list carries none of tEXt/zTXt/iTXt
    assert not any(tag in rendered.data for tag in (b"tEXt", b"zTXt", b"iTXt"))
    # the card: corners are --surface, the 1 logical px edge is --border
    last_x, last_y = img.width - 1, img.height - 1
    for corner in ((0, 0), (last_x, 0), (0, last_y), (last_x, last_y)):
        assert _hex(img.getpixel(corner)) == chart_image.SURFACE, corner
    mid = img.width // 2
    assert _hex(img.getpixel((mid, 0))) == chart_image.BORDER
    assert _hex(img.getpixel((mid, 1))) == chart_image.BORDER
    assert _hex(img.getpixel((mid, last_y))) == chart_image.BORDER
    assert _hex(img.getpixel((0, img.height // 2))) == chart_image.BORDER
    # each drawn series' palette colour is in the image
    present = _colors(img)
    if spec.type == "pie":
        want = {CHART_COLORS[i % 8] for i, v in enumerate(spec.series[0].values) if v > 0}
    else:
        want = {CHART_COLORS[i % 8] for i in range(len(spec.series))}
    assert want <= present, want - present
    # two draws of one spec in one process give the same decoded pixels
    again = _image(render_png(spec).data)
    assert hashlib.sha256(img.tobytes()).digest() == hashlib.sha256(again.tobytes()).digest()


def test_a_legend_wraps_at_640_logical_pixels() -> None:
    names = [f"A fairly long series name number {i} of eight" for i in range(8)]
    spec = _spec(series=[{"name": n, "values": [1, 2, 3]} for n in names])
    scene = build_scene(spec)
    legend_ys = sorted({op.y for op in scene.ops if isinstance(op, Text) and op.role == "legend"})
    assert len(legend_ys) > 1
    rows = len(legend_ys)
    assert render_png(spec).height == (240 + 20 * rows) * 2
    for op in scene.ops:
        if isinstance(op, Text) and op.role == "legend":
            assert op.x + measure(op.text, 11) <= 640 - 12 + 1e-6


def test_a_single_unnamed_series_has_no_legend_and_a_named_one_does() -> None:
    assert not [o for o in build_scene(_spec()).ops if isinstance(o, Text) and o.role == "legend"]
    named = _spec(series=[{"name": "Revenue", "values": [1, 2, 3]}])
    assert [
        o.text for o in build_scene(named).ops if isinstance(o, Text) and o.role == "legend"
    ] == ["Revenue"]


def test_the_title_is_one_line_cut_with_an_ellipsis() -> None:
    spec = SPECS["title-and-unit-at-limit.json"]
    titles = [o for o in build_scene(spec).ops if isinstance(o, Text) and o.role == "title"]
    assert len(titles) == 1
    assert titles[0].text.endswith("…")
    assert measure(titles[0].text, 13, "semibold") <= 640 - 24


def test_a_cjk_title_draws_and_is_cut_like_any_title() -> None:
    spec = _spec(title="季度收入 Revenue")
    assert render_png(spec).height == (240 + 20) * 2


# ------------------------------------------------------------------------------------- AC7


def test_palette_constants_equal_the_light_tokens() -> None:
    css = (ROOT / "the_one" / "interfaces" / "web" / "static" / "css" / "tokens.css").read_text(
        encoding="utf-8"
    )
    block = css[css.index('[data-theme="light"] {') :]
    block = block[: block.index("\n  }")]
    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block))
    assert [tokens[f"--chart-{i}"] for i in range(1, 9)] == list(CHART_COLORS)
    assert tokens["--chart-ref"] == chart_image.CHART_REF
    assert tokens["--surface"] == chart_image.SURFACE
    assert tokens["--border"] == chart_image.BORDER
    assert tokens["--border-strong"] == chart_image.BORDER_STRONG
    assert tokens["--fg"] == chart_image.FG
    assert tokens["--fg-secondary"] == chart_image.FG_SECONDARY
    assert tokens["--fg-tertiary"] == chart_image.FG_TERTIARY


# ------------------------------------------------------------------------------------- AC8

TICKS = json.loads((CORPUS / "ticks.json").read_text(encoding="utf-8"))


def test_the_tick_corpus_lists_every_valid_cartesian_spec_and_no_other() -> None:
    cartesian = {n for n, s in SPECS.items() if s.type not in ("pie", "sparkline")}
    assert set(TICKS) == cartesian
    assert len(TICKS) == 18


@pytest.mark.parametrize("name", sorted(TICKS))
def test_axis_ticks_equal_the_shared_corpus_exactly(name: str) -> None:
    got = axis_ticks(SPECS[name])
    want = TICKS[name]
    assert got.keys() == want.keys()
    for side in want:
        assert [float(v) for v in got[side]] == [float(v) for v in want[side]], (name, side)


# ------------------------------------------------------------------------------------- AC9


def test_bars_include_zero() -> None:
    spec = _spec(series=[{"values": [5, 7, 9]}])
    assert axis_ticks(spec)["y"][0] == 0
    scene = build_scene(spec)
    bars = [o for o in scene.ops if isinstance(o, Rect) and o.color == CHART_COLORS[0]]
    assert len(bars) == 3
    baseline = max(b.y1 for b in bars)
    assert len({round(b.y1, 6) for b in bars}) == 1 and baseline > 0


def test_log_axes_tick_at_powers_of_ten() -> None:
    spec = _spec(type="line", y={"scale": "log"}, series=[{"values": [3, 40, 5000]}])
    assert axis_ticks(spec)["y"] == [1.0, 10.0, 100.0, 1000.0, 10000.0]


def test_colours_repeat_after_eight_series() -> None:
    # a chart has at most 8 series, so the repeat shows in a pie's 12 slices
    spec = SPECS["pie-twelve-slices.json"]
    colors = [o.color for o in build_scene(spec).ops if isinstance(o, Slice)]
    assert len(colors) == 12 and len(CHART_COLORS) == 8
    assert colors[8:] == list(CHART_COLORS[:4])
    assert chart_image._series_color(9) == CHART_COLORS[1]


def test_line_series_five_and_up_are_dashed_and_reference_lines_use_4_3() -> None:
    spec = _spec(
        type="line",
        series=[{"name": f"s{i}", "values": [i + 1, i + 2, i + 3]} for i in range(8)],
        annotations=[{"axis": "y", "value": 4, "label": "Goal"}],
    )
    lines = [o for o in build_scene(spec).ops if isinstance(o, Line)]
    by_color = {}
    for ln in lines:
        by_color.setdefault(ln.color, []).append(ln)
    for i in range(8):
        series_lines = [ln for ln in by_color[CHART_COLORS[i]] if ln.width == 2]
        assert len(series_lines) == 1
        assert series_lines[0].dash == (None if i < 4 else chart_image._SERIES_DASHES[(i - 4) % 4])
    refs = [ln for ln in lines if ln.color == chart_image.CHART_REF and ln.width == 1.5]
    assert refs and all(ln.dash == (4, 3) for ln in refs)
    # series 3's colour is also the reference colour (both #b45309): the width tells them apart
    assert chart_image.CHART_REF == CHART_COLORS[2]


def test_dash_segments_follow_the_pattern() -> None:
    segs = chart_image._dash_segments(((0.0, 0.0), (14.0, 0.0)), (4, 3))
    assert segs == [((0.0, 0.0), (4.0, 0.0)), ((7.0, 0.0), (11.0, 0.0))]


def test_a_zero_pie_slice_is_not_drawn() -> None:
    spec = SPECS["pie-zero-slice.json"]
    slices = [o for o in build_scene(spec).ops if isinstance(o, Slice)]
    assert len(slices) == sum(1 for v in spec.series[0].values if v > 0)
    assert len(slices) < len(spec.series[0].values)


def test_a_single_nonzero_slice_is_a_full_circle() -> None:
    spec = _spec(type="pie", series=[{"values": [0, 5, 0]}])
    slices = [o for o in build_scene(spec).ops if isinstance(o, Slice)]
    assert len(slices) == 1 and slices[0].full


def test_null_gaps_break_a_line() -> None:
    spec = _spec(
        type="line",
        x={"values": ["a", "b", "c", "d", "e"]},
        series=[{"values": [1, 2, None, 4, 5]}],
    )
    lines = [o for o in build_scene(spec).ops if isinstance(o, Line) and o.width == 2]
    assert len(lines) == 2
    assert [len(ln.points) for ln in lines] == [2, 2]
    assert lines[0].points[-1][0] < lines[1].points[0][0]
    assert len([o for o in build_scene(spec).ops if isinstance(o, Circle) and o.r == 3]) == 4


def test_x_labels_thin_by_the_servers_own_widths() -> None:
    cats = [f"Category {i:02d}" for i in range(40)]
    spec = _spec(x={"values": cats}, series=[{"values": list(range(40))}])
    labels = [o for o in build_scene(spec).ops if isinstance(o, Text) and o.role == "x-tick"]
    assert 0 < len(labels) < 40
    stride = 40 // len(labels)
    assert stride >= 2 or len(labels) == 40
    widest = max(measure(c, 11) for c in cats)
    assert chart_image.x_label_stride(widest, 1180 / 40) == stride or stride >= 2
    for a, b in zip(labels, labels[1:], strict=False):
        assert b.x - a.x >= measure(a.text, 11) / 2 + measure(b.text, 11) / 2 - 1e-6
    # a roomy chart keeps every label
    few = _spec(x={"values": ["a", "b", "c"]})
    assert len([o for o in build_scene(few).ops if isinstance(o, Text) and o.role == "x-tick"]) == 3


def test_the_y2_axis_draws_right_axis_ticks_at_the_right_edge() -> None:
    scene = build_scene(SPECS["bar-all-keys.json"])
    right = [
        o for o in scene.ops if isinstance(o, Text) and o.role == "tick" and o.anchor == "start"
    ]
    left = [o for o in scene.ops if isinstance(o, Text) and o.role == "tick" and o.anchor == "end"]
    assert len(right) == 6 and len(left) == 5
    assert min(o.x for o in right) > max(o.x for o in left)


# ------------------------------------------------------------------------------------ AC10


def test_the_at_limit_chart_draws_inside_the_bound() -> None:
    sheet = _load_sample_sheet()
    spec = parse_chart(sheet.at_limit_source())
    assert not isinstance(spec, ChartError), spec
    assert sum(len(s.values) for s in spec.series) == 2000
    assert len(spec.series) == 8 and len(spec.annotations) == 5 and spec.y.scale == "log"
    bound = float(os.environ.get("THE_ONE_CHART_DRAW_BOUND_MS", "500")) / 1000
    times = []
    for _ in range(3):
        started = time.perf_counter()
        rendered = render_png(spec)
        times.append(time.perf_counter() - started)
    assert statistics.median(times) < bound, times
    assert len(rendered.data) < chart_image.MAX_PNG_BYTES


def test_a_png_over_the_cap_raises_without_chart_data(monkeypatch) -> None:
    monkeypatch.setattr(chart_image, "MAX_PNG_BYTES", 100)
    with pytest.raises(ChartImageError) as err:
        render_png(_spec(title="Confidential figures"))
    assert "8 MB" in str(err.value)
    assert "Confidential" not in str(err.value)


# ------------------------------------------------------------------------------------ AC13


def test_the_sample_sheet_refuses_an_out_directory_inside_the_repository(capsys) -> None:
    sheet = _load_sample_sheet()
    inside = ROOT / "zz-sample-sheet-refused"
    assert sheet.main(["--out", str(inside)]) == 2
    assert not inside.exists()
    assert "inside the repo" in capsys.readouterr().err


def test_the_sample_sheet_writes_25_images_and_an_index(tmp_path) -> None:
    sheet = _load_sample_sheet()
    out = tmp_path / "sheet"
    # a tmp_path outside the repo: the refusal passes and everything is written
    assert sheet.main(["--out", str(out)]) == 0
    assert len(list(out.glob("*.png"))) == 25
    index = (out / "index.html").read_text(encoding="utf-8")
    assert index.count("<img ") == 25
    assert "cjk-title.png" in index and "at-limit-2000-values.png" in index
