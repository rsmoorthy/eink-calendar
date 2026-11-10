"""SQLite storage for day records, rendered bitmaps, and admin overrides.

Every calendar day has exactly one row keyed by its ISO date. The row carries
the panchanga fields (scraped or manually overridden), the custom text, and the
rendered raw 1-bit bitmap together with the checksum of that bitmap. The ESP32
polls the checksum list, so this table is the single authoritative source of
what a given date currently looks like.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date as Date
from pathlib import Path

from panchanga import NEXT_EKADASHI_NONE

SERVER_DIR = Path(__file__).resolve().parent

# Fields that make up a day's content. Kept in one place so the API, renderer
# and web form cannot drift apart.
CONTENT_FIELDS = (
    "masa",
    "paksha",
    "tithi",
    "tithi_number",
    "nakshatra",
    "festival",
    "next_ekadashi",
    "tamil_month",
    "tamil_month_ta",
    "tamil_date",
    "custom_text",
    "day_image",
    "addl_image",
)

# Metadata fields stored alongside content but not rendered.
META_FIELDS = ("panchanga_ok", "tithi_source")

SCHEMA = """
CREATE TABLE IF NOT EXISTS day (
    date            TEXT PRIMARY KEY,
    masa            TEXT,
    paksha          TEXT,
    tithi           TEXT,
    tithi_number    INTEGER,
    nakshatra       TEXT,
    festival        TEXT,
    next_ekadashi   TEXT,
    tamil_month     TEXT,
    tamil_month_ta  TEXT,
    tamil_date      INTEGER,
    custom_text     TEXT,
    day_image       TEXT,
    addl_image      TEXT,
    panchanga_ok    INTEGER NOT NULL DEFAULT 0,
    tithi_source    TEXT,
    overrides       TEXT NOT NULL DEFAULT '[]',
    bitmap          BLOB,
    checksum        TEXT,
    rendered_at     TEXT,
    fetched_at      TEXT
);

