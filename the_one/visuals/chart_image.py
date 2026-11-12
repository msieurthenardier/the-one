"""Chart images: draw a valid chart as a light-theme PNG (M35 F3 L1, flight DD4, DD5, DD10).

The layout mirrors the browser control (``static/js/ui/chart-scale.js`` and ``chart-layout.js``;
names are kept close to the JavaScript so the two can be diffed). The server draws with Pillow
and the bundled, SHA-pinned Geist TTFs under ``the_one/visuals/fonts/``.

Text width is a property of the font file, not of the host:

* every font is loaded with ``Layout.BASIC`` (RAQM is host-dependent and is never used);
* a string's width is the sum of each character's own advance, measured on a font loaded at
  ``size = unitsPerEm`` (the "design units"), then scaled to the logical size;
* text is drawn one character at a time at positions accumulated from the same advances, so
  what is drawn is what was measured, whatever tables (``kern`` or not) the font carries.

Pillow is imported inside functions only, so importing this module never imports ``PIL``.
All drawing runs under one module-level lock (FreeType faces are not shared safely).
"""

from __future__ import annotations

import io
import math
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

from the_one.visuals.chart_spec import Axis, ChartSpec, format_full, format_tick

# ---------------------------------------------------------------------------
# Constants: sizes, palette (pinned to the light block of css/tokens.css by a test)
# ---------------------------------------------------------------------------

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_FILES = {"regular": "Geist-Regular.ttf", "semibold": "Geist-SemiBold.ttf"}

DENSITY = 2  # output pixels per logical pixel
_SUPER = 4  # shapes are drawn at 4x and reduced to 2x (anti-aliasing)
MAX_PNG_BYTES = 8 * 1024 * 1024

WIDTH = 640  # logical width of a cartesian or pie image
SPARK_WIDTH = 320
SPARK_HEIGHT = 64
HEIGHT = 240  # logical height of the drawing area (chart-scale.js HEIGHT)
TITLE_ROW = 20
LEGEND_ROW = 20
PAD_X = 12  # logical left and right padding inside the card
TICK_SIZE = 11
TITLE_SIZE = 13
CARD_RADIUS = 8

CHART_COLORS = (
    "#6d28d9",  # --chart-1
    "#0e7490",  # --chart-2
    "#b45309",  # --chart-3
    "#be185d",  # --chart-4
    "#15803d",  # --chart-5
    "#c2410c",  # --chart-6
    "#1d4ed8",  # --chart-7
    "#475569",  # --chart-8
)
CHART_REF = "#b45309"  # --chart-ref
SURFACE = "#fafafa"  # --surface
BORDER = "#e4e4e7"  # --border
BORDER_STRONG = "#a1a1aa"  # --border-strong
FG = "#18181b"  # --fg
FG_SECONDARY = "#52525b"  # --fg-secondary
FG_TERTIARY = "#5f5f68"  # --fg-tertiary

# stroke-dasharray of .ui-chart-dash-1..4 (series 5 and up), and of .ui-chart-ref
_SERIES_DASHES = ((6, 3), (2, 3), (8, 3, 2, 3), (1, 4))
REF_DASH = (4, 3)

# Geist has no glyph for the thin space the unit formatter puts before a suffix unit (nor the
# no-break spaces), so those draw and measure as an ordinary space instead of a missing box.
_SPACES = str.maketrans({" ": " ", " ": " ", " ": " "})

_LOCK = threading.Lock()


class ChartImageError(Exception):
    """A chart image could not be drawn. The message never includes chart data."""


@dataclass(frozen=True)
class RenderedChart:
    data: bytes
    width: int  # pixels
    height: int  # pixels


# ---------------------------------------------------------------------------
# Fonts and design-unit measurement
# ---------------------------------------------------------------------------


def units_per_em(path: Path) -> int:
    """``head.unitsPerEm`` of a TrueType file (table directory, offset 18, big-endian)."""
    raw = Path(path).read_bytes()
    count = struct.unpack(">H", raw[4:6])[0]
    for i in range(count):
        entry = raw[12 + 16 * i : 28 + 16 * i]
        if entry[:4] == b"head":
            offset = struct.unpack(">I", entry[8:12])[0]
            return struct.unpack(">H", raw[offset + 18 : offset + 20])[0]
    raise ChartImageError("The chart font file has no head table.")


