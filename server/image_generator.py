import os
import math
import hashlib
import yaml
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

TITHI_INDEX_MAP = {
    "prathama": 1,
    "pratipada": 1,
    "prathame": 1,
    "padya": 1,
    "padyami": 1,
    "padai": 1,
    "1": 1,
    "dvitiya": 2,
    "dwitiya": 2,
    "dvitheeya": 2,
    "bidige": 2,
    "2": 2,
    "tritiya": 3,
    "triteeyaa": 3,
    "thadige": 3,
    "tadige": 3,
    "3": 3,
    "chaturthi": 4,
    "chauthi": 4,
    "chavithi": 4,
    "4": 4,
    "panchami": 5,
    "5": 5,
    "shashthi": 6,
    "shasthi": 6,
    "sashti": 6,
    "6": 6,
    "saptami": 7,
    "7": 7,
    "ashtami": 8,
    "astami": 8,
    "8": 8,
    "navami": 9,
    "9": 9,
    "dashami": 10,
    "dasami": 10,
    "10": 10,
    "ekadashi": 11,
    "ekadasi": 11,
    "11": 11,
    "dwadashi": 12,
    "dvadashi": 12,
    "dvadasi": 12,
    "12": 12,
    "trayodashi": 13,
    "trayodasi": 13,
    "thrayodashi": 13,
    "13": 13,
    "chaturdashi": 14,
    "chaturdasi": 14,
    "14": 14,
    "purnima": 15,
    "poornima": 15,
    "hunnime": 15,
    "pournami": 15,
    "amavasya": 15,
    "amavasye": 15,
    "amavasai": 15,
}


def get_tithi_index(tithi_name: str) -> int:
    if not tithi_name:
        return 7
    raw = tithi_name.lower().strip().replace("-", "/").replace(" ", "/")
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    for p in parts:
        if p in TITHI_INDEX_MAP:
            return TITHI_INDEX_MAP[p]
    for k, v in TITHI_INDEX_MAP.items():
        if k in raw:
            return v
    return 7