CREATE TABLE IF NOT EXISTS admin_user (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS tamil_month (
    start_date TEXT PRIMARY KEY,
    month_en   TEXT NOT NULL,
    month_ta   TEXT NOT NULL
);
"""


def _db_path() -> Path:
    override = os.environ.get("EINK_DB_PATH")
    if override:
        return Path(override)
    return SERVER_DIR / "data" / "calendar.db"


class Database:
    """Thread-safe SQLite wrapper.

    Connections are per-thread because the Flask dev server and the renderer run
    on different threads; a module-level connection would raise.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else _db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialise()

    # ------------------------------------------------------------- connection
    @property
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            # WAL lets the hourly ESP poll read while an admin regeneration
            # writes; without it concurrent access raises "database is locked".
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def write(self):
        """Serialise writers; SQLite allows a single writer at a time."""
        with self._init_lock:
            conn = self.connection
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _initialise(self) -> None:
        conn = self.connection
        conn.executescript(SCHEMA)
        self._migrate(conn)
        conn.commit()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after a database was first created.

        CREATE TABLE IF NOT EXISTS leaves an existing table untouched, so new
        columns have to be added explicitly or an upgraded deployment would fail
        with "no such column". Adding a column with a default is safe and cheap
        in SQLite.
        """
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(day)").fetchall()
        }
        for column, definition in MIGRATIONS:
            if column not in existing:
                conn.execute(f"ALTER TABLE day ADD COLUMN {column} {definition}")
        _backfill(conn, existing)

    # ------------------------------------------------------------------- days
    def get_day(self, day: Date | str) -> sqlite3.Row | None:
        key = day.isoformat() if isinstance(day, Date) else day
        cur = self.connection.execute("SELECT * FROM day WHERE date = ?", (key,))
        return cur.fetchone()

    def get_content(self, day: Date | str) -> dict | None:
        """Return just the content fields plus bitmap metadata."""
        row = self.get_day(day)
        if row is None:
            return None
        result = {field: row[field] for field in CONTENT_FIELDS}
        result["date"] = row["date"]
        result["panchanga_ok"] = bool(row["panchanga_ok"])
        result["tithi_source"] = row["tithi_source"]
        result["overrides"] = _parse_overrides(row["overrides"])
        result["checksum"] = row["checksum"]
        result["has_bitmap"] = row["bitmap"] is not None
        result["rendered_at"] = row["rendered_at"]
        return result

    def upsert_content(self, day: Date, values: dict[str, object]) -> None:
        """Insert or update content fields without touching the bitmap.

        Only the supplied fields are written, so a scrape refresh does not
        clobber an admin's manual edit (see ``overrides``).
        """
        key = day.isoformat()
        columns = [f for f in VALUES_FIELDS if f in values]
        with self.write() as conn:
            conn.execute("INSERT OR IGNORE INTO day (date) VALUES (?)", (key,))
            if columns:
                assignments = ", ".join(f"{col} = ?" for col in columns)
                params = [_serialise_value(values[col]) for col in columns]
                params.append(key)
                conn.execute(
                    f"UPDATE day SET {assignments} WHERE date = ?", params
                )

    def mark_override(self, day: Date, field: str) -> None:
        """Record that an admin manually set ``field`` for this date.

        Scrape refreshes skip overridden fields, so manual corrections survive
        the hourly/periodic panchanga refresh.
        """
        row = self.get_day(day)
        existing = _parse_overrides(row["overrides"]) if row else []
        if field not in existing:
            existing.append(field)
        self.upsert_content(day, {"overrides": existing})

    def clear_overrides(self, day: Date) -> None:
        self.upsert_content(day, {"overrides": []})

    def store_bitmap(self, day: Date, bitmap: bytes) -> str:
        """Persist a rendered bitmap and return its md5 checksum."""
        checksum = hashlib.md5(bitmap).hexdigest()
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO day (date, bitmap, checksum, rendered_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date) DO UPDATE SET
                    bitmap = excluded.bitmap,
                    checksum = excluded.checksum,
                    rendered_at = excluded.rendered_at
                """,
                (day.isoformat(), bitmap, checksum),
            )
        return checksum

    def get_bitmap(self, day: Date | str) -> bytes | None:
        row = self.get_day(day)
        if row is None or row["bitmap"] is None:
            return None
        return bytes(row["bitmap"])

    def list_between(self, start: Date, end: Date) -> list[sqlite3.Row]:
        """Rows for ``start``..``end`` inclusive, ordered by date."""
        cur = self.connection.execute(
            "SELECT * FROM day WHERE date >= ? AND date <= ? ORDER BY date",
            (start.isoformat(), end.isoformat()),
        )
        return list(cur.fetchall())

    def festivals_between(self, start: Date, end: Date) -> list[tuple[str, str]]:
        """``(date, festival)`` pairs for ``start``..``end`` inclusive, by date.

        Only these two columns are read: this is used to scan a window for an
        Ekadashi festival, and must not drag each day's rendered bitmap out of
        the table to do it.
        """
        cur = self.connection.execute(
            """
            SELECT date, festival FROM day
            WHERE date >= ? AND date <= ?
            ORDER BY date
            """,
            (start.isoformat(), end.isoformat()),
        )
        return [(row["date"], row["festival"] or "") for row in cur]

    def set_checksum_meta(self, day: Date, **values: object) -> None:
        self.upsert_content(day, values)

    # ------------------------------------------------------------ admin users
    def create_admin(self, username: str, password_hash: str) -> None:
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO admin_user (username, password_hash) VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
                """,
                (username, password_hash),
            )

    def get_admin(self, username: str) -> sqlite3.Row | None:
        cur = self.connection.execute(
            "SELECT * FROM admin_user WHERE username = ?", (username,)
        )
        return cur.fetchone()

    def admin_count(self) -> int:
        cur = self.connection.execute("SELECT COUNT(*) AS n FROM admin_user")
        return int(cur.fetchone()["n"])

    # --------------------------------------------------------------- settings
    def set_setting(self, key: str, value: str) -> None:
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        cur = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return row["value"] if row else default

    # ----------------------------------------------------------- tamil months
    def tamil_month_for(self, day: Date) -> sqlite3.Row | None:
        cur = self.connection.execute(
            "SELECT * FROM tamil_month WHERE start_date <= ? ORDER BY start_date DESC LIMIT 1",
            (day.isoformat(),),
        )
        return cur.fetchone()

    def seed_tamil_months(self, rows: list[tuple[Date, str, str]]) -> None:
        with self.write() as conn:
            conn.executemany(
                """
                INSERT INTO tamil_month (start_date, month_en, month_ta)
                VALUES (?, ?, ?)
                ON CONFLICT(start_date) DO UPDATE SET
                    month_en = excluded.month_en,
                    month_ta = excluded.month_ta
                """,
                [(d.isoformat(), en, ta) for d, en, ta in rows],
            )

    def list_tamil_months(self) -> list[sqlite3.Row]:
        cur = self.connection.execute(
            "SELECT * FROM tamil_month ORDER BY start_date"
        )
        return list(cur.fetchall())


# Content fields that may be written by upsert_content. Kept separate from
# CONTENT_FIELDS because "overrides" is bookkeeping, not display content.
VALUES_FIELDS = CONTENT_FIELDS + META_FIELDS + (
    "overrides",
    "fetched_at",
)

# Columns added after the initial schema, applied by Database._migrate.
MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("tithi_number", "INTEGER"),
    ("tithi_source", "TEXT"),
    ("day_image", "TEXT"),
    ("addl_image", "TEXT"),
    ("festival", "TEXT"),
    ("next_ekadashi", "TEXT"),
)


def _backfill(conn: sqlite3.Connection, existing: set[str]) -> None:
    """Give rows created before a column existed a sensible value for it.

    A column added by ALTER TABLE is NULL on every existing row. For
    ``next_ekadashi`` NULL would draw as an empty field, so those rows are set
    to the blank form ("N.Eka: —") that a freshly fetched day would have. The
    derived pass replaces them with real dates as it runs.
    """
    if "next_ekadashi" not in existing:
        conn.execute(
            "UPDATE day SET next_ekadashi = ? WHERE next_ekadashi IS NULL",
            (NEXT_EKADASHI_NONE,),
        )


def _parse_overrides(raw: str | None) -> list[str]:
    if not raw:
        return []
    import json

    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _serialise_value(value: object) -> object:
    """Convert Python values into types SQLite accepts."""
    if isinstance(value, (list, tuple)):
        import json

        return json.dumps(list(value))
    if isinstance(value, bool):
        return int(value)
    return value