class _Fonts:
    """Per-weight design-unit fonts, drawing fonts by pixel size, and the advance cache."""

    def __init__(self, font_dir: Path) -> None:
        from PIL import ImageFont

        self.font_dir = font_dir
        self.design: dict = {}
        self.units: dict = {}
        self._paths: dict = {}
        self._draw: dict = {}
        self._adv: dict = {}
        for weight, name in FONT_FILES.items():
            path = Path(font_dir) / name
            try:
                units = units_per_em(path)
                self.design[weight] = ImageFont.truetype(
                    str(path), size=units, layout_engine=ImageFont.Layout.BASIC
                )
            except ChartImageError:
                raise
            except Exception as exc:
                raise ChartImageError(
                    f"The chart font {name} could not be loaded ({exc.__class__.__name__})."
                ) from None
            self.units[weight] = units
            self._paths[weight] = path

    def advance(self, ch: str, weight: str) -> float:
        """One character's advance in design units."""
        key = (weight, ch)
        got = self._adv.get(key)
        if got is None:
            got = float(self.design[weight].getlength(ch))
            self._adv[key] = got
        return got

    def draw_font(self, weight: str, px: float):
        from PIL import ImageFont

        key = (weight, px)
        font = self._draw.get(key)
        if font is None:
            font = ImageFont.truetype(
                str(self._paths[weight]), size=px, layout_engine=ImageFont.Layout.BASIC
            )
            self._draw[key] = font
        return font


_FONTS_CACHE: dict = {}


def _fonts() -> _Fonts:
    key = str(FONT_DIR)
    got = _FONTS_CACHE.get(key)
    if got is None:
        got = _Fonts(Path(FONT_DIR))
        _FONTS_CACHE.clear()
        _FONTS_CACHE[key] = got
    return got


def measure(text: str, size_px: float, weight: str = "regular") -> float:
    """Width of ``text`` at ``size_px``: the sum of each character's own design-unit advance.

    The only width source for layout. Never uses a pair or whole-string measurement, so a
    kern table (or any other table) cannot make a width depend on the font file's tables.
    """
    fonts = _fonts()
    total = 0.0
    for ch in str(text).translate(_SPACES):
        total += fonts.advance(ch, weight)
    return total * size_px / fonts.units[weight]


def _cps(text: str) -> list:
    return list(text)


def fit_text(text: str, max_width: float, max_cp: int, size: float, weight: str = "regular") -> str:
    """The text if it fits, else the longest code-point-safe prefix plus an ellipsis."""
    text = str(text)
    cps = _cps(text)
    if len(cps) <= max_cp and measure(text, size, weight) <= max_width:
        return text
    lo = 1
    hi = max(1, min(len(cps) - 1, max_cp - 1))
    best = 1
    guard = 0
    while lo <= hi and guard < 8:
        mid = (lo + hi) >> 1
        if measure("".join(cps[:mid]) + "…", size, weight) <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
        guard += 1
    return "".join(cps[:best]) + "…"


# ---------------------------------------------------------------------------
# Scales and axes (ports of chart-scale.js; same names)
# ---------------------------------------------------------------------------


