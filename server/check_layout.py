#!/usr/bin/env python3
"""Check the layout config for overlapping or off-canvas elements.

The layout is data, so a font-size or coordinate change can silently push text
over the moon image, into a neighbouring field, or off the 400x300 canvas. This
script renders the widest strings the panchanga source actually produces and
reports any collision.

Run after editing the config:

    python3 check_layout.py

Exits non-zero if anything overlaps, so it can gate a commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calendar_config import ConfigStore  # noqa: E402
from renderer import DEFAULT_FONT, Renderer, is_hidden, line4_box  # noqa: E402

# Longest values observed from the panchanga source and the Tamil month table,
# used as the worst case for each field.
WORST_CASE = {
    "date": "31",
    "month": "Sep",
    "weekday": "Wed",
    "tithi": "Shraddhabhava",  # longest seen: 13 chars
    "paksha": "Krishna",
    "masa": "Margashira",
    "nakshatra": "Uttarabhadra",
    "tamil_month": "கார்த்திகை",  # Karthigai, the longest Tamil month name
    "tamil_date": "31",
    # "N.Eka: " plus the longest month abbreviation and a two-digit date.
    "next_ekadashi": "N.Eka: Sep 30",
    # Line 4 is drawn from the day's custom text, falling back to the
    # Festivals/Events element; this is the longest event seen from the source.
    "custom_text": "SHRIKAMBALURU RAMACHANDRATIRTHARA ARADHANE (RAYAVELURU)",
}


def main() -> int:
    config = ConfigStore().load()
    renderer = Renderer(config)
    width = int(config["canvas"]["width"])
    height = int(config["canvas"]["height"])

    problems: list[str] = []
    spans: list[tuple[str, float, float, float, float]] = []

    def span(name: str, element: dict, text: str, default_size=None):
        """Record the drawn box of one field: left, top, right, bottom."""
        x = element.get("x", -1)
        y = element.get("y", -1)
        size = element.get("font_size", default_size)
        if is_hidden(x, y, size):
            return  # element is switched off, so it cannot collide
        font_name = element.get("font") or DEFAULT_FONT
        font = renderer.font(font_name, int(size))
        advance = font.getlength(text)
        # Use the ascent/descent so vertical overlaps are caught too.
        ascent, descent = font.getmetrics()
        box = (float(x), float(y), float(x) + advance, float(y) + ascent + descent)
        spans.append((name, *box))
        if box[2] > width:
            problems.append(
                f"{name}: overflows the right edge by {box[2] - width:.0f}px "
                f"(ends at {box[2]:.0f}, canvas is {width})"
            )
        if box[3] > height:
            problems.append(
                f"{name}: overflows the bottom edge by {box[3] - height:.0f}px "
                f"(ends at {box[3]:.0f}, canvas is {height})"
            )

    line1 = config["line1"]
    span("line1.date", line1["date"], WORST_CASE["date"])
    span("line1.month", line1["month"], WORST_CASE["month"])
    span("line1.weekday", line1["weekday"], WORST_CASE["weekday"])

    # The day icon is a fixed box, treated as a span so text is checked against it.
    for label, cfg in (
        ("line1.day_image", line1.get("day_image", {})),
        ("addl_image", config.get("addl_image", {})),
    ):
        if not cfg:
            continue
        x = int(cfg.get("x", -1))
        y = int(cfg.get("y", -1))
        if is_hidden(x, y):
            continue
        # Either side may be derived from the source aspect ratio. Use whichever
        # is given, and when a side is absent or non-positive fall back to the
        # configured default for the other; the span is an estimate either way,
        # since the check has no access to the actual image files.
        box_w = int(cfg.get("width") or 64)
        box_h = int(cfg.get("height") or 64)
        if box_w <= 0:
            box_w = 64
        if box_h <= 0:
            box_h = 64
        spans.append(
            (label, float(x), float(y), float(x + box_w), float(y + box_h))
        )

    line2 = config["line2"]
    span("line2.tithi", {**line2["tithi"], "y": line2.get("y", 148)},
         WORST_CASE["tithi"])
    span("line2.paksha", {**line2["paksha"], "y": line2.get("y", 148)},
         WORST_CASE["paksha"])

    moon = line2["moon_image"]
    spans.append((
        "line2.moon_image",
        float(moon["x"] - moon["radius"]), float(moon["y"] - moon["radius"]),
        float(moon["x"] + moon["radius"]), float(moon["y"] + moon["radius"]),
    ))

    line3 = config["line3"]
    line3_y = line3.get("y", 190)
    span("line3.masa", {**line3["masa"], "y": line3["masa"].get("y", line3_y)},
         WORST_CASE["masa"])
    span("line3.tithi", {**line3["tithi"], "y": line3["tithi"].get("y", line3_y)},
         WORST_CASE["tithi"])
    span("line3.nakshatra",
         {**line3["nakshatra"], "y": line3["nakshatra"].get("y", line3_y)},
         WORST_CASE["nakshatra"])
    if "next_ekadashi" in line3:
        span("line3.next_ekadashi",
             {**line3["next_ekadashi"],
              "y": line3["next_ekadashi"].get("y", line3_y)},
             WORST_CASE["next_ekadashi"])
    span("line3.tamil_month", line3["tamil_month"], WORST_CASE["tamil_month"])
    span("line3.tamil_date", line3["tamil_date"], WORST_CASE["tamil_date"])

    # "line4" and "addl_image" share the bottom row, so a long custom text can
    # run into the second image; line4_box reports the wrapped block.
    line4 = config["line4"]

    # Line 4 is not a single run of text at a fixed size: the renderer wraps it
    # to "max_width" and steps the size down until it fits the space left above
    # "max_y", so the drawn block is what has to be checked. Measuring the raw
    # string at "font_size" would report a collision it does not have.
    block = line4_box(renderer, line4, WORST_CASE["custom_text"])
    if block is not None:
        spans.append(("line4.custom_text", *block))

    # Dividers are reported separately: a full-width line is meant to cross the
    # canvas, so it would otherwise register as a collision with everything.
    for index, divider in enumerate(config.get("dividers") or []):
        divider_y = int(divider.get("y", -1))
        if divider_y < 0:
            continue
        if divider_y >= height:
            problems.append(f"dividers[{index}]: y={divider_y} is off-canvas")
        print(f"  divider[{index}]       y {divider_y}")

    # Pairwise overlap check, ignoring fields that legitimately sit on different
    # rows (their bounding boxes differ vertically and so do not intersect).
    for index, (name_a, ax0, ay0, ax1, ay1) in enumerate(spans):
        for name_b, bx0, by0, bx1, by1 in spans[index + 1:]:
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                problems.append(
                    f"{name_a} overlaps {name_b} "
                    f"(x {ax0:.0f}-{ax1:.0f} vs {bx0:.0f}-{bx1:.0f}, "
                    f"y {ay0:.0f}-{ay1:.0f} vs {by0:.0f}-{by1:.0f})"
                )

    for name, x0, y0, x1, y1 in spans:
        print(f"  {name:20} x {x0:6.0f}..{x1:6.0f}   y {y0:5.0f}..{y1:5.0f}")

    print()
    if problems:
        print(f"{len(problems)} layout problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("Layout is clear: no overlaps, nothing off-canvas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
