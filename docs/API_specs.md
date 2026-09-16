# Calendar System API Specification

This document defines the REST API exposed by the Amma Clock Calendar Server (default port: `8080`) for both the ESP32-C6 e-Paper client and the Web Administration interface.

---

## 1. Overview & Conventions

- **Base URL**: `http://<server-ip>:8080` (e.g., `http://192.168.29.31:8080`)
- **Timezone**: All dates and times are handled in Indian Standard Time (**IST**, UTC+05:30).
- **Date Format**: ISO 8601 string (`YYYY-MM-DD`, e.g., `2026-09-13`).
- **Bitmap Format**: 
  - Resolution: 400 × 300 pixels.
  - Bit depth: 1 bit per pixel (monochrome: `0` = Black, `1` = White).
  - Bit packing: Horizontal, 8 pixels per byte, Most Significant Bit (MSB) first.
  - Buffer size: $(400 \times 300) / 8 = 15,000\text{ bytes}$.
- **Checksum**: Hexadecimal MD5 hash of the 15,000-byte bitmap buffer.

---

## 2. ESP32 Client Endpoints

The ESP32 communicates with the server using lightweight REST endpoints.

### 2.1 Get Current Date Info
Synchronizes current date, time in IST, and dynamic polling frequency on startup and on each polling cycle.

- **URL**: `GET /api/date` or `GET /date`
- **Headers**: `Accept: application/json`
- **Response**: `200 OK`
  ```json
  {
    "date": "2026-09-13",
    "day_of_week": "Sunday",
    "day_abbr": "Sun",
    "time": "19:30:00",
    "timestamp": 1789404000,
    "poll_interval_minutes": 5
  }
  ```
- **Fields**:
  - `poll_interval_minutes`: Dynamically loaded from `server/config.yaml` (`system.poll_interval_minutes`). Configurable to e.g. `2` or `5` during development/testing, and `60` in production.

---

### 2.2 Get Calendar List (Today + 3 Days)
Polled periodically by the ESP32 to detect if the bitmap for today or any of the next 3 days has changed.

- **URL**: `GET /api/calendar` or `GET /calendar`
- **Headers**: `Accept: application/json`
- **Response Headers**:
  - `X-Poll-Interval-Minutes`: `5` (contains the configured poll interval in minutes)
- **Response**: `200 OK`
  ```json
  [
    {
      "date": "2026-09-13",
      "checksum": "d41d8cd98f00b204e9800998ecf8427e"
    },
    {
      "date": "2026-09-14",
      "checksum": "8b1a9953c4611296a827abf8c47804d7"
    },
    {
      "date": "2026-09-15",
      "checksum": "c0543e06a5b6d5b00c3b0df055c65f94"
    },
    {
      "date": "2026-09-16",
      "checksum": "9e107d9d372bb6826bd81d3542a419d6"
    }
  ]
  ```

---

### 2.3 Get Day Image & Bitmap
Retrieves the pre-rendered bitmap for a specific date. Supports both **JSON** (with base64 bitmap) and **Raw Binary** streaming.

#### Option A: JSON Mode (Default)
- **URL**: `GET /api/calendar/{date}` or `GET /calendar/{date}`
- **Headers**: `Accept: application/json`
- **Response**: `200 OK`
  ```json
  {
    "date": "2026-09-13",
    "checksum": "d41d8cd98f00b204e9800998ecf8427e",
    "width": 400,
    "height": 300,
    "size_bytes": 15000,
    "bitmap": "<base64-encoded-15000-bytes>"
  }
  ```

#### Option B: Raw Binary Streaming (Zero-decoding for ESP32)
- **URL**: `GET /api/calendar/{date}?format=raw` or `GET /calendar/{date}?format=raw`
- **Headers**: `Accept: application/octet-stream`
- **Response Headers**:
  - `Content-Type: application/octet-stream`
  - `Content-Length: 15000`
  - `X-Calendar-Date: 2026-09-13`
  - `X-Calendar-Checksum: d41d8cd98f00b204e9800998ecf8427e`
- **Response Body**: Raw stream of 15,000 bytes.

---

## 3. Web Admin Endpoints

### 3.1 Authentication
- `GET /login`: Render login page.
- `POST /api/login`: Form/JSON login with `username` and `password`. Sets session cookie.
- `POST /api/logout` / `GET /logout`: Invalidate session.

### 3.2 Dashboard & Calendar Data
- `GET /` or `GET /home`: Main calendar web interface.
- `GET /api/day/{date}`: Retrieve day metadata, custom text, icons, and status:
  ```json
  {
    "date": "2026-09-13",
    "day_of_week": "Sunday",
    "gregorian_day": 13,
    "gregorian_month": "Sep",
    "lunar_masa": "Bhadrapada",
    "lunar_paksha": "Shukla",
    "lunar_tithi": "Dvitiya",
    "nakshatra": "Hasta",
    "tamil_month": "Purattasi",
    "tamil_month_ta": "புரட்டாசி",
    "tamil_date": 15,
    "custom_text": "Happy Birthday Ramesh!",
    "icon_name": "sun.png",
    "addl_icon_name": "vinayaka.png",
    "day_icon_file": "sun.png",
    "addl_icon_file": "vinayaka.png",
    "has_image": true,
    "checksum": "d41d8cd98f00b204e9800998ecf8427e"
  }
  ```
- `POST /api/day/{date}`: Update day fields, custom text, and icons, then regenerate the image:
  ```json
  {
    "custom_text": "Happy Birthday Ramesh!",
    "lunar_masa": "Bhadrapada",
    "lunar_tithi": "Dvitiya",
    "lunar_paksha": "Shukla",
    "nakshatra": "Hasta",
    "tamil_month_ta": "புரட்டாசி",
    "tamil_date": 15,
    "icon_name": "sun.png",
    "addl_icon_name": "vinayaka.png"
  }
  ```
- `GET /api/preview/{date}.png`: Returns a PNG rendering of the generated bitmap for web browser preview.

### 3.3 Micro-Configuration
- `GET /config`: Configuration editor UI.
- `GET /api/config`: Return current YAML configuration JSON/string.
- `POST /api/config`: Save updated YAML configuration and reload engine.

### 3.4 Bulk Generation
- `POST /api/generate`: Trigger bulk generation for $N$ days starting from a given date.
  ```json
  {
    "start_date": "2026-09-13",
    "days": 90,
    "force": false
  }
  ```

### 3.5 Icon Management
- `GET /upload`: Web UI for managing and uploading icon files. Lists day-of-week icons (`mon.png` to `sun.png`) and custom icons with 128px thumbnails and resolutions.
- `GET /icons/{filename}`: Static file endpoint serving icons directly.
- `POST /api/upload`: Multipart upload for icon images (accepts `file` and optional `custom_name`).
- `POST /api/icons/{filename}/delete` / `DELETE /api/icons/{filename}`: Delete a custom icon file. Core day-of-week icons (`mon.png` to `sun.png`) are protected and cannot be deleted.