def load_layout_config(yaml_string: str = None) -> dict:
    if yaml_string:
        try:
            return yaml.safe_load(yaml_string)
        except Exception:
            pass
    if os.path.exists(DEFAULT_CONFIG_PATH):
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def get_font(font_path: str, size: int):
    if not size or size <= 0:
        return ImageFont.load_default()
    # If path is relative, resolve from project root or server dir
    full_path = font_path
    if not os.path.isabs(full_path):
        full_path = os.path.join(BASE_DIR, "..", font_path)
        if not os.path.exists(full_path):
            full_path = os.path.join(BASE_DIR, font_path)
    if os.path.exists(full_path):
        return ImageFont.truetype(full_path, size)
    # Fallback
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def draw_moon_phase(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, tithi_name: str, paksha: str):
    """
    Draws moon phase using 1-bit checkerboard dithering for shadow.
    - Purnima: clear circle outline with white interior.
    - Amavasya: circle filled with 50% checkerboard dither.
    - Shukla Paksha (waxing): lit crescent on right, dithered shadow on left.
      Day 1 (Pratipada): >90% dithered shadow, <10% white crescent on right.
      Day 14 (Chaturdashi): >90% white, <10% dithered shadow on left.
    - Krishna Paksha (waning): lit crescent on left, dithered shadow on right.
      Day 1 (Pratipada): >90% white, <10% dithered shadow on right.
      Day 14 (Chaturdashi): >90% dithered shadow, <10% white crescent on left.
    """
    t_clean = tithi_name.lower().strip()
    p_clean = paksha.lower().strip()
    is_waxing = "shukla" in p_clean

    is_purnima = "purnima" in t_clean or "poornima" in t_clean or "pournami" in t_clean or (is_waxing and "15" in t_clean)
    is_amavasya = "amavasya" in t_clean or "amavasye" in t_clean or (not is_waxing and "15" in t_clean)

    # Bounding box
    x0 = cx - radius
    y0 = cy - radius
    x1 = cx + radius
    y1 = cy + radius

    # Clear area inside circle to white
    draw.ellipse([x0, y0, x1, y1], fill=255, outline=0, width=1)

    if is_purnima:
        # Full moon: just the outline, interior is pure white
        return

    if is_amavasya:
        # Amavasya: entire interior filled with 50% dither pattern
        r2 = radius * radius
        for py in range(y0, y1 + 1):
            dy = py - cy
            if dy * dy > r2:
                continue
            max_dx = math.sqrt(r2 - dy * dy)
            for px in range(int(math.ceil(cx - max_dx)), int(math.floor(cx + max_dx)) + 1):
                if (px + py) % 2 == 0:
                    draw.point((px, py), fill=0)
        draw.ellipse([x0, y0, x1, y1], outline=0, width=1)
        return

    t_idx = get_tithi_index(tithi_name)
    t_idx = max(1, min(14, t_idx))

    if is_waxing:
        # Shukla Paksha: waxing from new moon (0) to full moon (1)
        # Day 1: illum ~0.067, terminator ~+0.867 (norm_x < terminator is shadow -> >90% shadow)
        illum = t_idx / 15.0
        terminator_x = 1.0 - 2.0 * illum
    else:
        # Krishna Paksha: waning from full moon (1) to new moon (0)
        # Day 1: illum ~0.933, terminator ~+0.867 (norm_x > terminator is shadow -> <10% shadow, >90% white)
        illum = 1.0 - (t_idx / 15.0)
        terminator_x = -1.0 + 2.0 * illum

    # Pixel-level rendering with 50% checkerboard dither for shadow
    r2 = radius * radius
    for py in range(y0, y1 + 1):
        dy = py - cy
        dy2 = dy * dy
        if dy2 > r2:
            continue
        max_dx = math.sqrt(r2 - dy2)
        if max_dx <= 0:
            continue
        min_x = cx - max_dx
        max_x = cx + max_dx

        for px in range(int(math.ceil(min_x)), int(math.floor(max_x)) + 1):
            dx = px - cx
            norm_x = dx / max_dx

            if is_waxing:
                # Lit on the right: shadow on the left
                in_shadow = (norm_x < terminator_x)
            else:
                # Lit on the left: shadow on the right
                in_shadow = (norm_x > terminator_x)

            if in_shadow:
                # 50% checkerboard dither pattern: alternating black and white
                if (px + py) % 2 == 0:
                    draw.point((px, py), fill=0)
                else:
                    draw.point((px, py), fill=255)
            else:
                draw.point((px, py), fill=255)

    # Re-draw clean outer border
    draw.ellipse([x0, y0, x1, y1], outline=0, width=1)


def is_item_enabled(item_cfg: dict) -> bool:
    """
    Checks if a layout item is enabled.
    Returns False if:
    - enabled is False
    - font_size is 0
    - x == -1 or y == -1 (or both are -1)
    """
    if not isinstance(item_cfg, dict):
        return False
    if not item_cfg.get("enabled", True):
        return False
    fs = item_cfg.get("font_size")
    if fs is not None:
        try:
            if int(fs) == 0:
                return False
        except (ValueError, TypeError):
            pass
    x = item_cfg.get("x")
    y = item_cfg.get("y")
    try:
        if x is not None and int(x) == -1:
            return False
    except (ValueError, TypeError):
        pass
    try:
        if y is not None and int(y) == -1:
            return False
    except (ValueError, TypeError):
        pass
    return True


