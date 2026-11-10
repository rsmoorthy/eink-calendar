"""Orchestration between storage, the panchanga source, and the renderer.

Background refresh jobs and the web UI both go through :class:`CalendarService`
so that a given date is always produced the same way regardless of caller.
"""

from __future__ import annotations

import json
import logging
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

import requests

from calendar_config import ConfigStore
from calendar_db import Database
from panchanga import (
    DASH,
    NEXT_EKADASHI_NONE,
    NEXT_EKADASHI_PREFIX,
    TAMIL_MONTH_STARTS,
    Panchanga,
    TamilMonthOutOfRange,
    fetch_panchanga,
    is_ekadashi,
    resolve_tamil_month,
    tithi_number_for,
    today_ist,
)
from renderer import RenderInput, Renderer, default_assets_dir, require_raqm

log = logging.getLogger(__name__)

# Fields the scrape is allowed to refresh. Admin-edited fields are excluded at
# write time via the per-day override list.
SCRAPE_FIELDS = ("masa", "paksha", "tithi", "nakshatra", "tithi_number", "festival")

# What each scraped field falls back to when the source cannot be reached. The
# text fields show an em dash, which the "no panchanga" marker explains.
# Festival is left blank instead: the renderer draws it as the day's custom
# text, where a dash would read as content rather than as missing data. It also
# cannot share the em dash because tithi_number is an integer column.
SCRAPE_DASH_FALLBACK: dict[str, object] = {"tithi_number": None, "festival": ""}

# Fields whose value on a given day is derived from other days' stored data,
# not from that day's own scrape. They are written by a second pass over a
# refreshed window and refreshed as a group, because a change to one day's
# festival can change what every earlier day should point at.
DERIVED_FIELDS = ("next_ekadashi",)

# How far ahead an Ekadashi is looked for, counted from the day in question.
# Two consecutive Ekadashis are never more than 15 days apart, so this always
# reaches the next one when the window's data is complete.
NEXT_EKADASHI_HORIZON_DAYS = 16

MONTH_ABBR = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def next_ekadashi_annotation(day: Date) -> str:
    """The "N.Eka: <Mon> <date>" text for ``day``, naming the calendar date of
    the next Ekadashi on or after it. Callers pass the date they have already
    resolved, so this only formats.

    The date shown is the Gregorian one, abbreviated to three letters, which is
    what the field is for: planning against the wall calendar.
    """
    return f"{NEXT_EKADASHI_PREFIX}{MONTH_ABBR[day.month - 1]} {day.day}"


