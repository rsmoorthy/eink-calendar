"""REST API consumed by the ESP32 firmware.

Endpoints:
  GET /date                  current date in IST
  GET /calendar              list of (date, checksum) for today + 3 days
  GET /calendar/<date>       raw 400x300 1-bit bitmap for that date

The bitmap is served as ``application/octet-stream`` with the checksum in an
``X-Checksum`` header. That lets the firmware compare checksums from /calendar
and skip downloading unchanged images entirely, which is the common case.
"""

from __future__ import annotations

import binascii
import re
from datetime import date as Date
from datetime import timedelta

from flask import Response, jsonify, request

from panchanga import IST, today_ist

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# "today + 3 days ahead" per the PRD.
WINDOW_DAYS = 4


def _parse_date(raw: str) -> Date | None:
    if not DATE_RE.match(raw):
        return None
    try:
        return Date.fromisoformat(raw)
    except ValueError:
        return None


def register(app, service, db) -> None:
    @app.get("/date")
    def get_date():
        """Current date and time in IST plus the window the ESP should expect."""
        now = today_ist()
        from datetime import datetime

        return jsonify(
            {
                "date": now.isoformat(),
                "timezone": "IST",
                "utc_offset_minutes": int(
                    IST.utcoffset(datetime.now(IST)).total_seconds() // 60
                ),
                "epoch": int(datetime.now(IST).timestamp()),
                "window_days": WINDOW_DAYS,
                "dates": [
                    (now + timedelta(days=offset)).isoformat()
                    for offset in range(WINDOW_DAYS)
                ],
            }
        )

    @app.get("/calendar")
    def get_calendar():
        """Checksum manifest for today + WINDOW_DAYS-1.

        A date with no rendered bitmap reports ``checksum: null`` so the firmware
        knows to fetch it. Dates are always all present, in order, so the firmware
        can index into the response without re-deriving dates.
        """
        start = today_ist()
        requested = request.args.get("date")
        if requested:
            parsed = _parse_date(requested)
            if parsed is None:
                return jsonify({"error": "invalid date, expected YYYY-MM-DD"}), 400
            start = parsed

        days = []
        for entry in service.window(start, WINDOW_DAYS):
            days.append(
                {
                    "date": entry["date"],
                    "checksum": entry["checksum"],
                    "has_bitmap": entry["has_bitmap"],
                    "panchanga_ok": entry["panchanga_ok"],
                }
            )
        return jsonify({"start": start.isoformat(), "days": days})

    @app.get("/calendar/<day>")
    def get_calendar_day(day: str):
        """Raw bitmap for one date.

        Generates on demand when missing, so the ESP never has to be told to wait.
        """
        parsed = _parse_date(day)
        if parsed is None:
            return jsonify({"error": "invalid date, expected YYYY-MM-DD"}), 400

        checksum = db.get_day(parsed)["checksum"] if db.get_day(parsed) else None
        client_checksum = request.headers.get("If-None-Match") or request.args.get(
            "checksum"
        )

        # Cheap path: unchanged since the client's copy.
        if checksum and client_checksum and checksum == client_checksum:
            return Response(status=304)

        bitmap = db.get_bitmap(parsed)
        if bitmap is None:
            try:
                bitmap, checksum = service.generate(parsed)
            except Exception as exc:  # noqa: BLE001 - surface as 503, not a traceback
                app.logger.exception("generation failed for %s", day)
                return jsonify({"error": f"could not generate image: {exc}"}), 503

        response = Response(bitmap, mimetype="application/octet-stream")
        response.headers["X-Checksum"] = checksum or ""
        response.headers["X-Date"] = parsed.isoformat()
        response.headers["ETag"] = checksum or ""
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/calendar/<day>/meta")
    def get_calendar_meta(day: str):
        """Content fields for a date, used by the web UI and for debugging."""
        parsed = _parse_date(day)
        if parsed is None:
            return jsonify({"error": "invalid date, expected YYYY-MM-DD"}), 400
        content = db.get_content(parsed)
        if content is None:
            return jsonify({"error": "no record for date", "date": day}), 404
        return jsonify(_jsonable(content))


def _jsonable(content: dict) -> dict:
    """Make a content dict JSON-serialisable."""
    out = {}
    for key, value in content.items():
        if isinstance(value, (bytes, bytearray)):
            out[key] = binascii.hexlify(value).decode()
        else:
            out[key] = value
    return out
