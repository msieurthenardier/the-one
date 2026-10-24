"""Convert an `xwd` dump (32 bpp ZPixmap) to PNG with Pillow. Spike tooling, stdlib + Pillow.

usage: xwd2png.py in.xwd out.png
"""

import struct
import sys

from PIL import Image


def convert(src: str, dst: str) -> tuple[int, int]:
    data = open(src, "rb").read()
    fields = struct.unpack(">25I", data[:100])
    header_size, width, height = fields[0], fields[4], fields[5]
    byte_order, bpp, bytes_per_line, ncolors = fields[7], fields[11], fields[12], fields[19]
    if bpp != 32:
        raise SystemExit(f"xwd2png: unsupported bits_per_pixel {bpp}")
    offset = header_size + ncolors * 12
    raw = data[offset : offset + bytes_per_line * height]
    mode = "BGRX" if byte_order == 0 else "XRGB"
    img = Image.frombuffer("RGB", (width, height), raw, "raw", mode, bytes_per_line, 1)
    img.save(dst)
    return width, height


if __name__ == "__main__":
    w, h = convert(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[2]}: {w}x{h}")
