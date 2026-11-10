"""Panchanga and Tamil calendar data for a given date.

Panchanga values are scraped from the Vyasaraja Matha panchanga endpoint. The
matha's reckoning is authoritative for this project (different panchangas vary
slightly), so when the source is unavailable the day is marked as failed and the
image is rendered with dashes rather than a computed substitute.

Tithi selection: the matha publishes both "Tithi" and "Shraddha Tithi". They can
differ (for example on 2026-09-15 the page reports Tithi CHATURTHI but Shraddha
Tithi PANCHAMI). "Shraddha Tithi" wins, because it is the tithi that governs the
day's observances. It is skipped on the days it does not name a tithi of its own
— "SHRADDHABHAVA", or a compound such as "EKADASHI/DVADASHI" meaning the tithi
changes during the day — and the plain "Tithi" element names the day instead.

The "Festivals/Events" element is captured alongside as ``festival``. See
:func:`select_tithi`.

Ekadashi detection: a day is an Ekadashi when its "Festivals/Events" text
contains the letters "EKADASHI" as a substring, case-insensitively. The tithi is
not consulted. See :func:`is_ekadashi`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

PANCHANGA_URL = "https://vyasarajamatha.org/panchanga_ajax.php"

IST = timezone(timedelta(hours=5, minutes=30))

DASH = "—"

# The "next Ekadashi" annotation names a calendar date as "N.Eka: <Mon> <date>".
# Defined here rather than in the service because storage also needs the empty
# form: a day with no known Ekadashi ahead of it.
NEXT_EKADASHI_PREFIX = "N.Eka: "
NEXT_EKADASHI_NONE = f"{NEXT_EKADASHI_PREFIX}{DASH}"

# Tithi index within a paksha. Purnima/Amavasya close out the fortnight at 15.
TITHI_NUMBERS = {
    "PRATHAMA": 1,
    "PRATIPADA": 1,
    "DWITIYA": 2,
    "DVITIYA": 2,
    "TRITIYA": 3,
    "CHATURTHI": 4,
    "PANCHAMI": 5,
    "SHASHTHI": 6,
    "SHASTHI": 6,
    "SAPTAMI": 7,
    "ASHTAMI": 8,
    "NAVAMI": 9,
    "DASHAMI": 10,
    "DASAMI": 10,
    "EKADASHI": 11,
    "DWADASHI": 12,
    "DVADASHI": 12,
    "TRAYODASHI": 13,
    "CHATURDASHI": 14,
    "PURNIMA": 15,
    "POURNAMI": 15,
    "AMAVASYA": 15,
    "AMAVASYA": 15,
    "AMAVASYE": 15,
    "AMAVASI": 15,
}

_DISPLAY_OVERRIDES = {
    "PURNIMA": "Purnima",
    "POURNAMI": "Purnima",
    "AMAVASYA": "Amavasya",
    "AMAVASYA": "Amavasya",
    "AMAVASYE": "Amavasya",
    "AMAVASI": "Amavasya",
}

# Displayed on its own line, so the word "paksha" is redundant.
PAKSHA_DISPLAY = {"SHUKLA": "Shukla", "KRISHNA": "Krishna"}

# Festival values that mean "the source stated one but it carried no name"; the
# only one seen is the literal text "None" (a null the source rendered as a
# string). Treated as absent so it is never written to the database, and never
# drawn as the day's custom text.
_EMPTY_FESTIVALS = {"NONE", "NIL", "NA", "N/A"}


def select_tithi(tithi_raw: str | None, shraddha_raw: str | None) -> tuple[str, str]:
    """Choose the day's tithi from the two the source publishes.

    Returns ``(value, source_label)``, where the value is raw as scraped and the
    label names the element it came from, for display on the web page.

    "Shraddha Tithi" governs the day and wins, except where it does not name a
    single tithi:

    * "SHRADDHABHAVA" — a shraddha observance rather than a tithi, so the day is
      named by the "Tithi" element instead.
    * a compound such as "EKADASHI/DVADASHI" — the tithi changes during the day,
      so the "Tithi" element carries the name the day is known by.
    """
    tithi = (tithi_raw or "").strip()
    shraddha = (shraddha_raw or "").strip()

    if not shraddha:
        return tithi, "Tithi"
    if shraddha.upper() == "SHRADDHABHAVA" or "/" in shraddha:
        return tithi, "Tithi"
    return shraddha, "Shraddha Tithi"


def primary_tithi(name: str | None) -> str:
    """First component of a tithi name, upper-cased.

    The source reports compound names such as "EKADASHI/DVADASHI" or
    "EKADASHI/DVADASHI/TRAYODASHI" when the tithi changes during the day. The
    prevailing tithi at sunrise is the convention for naming the day, so the
    first component is the one displayed and used for the moon phase.
    """
    if not name:
        return ""
    return name.split("/")[0].strip().upper()


def tithi_number_for(name: str | None) -> int | None:
    """Fortnight position (1..15) for a tithi name, or None if unrecognised.

    Used both when scraping and when an admin edits the tithi text by hand, so
    the moon phase stays consistent with whatever name is displayed.
    """
    return TITHI_NUMBERS.get(primary_tithi(name))


def is_ekadashi(festival: str | None) -> bool:
    """Whether the day's festival text names an Ekadashi.

    The matha writes the occasion as one word, such as
    "SARVESHAMEKADASHI(PASHANKUSHA)", so this is a case-insensitive substring
    match rather than a word match. It is the only rule: the tithi is not
    consulted.
    """
    return "EKADASHI" in (festival or "").upper()

_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-IN,en-US;q=0.9,en;q=0.8",
    "referer": "https://vyasarajamatha.org/panchanga.php",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


@dataclass
class Panchanga:
    """Resolved panchanga values for a single day."""

    date: Date
    masa: str = DASH
    paksha: str = DASH
    tithi: str = DASH
    tithi_number: int | None = None
    nakshatra: str = DASH
    festival: str = ""
    tithi_source: str = "unavailable"
    ok: bool = False
    raw: dict | None = None

    @property
    def paksha_code(self) -> str | None:
        """Return 'SHUKLA' or 'KRISHNA' regardless of display formatting."""
        if not self.paksha or self.paksha == DASH:
            return None
        upper = self.paksha.upper()
        if "SHUKLA" in upper:
            return "SHUKLA"
        if "KRISHNA" in upper:
            return "KRISHNA"
        return None


def today_ist() -> Date:
    """Current date in IST, which is the calendar's reference timezone."""
    return datetime.now(IST).date()


