#!/usr/bin/env python3
"""Download the fonts used for rendering.

Fonts are fetched from CDN mirrors of the upstream releases rather than
committed to the repository, so the image stays small. Run this once before
first use, or let the Dockerfile do it at build time.

To add a font of your own, drop the .ttf into server/fonts/ and add a name for
it in the "fonts" block of config.default.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

FONTS = {
    "NotoSans-Regular.ttf": (
        "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io/"
        "fonts/NotoSans/hinted/ttf/NotoSans-Regular.ttf"
    ),
    "NotoSans-Bold.ttf": (
        "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io/"
        "fonts/NotoSans/hinted/ttf/NotoSans-Bold.ttf"
    ),
    "NotoSansTamil-Regular.ttf": (
        "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io/"
        "fonts/NotoSansTamil/hinted/ttf/NotoSansTamil-Regular.ttf"
    ),
    "NotoSansTamil-Bold.ttf": (
        "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io/"
        "fonts/NotoSansTamil/hinted/ttf/NotoSansTamil-Bold.ttf"
    ),
    "DejaVuSans.ttf": (
        "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf"
    ),
    "DejaVuSans-Bold.ttf": (
        "https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans-Bold.ttf"
    ),
}

TARGET_DIR = Path(__file__).resolve().parent / "fonts"


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for name, url in FONTS.items():
        destination = TARGET_DIR / name
        if destination.exists() and destination.stat().st_size > 1000:
            print(f"skip   {name} (already present)")
            continue
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"FAIL   {name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        # A wrong URL on a CDN can still return 200 with an HTML error page, so
        # check the payload actually looks like a TrueType file.
        if not response.content.startswith((b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf")):
            print(f"FAIL   {name}: response is not an OpenType font", file=sys.stderr)
            failures += 1
            continue

        destination.write_bytes(response.content)
        print(f"ok     {name} ({len(response.content)} bytes)")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
