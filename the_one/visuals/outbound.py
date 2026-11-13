"""Turn a reply's chart and widget blocks into platform text and images (M35 F3 L3).

Standard library only (imports ``chart_spec`` and ``blocks``). The plan is pure and draws
nothing; ``the_one/connectors/delivery.py::send_reply`` draws the candidates and sends.

A chart that parses becomes a marker line (when drawn) and an image; any other chart block
stays as its source. A widget block, closed or not, becomes a one-line note. At most
``MAX_IMAGES`` charts are candidates.
"""

from __future__ import annotations

from dataclasses import dataclass

from the_one.visuals.blocks import find_blocks
from the_one.visuals.chart_spec import ChartError, ChartSpec, parse_chart

MAX_IMAGES = 10
CHART_MARKER = "\U0001f4ca Chart: {title} (below)"
CHART_MARKER_UNTITLED = "\U0001f4ca Chart {number} (below)"
WIDGET_NOTE = "\U0001f9e9 Interactive widget: open this chat in the app to see it."


@dataclass(frozen=True, slots=True)
class OutboundImage:
    """One drawn image for a platform send. ``fallback`` is the chart's source block."""

    filename: str
    data: bytes
    title: str
    width: int
    height: int
    fallback: str


@dataclass(frozen=True, slots=True)
class ChartCandidate:
    index: int  # position among the candidates
    number: int  # position among every top-level chart block, 1-based
    title: str
    spec: ChartSpec
    source: str

    @property
    def alt(self) -> str:
        return self.title or f"Chart {self.number}"

    @property
    def marker(self) -> str:
        if self.title:
            return CHART_MARKER.format(title=self.title)
        return CHART_MARKER_UNTITLED.format(number=self.number)


@dataclass(frozen=True, slots=True)
class OutboundPlan:
    # ("text", str) | ("widget", source) | ("chart", ChartCandidate | None, source)
    segments: tuple
    candidates: tuple

    def render(self, drawn: set[int]) -> str:
        out: list[str] = []
        for seg in self.segments:
            kind = seg[0]
            if kind == "text":
                out.append(seg[1])
            elif kind == "widget":
                out.append(WIDGET_NOTE + ("\n" if seg[1].endswith("\n") else ""))
            else:
                cand, source = seg[1], seg[2]
                if cand is not None and cand.index in drawn:
                    out.append(cand.marker + ("\n" if source.endswith("\n") else ""))
                else:
                    out.append(source)
        return "".join(out)

    @property
    def fallback_text(self) -> str:
        return self.render(set())

    @property
    def has_widget(self) -> bool:
        return any(seg[0] == "widget" for seg in self.segments)


def plan_outbound(text: str) -> OutboundPlan | None:
    """The plan for ``text``, or ``None`` when nothing in it converts (send it unchanged)."""
    segments: list[tuple] = []
    candidates: list[ChartCandidate] = []
    pos = 0
    chart_number = 0
    has_widget = False
    for block in find_blocks(text):
        if block.tag not in ("chart", "widget"):
            continue
        source = text[block.start : block.end]
        if block.start > pos:
            segments.append(("text", text[pos : block.start]))
        pos = block.end
        if block.tag == "widget":
            has_widget = True
            segments.append(("widget", source))
            continue
        chart_number += 1
        cand = None
        if block.closed and len(candidates) < MAX_IMAGES:
            spec = parse_chart(block.body)
            if not isinstance(spec, ChartError):
                cand = ChartCandidate(
                    index=len(candidates),
                    number=chart_number,
                    title=" ".join(spec.title.split()),
                    spec=spec,
                    source=source,
                )
                candidates.append(cand)
        segments.append(("chart", cand, source))
    if not has_widget and not candidates:
        return None
    if pos < len(text):
        segments.append(("text", text[pos:]))
    return OutboundPlan(segments=tuple(segments), candidates=tuple(candidates))