def fetch_panchanga(day: Date, session: requests.Session | None = None) -> Panchanga:
    """Scrape panchanga for ``day``.

    Never raises for network or parse problems: returns a Panchanga with
    ``ok=False`` so callers can render the dash/error state.
    """
    client = session or requests
    try:
        response = client.get(
            PANCHANGA_URL,
            params={"selected_date": day.isoformat()},
            headers=_HEADERS,
            timeout=25,
        )
        if response.status_code != 200:
            return Panchanga(date=day, raw={"status": response.status_code})
        fields = _parse_fields(response.text)
    except requests.RequestException as exc:
        return Panchanga(date=day, raw={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - scrape data is untrusted
        return Panchanga(date=day, raw={"error": str(exc)})

    if not fields:
        return Panchanga(date=day, raw={"error": "no fields parsed"})

    masa = _clean(fields.get("Masa"))
    paksha_raw = _clean(fields.get("Paksha"))
    tithi_raw = _clean(fields.get("Tithi"))
    shraddha_raw = _clean(fields.get("Shraddha Tithi"))
    nakshatra = _clean(fields.get("Nakshatra"))
    festival = _clean_festival(fields.get("Festivals/Events"))

    chosen, source = select_tithi(tithi_raw, shraddha_raw)

    if not masa and not chosen and not nakshatra and not festival:
        return Panchanga(date=day, ok=False, raw=fields)

    # The moon's illuminated fraction needs the day's position in the
    # fortnight. The chosen value is normally a standard tithi name, but a
    # manually overridden row or an unexpected source value may not be, so fall
    # back to the plain Tithi for the phase.
    tithi_number = tithi_number_for(chosen)
    if tithi_number is None and tithi_raw:
        tithi_number = tithi_number_for(tithi_raw)

    return Panchanga(
        date=day,
        masa=_title(masa) if masa else DASH,
        paksha=PAKSHA_DISPLAY.get(paksha_raw.upper(), _title(paksha_raw))
        if paksha_raw
        else DASH,
        tithi=_display_tithi(chosen) if chosen else DASH,
        tithi_number=tithi_number,
        nakshatra=_title(nakshatra) if nakshatra else DASH,
        festival=festival,
        tithi_source=source,
        ok=True,
        raw=fields,
    )


def _parse_fields(html: str) -> dict[str, str]:
    """Extract the <strong>label</strong> value pairs from the response."""
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    for item in soup.find_all("li"):
        if item.strong is None:
            continue
        label = item.strong.get_text(strip=True).rstrip(":").strip()
        value = "".join(
            str(node).strip() for node in item.find_all(string=True, recursive=False)
        )
        if label:
            fields[label] = value.strip()
    return fields


def _clean(value: str | None) -> str:
    """Collapse whitespace and strip trailing punctuation from a field."""
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    return text.strip(" .,")


def _clean_festival(value: str | None) -> str:
    """Normalise the Festivals/Events element, or "" when it names nothing.

    The element is free text and sometimes holds more than one event separated
    by commas, which is kept as it stands: the renderer wraps it, and splitting
    or shortening it here would lose information the admin can still edit.
    """
    text = _clean(value)
    if text.upper() in _EMPTY_FESTIVALS:
        return ""
    return text


def _title(value: str) -> str:
    """Convert SHOUTY source text into readable title case."""
    if not value:
        return DASH
    upper = value.upper()
    if upper in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[upper]
    return " ".join(word.capitalize() for word in value.split())


def _display_tithi(value: str) -> str:
    word = primary_tithi(value)
    if not word:
        return DASH
    if word in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[word]
    return word.capitalize()


# --------------------------------------------------------------- Tamil month

# Tamil months begin at solar ingress (Sankranti), which drifts by a day or two
# year to year, so these are maintained as manual data rather than computed.
# Extend this table as years are added; see README.
TAMIL_MONTH_STARTS: list[tuple[Date, str, str]] = [
    (Date(2025, 12, 16), "Margazhi", "மார்கழி"),
    (Date(2026, 1, 15), "Thai", "தை"),
    (Date(2026, 2, 13), "Maasi", "மாசி"),
    (Date(2026, 3, 15), "Panguni", "பங்குனி"),
    (Date(2026, 4, 14), "Chithirai", "சித்திரை"),
    (Date(2026, 5, 15), "Vaikasi", "வைகாசி"),
    (Date(2026, 6, 15), "Aani", "ஆனி"),
    (Date(2026, 7, 17), "Aadi", "ஆடி"),
    (Date(2026, 8, 17), "Avani", "ஆவணி"),
    (Date(2026, 9, 17), "Purattasi", "புரட்டாசி"),
    (Date(2026, 10, 18), "Aippasi", "ஐப்பசி"),
    (Date(2026, 11, 17), "Karthigai", "கார்த்திகை"),
    (Date(2026, 12, 16), "Margazhi", "மார்கழி"),
    (Date(2027, 1, 15), "Thai", "தை"),
    (Date(2027, 2, 13), "Maasi", "மாசி"),
    (Date(2027, 3, 15), "Panguni", "பங்குனி"),
    (Date(2027, 4, 14), "Chithirai", "சித்திரை"),
    (Date(2027, 5, 15), "Vaikasi", "வைகாசி"),
    (Date(2027, 6, 15), "Aani", "ஆனி"),
    (Date(2027, 7, 17), "Aadi", "ஆடி"),
    (Date(2027, 8, 17), "Avani", "ஆவணி"),
    (Date(2027, 9, 17), "Purattasi", "புரட்டாசி"),
    (Date(2027, 10, 18), "Aippasi", "ஐப்பசி"),
    (Date(2027, 11, 17), "Karthigai", "கார்த்திகை"),
    (Date(2027, 12, 16), "Margazhi", "மார்கழி"),
    (Date(2028, 1, 15), "Thai", "தை"),
    (Date(2028, 2, 13), "Maasi", "மாசி"),
    (Date(2028, 3, 15), "Panguni", "பங்குனி"),
    (Date(2028, 4, 14), "Chithirai", "சித்திரை"),
]


class TamilMonthOutOfRange(Exception):
    """Raised when a date falls outside the maintained Tamil month table."""


def tamil_month_for(day: Date) -> tuple[str, str, int, str]:
    """Return ``(month_en, month_ta, tamil_day, start_iso)`` for ``day``.

    Uses the built-in table. Raises TamilMonthOutOfRange when the date is not
    covered, so the caller can surface a dash instead of a silently wrong month.
    Callers that support a user-maintained table should use
    :func:`resolve_tamil_month` instead.
    """
    return resolve_tamil_month(day, TAMIL_MONTH_STARTS)


def resolve_tamil_month(
    day: Date, rows: list[tuple[Date, str, str]]
) -> tuple[str, str, int, str]:
    """Resolve the Tamil month from ``rows``, a list of Sankranti start dates.

    ``rows`` may come from the database (edited via the web UI) or from the
    built-in table. Merged by date so a user-entered year can extend or correct
    the shipped data.

    Raises TamilMonthOutOfRange when ``rows`` does not cover ``day``.
    """
    if not rows:
        raise TamilMonthOutOfRange(f"no Tamil month data for {day.isoformat()}")

    starts = sorted(rows, key=lambda item: item[0])
    for index, (start, month_en, month_ta) in enumerate(starts):
        next_start = starts[index + 1][0] if index + 1 < len(starts) else None
        if day < start:
            continue
        if next_start is not None and day >= next_start:
            continue
        tamil_day = (day - start).days + 1
        return month_en, month_ta, tamil_day, start.isoformat()

    raise TamilMonthOutOfRange(
        f"{day.isoformat()} is outside the Tamil month table "
        f"({starts[0][0].isoformat()}..{starts[-1][0].isoformat()})"
    )