def _x_text(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return format_full(v, "")
    return str(v)


def _x_tick(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return format_tick(v, "")
    return str(v)


def _series_name(s) -> str:
    return s.name or "Value"


def _pow10(e: int) -> float:
    return float(f"1e{e}")


def _round_clean(v: float) -> float:
    return float(f"{v:.12g}")


_LN10 = math.log(10)


def nice_step(rng: float, count: int) -> float:
    raw = rng / count
    mag = 10.0 ** math.floor(math.log(raw) / _LN10)
    norm = raw / mag
    nice = 1 if norm < 1.5 else 2 if norm < 3 else 5 if norm < 7 else 10
    return nice * mag


class _Extent:
    def __init__(self) -> None:
        self.min = math.inf
        self.max = -math.inf

    def extend(self, v: float) -> None:
        if v < self.min:
            self.min = v
        if v > self.max:
            self.max = v


@dataclass(frozen=True)
class _AxisScale:
    log: bool
    d0: float
    d1: float
    ticks: tuple


def build_axis(axis_spec: Axis, ext: _Extent, include_zero: bool) -> _AxisScale:
    log = axis_spec.scale == "log"
    lo = ext.min
    hi = ext.max
    ticks: list = []
    if lo == math.inf:
        lo = 1 if log else 0
        hi = 10 if log else 1
    fixed_lo = axis_spec.min is not None
    fixed_hi = axis_spec.max is not None
    if log:
        d0 = axis_spec.min if fixed_lo else _pow10(math.floor(math.log(lo) / _LN10 + 1e-12))
        d1 = axis_spec.max if fixed_hi else _pow10(math.ceil(math.log(hi) / _LN10 - 1e-12))
        if d1 <= d0:
            d1 = d0 * 10
        e0 = math.ceil(math.log(d0) / _LN10 - 1e-9)
        e1 = math.floor(math.log(d1) / _LN10 + 1e-9)
        stride = max(1, math.ceil((e1 - e0 + 1) / 7))
        e = e0
        while e <= e1:
            ticks.append(_pow10(e))
            e += stride
        if not ticks:
            ticks.append(d0)
        return _AxisScale(True, d0, d1, tuple(ticks))
    if include_zero:
        lo = min(lo, 0)
        hi = max(hi, 0)
    if hi == lo:
        pad = abs(lo) * 0.1 or 1
        lo -= pad
        hi += pad
    elif not include_zero:
        span = (hi - lo) * 0.04
        lo -= span
        hi += span
    if fixed_lo:
        lo = axis_spec.min
    if fixed_hi:
        hi = axis_spec.max
    if hi <= lo:
        hi = lo + 1
    step = nice_step(hi - lo, 5)
    a = lo if fixed_lo else math.floor(lo / step + 1e-9) * step
    b = hi if fixed_hi else math.ceil(hi / step - 1e-9) * step
    t = math.ceil(a / step - 1e-9)
    while t * step <= b + step * 1e-9:
        ticks.append(_round_clean(t * step))
        t += 1
    return _AxisScale(False, _round_clean(a), _round_clean(b), tuple(ticks))


def make_scale(axis: _AxisScale, r0: float, r1: float):
    if axis.log:
        l0 = math.log(axis.d0) / _LN10
        k = (r1 - r0) / (math.log(axis.d1) / _LN10 - l0)
        return lambda v: r0 + (math.log(v) / _LN10 - l0) * k
    kk = (r1 - r0) / (axis.d1 - axis.d0)
    return lambda v: r0 + (v - axis.d0) * kk


def kind_of(spec: ChartSpec, s) -> str:
    if s.type:
        return s.type
    return "bar" if spec.type == "bar" else "line" if spec.type == "line" else "area"


def compute_stacks(spec: ChartSpec, kinds: list) -> list:
    stacks: list = []
    n = len(spec.x.values) if spec.x.values else 0
    pos_top = {"left": {}, "right": {}}
    neg_top = {"left": {}, "right": {}}
    for si, s in enumerate(spec.series):
        stackable = spec.stacked and kinds[si] in ("bar", "area")
        if not stackable:
            stacks.append(None)
            continue
        side = s.axis
        row: list = []
        for i in range(n):
            v = s.values[i]
            if i not in pos_top[side]:
                pos_top[side][i] = 0
                neg_top[side][i] = 0
            if v is None:
                row.append(None)
                continue
            if kinds[si] == "area" or v >= 0:
                row.append((pos_top[side][i], pos_top[side][i] + v))
                pos_top[side][i] += v
            else:
                row.append((neg_top[side][i], neg_top[side][i] + v))
                neg_top[side][i] += v
        stacks.append(row)
    return stacks


def _cartesian_axes(spec: ChartSpec, stacks=None, kinds=None):
    """(left axis, right axis or None, used-right, zero flags) exactly as layoutCartesian."""
    n = len(spec.x.values)
    kinds = kinds or [kind_of(spec, s) for s in spec.series]
    stacks = stacks if stacks is not None else compute_stacks(spec, kinds)
    ext = {"left": _Extent(), "right": _Extent()}
    zero = {"left": False, "right": False}
    used = {"left": False, "right": False}
    for si, s in enumerate(spec.series):
        used[s.axis] = True
        if kinds[si] in ("bar", "area"):
            zero[s.axis] = True
        for i in range(n):
            v = s.values[i]
            if v is None:
                continue
            if stacks[si] and stacks[si][i]:
                ext[s.axis].extend(stacks[si][i][0])
                ext[s.axis].extend(stacks[si][i][1])
            else:
                ext[s.axis].extend(v)
    for an in spec.annotations:
        if an.axis == "y":
            ext["left"].extend(an.value)
        elif an.axis == "y2":
            ext["right"].extend(an.value)
            used["right"] = True
    ax_l = build_axis(spec.y, ext["left"], zero["left"])
    ax_r = build_axis(spec.y2, ext["right"], zero["right"]) if used["right"] and spec.y2 else None
    return ax_l, ax_r


def axis_ticks(spec: ChartSpec) -> dict:
    """The y (and y2) tick values of a cartesian chart, as the shared tick corpus lists them."""
    if spec.type == "scatter":
        ext_y = _Extent()
        for s in spec.series:
            for _, py in s.values:
                ext_y.extend(py)
        for an in spec.annotations:
            if an.axis != "x":
                ext_y.extend(an.value)
        return {"y": list(build_axis(spec.y, ext_y, False).ticks)}
    ax_l, ax_r = _cartesian_axes(spec)
    out = {"y": list(ax_l.ticks)}
    if ax_r is not None:
        out["y2"] = list(ax_r.ticks)
    return out


def x_label_stride(max_text: float, band: float) -> int:
    """How many categories per drawn x label (per renderer: uses the server's own widths)."""
    return max(1, math.ceil((min(max_text, 120) + 8) / band))


# ---------------------------------------------------------------------------
# The scene: a list of drawing operations in logical pixels
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    points: tuple
    color: str
    width: float
    dash: tuple | None = None
    round_caps: bool = False


@dataclass(frozen=True)
class Area:
    points: tuple
    color: str
    alpha: float


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float
    color: str


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float
    color: str
    outline: str | None = None
    outline_width: float = 0


@dataclass(frozen=True)
class Slice:
    cx: float
    cy: float
    r: float
    start: float  # degrees, clockwise from 3 o'clock
    end: float
    color: str
    full: bool = False


@dataclass(frozen=True)
class Text:
    x: float
    y: float  # baseline
    text: str
    size: float
    weight: str
    color: str
    anchor: str  # start | middle | end
    role: str = ""


@dataclass
class Scene:
    width: int  # logical
    height: int  # logical
    ops: list


class _Builder:
    def __init__(self, width: int, height: int) -> None:
        self.scene = Scene(width, height, [])
        self.ox = 0.0
        self.oy = 0.0

    def line(self, pts, color, width, dash=None, round_caps=False) -> None:
        pts = tuple((x + self.ox, y + self.oy) for x, y in pts)
        self.scene.ops.append(Line(pts, color, width, dash, round_caps))

    def area(self, pts, color, alpha) -> None:
        pts = tuple((x + self.ox, y + self.oy) for x, y in pts)
        self.scene.ops.append(Area(pts, color, alpha))

    def rect(self, x0, y0, x1, y1, color) -> None:
        self.scene.ops.append(Rect(x0 + self.ox, y0 + self.oy, x1 + self.ox, y1 + self.oy, color))

    def circle(self, cx, cy, r, color, outline=None, outline_width=0) -> None:
        self.scene.ops.append(Circle(cx + self.ox, cy + self.oy, r, color, outline, outline_width))

    def slice(self, cx, cy, r, start, end, color, full=False) -> None:
        self.scene.ops.append(Slice(cx + self.ox, cy + self.oy, r, start, end, color, full))

    def text(self, x, y, text, size, weight, color, anchor, role="") -> None:
        self.scene.ops.append(
            Text(x + self.ox, y + self.oy, text, size, weight, color, anchor, role)
        )


def _series_color(i: int) -> str:
    return CHART_COLORS[i % 8]


def _series_dash(i: int):
    return _SERIES_DASHES[(i - 4) % 4] if i >= 4 else None


# ---------------------------------------------------------------------------
# Layout (ports of chart-layout.js)
# ---------------------------------------------------------------------------


def _tick_width(axis: _AxisScale, unit: str) -> int:
    w = 0.0
    for t in axis.ticks:
        w = max(w, measure(format_tick(t, unit), TICK_SIZE))
    return math.ceil(w) + 12


def _grid_and_ticks(b: _Builder, axis: _AxisScale, scale, side: str, plot: dict, unit: str) -> None:
    for t in axis.ticks:
        py = scale(t)
        if side == "left":
            b.line(((plot["l"], py), (plot["r"], py)), BORDER, 1)
            b.text(
                plot["l"] - 6,
                py + 4,
                format_tick(t, unit),
                TICK_SIZE,
                "regular",
                FG_TERTIARY,
                "end",
                "tick",
            )
        else:
            b.text(
                plot["r"] + 6,
                py + 4,
                format_tick(t, unit),
                TICK_SIZE,
                "regular",
                FG_TERTIARY,
                "start",
                "tick",
            )


def _ref_line(b: _Builder, pos: dict, plot: dict, label: str) -> None:
    if pos["vertical"]:
        v = pos["v"]
        b.line(((v, plot["t"]), (v, plot["b"])), CHART_REF, 1.5, REF_DASH)
        if label:
            right = v > plot["l"] + (plot["r"] - plot["l"]) * 0.7
            b.text(
                v - 4 if right else v + 4,
                plot["t"] + 11,
                label,
                TICK_SIZE,
                "regular",
                CHART_REF,
                "end" if right else "start",
                "ref-label",
            )
    else:
        v = pos["v"]
        b.line(((plot["l"], v), (plot["r"], v)), CHART_REF, 1.5, REF_DASH)
        if label:
            b.text(plot["r"] - 4, v - 4, label, TICK_SIZE, "regular", CHART_REF, "end", "ref-label")


def _axis_labels(b: _Builder, spec: ChartSpec, plot: dict, has_right: bool) -> None:
    if spec.y.label:
        b.text(
            plot["l"], 12, spec.y.label, TICK_SIZE, "regular", FG_SECONDARY, "start", "axis-label"
        )
    if has_right and spec.y2 and spec.y2.label:
        b.text(
            plot["r"], 12, spec.y2.label, TICK_SIZE, "regular", FG_SECONDARY, "end", "axis-label"
        )
    if spec.x.label:
        b.text(
            (plot["l"] + plot["r"]) / 2,
            HEIGHT - 4,
            spec.x.label,
            TICK_SIZE,
            "regular",
            FG_SECONDARY,
            "middle",
            "axis-label",
        )


def _layout_cartesian(b: _Builder, spec: ChartSpec, width: float) -> None:
    n = len(spec.x.values)
    kinds = [kind_of(spec, s) for s in spec.series]
    stacks = compute_stacks(spec, kinds)
    ax_l, ax_r = _cartesian_axes(spec, stacks, kinds)
    has_labels = bool(spec.y.label or (ax_r and spec.y2.label))
    plot = {
        "l": max(34, _tick_width(ax_l, spec.y.unit)),
        "r": width - (max(34, _tick_width(ax_r, spec.y2.unit)) if ax_r else 12),
        "t": 24 if has_labels else 10,
        "b": HEIGHT - (40 if spec.x.label else 24),
    }
    if plot["r"] - plot["l"] < 40:
        plot["r"] = plot["l"] + 40
    ys = make_scale(ax_l, plot["b"], plot["t"])
    yr = make_scale(ax_r, plot["b"], plot["t"]) if ax_r else None
    band = (plot["r"] - plot["l"]) / n

    def cx(idx: float) -> float:
        return plot["l"] + (idx + 0.5) * band

    def scale_for(side: str):
        return yr if side == "right" and yr else ys

    def base_for(side: str) -> float:
        ax = ax_r if side == "right" and ax_r else ax_l
        if ax.log:
            return ax.d0
        return max(ax.d0, min(ax.d1, 0))

    def dom_lo(side: str) -> float:
        return ax_r.d0 if side == "right" and ax_r else ax_l.d0

    def dom_hi(side: str) -> float:
        return ax_r.d1 if side == "right" and ax_r else ax_l.d1

    _grid_and_ticks(b, ax_l, ys, "left", plot, spec.y.unit)
    if ax_r:
        _grid_and_ticks(b, ax_r, yr, "right", plot, spec.y2.unit)
    b.line(((plot["l"], plot["b"]), (plot["r"], plot["b"])), BORDER_STRONG, 1)

    # x tick labels, thinned to fit and cut with an ellipsis (design-unit widths)
    max_text = 0.0
    for i in range(n):
        max_text = max(max_text, measure(_x_tick(spec.x.values[i]), TICK_SIZE))
    stride = x_label_stride(max_text, band)
    max_width = max(19, band * stride - 6)
    for i in range(0, n, stride):
        b.text(
            cx(i),
            plot["b"] + 16,
            fit_text(_x_tick(spec.x.values[i]), max_width, 24, TICK_SIZE),
            TICK_SIZE,
            "regular",
            FG_TERTIARY,
            "middle",
            "x-tick",
        )
    _axis_labels(b, spec, plot, bool(ax_r))

    # bars
    slot_of: list = []
    slots = 0
    slot_by_axis: dict = {}
    for si, s in enumerate(spec.series):
        if kinds[si] != "bar":
            slot_of.append(-1)
            continue
        if spec.stacked:
            if s.axis not in slot_by_axis:
                slot_by_axis[s.axis] = slots
                slots += 1
            slot_of.append(slot_by_axis[s.axis])
        else:
            slot_of.append(slots)
            slots += 1
    bar_w = max(1, (band * 0.72) / slots) if slots else 0
    for si, s in enumerate(spec.series):
        if kinds[si] != "bar":
            continue
        sc = scale_for(s.axis)
        base = base_for(s.axis)
        for i in range(n):
            if s.values[i] is None:
                continue
            y0 = stacks[si][i][0] if stacks[si] else base
            y1 = stacks[si][i][1] if stacks[si] else s.values[i]
            p0 = sc(max(y0, dom_lo(s.axis)))
            p1 = sc(min(max(y1, dom_lo(s.axis)), dom_hi(s.axis)))
            bx = cx(i) - (slots * bar_w) / 2 + slot_of[si] * bar_w
            b.rect(
                bx,
                min(p0, p1),
                bx + max(1, bar_w - 1),
                min(p0, p1) + abs(p1 - p0),
                _series_color(si),
            )

    # areas and lines
    for si, s in enumerate(spec.series):
        if kinds[si] == "bar":
            continue
        lsc = scale_for(s.axis)
        lbase = base_for(s.axis)
        segs: list = []
        seg: list = []
        for i in range(n):
            if s.values[i] is None:
                if seg:
                    segs.append(seg)
                    seg = []
                continue
            top = stacks[si][i][1] if stacks[si] else s.values[i]
            bottom = stacks[si][i][0] if stacks[si] else lbase
            seg.append((cx(i), lsc(top), lsc(bottom)))
        if seg:
            segs.append(seg)
        color = _series_color(si)
        for pts in segs:
            line_pts = tuple((x, y) for x, y, _ in pts)
            if kinds[si] == "area" and len(pts) > 1:
                poly = line_pts + tuple((x, bt) for x, _, bt in reversed(pts))
                b.area(poly, color, 0.22)
            if len(pts) > 1:
                b.line(line_pts, color, 2, _series_dash(si), True)
            if len(pts) == 1 or n <= 24:
                for x, y, _ in pts:
                    b.circle(x, y, 3, color)

    # reference lines
    for an in spec.annotations:
        if an.axis == "x":
            at = -1
            for i in range(n):
                if _x_text(spec.x.values[i]) == _x_text(an.value):
                    at = i
            if at == -1:
                continue
            pos = {"vertical": True, "v": cx(at)}
        else:
            pos = {"vertical": False, "v": (yr if an.axis == "y2" and yr else ys)(an.value)}
        _ref_line(b, pos, plot, an.label)


def _layout_scatter(b: _Builder, spec: ChartSpec, width: float) -> None:
    ext_x = _Extent()
    ext_y = _Extent()
    for s in spec.series:
        for px, py in s.values:
            ext_x.extend(px)
            ext_y.extend(py)
    for an in spec.annotations:
        (ext_x if an.axis == "x" else ext_y).extend(an.value)
    ax_y = build_axis(spec.y, ext_y, False)
    ax_x = build_axis(Axis(scale=spec.x.scale), ext_x, False)
    plot = {
        "l": max(34, _tick_width(ax_y, spec.y.unit)),
        "r": width - 16,
        "t": 24 if spec.y.label else 10,
        "b": HEIGHT - (40 if spec.x.label else 24),
    }
    if plot["r"] - plot["l"] < 40:
        plot["r"] = plot["l"] + 40
    ys = make_scale(ax_y, plot["b"], plot["t"])
    xs = make_scale(ax_x, plot["l"], plot["r"])
    _grid_and_ticks(b, ax_y, ys, "left", plot, spec.y.unit)
    b.line(((plot["l"], plot["b"]), (plot["r"], plot["b"])), BORDER_STRONG, 1)
    for t in ax_x.ticks:
        b.text(
            xs(t),
            plot["b"] + 16,
            format_tick(t, ""),
            TICK_SIZE,
            "regular",
            FG_TERTIARY,
            "middle",
            "x-tick",
        )
    _axis_labels(b, spec, plot, False)
    for si, s in enumerate(spec.series):
        for px, py in s.values:
            b.circle(xs(px), ys(py), 4, _series_color(si), SURFACE, 1)
    for an in spec.annotations:
        pos = (
            {"vertical": True, "v": xs(an.value)}
            if an.axis == "x"
            else {"vertical": False, "v": ys(an.value)}
        )
        _ref_line(b, pos, plot, an.label)


def _layout_pie(b: _Builder, spec: ChartSpec, width: float) -> None:
    s = spec.series[0]
    total = sum(s.values)
    cx = width / 2
    cy = HEIGHT / 2
    r = max(20, min(width / 2, HEIGHT / 2) - 10)
    angle = -math.pi / 2
    non_zero = sum(1 for v in s.values if v > 0)
    for i, v in enumerate(s.values):
        sweep = (v / total) * math.pi * 2
        color = _series_color(i)
        if v > 0 and non_zero == 1:
            b.slice(cx, cy, r, 0, 360, color, True)
        elif v > 0:
            b.slice(cx, cy, r, math.degrees(angle), math.degrees(angle + sweep), color)
        angle += sweep


def _layout_spark(b: _Builder, spec: ChartSpec, width: float, height: float) -> None:
    vals = spec.series[0].values
    present = [v for v in vals if v is not None]
    lo = min(present)
    hi = max(present)
    if hi == lo:
        lo -= 1
        hi += 1
    n = len(vals)
    inset_x = 6
    inset_y = 8

    def sx(idx: int) -> float:
        span = width - 2 * inset_x
        return inset_x + ((idx / (n - 1)) * span if n > 1 else span / 2)

    def sy(v: float) -> float:
        return height - inset_y - ((v - lo) / (hi - lo)) * (height - 2 * inset_y)

    segs: list = []
    seg: list = []
    last = None
    for i, v in enumerate(vals):
        if v is None:
            if seg:
                segs.append(seg)
                seg = []
            continue
        seg.append((sx(i), sy(v)))
        last = (sx(i), sy(v))
    if seg:
        segs.append(seg)
    color = _series_color(0)
    for pts in segs:
        if len(pts) > 1:
            b.line(tuple(pts), color, 3, None, True)
    if last is not None:
        b.circle(last[0], last[1], 5, color)


# ---------------------------------------------------------------------------
# Title, legend and the whole scene
# ---------------------------------------------------------------------------


def _legend_items(spec: ChartSpec) -> list:
    items: list = []
    if spec.type == "sparkline":
        return items
    if spec.type == "pie":
        for i, v in enumerate(spec.x.values):
            items.append((_x_text(v), _series_color(i), False))
    elif len(spec.series) > 1 or spec.series[0].name:
        for i, s in enumerate(spec.series):
            line = spec.type != "scatter" and kind_of(spec, s) == "line"
            items.append((_series_name(s), _series_color(i), line))
    return items


def _legend_rows(items: list, width: float) -> list:
    """Entries flow left to right and wrap like flex-wrap: a list of rows of placed items."""
    rows: list = [[]]
    x = float(PAD_X)
    limit = width - PAD_X
    for name, color, line in items:
        w = (14 if line else 10) + 6 + measure(name, TICK_SIZE)
        if x + w > limit and rows[-1]:
            rows.append([])
            x = float(PAD_X)
        rows[-1].append((x, name, color, line))
        x += w + 14
    return rows


def build_scene(spec: ChartSpec) -> Scene:
    """Every drawing operation for a valid chart, in logical pixels."""
    spark = spec.type == "sparkline"
    width = SPARK_WIDTH if spark else WIDTH
    title_rows = 1 if spec.title else 0
    rows = [] if spark else _legend_rows(_legend_items(spec), width)
    rows = [r for r in rows if r]
    legend_rows = len(rows)
    body = SPARK_HEIGHT if spark else HEIGHT
    height = body + TITLE_ROW * title_rows + LEGEND_ROW * legend_rows
    b = _Builder(width, height)
    y = 0
    if title_rows:
        title = fit_text(spec.title, width - 2 * PAD_X, MAX_TITLE_CP, TITLE_SIZE, "semibold")
        b.text(PAD_X, y + 14, title, TITLE_SIZE, "semibold", FG, "start", "title")
        y += TITLE_ROW
    for row in rows:
        for x, name, color, line in row:
            if line:
                b.rect(x, y + 8.5, x + 14, y + 11.5, color)
                tx = x + 14 + 6
            else:
                b.rect(x, y + 5, x + 10, y + 15, color)
                tx = x + 10 + 6
            b.text(tx, y + 14, name, TICK_SIZE, "regular", FG_SECONDARY, "start", "legend")
        y += LEGEND_ROW
    b.oy = y
    b.ox = PAD_X
    inner = width - 2 * PAD_X
    if spark:
        _layout_spark(b, spec, inner, SPARK_HEIGHT)
    elif spec.type == "scatter":
        _layout_scatter(b, spec, inner)
    elif spec.type == "pie":
        _layout_pie(b, spec, inner)
    else:
        _layout_cartesian(b, spec, inner)
    return b.scene


MAX_TITLE_CP = 120


# ---------------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------------


def _rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _dash_segments(points: tuple, pattern: tuple) -> list:
    """Walk a polyline and emit the 'on' pieces of a stroke-dasharray, as 2-point segments."""
    out: list = []
    idx = 0
    remaining = float(pattern[0])
    on = True
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len == 0:
            continue
        pos = 0.0
        while pos < seg_len:
            step = min(remaining, seg_len - pos)
            if on:
                a = pos / seg_len
                c = (pos + step) / seg_len
                out.append(
                    (
                        (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a),
                        (x0 + (x1 - x0) * c, y0 + (y1 - y0) * c),
                    )
                )
            pos += step
            remaining -= step
            if remaining <= 1e-9:
                idx = (idx + 1) % len(pattern)
                remaining = float(pattern[idx])
                on = not on
    return out


def _paint(scene: Scene):
    from PIL import Image, ImageDraw

    s = _SUPER
    w4 = scene.width * s
    h4 = scene.height * s
    canvas = Image.new("RGB", (w4, h4), _rgb(SURFACE))
    draw = ImageDraw.Draw(canvas)

    def px(pts):
        return [(x * s, y * s) for x, y in pts]

    for op in scene.ops:
        if isinstance(op, Line):
            width = max(1, round(op.width * s))
            if op.dash:
                for a, c in _dash_segments(op.points, op.dash):
                    draw.line(px((a, c)), fill=_rgb(op.color), width=width)
            else:
                draw.line(px(op.points), fill=_rgb(op.color), width=width, joint="curve")
                if op.round_caps:
                    r = width / 2
                    for x, y in (op.points[0], op.points[-1]):
                        draw.ellipse(
                            (x * s - r, y * s - r, x * s + r, y * s + r), fill=_rgb(op.color)
                        )
        elif isinstance(op, Area):
            pts = px(op.points)
            x0 = max(0, int(min(p[0] for p in pts)) - 1)
            y0 = max(0, int(min(p[1] for p in pts)) - 1)
            x1 = min(w4, int(max(p[0] for p in pts)) + 2)
            y1 = min(h4, int(max(p[1] for p in pts)) + 2)
            if x1 > x0 and y1 > y0:
                mask = Image.new("L", (x1 - x0, y1 - y0), 0)
                ImageDraw.Draw(mask).polygon(
                    [(x - x0, y - y0) for x, y in pts], fill=round(255 * op.alpha)
                )
                canvas.paste(_rgb(op.color), (x0, y0), mask)
        elif isinstance(op, Rect):
            draw.rectangle(
                (op.x0 * s, op.y0 * s, op.x1 * s - 1, op.y1 * s - 1), fill=_rgb(op.color)
            )
        elif isinstance(op, Circle):
            box = ((op.cx - op.r) * s, (op.cy - op.r) * s, (op.cx + op.r) * s, (op.cy + op.r) * s)
            if op.outline:
                draw.ellipse(
                    box,
                    fill=_rgb(op.color),
                    outline=_rgb(op.outline),
                    width=max(1, round(op.outline_width * s)),
                )
            else:
                draw.ellipse(box, fill=_rgb(op.color))
        elif isinstance(op, Slice):
            box = ((op.cx - op.r) * s, (op.cy - op.r) * s, (op.cx + op.r) * s, (op.cy + op.r) * s)
            if op.full:
                draw.ellipse(box, fill=_rgb(op.color), outline=_rgb(SURFACE), width=2 * s)
            else:
                draw.pieslice(
                    box, op.start, op.end, fill=_rgb(op.color), outline=_rgb(SURFACE), width=2 * s
                )
    # the card edge: a 1 logical px border with rounded corners; outside it stays --surface
    draw.rounded_rectangle(
        (0, 0, w4 - 1, h4 - 1), radius=CARD_RADIUS * s, outline=_rgb(BORDER), width=s
    )
    image = canvas.reduce(s // DENSITY)
    _paint_text(image, scene)
    return image


def _paint_text(image, scene: Scene) -> None:
    from PIL import ImageDraw

    fonts = _fonts()
    draw = ImageDraw.Draw(image)
    for op in scene.ops:
        if not isinstance(op, Text):
            continue
        total = measure(op.text, op.size, op.weight)
        x = op.x - (total if op.anchor == "end" else total / 2 if op.anchor == "middle" else 0)
        scale = DENSITY * op.size / fonts.units[op.weight]
        font = fonts.draw_font(op.weight, op.size * DENSITY)
        pos = x * DENSITY
        for ch in op.text.translate(_SPACES):
            if ch != " ":
                draw.text(
                    (round(pos), round(op.y * DENSITY)),
                    ch,
                    font=font,
                    fill=_rgb(op.color),
                    anchor="ls",
                )
            pos += fonts.advance(ch, op.weight) * scale


def render_png(spec: ChartSpec) -> RenderedChart:
    """Draw a valid chart as an RGB light-theme PNG at 2x. Raises ``ChartImageError``."""
    with _LOCK:
        try:
            scene = build_scene(spec)
            image = _paint(scene)
            buf = io.BytesIO()
            image.save(buf, format="PNG")
        except ChartImageError:
            raise
        except Exception as exc:
            raise ChartImageError(
                f"The chart image could not be drawn ({exc.__class__.__name__})."
            ) from None
        data = buf.getvalue()
        if len(data) > MAX_PNG_BYTES:
            raise ChartImageError("The chart image is larger than the 8 MB limit.")
        return RenderedChart(data, image.width, image.height)