def resolve_icon_path(icon_name: str, config: dict) -> str | None:
    """
    Resolves an icon filename against the configured icons_dir.
    Supports names with or without .png extension.
    """
    if not icon_name:
        return None
    icon_name = str(icon_name).strip()
    if not icon_name:
        return None
    if os.path.isabs(icon_name) and os.path.isfile(icon_name):
        return icon_name

    icons_dir = config.get("icons_dir", "server/icons")
    candidates = []
    for base in [
        os.path.join(BASE_DIR, "..", icons_dir),
        os.path.join(BASE_DIR, icons_dir),
        icons_dir,
    ]:
        norm_base = os.path.normpath(base)
        candidates.append(os.path.join(norm_base, icon_name))
        if not icon_name.lower().endswith(".png"):
            candidates.append(os.path.join(norm_base, f"{icon_name}.png"))

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def render_icon(icon_path: str, target_w: int | None = None, target_h: int | None = None) -> Image.Image:
    """
    Loads an icon image, flattens transparency onto a white background,
    and resizes it. If only target_w or only target_h is defined (> 0),
    the original aspect ratio is maintained.
    Returns 1-bit monochrome PIL Image.
    """
    icon_img = Image.open(icon_path)

    # If image has alpha channel or transparency, composite over white background
    if icon_img.mode in ("RGBA", "LA") or (icon_img.mode == "P" and "transparency" in icon_img.info):
        rgba = icon_img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        icon_img = bg.convert("L")
    else:
        icon_img = icon_img.convert("L")

    orig_w, orig_h = icon_img.size

    w_def = target_w is not None and isinstance(target_w, (int, float)) and target_w > 0
    h_def = target_h is not None and isinstance(target_h, (int, float)) and target_h > 0

    if w_def and not h_def:
        new_w = int(target_w)
        new_h = max(1, int(round(orig_h * (new_w / orig_w))))
    elif h_def and not w_def:
        new_h = int(target_h)
        new_w = max(1, int(round(orig_w * (new_h / orig_h))))
    elif w_def and h_def:
        new_w = int(target_w)
        new_h = int(target_h)
    else:
        new_w = orig_w
        new_h = orig_h

    icon_img = icon_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return icon_img.convert("1")


