"""Renders a calendar day into the display's native 1-bit bitmap.

Output format is a raw 400x300 monochrome buffer, 15000 bytes, MSB-first within
each byte and row-major, with a set bit meaning white. That is exactly what the
Waveshare driver expects for a full refresh, so the buffer is sent to the ESP32
unmodified.

The firmware uses the fast refresh path (Init_Fast/Display_Fast); see the
firmware's config.h for how often a full clear is interleaved.

Tamil text relies on the Raqm layout engine. Without it, Pillow silently falls
back to basic layout and vowel signs are positioned by code point order rather
than visual order, producing malformed Tamil. ``require_raqm`` guards this.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from calendar_config import resolve_font_path

SERVER_DIR = Path(__file__).resolve().parent

# Artwork baked into the image. It seeds the writable assets directory and is
# never written to at runtime.
SHIPPED_ASSETS_DIR = SERVER_DIR / "assets"


def default_assets_dir() -> Path:
    """Writable directory images are read from.

    Defaults to the shipped ``server/assets`` for a checkout run, but the
    container points ``EINK_ASSETS_DIR`` at the data volume: artwork uploaded
    through the web UI has to survive the container being recreated, and the
    image's own filesystem does not.
    """
    override = os.environ.get("EINK_ASSETS_DIR")
    if override:
        return Path(override)
    return SHIPPED_ASSETS_DIR

DASH = "—"

WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAY_ICON = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# Image files are looked up in this subdirectory of assets/.
DAY_IMAGE_DIR = "day"

# Coverage at or above which a text pixel becomes solid black. The 50% midpoint
# (128) erodes thin strokes, so the cutoff is biased towards ink; text is drawn
# anti-aliased into a greyscale layer and thresholded with this value.
TEXT_THRESHOLD = 170

# Font name used by elements that do not set "font" themselves. Any name in the
# fonts block works; this is only the fallback.
DEFAULT_FONT = "latin"


class RaqmUnavailable(RuntimeError):
    """Raised when Tamil shaping support is missing from Pillow."""


class ConfigError(ValueError):
    """Raised when the layout config refers to something that does not exist."""


def require_raqm() -> None:
    """Fail loudly if Pillow cannot shape complex scripts."""
    from PIL import features

    if not features.check("raqm"):
        raise RaqmUnavailable(
            "Pillow was built without Raqm, so Tamil vowel signs would be placed "
            "incorrectly and no error would be raised. Install libraqm (Debian: "
            "'libraqm0') or use the distro python3-pil package."
        )


def is_hidden(x: object, y: object, font_size: object = None) -> bool:
    """Whether an element should be skipped.

    An element is hidden when its x or y is negative, or when its font size is
    zero. That lets a field be switched off in the config without deleting the
    rest of its settings.
    """
    if font_size is not None and int(font_size) == 0:
        return True
    return int(x) < 0 or int(y) < 0


def _derived_side(value: object) -> int | None:
    """A configured width/height, or None when that side should be derived.

    Absent, zero and negative all mean "work this side out from the source
    aspect ratio". Zero is the documented convention; the other two are accepted
    so a parked or commented-out value behaves the same way instead of drawing
    something nonsensical.
    """
    if value is None:
        return None
    side = int(value)
    return side if side > 0 else None


@dataclass
class RenderInput:
    """Everything needed to draw one day."""

    date: Date
    masa: str = DASH
    paksha: str = DASH
    tithi: str = DASH
    nakshatra: str = DASH
    next_ekadashi: str = DASH
    tamil_month: str = ""
    tamil_month_ta: str = ""
    tamil_date: int | None = None
    custom_text: str = ""
    day_image: str = ""
    addl_image: str = ""
    paksha_code: str | None = None
    tithi_number: int | None = None
    panchanga_ok: bool = True

    @property
    def date_number(self) -> str:
        return str(self.date.day)

    @property
    def month_abbr(self) -> str:
        return MONTH_ABBR[self.date.month - 1]

    @property
    def weekday_abbr(self) -> str:
        return WEEKDAY_ABBR[self.date.weekday()]

    @property
    def default_icon(self) -> str:
        """Icon file stem for the weekday, e.g. "mon"."""
        return WEEKDAY_ICON[self.date.weekday()]


class Renderer:
    """Draws day bitmaps, caching loaded fonts across calls."""

    def __init__(self, config: dict, assets_dir: Path | None = None) -> None:
        self.config = config
        self.assets_dir = Path(assets_dir) if assets_dir else default_assets_dir()
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        # Set for the duration of a render(); text goes here, not to the bitmap.
        self._text_layer: Image.Image | None = None
        self._text_draw: ImageDraw.ImageDraw | None = None

    # ------------------------------------------------------------------ fonts
    def font_files(self) -> dict[str, str]:
        """The ``fonts`` block: a name -> font-file mapping from the config."""
        fonts_cfg = self.config.get("fonts") or {}
        if not isinstance(fonts_cfg, dict):
            raise ConfigError("The 'fonts' section must be a mapping of name to font file.")
        return {str(name): str(path) for name, path in fonts_cfg.items()}

    def font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        """Load a named font from the ``fonts`` block at ``size`` pixels.

        Any key in ``fonts`` may be used, and any element may select one with a
        "font" setting; an unknown name is an error rather than a silent fallback
        to another face, because a silent fallback renders plausible-looking text
        in the wrong font.
        """
        key = (name, size)
        cached = self._fonts.get(key)
        if cached is not None:
            return cached

        files = self.font_files()
        if name not in files:
            known = ", ".join(sorted(files)) or "(none defined)"
            raise ConfigError(
                f"No font named {name!r} in the fonts section. Known names: {known}."
            )

        path = resolve_font_path(files[name])
        if not Path(path).exists():
            raise ConfigError(
                f"Font {name!r} points at {path}, which does not exist. Add the "
                "file to server/fonts/ (and rebuild the container), or point the "
                "name at a font that is already there."
            )

        # Raqm is required for Tamil; requesting it explicitly makes the missing
        # case visible instead of a silent basic-layout fallback.
        loaded = ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
        self._fonts[key] = loaded
        return loaded

    # ------------------------------------------------------------------ image
    def render(self, data: RenderInput) -> bytes:
        """Render ``data`` and return the 15000-byte 1-bit buffer."""
        canvas = self.config.get("canvas", {})
        width = int(canvas.get("width", 400))
        height = int(canvas.get("height", 300))

        image = Image.new("1", (width, height), 1)
        draw = ImageDraw.Draw(image)

        # Dividers are drawn first so text and images sit on top of them.
        self._draw_dividers(draw)

        # Text accumulates in a greyscale layer that is thresholded once at the
        # end, so anti-aliased glyph edges survive instead of being cut off one
        # pixel at a time against the 1-bit canvas.
        self._text_layer = Image.new("L", (width, height), 255)
        self._text_draw = ImageDraw.Draw(self._text_layer)
        try:
            self._draw_line1(draw, image, data)
            self._draw_line2(draw, image, data)
            self._draw_line3(draw, data)
            self._draw_line4(draw, data)
            self._draw_addl_image(image, data)

            if not data.panchanga_ok:
                self._draw_dashes_note(draw)
        finally:
            self._merge_text_layer(image)
            self._text_layer = None
            self._text_draw = None

        buffer = image.tobytes()
        expected = width * height // 8
        if len(buffer) != expected:
            raise AssertionError(
                f"bitmap is {len(buffer)} bytes, expected {expected}"
            )
        return buffer

    def render_to_png(self, data: RenderInput, path: Path, scale: int = 2) -> None:
        """Debug helper: render and save a viewable PNG for inspection."""
        canvas = self.config.get("canvas", {})
        width = int(canvas.get("width", 400))
        height = int(canvas.get("height", 300))
        Image.frombytes("1", (width, height), self.render(data)).convert("L").resize(
            (width * scale, height * scale), Image.NEAREST
        ).save(path)

    # ------------------------------------------------------------- line drawing
    def _draw_line1(self, draw: ImageDraw.ImageDraw, image: Image.Image, data: RenderInput) -> None:
        cfg = self.config.get("line1", {})

        date_cfg = cfg.get("date", {})
        self._text_cfg(draw, date_cfg, date_cfg.get("y", 60), data.date_number)

        month_cfg = cfg.get("month", {})
        self._text_cfg(draw, month_cfg, month_cfg.get("y", 78), data.month_abbr)

        weekday_cfg = cfg.get("weekday", {})
        self._text_cfg(draw, weekday_cfg, weekday_cfg.get("y", 78), data.weekday_abbr)

        # The day image is named by the day record, falling back to the weekday.
        name = (data.day_image or "").strip() or data.default_icon
        img_cfg = cfg.get("day_image", {})
        self._place_image(image, name, img_cfg)

    def _draw_line2(self, draw: ImageDraw.ImageDraw, image: Image.Image, data: RenderInput) -> None:
        cfg = self.config.get("line2", {})
        default_y = int(cfg.get("y", 148))

        tithi_cfg = cfg.get("tithi", {})
        self._text_cfg(draw, tithi_cfg, tithi_cfg.get("y", default_y), data.tithi)

        moon_cfg = cfg.get("moon_image", {})
        cx = int(moon_cfg.get("x", 196))
        cy = int(moon_cfg.get("y", 146))
        radius = moon_cfg.get("radius")
        # The moon is skipped like any other element: x/y of -1 turns it off.
        if not is_hidden(cx, cy) and radius is not None and int(radius) > 0:
            self._draw_moon(
                image,
                cx=cx,
                cy=cy,
                radius=int(radius),
                paksha=data.paksha_code,
                tithi_number=data.tithi_number,
            )

        paksha_cfg = cfg.get("paksha", {})
        self._text_cfg(draw, paksha_cfg, paksha_cfg.get("y", default_y), data.paksha)

    def _draw_line3(self, draw: ImageDraw.ImageDraw, data: RenderInput) -> None:
        cfg = self.config.get("line3", {})
        default_y = int(cfg.get("y", 190))

        for key, value in (
            ("masa", data.masa),
            ("tithi", data.tithi),
            ("nakshatra", data.nakshatra),
            ("next_ekadashi", data.next_ekadashi),
        ):
            element = cfg.get(key, {})
            self._text_cfg(draw, element, element.get("y", default_y), value)

        # The Tamil fields select the Tamil face via their own "font" key; there
        # is no special-casing by field name.
        tmonth_cfg = cfg.get("tamil_month", {})
        self._text_cfg(
            draw,
            tmonth_cfg,
            tmonth_cfg.get("y", 228),
            data.tamil_month_ta or data.tamil_month or DASH,
        )

        tdate_cfg = cfg.get("tamil_date", {})
        self._text_cfg(
            draw,
            tdate_cfg,
            tdate_cfg.get("y", 228),
            str(data.tamil_date) if data.tamil_date is not None else DASH,
        )

    def _draw_line4(self, draw: ImageDraw.ImageDraw, data: RenderInput) -> None:
        cfg = self.config.get("line4", {})
        x = int(cfg.get("x", 20))
        y = int(cfg.get("y", 258))
        font_size = int(cfg.get("font_size", 20))

        if is_hidden(x, y, font_size):
            return

        text = (data.custom_text or "").strip()
        if not text:
            return

        line_height = int(cfg.get("line_height", 20))
        font, lines = fit_line4(self, cfg, text)
        for index, line in enumerate(lines):
            self._text(draw, x, y + index * line_height, line, font)

    def _draw_addl_image(self, image: Image.Image, data: RenderInput) -> None:
        """Draw the optional second image under line4.

        Nothing is drawn when the day has no addl_image set, which is the
        default, so the layout is unchanged until an admin assigns one.
        """
        cfg = self.config.get("addl_image", {})
        if not cfg:
            return
        name = (data.addl_image or "").strip()
        if not name:
            return
        self._place_image(image, name, cfg)

    def _draw_dividers(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw the configured horizontal separator lines."""
        canvas_width = int(self.config.get("canvas", {}).get("width", 400))
        for index, divider in enumerate(self.config.get("dividers") or []):
            if not isinstance(divider, dict):
                continue
            y = int(divider.get("y", -1))
            if y < 0:
                continue  # y: -1 disables this divider
            x_start = int(divider.get("x_start", 0))
            x_end = int(divider.get("x_end", canvas_width - 1))
            if x_start < 0:
                x_start = 0
            if x_end < 0:
                x_end = canvas_width - 1
            thickness = max(1, int(divider.get("thickness", 1)))
            for offset in range(thickness):
                draw.line([(x_start, y + offset), (x_end, y + offset)], fill=0)

    def _draw_dashes_note(self, draw: ImageDraw.ImageDraw) -> None:
        """Mark a day whose panchanga could not be fetched.

        The values already render as em dashes; this adds a small marker so a
        failed scrape is distinguishable from genuinely empty data.
        """
        cfg = self.config.get("scrape_failed_marker", {})
        if not cfg:
            return
        x = int(cfg.get("x", 258))
        y = int(cfg.get("y", 285))
        size = int(cfg.get("font_size", 14))
        if is_hidden(x, y, size):
            return
        name = str(cfg.get("font") or DEFAULT_FONT)
        self._text(draw, x, y, cfg.get("text", "no panchanga"), self.font(name, size))

    # ----------------------------------------------------------------- helpers
    def _text_cfg(
        self,
        draw: ImageDraw.ImageDraw,
        element: dict,
        fallback_y: int,
        text: str,
    ) -> None:
        """Draw one configured text element, honouring the hide rules.

        The font comes from the element's own "font" key, falling back to the
        default name, so any field can use any font listed in the fonts block.
        """
        if not isinstance(element, dict):
            return
        x = int(element.get("x", -1))
        y = int(element.get("y", fallback_y))
        size = int(element.get("font_size", 0))
        if is_hidden(x, y, size):
            return
        name = str(element.get("font") or DEFAULT_FONT)
        self._text(draw, x, y, text, self.font(name, size))

    def _text(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: int = 0,
    ) -> None:
        """Draw text into the render's greyscale text layer.

        The layer is thresholded and merged into the bitmap at the end of the
        render. Drawing text here rather than straight onto the 1-bit canvas
        means the rasteriser can anti-alias the glyph first: on the 1-bit canvas
        each pixel is decided at the final size, which drops the thin strokes of
        small text below the cutoff and leaves them broken and ragged.
        """
        if not text:
            return
        if fill != 0:
            # Only black ink is expected; the layer carries no colour.
            raise ValueError("text fill must be 0 (black ink)")
        if self._text_draw is None:
            raise RuntimeError("_text() called outside render()")
        self._text_draw.text((int(x), int(y)), text, font=font, fill=0)

    def _merge_text_layer(self, image: Image.Image) -> None:
        """Threshold the greyscale text layer into the 1-bit bitmap."""
        if self._text_layer is None:
            return
        mask = self._text_layer.point(
            lambda value: 255 if value < TEXT_THRESHOLD else 0, "1"
        )
        image.paste(0, (0, 0), mask)

    def _wrap(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Greedy word wrap measured in actual rendered pixels."""
        words = text.split()
        if not words:
            return []

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.getlength(candidate) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def _ellipsise(
        lines: list[str], font: ImageFont.FreeTypeFont, max_lines: int
    ) -> list[str]:
        """Truncate to ``max_lines``, marking elision with an ellipsis."""
        if len(lines) <= max_lines or max_lines <= 0:
            return lines[:max_lines] if max_lines > 0 else []
        kept = lines[:max_lines]
        last = kept[-1]
        while last and font.getlength(last + "…") > font.getlength(lines[max_lines - 1]):
            last = last[:-1]
        kept[-1] = last + "…"
        return kept

    # ------------------------------------------------------------------ images
    def image_path(self, name: str) -> Path:
        """Resolve an image name from a day record to a file on disk.

        Only the base name is honoured, so a stored value cannot escape the
        assets directory.
        """
        stem = Path(name).name
        if not Path(stem).suffix:
            stem = f"{stem}.png"
        return self.assets_dir / DAY_IMAGE_DIR / stem

    def _place_image(self, image: Image.Image, name: str, cfg: dict) -> None:
        """Paste a named image, preserving aspect ratio when only one size is given.

        A missing file is skipped rather than failing the render: the calendar is
        still useful without its artwork.
        """
        if not isinstance(cfg, dict):
            return
        x = int(cfg.get("x", -1))
        y = int(cfg.get("y", -1))
        if is_hidden(x, y):
            return

        raw_width = cfg.get("width")
        raw_height = cfg.get("height")
        # Leaving a side out, or setting it to 0 (or anything negative, so a
        # parked "-1" also works), derives that side from the source aspect
        # ratio: a 200x50 logo drawn at width 64 becomes 64x16.
        width = _derived_side(raw_width)
        height = _derived_side(raw_height)
        if width is None and height is None:
            return

        path = self.image_path(name)
        if not path.exists():
            return

        with Image.open(path) as handle:
            source = handle.convert("L")

        if width is not None and height is not None:
            target = (width, height)
        else:
            # Keep the source aspect ratio: scale the given side and derive the
            # other from the file's own dimensions.
            ratio = source.width / source.height if source.height else 1.0
            if width is not None:
                target = (width, max(1, round(width / ratio)))
            else:
                target = (max(1, round(height * ratio)), height)

        # Threshold rather than dither: the icons are line art and dithering
        # produces speckle on e-ink at this size.
        icon = source.resize(target, Image.LANCZOS).point(
            lambda value: 0 if value < 128 else 255, "1"
        )
        image.paste(icon, (x, y))

    # -------------------------------------------------------------------- moon
    def _draw_moon(
        self,
        image: Image.Image,
        cx: int,
        cy: int,
        radius: int,
        paksha: str | None,
        tithi_number: int | None,
    ) -> None:
        """Draw the moon phase as a dithered disc.

        The display is strictly 1-bit, so "gray" is a 50% checkerboard dither.
        Conventions follow the PRD:
          - new moon (Amavasya): solid black disc
          - full moon (Purnima): white disc with a gray (dithered) outer ring
          - waxing (shukla): gray on the left, white on the right
          - waning (krishna): the mirror image
        """
        fraction = self._moon_fraction(paksha, tithi_number)

        if fraction is None:
            # Unknown phase: draw the outline only so the position is still read.
            self._ring(image, cx, cy, radius, dithered=True)
            return

        if fraction <= 0.01:
            ImageDraw.Draw(image).ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius), fill=0
            )
            return

        if fraction >= 0.99:
            # Full moon: fully lit disc, plus a gray ring as the PRD specifies.
            self._fill_disc(image, cx, cy, radius, lit=True)
            self._ring(image, cx, cy, radius, dithered=True)
            return

        waxing = (paksha or "SHUKLA").upper().startswith("SHUKLA")
        self._fill_disc(image, cx, cy, radius, lit=None, fraction=fraction, waxing=waxing)
        self._ring(image, cx, cy, radius, dithered=True)

    @staticmethod
    def _moon_fraction(paksha: str | None, tithi_number: int | None) -> float | None:
        """Illuminated fraction in [0, 1]; None when the phase is unknown."""
        if not paksha or tithi_number is None:
            return None
        code = paksha.upper()
        if "SHUKLA" in code:
            return max(0.0, min(1.0, tithi_number / 15.0))
        if "KRISHNA" in code:
            return max(0.0, min(1.0, (15 - tithi_number) / 15.0))
        return None

    def _fill_disc(
        self,
        image: Image.Image,
        cx: int,
        cy: int,
        radius: int,
        lit: bool | None,
        fraction: float = 1.0,
        waxing: bool = True,
    ) -> None:
        """Fill the moon disc.

        ``lit=True`` fills white, ``lit=False`` fills dithered gray, and
        ``lit=None`` splits the disc at the terminator ellipse.
        """
        pixels = image.load()
        radius_sq = radius * radius
        # Terminator semi-axis factor: +1 at new moon, -1 at full moon.
        k = 1.0 - 2.0 * fraction

        for dy in range(-radius, radius + 1):
            span = radius_sq - dy * dy
            if span < 0:
                continue
            half = span ** 0.5
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius_sq:
                    continue

                if lit is True:
                    is_lit = True
                elif lit is False:
                    is_lit = False
                else:
                    offset = k * half
                    if waxing:
                        is_lit = dx > offset
                    else:
                        is_lit = dx < -offset

                x = cx + dx
                y = cy + dy
                if not self._in_bounds(image, x, y):
                    continue
                if is_lit:
                    pixels[x, y] = 1
                elif (x + y) % 2 == 0:
                    # Dithered gray reads as shading on the 1-bit panel.
                    pixels[x, y] = 0

    def _ring(
        self, image: Image.Image, cx: int, cy: int, radius: int, dithered: bool = True
    ) -> None:
        """Outline the disc so its extent is visible even when fully lit."""
        pixels = image.load()
        radius_sq = radius * radius
        inner_sq = (radius - 2) * (radius - 2)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                dist_sq = dx * dx + dy * dy
                if dist_sq > radius_sq or dist_sq < inner_sq:
                    continue
                x = cx + dx
                y = cy + dy
                if not self._in_bounds(image, x, y):
                    continue
                if dithered and (x + y) % 2 != 0:
                    continue
                pixels[x, y] = 0

    @staticmethod
    def _in_bounds(image: Image.Image, x: int, y: int) -> bool:
        return 0 <= x < image.width and 0 <= y < image.height


def render_day(
    config: dict,
    data: RenderInput,
    assets_dir: Path | None = None,
) -> bytes:
    """Convenience wrapper returning the raw 1-bit bitmap."""
    return Renderer(config, assets_dir).render(data)


def line4_block_height(font: ImageFont.FreeTypeFont, lines: int, line_height: int) -> int:
    """Vertical space the drawn block occupies, in pixels.

    Lines are spaced by "line_height", but a line's glyphs occupy their own
    ascent + descent, which is not the same number: Noto Sans at 20px has
    metrics of 28 while the shipped "line_height" is 20. Counting only the line
    boxes therefore under-states the block by the last line's descent and lets
    it be drawn off the bottom of the canvas, where it is invisible.
    """
    ascent, descent = font.getmetrics()
    return (lines - 1) * line_height + ascent + descent


def fit_line4(
    renderer: Renderer, cfg: dict, text: str
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Choose the font size and wrapped lines for the custom text.

    The text is free-form — an admin's own note, or a festival name from the
    source — so it can be arbitrarily long. Wrap it first, then step the size
    down until the block fits the space left between "y" and "max_y" rather than
    drawing off-canvas where it would be invisible.

    Split out of :meth:`Renderer._draw_line4` so ``check_layout.py`` can measure
    the block that is actually drawn instead of the raw string.
    """
    lines: list[str] = []
    size = int(cfg.get("font_size", 20))
    min_size = int(cfg.get("min_font_size", 12))
    max_width = int(cfg.get("max_width", 360))
    line_height = int(cfg.get("line_height", 20))
    limit = int(cfg.get("max_y", 300)) - int(cfg.get("y", 258))
    font_name = str(cfg.get("font") or DEFAULT_FONT)

    while size >= min_size:
        font = renderer.font(font_name, size)
        lines = renderer._wrap(text, font, max_width)
        if line4_block_height(font, len(lines), line_height) <= limit:
            return font, lines
        size -= 2

    font = renderer.font(font_name, min_size)
    lines = renderer._wrap(text, font, max_width)
    return font, renderer._ellipsise(lines, font, max_line4_lines(font, cfg))


def max_line4_lines(font: ImageFont.FreeTypeFont, cfg: dict) -> int:
    """How many lines fit between "y" and "max_y" at this font's metrics."""
    line_height = int(cfg.get("line_height", 20))
    limit = int(cfg.get("max_y", 300)) - int(cfg.get("y", 258))
    ascent, descent = font.getmetrics()
    room = limit - (ascent + descent)
    if room < 0:
        return 0
    return 1 + room // max(line_height, 1)


def line4_box(
    renderer: Renderer, cfg: dict, text: str
) -> tuple[float, float, float, float] | None:
    """Drawn box of the custom text, or None when it is switched off or empty.

    The block is as wide as its longest line and as tall as the lines drawn plus
    the spacing between them, measured the same way ``fit_line4`` fits them.
    """
    x = cfg.get("x", 20)
    y = cfg.get("y", 258)
    if is_hidden(x, y, cfg.get("font_size", 20)):
        return None
    stripped = (text or "").strip()
    if not stripped:
        return None

    font, lines = fit_line4(renderer, cfg, stripped)
    if not lines:
        return None

    advance = max(font.getlength(line) for line in lines)
    line_height = int(cfg.get("line_height", 20))
    top = float(y)
    bottom = top + line4_block_height(font, len(lines), line_height)
    return (float(x), top, float(x) + advance, bottom)
