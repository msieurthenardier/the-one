#!/usr/bin/env python3
"""Chart image sample sheet (M35 F3 L1, a developer tool; not part of the product).

Draws one PNG per valid corpus chart (``tests/fixtures/charts/valid/*.json``), plus an at-limit
chart and a chart with a CJK title, with the server's renderer, and writes an ``index.html`` that
shows each at its natural size on a plain white page, so the operator sees what a chat platform
shows. Output goes to ``--out DIR``, which must be outside the repository (the images are local
evidence, never committed).

    python scripts/chart_sample_sheet.py --out ~/m35f3-sample-sheet

Exit codes: 0 written, 2 refused (``--out`` inside the repository) or a chart failed to draw.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from the_one.visuals.chart_image import ChartImageError, render_png  # noqa: E402
from the_one.visuals.chart_spec import ChartError, parse_chart  # noqa: E402

CORPUS_DIR = REPO_ROOT / "tests" / "fixtures" / "charts" / "valid"
CJK_TITLE = "季度收入 Revenue"


def at_limit_source() -> str:
    """2000 values over 8 series, a log y axis and 5 annotations (the format's limits)."""
    series = []
    for si in range(8):
        pts = [[i + 1, 1 + ((si * 131 + i * 37) % 997) * 10] for i in range(250)]
        series.append({"name": f"Series {si + 1}", "values": pts})
    annotations = [
        {"axis": "y", "value": 10, "label": "Floor"},
        {"axis": "y", "value": 1000, "label": "Target"},
        {"axis": "y", "value": 5000, "label": "Stretch"},
        {"axis": "x", "value": 50, "label": "Start"},
        {"axis": "x", "value": 200, "label": "Launch"},
    ]
    return json.dumps(
        {
            "type": "scatter",
            "title": "At the format limits",
            "x": {"label": "Sample"},
            "y": {"label": "Latency", "unit": "ms", "scale": "log"},
            "series": series,
            "annotations": annotations,
        }
    )


def cjk_title_source() -> str:
    return json.dumps(
        {
            "type": "bar",
            "title": CJK_TITLE,
            "x": {"values": ["Q1", "Q2", "Q3", "Q4"]},
            "y": {"unit": "$"},
            "series": [{"name": "Revenue", "values": [120, 135, 150, 180]}],
        }
    )


def sample_sources() -> dict:
    """File name (without extension) -> chart text, in the order shown on the sheet."""
    out = {p.stem: p.read_text(encoding="utf-8") for p in sorted(CORPUS_DIR.glob("*.json"))}
    out["at-limit-2000-values"] = at_limit_source()
    out["cjk-title"] = cjk_title_source()
    return out


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def main(argv: list | None = None, repo_root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="output directory, outside the repository")
    args = parser.parse_args(argv)
    out = Path(args.out).expanduser()
    if _inside(out, repo_root):
        print(
            f"refusing --out {out}: it is inside the repo ({repo_root}). The sample sheet is "
            "local evidence and is never committed; pick a directory outside it.",
            file=sys.stderr,
        )
        return 2
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, source in sample_sources().items():
        spec = parse_chart(source)
        if isinstance(spec, ChartError):
            print(f"{name}: does not parse: {spec.message}", file=sys.stderr)
            return 2
        try:
            rendered = render_png(spec)
        except ChartImageError as exc:
            print(f"{name}: {exc}", file=sys.stderr)
            return 2
        (out / f"{name}.png").write_bytes(rendered.data)
        entries.append((name, rendered))
        print(f"{name}.png  {rendered.width}x{rendered.height}  {len(rendered.data)} bytes")
    rows = "\n".join(
        f"<h3>{html.escape(name)}.png ({r.width}x{r.height} px)</h3>\n"
        f'<img src="{html.escape(name)}.png" width="{r.width}" height="{r.height}" alt="">'
        for name, r in entries
    )
    (out / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>Chart image sample sheet</title>'
        "<style>body{background:#fff;font:14px sans-serif;margin:24px}"
        "h3{margin:28px 0 6px;font-weight:600}img{display:block}</style></head><body>"
        f"<h1>Chart image sample sheet</h1>\n{rows}\n</body></html>\n",
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} images and index.html to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
