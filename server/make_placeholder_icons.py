#!/usr/bin/env python3
"""Create the placeholder day-icon PNGs.

The layout places a 64x64 image at the top-right for the current weekday, or a
"special" image on days with custom text. Real artwork will replace these; until
then they are generated from a simple geometric motif so the page renders with
the icon slot visibly occupied.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

TARGET = Path(__file__).resolve().parent / "assets" / "day"

# One distinct simple glyph per weekday, plus a star for special days.
NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun", "special")


def draw_icon(name: str, size: int = 64) -> Image.Image:
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    margin = 6
    box = (margin, margin, size - margin, size - margin)

    if name == "special":
        # Five-point star to distinguish special days.
        import math

        cx = cy = size / 2
        outer, inner = size / 2 - margin, size / 4.5
        points = []
        for index in range(10):
            radius = outer if index % 2 == 0 else inner
            angle = -math.pi / 2 + index * math.pi / 5
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(points, outline=0, fill=None)
        draw.line(points + [points[0]], fill=0, width=2)
    elif name == "sun":
        draw.ellipse(box, outline=0, width=3)
        for index in range(8):
            import math

            angle = index * math.pi / 4
            cx = cy = size / 2
            r1, r2 = size / 2 - margin, size / 2 - 2
            draw.line(
                [cx + r1 * math.cos(angle), cy + r1 * math.sin(angle),
                 cx + r2 * math.cos(angle), cy + r2 * math.sin(angle)],
                fill=0, width=2,
            )
    elif name == "mon":
        # Crescent.
        draw.ellipse(box, outline=0, width=3)
        draw.ellipse(
            (margin + 10, margin - 6, size - margin + 10, size - margin - 6),
            fill=255, outline=255,
        )
        draw.ellipse(box, outline=0, width=3)
    else:
        # Distinguishable per weekday by number of bars.
        draw.rectangle(box, outline=0, width=3)
        count = NAMES.index(name) + 1
        for index in range(count):
            y = margin + 10 + index * (size - 2 * margin - 16) / max(count - 1, 1)
            draw.line([margin + 8, y, size - margin - 8, y], fill=0, width=3)

    return image


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        icon = draw_icon(name)
        # Threshold to pure black/white: the renderer treats icons as 1-bit and
        # dithering line art produces speckle on the panel.
        icon = icon.point(lambda value: 0 if value < 128 else 255, "1")
        icon.save(TARGET / f"{name}.png")
        print(f"wrote {TARGET / name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
