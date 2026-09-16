# Database Schema Documentation

The calendar server uses an embedded **SQLite** database (`calendar.db`). This file documents the schema, data types, indexes, and relationships.

---

## 1. Entity-Relationship Overview

```
+-----------------------------------+
|               users               |
+-----------------------------------+
| id            INTEGER (PK, AUTO)  |
| username      TEXT (UNIQUE, NN)   |
| password_hash TEXT (NN)           |
| salt          TEXT (NN)           |
| created_at    DATETIME            |
+-----------------------------------+

+-----------------------------------+
|           calendar_days           |
+-----------------------------------+
| date             TEXT (PK, YYYY-MM-DD)
| day_of_week      TEXT             |
| gregorian_day    INTEGER          |
| gregorian_month  TEXT             |
| lunar_masa       TEXT             |
| lunar_paksha     TEXT             |
| lunar_tithi      TEXT             |
| nakshatra        TEXT             |
| tamil_month      TEXT             |
| tamil_month_ta   TEXT             |
| tamil_date       INTEGER          |
| custom_text      TEXT             |
| icon_name        TEXT             |
| addl_icon_name   TEXT             |
| bitmap           BLOB (15000 bytes)
| checksum         TEXT (MD5 hex)   |
| updated_at       DATETIME         |
+-----------------------------------+

+-----------------------------------+
|           config_store            |
+-----------------------------------+
| key           TEXT (PK)           |
| value         TEXT                |
| updated_at    DATETIME            |
+-----------------------------------+
```

---

## 2. Table Definitions

### 2.1 `users` Table
Stores web administration credentials. Passwords are encrypted using SHA-256 with a unique random salt per user.

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

- **`id`**: Auto-incrementing primary key.
- **`username`**: Unique username for admin login.
- **`password_hash`**: Hex-encoded SHA-256 hash of `(password + salt)`.
- **`salt`**: 32-character hexadecimal random salt.
- **`created_at`**: Timestamp of user creation.

---

### 2.2 `calendar_days` Table
Stores calendar metadata and the generated 1-bit monochrome bitmap for every calendar date.

```sql
CREATE TABLE IF NOT EXISTS calendar_days (
    date TEXT PRIMARY KEY,               -- ISO format 'YYYY-MM-DD'
    day_of_week TEXT NOT NULL,          -- Full day name ('Sunday', 'Monday', ...)
    gregorian_day INTEGER NOT NULL,     -- 1 to 31
    gregorian_month TEXT NOT NULL,      -- Short month name ('Jan', 'Feb', ...)
    lunar_masa TEXT DEFAULT '',         -- e.g. 'Bhadrapada'
    lunar_paksha TEXT DEFAULT '',       -- 'Shukla' or 'Krishna'
    lunar_tithi TEXT DEFAULT '',        -- 'Prathama', 'Dvitiya', ...
    nakshatra TEXT DEFAULT '',          -- 'Hasta', 'Ashwini', ...
    tamil_month TEXT DEFAULT '',        -- English name ('Purattasi')
    tamil_month_ta TEXT DEFAULT '',     -- Tamil script ('புரட்டாசி')
    tamil_date INTEGER DEFAULT 0,       -- 1 to 32
    custom_text TEXT DEFAULT '',        -- Special messages / birthday greetings
    icon_name TEXT DEFAULT '',          -- Name of Day icon file ('sun.png', etc.)
    addl_icon_name TEXT DEFAULT '',     -- Name of Additional icon file for line 4
    bitmap BLOB,                        -- Exactly 15,000 bytes (400x300 1-bit)
    checksum TEXT DEFAULT '',           -- MD5 hash of bitmap
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_calendar_days_date ON calendar_days(date);
```

- **`date`**: Primary key in format `YYYY-MM-DD`. Fast range queries for date windows (e.g., today + 3 days).
- **`bitmap`**: Raw binary 1-bit packed image (1 byte = 8 pixels, 50 bytes/row × 300 rows = 15,000 bytes).
- **`checksum`**: Hex MD5 string computed from `bitmap`. Used by the ESP32 to decide if an image must be re-downloaded.

---

### 2.3 `config_store` Table
Stores system-level settings and the layout YAML configuration used by the image generation engine.

```sql
CREATE TABLE IF NOT EXISTS config_store (
    key TEXT PRIMARY KEY,               -- Configuration key, e.g. 'layout_yaml'
    value TEXT NOT NULL,                -- Configuration payload (YAML/JSON text)
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

- Enables configuration changes from the `/config` web interface to persist in SQLite, while allowing fallback to a local default `config.yaml` file on disk.

---

## 3. Database Management & CLI Usage

The database file is located at `server/calendar.db`.

To create or reset the administrator password via CLI:
```bash
python3 server/manage_users.py create-user --username admin --password secretpassword
```

To verify database integrity:
```bash
sqlite3 server/calendar.db "SELECT date, day_of_week, lunar_tithi, checksum FROM calendar_days LIMIT 5;"
```
