"""Derive favicon and topbar-icon PNG variants from the source mascot.

This script is invoked by `make brand-assets` (which runs it inside the live
`the-one` container via `docker exec`). It reads a single source PNG and
produces 8 derived assets in the static brand directory: seven sized PNGs
(16, 24, 32, 48, 180, 192, 512) plus one multi-resolution `.ico` packaging
16/32/48.

When to re-run: any time the source mascot is refreshed. The derivation is
idempotent at the pixel level — running twice produces outputs whose decoded
pixel bytes (`PIL.Image.open(p).tobytes()`) match between runs. File-byte
equality is NOT guaranteed because Pillow's PNG encoder output can vary
across Pillow versions; pixel equality is the contract.

The 8 derived files commit to the repository — they are NOT gitignored —
because they ship inside the built image and are served at `/static/brand/`.

Usage:
    docker exec the-one python /app/scripts/derive_brand_assets.py
    docker exec the-one python /app/scripts/derive_brand_assets.py \\
        --source /app/the_one/interfaces/web/static/brand/gleepglorp_med.png

Source-file evolution:
    Flight 01 leg 01 originally used `gleepglorp_med.png` (the full circular
    emblem with baked-in wordmark) as the source. At HAT (leg 05), the
    operator added `gleepglorp_icon.png` — a simpler head-crop variant that
    downscales more cleanly at favicon sizes (16x16, 32x32 lose less
    recognizable detail). Default source switched to `gleepglorp_icon.png`
    at HAT. The med PNG remains in the brand/ directory as the
    full-emblem reference; pass it via `--source` to regenerate from the
    emblem if a future surface needs the wordmark baked into the bitmap.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# Default source / output paths inside the container. The container's WORKDIR
# is /app (Dockerfile), and ./the_one is bind-mounted at /app/the_one (see
# docker-compose.yml), so these absolute paths resolve correctly under
# `docker exec the-one ...`.
DEFAULT_SOURCE = Path("/app/the_one/interfaces/web/static/brand/gleepglorp_icon.png")
DEFAULT_OUT_DIR = Path("/app/the_one/interfaces/web/static/brand")

# Sized PNG outputs: (target_pixels, filename_template).
# The 24px asset is `topbar-icon-24.png` (consumed by the topbar `<img>`),
# 180px is `apple-touch-icon.png`, 192/512 are `icon-{size}.png` (PWA
# convention; no manifest yet, but matches future PWA wiring), and 16/32/48
# are `favicon-{size}.png` (used directly by the favicon `<link>` set
# alongside the multi-res `.ico`).
PNG_OUTPUTS: list[tuple[int, str]] = [
    (16, "favicon-16.png"),
    (24, "topbar-icon-24.png"),
    (32, "favicon-32.png"),
    (48, "favicon-48.png"),
    (180, "apple-touch-icon.png"),
    (192, "icon-192.png"),
    (512, "icon-512.png"),
]

# Multi-resolution ICO: Pillow handles the multi-size packaging internally
# when `sizes=` is passed to `.save(..., "ICO", sizes=[...])`.
ICO_FILENAME = "favicon.ico"
ICO_SIZES: list[tuple[int, int]] = [(16, 16), (32, 32), (48, 48)]


def square_pad(source: Image.Image) -> Image.Image:
    """Return an RGBA canvas of `max(w, h)` square dimensions with the source pasted centered.

    Pillow's downscalers expect a square input to avoid distortion; AI-generated
    PNGs occasionally drift from exact squareness. If the source is already
    square, the paste is a visual no-op but the code path stays uniform.

    Always returns RGBA: the canvas is constructed as RGBA with a fully
    transparent fill, so an RGB source (no alpha) becomes RGBA-with-opaque
    pixels in the union region and transparent elsewhere.
    """
    w, h = source.size
    size = max(w, h)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - w) // 2, (size - h) // 2)
    canvas.paste(source, offset)
    return canvas


def derive(source_path: Path, out_dir: Path) -> list[Path]:
    """Read `source_path`, derive all 8 brand assets into `out_dir`. Returns output paths."""
    if not source_path.exists():
        raise FileNotFoundError(f"source PNG not found: {source_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as raw:
        # `.load()` materializes the image so the `with` block can close the
        # underlying file handle without leaving us holding a lazy reference.
        raw.load()
        canvas = square_pad(raw)

    written: list[Path] = []

    for target, filename in PNG_OUTPUTS:
        out_path = out_dir / filename
        resized = canvas.resize((target, target), Image.Resampling.LANCZOS)
        resized.save(out_path, "PNG", optimize=True)
        written.append(out_path)

    # The .ico is generated from a 48×48 resize of the square-padded canvas;
    # Pillow then packages the requested sizes inside the single .ico file.
    ico_path = out_dir / ICO_FILENAME
    ico_base = canvas.resize((48, 48), Image.Resampling.LANCZOS)
    ico_base.save(ico_path, "ICO", sizes=ICO_SIZES)
    written.append(ico_path)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Source PNG to derive from (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory for derived assets (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args(argv)

    written = derive(args.source, args.out_dir)
    print(f"Derived {len(written)} brand assets from {args.source}:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