class CalendarService:
    def __init__(
        self,
        db: Database,
        config_store: ConfigStore,
        assets_dir: Path | None = None,
    ) -> None:
        self.db = db
        self.config_store = config_store
        # Resolved eagerly so callers always have a concrete directory; the
        # asset store needs it to list and delete uploads.
        self.assets_dir = Path(assets_dir) if assets_dir else default_assets_dir()

    # ------------------------------------------------------------------ paths
    def renderer(self) -> Renderer:
        return Renderer(self.config_store.load(), self.assets_dir)

    # ------------------------------------------------------------- refreshing
    def refresh_date(self, day: Date, force: bool = False) -> bool:
        """Fetch panchanga and Tamil month data for ``day``.

        Returns True when panchanga was retrieved. Manually overridden fields are
        preserved. Existing rows are updated in place; a failure never clears
        previously good data unless ``force`` is set.
        """
        existing = self.db.get_day(day)
        overrides = _overrides_of(existing)

        panchanga = fetch_panchanga(day)
        values: dict[str, object] = {
            "panchanga_ok": panchanga.ok,
            "tithi_source": panchanga.tithi_source,
        }

        if panchanga.ok:
            for field in SCRAPE_FIELDS:
                if field in overrides and not force:
                    continue
                values[field] = getattr(panchanga, field)
        elif existing is None or force:
            # No usable data and nothing to preserve: show dashes.
            for field in SCRAPE_FIELDS:
                if field in overrides and not force:
                    continue
                values[field] = SCRAPE_DASH_FALLBACK.get(field, DASH)

        self._apply_tamil_month(day, values, overrides, force)

        self.db.upsert_content(day, values)
        self.db.set_checksum_meta(day, fetched_at=_now())
        # This day's own tithi is known now, so it can be settled as somebody
        # else's "next Ekadashi" too.
        self.refresh_derived_around(day)
        log.info(
            "refreshed %s (panchanga_ok=%s, tithi_source=%s)",
            day,
            panchanga.ok,
            panchanga.tithi_source,
        )
        return panchanga.ok

    def refresh_range(self, start: Date, days: int) -> dict[str, bool]:
        """Refresh ``days`` consecutive dates beginning at ``start``.

        Runs in two passes. The first scrapes every day and stores its own
        panchanga. The second fills in the fields derived from other days in the
        window (currently ``next_ekadashi``), which cannot be worked out until
        the whole range's festivals are known: the day an Ekadashi falls on is
        only recorded once its own scrape has been stored.
        """
        session = requests.Session()
        results: dict[str, bool] = {}
        for offset in range(days):
            day = start + timedelta(days=offset)
            try:
                results[day.isoformat()] = self._refresh_with_session(day, session)
            except Exception as exc:  # noqa: BLE001 - one bad day must not stop the run
                log.exception("refresh failed for %s: %s", day, exc)
                results[day.isoformat()] = False

        self.refresh_derived_range(start, days)
        return results

    def refresh_derived_range(self, start: Date, days: int) -> int:
        """Second pass: recompute the derived fields for ``start``..``start+days``.

        Returns how many rows were written. Only the days that actually changed
        are written, so re-running this leaves the stored checksums (and so the
        images) alone.

        A day late in the window can find no Ekadashi after it — the window ends
        before the next one — and is left showing the dash until a later run
        covers the following fortnight. Rows outside the window are never read
        except to look up an Ekadashi date, and never written.
        """
        updated = 0
        for offset in range(days):
            day = start + timedelta(days=offset)
            try:
                if self._apply_next_ekadashi(day):
                    updated += 1
            except Exception as exc:  # noqa: BLE001 - one bad day must not stop the pass
                log.exception("derived refresh failed for %s: %s", day, exc)
        if updated:
            log.info(
                "derived pass updated %s of %s days from %s",
                updated,
                days,
                start,
            )
        return updated

    def _apply_next_ekadashi(self, day: Date) -> bool:
        """Set ``day``'s next-Ekadashi text. True when the row was written."""
        row = self.db.get_day(day)
        if row is None:
            return False
        if "next_ekadashi" in _overrides_of(row):
            # Hand-edited: left to the admin, like any other overridden field.
            return False

        target = self._next_ekadashi_on_or_after(day + timedelta(days=1))
        value = (
            next_ekadashi_annotation(target) if target else NEXT_EKADASHI_NONE
        )
        if (row["next_ekadashi"] or "") == value:
            return False

        self.db.upsert_content(day, {"next_ekadashi": value})
        return True

    def _next_ekadashi_on_or_after(self, start: Date) -> Date | None:
        """First stored date on or after ``start`` whose festival is an Ekadashi.

        Reads the festivals already stored, so a day whose panchanga has not
        been fetched is simply not a candidate — the annotation is built from
        what is known, and a later run fills it in as the window advances.
        """
        end = start + timedelta(days=NEXT_EKADASHI_HORIZON_DAYS - 1)
        for raw_date, festival in self.db.festivals_between(start, end):
            if is_ekadashi(festival):
                try:
                    return Date.fromisoformat(raw_date)
                except ValueError:
                    continue
        return None

    def refresh_derived_around(self, day: Date) -> int:
        """Recompute the derived fields for the fortnight up to ``day``.

        Used when a single date is refreshed: it is the day before it that this
        date's tithi most affects, but every day within the horizon is cheap to
        recheck and the lookups stay local to one SQLite file.
        """
        start = day - timedelta(days=NEXT_EKADASHI_HORIZON_DAYS - 1)
        return self.refresh_derived_range(start, NEXT_EKADASHI_HORIZON_DAYS)

    def _refresh_with_session(self, day: Date, session: requests.Session) -> bool:
        existing = self.db.get_day(day)
        overrides = _overrides_of(existing)
        panchanga = fetch_panchanga(day, session=session)
        values: dict[str, object] = {
            "panchanga_ok": panchanga.ok,
            "tithi_source": panchanga.tithi_source,
        }

        if panchanga.ok:
            for field in SCRAPE_FIELDS:
                if field in overrides:
                    continue
                values[field] = getattr(panchanga, field)
        elif existing is None:
            for field in SCRAPE_FIELDS:
                values[field] = SCRAPE_DASH_FALLBACK.get(field, DASH)

        self._apply_tamil_month(day, values, overrides, force=False)

        self.db.upsert_content(day, values)
        self.db.set_checksum_meta(day, fetched_at=_now())
        return panchanga.ok

    def tamil_month_rows(self) -> list[tuple[Date, str, str]]:
        """Tamil month start dates, preferring the user-maintained table.

        The /tamil-months page writes to the database; the built-in table is the
        seed and the fallback when the database has no rows.
        """
        stored = self.db.list_tamil_months()
        if not stored:
            return list(TAMIL_MONTH_STARTS)

        rows: dict[Date, tuple[str, str]] = {}
        for start, english, tamil in TAMIL_MONTH_STARTS:
            rows[start] = (english, tamil)
        # Database entries win, so a correction in the UI takes effect.
        for row in stored:
            try:
                start = Date.fromisoformat(row["start_date"])
            except (ValueError, TypeError):
                continue
            rows[start] = (row["month_en"], row["month_ta"])
        return [(start, en, ta) for start, (en, ta) in rows.items()]

    def _apply_tamil_month(
        self,
        day: Date,
        values: dict[str, object],
        overrides: list[str],
        force: bool,
    ) -> None:
        if "tamil_month" in overrides and not force:
            return
        try:
            month_en, month_ta, tamil_day, _ = resolve_tamil_month(
                day, self.tamil_month_rows()
            )
        except TamilMonthOutOfRange as exc:
            log.warning("Tamil month unavailable for %s: %s", day, exc)
            values["tamil_month"] = DASH
            values["tamil_month_ta"] = ""
            values["tamil_date"] = None
            return
        values["tamil_month"] = month_en
        values["tamil_month_ta"] = month_ta
        values["tamil_date"] = tamil_day

    # -------------------------------------------------------------- generation
    def generate(self, day: Date, store: bool = True) -> tuple[bytes, str]:
        """Render ``day`` and optionally persist the bitmap.

        Returns ``(bitmap, checksum)``.
        """
        require_raqm()
        row = self.db.get_day(day)
        if row is None:
            # Nothing known about this date yet: fetch, then render.
            self.refresh_date(day)
            row = self.db.get_day(day)

        data = RenderInput(
            date=day,
            masa=row["masa"] or DASH,
            paksha=row["paksha"] or DASH,
            tithi=row["tithi"] or DASH,
            nakshatra=row["nakshatra"] or DASH,
            next_ekadashi=row["next_ekadashi"] or NEXT_EKADASHI_NONE,
            tamil_month=row["tamil_month"] or "",
            tamil_month_ta=row["tamil_month_ta"] or "",
            tamil_date=row["tamil_date"],
            custom_text=_custom_text(row),
            day_image=row["day_image"] or "",
            addl_image=row["addl_image"] or "",
            paksha_code=_paksha_code(row["paksha"]),
            tithi_number=_stored_tithi_number(row),
            panchanga_ok=bool(row["panchanga_ok"]),
        )

        bitmap = self.renderer().render(data)
        if store:
            checksum = self.db.store_bitmap(day, bitmap)
            return bitmap, checksum

        import hashlib

        return bitmap, hashlib.md5(bitmap).hexdigest()

    def generate_range(self, start: Date, days: int, refresh: bool = True) -> dict:
        """Generate bitmaps for a span of days, used by the bulk cron job."""
        if refresh:
            self.refresh_range(start, days)

        generated = 0
        failed: list[str] = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            try:
                self.generate(day)
                generated += 1
            except Exception as exc:  # noqa: BLE001 - report and continue
                log.exception("generation failed for %s: %s", day, exc)
                failed.append(f"{day.isoformat()}: {exc}")
        return {"start": start.isoformat(), "days": days, "generated": generated, "failed": failed}

    # ------------------------------------------------------------------- reads
    def window(self, start: Date | None = None, days: int = 4) -> list[dict]:
        """Content metadata for ``days`` dates beginning at ``start``."""
        begin = start or today_ist()
        out = []
        for offset in range(days):
            day = begin + timedelta(days=offset)
            row = self.db.get_day(day)
            if row is None:
                out.append(
                    {
                        "date": day.isoformat(),
                        "checksum": None,
                        "has_bitmap": False,
                        "panchanga_ok": False,
                        "custom_text": "",
                    }
                )
                continue
            out.append(
                {
                    "date": row["date"],
                    "checksum": row["checksum"],
                    "has_bitmap": row["bitmap"] is not None,
                    "panchanga_ok": bool(row["panchanga_ok"]),
                    "custom_text": row["custom_text"] or "",
                }
            )
        return out


