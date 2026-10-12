"""Generate the multi-resolution .ico used by the app and the installer.

Run:  python installer/make_icon.py
Output: installer/app.ico
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

SIZE = 256


def build_frame(size: int) -> Image.Image:
    """Draw the TVBox logo at an arbitrary size (supersampled 4x)."""
    ss = size * 4
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded background (dark navy)
    margin = int(ss * 0.04)
    radius = int(ss * 0.20)
    d.rounded_rectangle(
        [margin, margin, ss - margin, ss - margin],
        radius=radius,
        fill=(24, 32, 56, 255),
    )

    # Inner "screen" area (slightly lighter)
    inner_inset = int(ss * 0.16)
    d.rounded_rectangle(
        [inner_inset, inner_inset, ss - inner_inset, ss - inner_inset],
        radius=int(ss * 0.10),
        fill=(36, 48, 78, 255),
    )

    # Play triangle (red — matches TVBox accent)
    cx, cy = ss / 2, ss / 2
    tri_h = ss * 0.26
    tri_w = ss * 0.22
    d.polygon(
        [
            (cx - tri_w * 0.45, cy - tri_h / 2),
            (cx - tri_w * 0.45, cy + tri_h / 2),
            (cx + tri_w * 0.75, cy),
        ],
        fill=(233, 69, 60, 255),
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "app.ico")
    # Draw once at the max size and let Pillow produce every requested frame.
    master = build_frame(SIZE)
    master.save(out, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
