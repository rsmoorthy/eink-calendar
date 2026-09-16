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
    TAMIL_MONTH_STARTS,
    Panchanga,
    TamilMonthOutOfRange,
    fetch_panchanga,
    resolve_tamil_month,
    tithi_number_for,
    today_ist,
)
from renderer import RenderInput, Renderer, default_assets_dir, require_raqm

log = logging.getLogger(__name__)

# Fields the scrape is allowed to refresh. Admin-edited fields are excluded at
# write time via the per-day override list.
SCRAPE_FIELDS = ("masa", "paksha", "tithi", "nakshatra", "tithi_number")


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
                values[field] = DASH

        self._apply_tamil_month(day, values, overrides, force)

        self.db.upsert_content(day, values)
        self.db.set_checksum_meta(day, fetched_at=_now())
        log.info(
            "refreshed %s (panchanga_ok=%s, tithi_source=%s)",
            day,
            panchanga.ok,
            panchanga.tithi_source,
        )
        return panchanga.ok

    def refresh_range(self, start: Date, days: int) -> dict[str, bool]:
        """Refresh ``days`` consecutive dates beginning at ``start``."""
        session = requests.Session()
        results: dict[str, bool] = {}
        for offset in range(days):
            day = start + timedelta(days=offset)
            try:
                results[day.isoformat()] = self._refresh_with_session(day, session)
            except Exception as exc:  # noqa: BLE001 - one bad day must not stop the run
                log.exception("refresh failed for %s: %s", day, exc)
                results[day.isoformat()] = False
        return results

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
                values[field] = DASH

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
            tamil_month=row["tamil_month"] or "",
            tamil_month_ta=row["tamil_month_ta"] or "",
            tamil_date=row["tamil_date"],
            custom_text=row["custom_text"] or "",
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