def _custom_text(row) -> str:
    """The text drawn on the image's last line.

    An admin's own custom text always wins; when there is none, the day's
    Festival takes its place. The festival stays in its own column rather than
    being copied into custom_text, so editing the custom text later cannot
    destroy the scraped value, and clearing it brings the festival back.
    """
    custom = (row["custom_text"] or "").strip()
    if custom:
        return custom
    return (row["festival"] or "").strip()


def _overrides_of(row) -> list[str]:
    if row is None:
        return []
    raw = row["overrides"] if "overrides" in row.keys() else None
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _paksha_code(paksha: str | None) -> str | None:
    if not paksha:
        return None
    upper = paksha.upper()
    if "SHUKLA" in upper:
        return "SHUKLA"
    if "KRISHNA" in upper:
        return "KRISHNA"
    return None




def _stored_tithi_number(row) -> int | None:
    """Tithi position in the fortnight for the moon phase.

    Prefers the value captured at scrape time, which is derived from the plain
    Tithi when the Shraddha Tithi name is not a standard one. Falls back to
    parsing the display text for rows written before the column existed.
    """
    try:
        stored = row["tithi_number"]
    except (IndexError, KeyError):
        stored = None
    if stored is not None:
        return int(stored)
    return tithi_number_for(row["tithi"])




def _now() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat(timespec="seconds")
