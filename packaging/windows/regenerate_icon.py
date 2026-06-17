"""Regenerate installer-assets/the-one.ico from the 512px brand master.

Produces a reproducible multi-size .ico from the_one/interfaces/web/static/brand/icon-512.png
with sizes [(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)].  Pillow downsamples
from the 512 source using LANCZOS; no size is larger than the source so no upscaling occurs.

Design decision DD5: icon= is set on exe_gui EXE() in the-one.spec so the windowed
the-one-app.exe carries an embedded brand icon (window, taskbar, Alt-Tab).

Usage (runnable from any directory):
    python packaging/windows/regenerate_icon.py
"""

import pathlib

from PIL import Image

# Paths relative to this file so the script is runnable from anywhere.
_HERE = pathlib.Path(__file__).parent
_SRC = _HERE.parent.parent / "the_one" / "interfaces" / "web" / "static" / "brand" / "icon-512.png"
_OUT = _HERE / "installer-assets" / "the-one.ico"

_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def main() -> None:
    img = Image.open(_SRC)
    print(f"Source: {_SRC}  size={img.size}  mode={img.mode}")
    # Do NOT mutate the source image before saving — Pillow downsamples each
    # ICO frame from the original on write.
    img.save(_OUT, format="ICO", sizes=_SIZES)
    # Verify the written sizes.
    with Image.open(_OUT) as out_img:
        written = sorted(out_img.info["sizes"])
    print(f"Written: {_OUT}")
    print(f"ICO sizes: {written}")


if __name__ == "__main__":
    main()