def generate_calendar_image(day_info: dict, config_override: dict = None) -> Image.Image:
    """
    Constructs the 400x300 1-bit monochrome PIL image for a given day.
    """
    config = config_override if config_override else load_layout_config()
    disp_cfg = config.get("display", {})
    width = disp_cfg.get("width", 400)
    height = disp_cfg.get("height", 300)

    # Create 1-bit image (mode "1", default white background = 255)
    img = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(img)

    fonts_cfg = config.get("fonts", {})
    layout = config.get("layout", {})

    # Resolve fonts
    f_latin_bold = fonts_cfg.get("latin_bold", "server/fonts/DejaVuSans-Bold.ttf")
    f_latin_reg = fonts_cfg.get("latin_regular", "server/fonts/DejaVuSans.ttf")
    f_tamil_bold = fonts_cfg.get("tamil_bold", "server/fonts/NotoSansTamil-Bold.ttf")
    f_tamil_reg = fonts_cfg.get("tamil_regular", "server/fonts/NotoSansTamil-Regular.ttf")

    font_cache = {
        "latin_bold": f_latin_bold,
        "latin_regular": f_latin_reg,
        "tamil_bold": f_tamil_bold,
        "tamil_regular": f_tamil_reg,
    }

    # Line 1
    l1 = layout.get("line1", {})
    if l1.get("enabled", True):
        # Date number
        d_cfg = l1.get("date", {})
        if is_item_enabled(d_cfg):
            d_font = get_font(font_cache.get(d_cfg.get("font", "latin_bold")), d_cfg.get("font_size", 64))
            draw.text((d_cfg.get("x", 18), d_cfg.get("y", 10)), str(day_info.get("gregorian_day", "")), font=d_font, fill=0)

        # Month
        m_cfg = l1.get("month", {})
        if is_item_enabled(m_cfg):
            m_font = get_font(font_cache.get(m_cfg.get("font", "latin_bold")), m_cfg.get("font_size", 26))
            draw.text((m_cfg.get("x", 120), m_cfg.get("y", 18)), str(day_info.get("gregorian_month", "")), font=m_font, fill=0)

        # Day of week
        dow_cfg = l1.get("day_of_week", {})
        if is_item_enabled(dow_cfg):
            dow_font = get_font(font_cache.get(dow_cfg.get("font", "latin_regular")), dow_cfg.get("font_size", 22))
            draw.text((dow_cfg.get("x", 120), dow_cfg.get("y", 48)), str(day_info.get("day_of_week", "")), font=dow_font, fill=0)

        # Line 1 Icon (Day icon file or day of week fallback)
        ic_cfg = l1.get("icon", {})
        if is_item_enabled(ic_cfg):
            day_icon = day_info.get("icon_name", "") or day_info.get("day_icon_file", "")
            icon_path = None
            if day_icon:
                icon_path = resolve_icon_path(day_icon, config)
            if not icon_path:
                dow_abbr = str(day_info.get("day_of_week", "sun"))[:3].lower()
                icon_path = resolve_icon_path(f"{dow_abbr}.png", config)

            if icon_path and os.path.isfile(icon_path):
                try:
                    w = ic_cfg.get("width")
                    h = ic_cfg.get("height")
                    if (w is None or w <= 0) and (h is None or h <= 0):
                        w, h = 64, 64
                    icon_1bit = render_icon(icon_path, w, h)
                    img.paste(icon_1bit, (ic_cfg.get("x", 300), ic_cfg.get("y", 2)))
                except Exception:
                    pass

    # Divider 1
    div1 = layout.get("divider1", {})
    if is_item_enabled(div1):
        y = div1.get("y", 76)
        draw.line([(10, y), (width - 10, y)], fill=0, width=1)

    # Line 2: Lunar Tithi, Moon Phase, Lunar Paksha
    l2 = layout.get("line2", {})
    if l2.get("enabled", True):
        tithi_text = day_info.get("lunar_tithi", "")
        paksha_text = day_info.get("lunar_paksha", "")

        t_cfg = l2.get("tithi", {})
        if is_item_enabled(t_cfg):
            t_font = get_font(font_cache.get(t_cfg.get("font", "latin_bold")), t_cfg.get("font_size", 20))
            draw.text((t_cfg.get("x", 18), t_cfg.get("y", 86)), tithi_text, font=t_font, fill=0)

        # Moon phase
        moon_cfg = l2.get("moon", {})
        if is_item_enabled(moon_cfg):
            cx = moon_cfg.get("x", 195)
            cy = moon_cfg.get("y", 98)
            radius = moon_cfg.get("radius", 14)
            draw_moon_phase(draw, cx, cy, radius, tithi_text, paksha_text)

        # Paksha text
        p_cfg = l2.get("paksha", {})
        if is_item_enabled(p_cfg):
            p_font = get_font(font_cache.get(p_cfg.get("font", "latin_regular")), p_cfg.get("font_size", 20))
            paksha_val = paksha_text.replace("Paksha", "").replace("paksha", "").strip()
            if paksha_val:
                draw.text((p_cfg.get("x", 235), p_cfg.get("y", 86)), paksha_val, font=p_font, fill=0)

    # Divider 2
    div2 = layout.get("divider2", {})
    if is_item_enabled(div2):
        y = div2.get("y", 122)
        draw.line([(10, y), (width - 10, y)], fill=0, width=1)

    # Line 3: Lunar Masa, Nakshatra, Tamil Month & Date
    l3 = layout.get("line3", {})
    if l3.get("enabled", True):
        m_cfg = l3.get("masa", {})
        if is_item_enabled(m_cfg):
            m_font = get_font(font_cache.get(m_cfg.get("font", "latin_regular")), m_cfg.get("font_size", 19))
            masa_val = day_info.get("lunar_masa", "").strip()
            if masa_val.lower().startswith("masa:"):
                masa_val = masa_val[5:].strip()
            elif masa_val.lower().startswith("masa"):
                masa_val = masa_val[4:].strip()
            if masa_val:
                draw.text((m_cfg.get("x", 18), m_cfg.get("y", 130)), masa_val, font=m_font, fill=0)

        n_cfg = l3.get("nakshatra", {})
        if is_item_enabled(n_cfg):
            n_font = get_font(font_cache.get(n_cfg.get("font", "latin_regular")), n_cfg.get("font_size", 19))
            nakshatra_val = day_info.get("nakshatra", "")
            nak_label = f"Nakshatra: {nakshatra_val}" if nakshatra_val else ""
            if nak_label:
                draw.text((n_cfg.get("x", 18), n_cfg.get("y", 156)), nak_label, font=n_font, fill=0)

        # Tamil Month & Date
        ta_cfg = l3.get("tamil", {})
        if is_item_enabled(ta_cfg):
            ta_font = get_font(font_cache.get(ta_cfg.get("font", "tamil_bold")), ta_cfg.get("font_size", 24))
            tamil_m = day_info.get("tamil_month_ta", "")
            tamil_d = day_info.get("tamil_date", 0)
            tamil_label = f"{tamil_m} {tamil_d}" if (tamil_m and tamil_d) else ""
            if tamil_label:
                draw.text((ta_cfg.get("x", 18), ta_cfg.get("y", 184)), tamil_label, font=ta_font, fill=0)

    # Divider 3
    div3 = layout.get("divider3", {})
    if is_item_enabled(div3):
        y = div3.get("y", 222)
        draw.line([(10, y), (width - 10, y)], fill=0, width=1)

    # Line 4: Custom Text and Additional Icon
    l4 = layout.get("line4", {})
    if l4.get("enabled", True):
        c_cfg = l4.get("custom_text", {})
        if is_item_enabled(c_cfg):
            c_font = get_font(font_cache.get(c_cfg.get("font", "latin_bold")), c_cfg.get("font_size", 22))
            custom_val = day_info.get("custom_text", "").strip()
            if not custom_val:
                custom_val = c_cfg.get("default_message", "")
            if custom_val:
                draw.text((c_cfg.get("x", 18), c_cfg.get("y", 232)), custom_val, font=c_font, fill=0)

        # Line 4 Icon: "Addl icon file"
        # Only if this field is having valid value, and line4.icon.x and line4.icon.y is not -1,
        # and one of line4.icon.width or line4.icon.height is defined, then it will print this icon.
        l4_ic = l4.get("icon", {})
        if is_item_enabled(l4_ic):
            addl_icon = day_info.get("addl_icon_name", "") or day_info.get("addl_icon_file", "")
            addl_icon_path = resolve_icon_path(addl_icon, config) if addl_icon else None
            ic_x = l4_ic.get("x", -1)
            ic_y = l4_ic.get("y", -1)
            ic_w = l4_ic.get("width")
            ic_h = l4_ic.get("height")
            w_def = ic_w is not None and isinstance(ic_w, (int, float)) and ic_w > 0
            h_def = ic_h is not None and isinstance(ic_h, (int, float)) and ic_h > 0

            if addl_icon_path and os.path.isfile(addl_icon_path) and ic_x != -1 and ic_y != -1 and (w_def or h_def):
                try:
                    icon_1bit = render_icon(addl_icon_path, ic_w if w_def else None, ic_h if h_def else None)
                    img.paste(icon_1bit, (ic_x, ic_y))
                except Exception:
                    pass

    return img


