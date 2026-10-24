#!/usr/bin/env python3
"""Write an .icns (and optional PNG sizes) from the staged 512px icon (Mission 32 Flight 1 spike).

    make-icns.py ICON_512_PNG OUT.icns [--png-dir DIR]

Pillow writes ICNS directly, so this runs the same on Linux (rehearsal) and on the macOS
runner (where `iconutil` also exists but needs an .iconset folder). With --png-dir it also writes
icon-<size>.png. Needs Pillow.
"""

import sys
from pathlib import Path

from PIL import Image

SIZES = (16, 32, 64, 128, 256, 512)


def main() -> int:
    args = sys.argv[1:]
    png_dir = None
    if "--png-dir" in args:
        i = args.index("--png-dir")
        png_dir = Path(args[i + 1])
        del args[i : i + 2]
    src_path, out = Path(args[0]), Path(args[1])
    src = Image.open(src_path).convert("RGBA")
    if src.size[0] != src.size[1] or src.size[0] < 512:
        raise SystemExit(f"{src_path}: expected a square image of at least 512 px, got {src.size}")
    src.save(out, format="ICNS", sizes=[(s, s) for s in SIZES])
    if png_dir is not None:
        png_dir.mkdir(parents=True, exist_ok=True)
        for s in SIZES:
            src.resize((s, s), Image.LANCZOS).save(png_dir / f"icon-{s}.png")
    check = Image.open(out)
    print(f"wrote {out} ({out.stat().st_size} bytes), sizes {sorted(check.info.get('sizes', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
