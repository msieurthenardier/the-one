"""Chart format v1: the pure-Python validator and number formatter (M35 F1 L1).

The language-neutral specification is ``docs/chart-format.md``; the shared corpus is
``tests/fixtures/charts/``. ``App.ui.chart.parse`` in the browser is a second implementation
of the same document, and both are tested against the same corpus with identical sentences.
A new rule lands in the document, the corpus and both validators together.

Standard library only: nothing here imports the web layer, the agent or Pillow.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext

TYPES = ("bar", "line", "area", "scatter", "pie", "sparkline")
MAX_SERIES = 8
MAX_VALUES = 2000
MAX_CATEGORIES = 200
MAX_SLICES = 12
MAX_ANNOTATIONS = 5
MAX_LABEL = 60
MAX_UNIT = 12
MAX_TITLE = 120
PREFIX_UNITS = ("$", "€", "£", "¥")
THIN_SPACE = " "

# Which optional keys each type reads. Keys a type does not read are dropped (normalised
# to their defaults) before any checking, so they can never raise an error.
_X_TYPES = ("bar", "line", "area", "pie", "scatter")
_Y2_TYPES = ("bar", "line", "area")
_ANNOTATION_TYPES = ("bar", "line", "area", "scatter")
_SERIES_TYPE_CHARTS = ("bar", "line")


@dataclass(frozen=True)
class ChartError:
    """The one plain sentence for the first rule a chart text breaks."""

    message: str


@dataclass(frozen=True)
class Axis:
    label: str = ""
    unit: str = ""
    scale: str = "linear"
    min: float | None = None
    max: float | None = None
    values: tuple | None = None


@dataclass(frozen=True)
class Series:
    name: str
    values: tuple  # numbers or None; for a scatter, (x, y) tuples
    axis: str = "left"
    type: str | None = None


@dataclass(frozen=True)
class Annotation:
    axis: str
    value: object
    label: str = ""


@dataclass(frozen=True)
class ChartSpec:
    type: str
    title: str
    x: Axis
    y: Axis
    y2: Axis | None
    series: tuple
    stacked: bool
    annotations: tuple


class _FailError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _fail(message: str) -> _FailError:
    return _FailError(message)


# ---------------------------------------------------------------------------
# Number display (locale-neutral; see "Number display" in docs/chart-format.md)
# ---------------------------------------------------------------------------


def _is_num(v: object) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if isinstance(v, int):
        try:
            float(v)
        except OverflowError:
            return False
        return True
    return math.isfinite(v)


def _sig3(a: float) -> tuple[str, int]:
    """Three significant digits of a positive number, rounded half up on its exact value."""
    d = Context(prec=3, rounding=ROUND_HALF_UP).create_decimal(Decimal(a))
    digits = "".join(str(n) for n in d.as_tuple().digits).ljust(3, "0")
    return digits, d.adjusted()


def _trim(text: str) -> str:
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _exp_form(digits: str, exp: int) -> str:
    return _trim(digits[0] + "." + digits[1:]) + "e" + str(exp)


def _with_unit(sign: str, body: str, unit: str) -> str:
    if unit in PREFIX_UNITS:
        return sign + unit + body
    if unit:
        return sign + body + THIN_SPACE + unit
    return sign + body


def format_tick(value: float, unit: str = "") -> str:
    """Compact axis text: ``1.2k``, ``3.4M``, at most three significant digits."""
    value = float(value) if not isinstance(value, int) else value
    if value == 0:
        return _with_unit("", "0", unit)
    sign = "-" if value < 0 else ""
    digits, exp = _sig3(abs(value))
    if exp >= 15 or exp < -6:
        return _with_unit(sign, _exp_form(digits, exp), unit)
    suffix, shift = ("", 0)
    if exp >= 9:
        suffix, shift = ("B", 9)
    elif exp >= 6:
        suffix, shift = ("M", 6)
    elif exp >= 3:
        suffix, shift = ("k", 3)
    point = exp - shift + 1  # integer digits before the decimal point
    if point <= 0:
        body = "0." + "0" * (-point) + digits
    elif point >= 3:
        body = digits + "0" * (point - 3)
    else:
        body = digits[:point] + "." + digits[point:]
    return _with_unit(sign, _trim(body) + suffix, unit)


def format_full(value: float, unit: str = "") -> str:
    """Full value: ``,`` grouping, ``.`` decimals (at most six), the unit placed as ever."""
    if value == 0:
        return _with_unit("", "0", unit)
    sign = "-" if value < 0 else ""
    a = abs(value)
    digits, exp = _sig3(a)
    if exp >= 15 or exp < -6:
        return _with_unit(sign, _exp_form(digits, exp), unit)
    with localcontext() as ctx:
        ctx.prec = 60
        fixed = format(Decimal(a).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")
    whole, _, frac = fixed.partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    text = _trim(",".join(groups) + "." + frac)
    if text == "0":
        sign = ""
    return _with_unit(sign, text, unit)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _refuse_constant(name: str) -> None:
    raise ValueError(name)


def _ref(series: list, i: int) -> str:
    name = series[i].get("name") if isinstance(series[i], dict) else None
    if isinstance(name, str) and name:
        return f'Series "{name}"'
    return f"Series {i + 1}"


def _label_check(text: str) -> None:
    if len(text) > MAX_LABEL:
        raise _fail(f"A label is {len(text)} characters; the limit is {MAX_LABEL}.")


def _scalar_key(v: object) -> tuple:
    return ("s", v) if isinstance(v, str) else ("n", float(v))


def _parse_axis(raw: object, key: str, chart_type: str) -> Axis:
    """Check one axis object (``x``, ``y`` or ``y2``) and return its normalised form."""
    if raw is None:
        if key == "x" and chart_type != "scatter":
            raise _fail('Axis "x" needs a list of "values" with at least one entry.')
        return Axis()
    if not isinstance(raw, dict):
        raise _fail(f'Axis "{key}" must be an object.')
    label = raw.get("label")
    if "label" in raw:
        if not isinstance(label, str):
            raise _fail(f'Axis "{key}" has a "label" that isn\'t text.')
        _label_check(label)
    unit = raw.get("unit")
    if key != "x" and "unit" in raw:
        if not isinstance(unit, str):
            raise _fail(f'Axis "{key}" has a "unit" that isn\'t text.')
        if len(unit) > MAX_UNIT:
            raise _fail(f"A unit is {len(unit)} characters; the limit is {MAX_UNIT}.")
    scale = raw.get("scale", "linear")
    if "scale" in raw:
        if scale not in ("linear", "log"):
            raise _fail(f'Axis "{key}" has a "scale" that isn\'t linear or log.')
        if key == "x" and scale == "log" and chart_type != "scatter":
            raise _fail('A log scale on axis "x" only works on a scatter chart.')
    lo = hi = None
    if key != "x":
        for name in ("min", "max"):
            if name in raw and not _is_num(raw[name]):
                raise _fail(f'Axis "{key}" has a "{name}" that isn\'t a number.')
        lo = float(raw["min"]) if "min" in raw else None
        hi = float(raw["max"]) if "max" in raw else None
        if lo is not None and hi is not None and lo >= hi:
            raise _fail(f'Axis "{key}" needs "min" to be below "max".')
        if scale == "log" and lo is not None and lo <= 0:
            raise _fail(f'Axis "{key}" has a log scale, so "min" must be above 0.')
    values = None
    if key == "x" and chart_type != "scatter":
        vals = raw.get("values")
        if not isinstance(vals, list) or not vals:
            raise _fail('Axis "x" needs a list of "values" with at least one entry.')
        seen = set()
        out = []
        for v in vals:
            if isinstance(v, str):
                _label_check(v)
            elif not _is_num(v):
                raise _fail('Axis "x" has a value that is neither text nor a number.')
            k = _scalar_key(v)
            if k in seen:
                raise _fail('Axis "x" lists the same value twice.')
            seen.add(k)
            out.append(v if isinstance(v, str) else float(v))
        values = tuple(out)
    return Axis(
        label=label if isinstance(label, str) else "",
        unit=unit if isinstance(unit, str) else "",
        scale=scale,
        min=lo,
        max=hi,
        values=values,
    )


def _parse_series_one(
    s: object, i: int, chart_type: str, multiple: bool, has_y2: bool, ref_list: list
) -> Series:
    if not isinstance(s, dict):
        raise _fail(f"Series {i + 1} isn't an object.")
    name = s.get("name")
    if multiple and not (isinstance(name, str) and name):
        raise _fail(f'Series {i + 1} needs a "name".')
    if "name" in s and not isinstance(name, str):
        raise _fail(f'Series {i + 1} needs a "name".')
    if isinstance(name, str):
        _label_check(name)
    ref = _ref(ref_list, i)
    stype = None
    if "type" in s:
        if chart_type not in _SERIES_TYPE_CHARTS:
            raise _fail(f'{ref} has its own "type", which only bar and line charts allow.')
        stype = s["type"]
        if stype not in ("bar", "line"):
            raise _fail(f'{ref} has a "type" that isn\'t bar or line.')
    axis = s.get("axis", "left")
    if "axis" in s:
        if axis not in ("left", "right"):
            raise _fail(f'{ref} has an "axis" that isn\'t left or right.')
        if axis == "right" and not has_y2:
            raise _fail(f'{ref} is on the right axis, but the chart has no "y2".')
    vals = s.get("values")
    if not isinstance(vals, list):
        raise _fail(f'{ref} needs a list of "values".')
    out: list = []
    for v in vals:
        if chart_type == "scatter":
            if not (isinstance(v, list) and len(v) == 2 and _is_num(v[0]) and _is_num(v[1])):
                raise _fail(f"{ref} has a point that isn't an [x, y] pair of numbers.")
            out.append((float(v[0]), float(v[1])))
        elif chart_type == "pie":
            if not _is_num(v):
                raise _fail(f"{ref} has a value that isn't a number.")
            out.append(float(v))
        else:
            if v is not None and not _is_num(v):
                raise _fail(f"{ref} has a value that isn't a number or null.")
            out.append(None if v is None else float(v))
    return Series(
        name=name if isinstance(name, str) else "",
        values=tuple(out),
        axis=axis,
        type=stype,
    )


def _parse_annotations(raw: object, chart_type: str, x: Axis, y: Axis, y2: Axis | None) -> tuple:
    if not isinstance(raw, list):
        raise _fail('The "annotations" must be a list.')
    out = []
    for i, a in enumerate(raw, start=1):
        if not isinstance(a, dict):
            raise _fail(f"Annotation {i} isn't an object.")
        axis = a.get("axis")
        if axis not in ("y", "y2", "x"):
            raise _fail(f'Annotation {i} needs an "axis" of y, y2 or x.')
        if axis == "y2" and y2 is None:
            raise _fail(f'Annotation {i} is on "y2", but the chart has no "y2".')
        value = a.get("value")
        if axis == "x" and chart_type != "scatter":
            if not (isinstance(value, str) or _is_num(value)) or (
                _scalar_key(value) not in {_scalar_key(v) for v in (x.values or ())}
            ):
                raise _fail(f"Annotation {i} is at a category that isn't in the x values.")
            value = value if isinstance(value, str) else float(value)
        else:
            if not _is_num(value):
                raise _fail(f'Annotation {i} needs a numeric "value".')
            value = float(value)
        label = a.get("label", "")
        if "label" in a:
            if not isinstance(label, str):
                raise _fail(f'Annotation {i} has a "label" that isn\'t text.')
            _label_check(label)
        log = {"y": y, "y2": y2, "x": x if chart_type == "scatter" else None}[axis]
        if log is not None and log.scale == "log" and value <= 0:
            raise _fail(f"Annotation {i} is on a log axis, so its value must be above 0.")
        out.append(Annotation(axis=axis, value=value, label=label))
    return tuple(out)


def _validate(source: str) -> ChartSpec:
    try:
        data = json.loads(source, parse_constant=_refuse_constant)
    except (ValueError, RecursionError):
        raise _fail("The chart text isn't valid JSON.") from None
    if not isinstance(data, dict):
        raise _fail("The chart must be one JSON object.")
    if "type" not in data:
        raise _fail('The chart needs a "type".')
    chart_type = data["type"]
    if not isinstance(chart_type, str) or chart_type not in TYPES:
        raise _fail('The chart "type" must be one of bar, line, area, scatter, pie or sparkline.')

    title = data.get("title", "")
    if "title" in data:
        if not isinstance(title, str):
            raise _fail('The "title" must be text.')
        if len(title) > MAX_TITLE:
            raise _fail(f"The title is {len(title)} characters; the limit is {MAX_TITLE}.")
    if "stacked" in data and not isinstance(data["stacked"], bool):
        raise _fail('The "stacked" setting must be true or false.')
    stacked = bool(data.get("stacked", False)) and chart_type in ("bar", "area")

    x = _parse_axis(data.get("x"), "x", chart_type) if chart_type in _X_TYPES else Axis()
    y = _parse_axis(data.get("y"), "y", chart_type)
    y2 = None
    if chart_type in _Y2_TYPES and data.get("y2") is not None:
        y2 = _parse_axis(data.get("y2"), "y2", chart_type)

    raw_series = data.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise _fail('The chart needs a "series" list with at least one entry.')
    multiple = len(raw_series) > 1
    series = [
        _parse_series_one(s, i, chart_type, multiple, y2 is not None, raw_series)
        for i, s in enumerate(raw_series)
    ]

    def ref(i: int) -> str:
        return _ref(raw_series, i)

    if chart_type == "pie" and len(series) != 1:
        raise _fail(f"A pie chart takes one series; this one has {len(series)}.")
    names = set()
    for s in series:
        if multiple and s.name in names:
            raise _fail(f'Two series are both named "{s.name}".')
        names.add(s.name)
    if chart_type in ("bar", "line", "area", "pie"):
        n = len(x.values or ())
        for i, s in enumerate(series):
            if len(s.values) != n:
                raise _fail(f"{ref(i)} has {len(s.values)} values, but the x axis has {n}.")
    for i, s in enumerate(series):
        if all(v is None for v in s.values):
            raise _fail(f"{ref(i)} has no values to draw.")
    if chart_type == "pie":
        for i, s in enumerate(series):
            if any(v < 0 for v in s.values):
                raise _fail(f"{ref(i)} has a negative value; a pie needs every slice at 0 or more.")
        if sum(series[0].values) <= 0:
            raise _fail("A pie chart needs a total above 0.")
    for i, s in enumerate(series):
        if chart_type == "scatter":
            if y.scale == "log" and any(v[1] <= 0 for v in s.values):
                raise _fail(
                    f"{ref(i)} has a value of 0 or less; a log scale needs every value above 0."
                )
            if x.scale == "log" and any(v[0] <= 0 for v in s.values):
                raise _fail(
                    f"{ref(i)} has an x value of 0 or less; a log scale needs every x above 0."
                )
        else:
            axis_scale = (y2 if s.axis == "right" and y2 is not None else y).scale
            if axis_scale == "log" and any(v is not None and v <= 0 for v in s.values):
                raise _fail(
                    f"{ref(i)} has a value of 0 or less; a log scale needs every value above 0."
                )
    if stacked and (y.scale == "log" or (y2 is not None and y2.scale == "log")):
        raise _fail("A stacked chart can't use a log scale.")

    annotations: tuple = ()
    raw_ann = data.get("annotations")
    if chart_type in _ANNOTATION_TYPES and "annotations" in data and raw_ann is not None:
        annotations = _parse_annotations(raw_ann, chart_type, x, y, y2)

    total = sum(len(s.values) for s in series)
    if total > MAX_VALUES:
        raise _fail(f"This chart has {total} values; the limit is {MAX_VALUES}.")
    if chart_type in ("bar", "line", "area", "pie") and len(x.values or ()) > MAX_CATEGORIES:
        raise _fail(
            f"This chart has {len(x.values or ())} categories; the limit is {MAX_CATEGORIES}."
        )
    if len(series) > MAX_SERIES:
        raise _fail(f"This chart has {len(series)} series; the limit is {MAX_SERIES}.")
    if chart_type == "pie" and len(series[0].values) > MAX_SLICES:
        raise _fail(
            f"This pie chart has {len(series[0].values)} slices; the limit is {MAX_SLICES}."
        )
    if len(annotations) > MAX_ANNOTATIONS:
        raise _fail(
            f"This chart has {len(annotations)} annotations; the limit is {MAX_ANNOTATIONS}."
        )

    return ChartSpec(
        type=chart_type,
        title=title,
        x=x,
        y=y,
        y2=y2,
        series=tuple(series),
        stacked=stacked,
        annotations=annotations,
    )


def parse_chart(source: str) -> ChartSpec | ChartError:
    """Parse and validate chart text. Never raises: a problem is a ``ChartError`` sentence."""
    try:
        return _validate(source)
    except _FailError as exc:
        return ChartError(exc.message)
    except Exception:  # pragma: no cover - defensive: the contract is "never raises"
        return ChartError("The chart couldn't be read.")