def image_to_bitmap_bytes(img: Image.Image) -> bytes:
    """
    Packs 400x300 1-bit image into 15,000 bytes (MSB first, 1=white, 0=black).
    Matches Waveshare Epd::Display format.
    """
    img = img.convert("1")
    pixels = img.load()
    width, height = img.size
    data = bytearray()

    for y in range(height):
        for xbyte in range(width // 8):
            b = 0
            for bit in range(8):
                x = xbyte * 8 + bit
                # 1 = White, 0 = Black
                if pixels[x, y] != 0:
                    b |= (0x80 >> bit)
            data.append(b)

    return bytes(data)


def bitmap_bytes_to_image(bitmap: bytes, width: int = 400, height: int = 300) -> Image.Image:
    """
    Unpacks 15,000 bytes back into a PIL Image for browser display / preview.
    """
    img = Image.new("1", (width, height), 255)
    pixels = img.load()
    bytes_per_row = width // 8

    for y in range(height):
        row_offset = y * bytes_per_row
        for xbyte in range(bytes_per_row):
            b = bitmap[row_offset + xbyte]
            for bit in range(8):
                x = xbyte * 8 + bit
                is_white = (b & (0x80 >> bit)) != 0
                pixels[x, y] = 255 if is_white else 0

    return img


def compute_checksum(bitmap_bytes: bytes) -> str:
    return hashlib.md5(bitmap_bytes).hexdigest()
