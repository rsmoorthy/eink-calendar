import sqlite3
import os
import hashlib
import binascii

DB_PATH = os.environ.get("CALENDAR_DB_PATH", os.path.join(os.path.dirname(__file__), "calendar.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calendar_days (
        date TEXT PRIMARY KEY,
        day_of_week TEXT NOT NULL,
        gregorian_day INTEGER NOT NULL,
        gregorian_month TEXT NOT NULL,
        lunar_masa TEXT DEFAULT '',
        lunar_paksha TEXT DEFAULT '',
        lunar_tithi TEXT DEFAULT '',
        nakshatra TEXT DEFAULT '',
        tamil_month TEXT DEFAULT '',
        tamil_month_ta TEXT DEFAULT '',
        tamil_date INTEGER DEFAULT 0,
        custom_text TEXT DEFAULT '',
        icon_name TEXT DEFAULT '',
        addl_icon_name TEXT DEFAULT '',
        bitmap BLOB,
        checksum TEXT DEFAULT '',
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Migration check for addl_icon_name on existing tables
    cursor.execute("PRAGMA table_info(calendar_days);")
    cols = [col[1] for col in cursor.fetchall()]
    if "addl_icon_name" not in cols:
        cursor.execute("ALTER TABLE calendar_days ADD COLUMN addl_icon_name TEXT DEFAULT '';")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config_store (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_calendar_days_date ON calendar_days(date);")

    conn.commit()
    conn.close()


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = binascii.hexlify(os.urandom(16)).decode("utf-8")
    pwd_hash = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return pwd_hash, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    expected_hash, _ = hash_password(password, salt)
    return expected_hash == password_hash


def create_or_update_user(username: str, password: str):
    pwd_hash, salt = hash_password(password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, salt)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, salt=excluded.salt;
    """, (username, pwd_hash, salt))
    conn.commit()
    conn.close()


def get_user_by_username(username: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_calendar_day(date_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM calendar_days WHERE date = ?", (date_str,))
    row = cursor.fetchone()
    conn.close()
    return row


def save_calendar_day(day_data: dict):
    conn = get_connection()
    cursor = conn.cursor()
    data = dict(day_data)
    data.setdefault("icon_name", "")
    data.setdefault("addl_icon_name", "")
    cursor.execute("""
        INSERT INTO calendar_days (
            date, day_of_week, gregorian_day, gregorian_month,
            lunar_masa, lunar_paksha, lunar_tithi, nakshatra,
            tamil_month, tamil_month_ta, tamil_date,
            custom_text, icon_name, addl_icon_name, bitmap, checksum, updated_at
        ) VALUES (
            :date, :day_of_week, :gregorian_day, :gregorian_month,
            :lunar_masa, :lunar_paksha, :lunar_tithi, :nakshatra,
            :tamil_month, :tamil_month_ta, :tamil_date,
            :custom_text, :icon_name, :addl_icon_name, :bitmap, :checksum, CURRENT_TIMESTAMP
        )
        ON CONFLICT(date) DO UPDATE SET
            day_of_week=excluded.day_of_week,
            gregorian_day=excluded.gregorian_day,
            gregorian_month=excluded.gregorian_month,
            lunar_masa=excluded.lunar_masa,
            lunar_paksha=excluded.lunar_paksha,
            lunar_tithi=excluded.lunar_tithi,
            nakshatra=excluded.nakshatra,
            tamil_month=excluded.tamil_month,
            tamil_month_ta=excluded.tamil_month_ta,
            tamil_date=excluded.tamil_date,
            custom_text=excluded.custom_text,
            icon_name=excluded.icon_name,
            addl_icon_name=excluded.addl_icon_name,
            bitmap=excluded.bitmap,
            checksum=excluded.checksum,
            updated_at=CURRENT_TIMESTAMP;
    """, data)
    conn.commit()
    conn.close()


def get_calendar_range(start_date: str, count: int = 4):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, checksum, day_of_week, gregorian_day, gregorian_month,
               lunar_tithi, lunar_masa, lunar_paksha, tamil_month_ta, tamil_date, custom_text
        FROM calendar_days
        WHERE date >= ?
        ORDER BY date ASC
        LIMIT ?;
    """, (start_date, count))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_config(key: str, default: str = None) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config_store WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def save_config(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO config_store (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP;
    """, (key, value))
    conn.commit()
    conn.close()
