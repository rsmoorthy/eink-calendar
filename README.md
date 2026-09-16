# Amma Clock - E-Ink Calendar System

A smart digital calendar for the **Waveshare 4.2" Black & White e-Paper display** (400×300 resolution) driven by an **ESP32-C6 Super Mini**, backed by a Python server running in Docker with a Web Administration interface.

---

## Architecture Overview

```
               +--------------------------------------------+
               |         Calendar Server (Docker)           |
               |  FastAPI + SQLite + Pillow Image Generator |
               |  Port: 8080                                |
               +---------------------+----------------------+
                                     |
               REST API              | REST API / Web UI
      (Date, Checksums, 1-bit Raw)   | (Preview, Edits, YAML Config)
                                     |
            v                                  v
+-----------------------+            +-------------------+
|   ESP32-C6 Client     |            |  Admin Web Browser|
|  - WiFi (Advaita)     |            |  - /home          |
|  - 4-Day RAM Cache    |            |  - /config        |
|  - Hourly Polling     |            +-------------------+
|  - Waveshare 4.2" EPD |
+-----------------------+
```

1. **Server-Side Image Rendering**:
   - All text, Tamil fonts ([`NotoSansTamil`](file:///home/rsm/src/amma-clock/server/fonts/NotoSansTamil-Bold.ttf)), icons, and Moon phase graphics are pre-rendered into a 400×300 1-bit monochrome bitmap on the server.
   - The Moon phase is rendered with **1-bit checkerboard dithering** for realistic e-ink shading.
   - Bitmaps are 15,000 bytes ($400 \times 300 / 8$), matching Waveshare's native display buffer format.
2. **ESP32 Client**:
   - Holds 4 pre-rendered days in RAM (Today + next 3 days, ~60 KB total RAM).
   - Polls the server hourly for checksum changes. If today's image is updated, it refreshes the e-Paper immediately.
   - If the server cannot be reached continuously for $>24$ hours, an **"ERROR"** badge is rendered at the bottom-right corner.
3. **Web Administration Dashboard**:
   - `/home`: Shows the calendar date navigator, live 400×300 display preview, and an editable two-column metadata table (Date, Lunar Month, Tithi, Paksha, Nakshatra, Tamil Month, Tamil Date, and Custom Text for greetings/birthdays).
   - `/config`: In-browser YAML editor to fine-tune layout coordinates (X, Y), font sizes, dividers, and icon positions.

---

## Documentation

- [API Specification](file:///home/rsm/src/amma-clock/docs/API_specs.md)
- [Database Schema](file:///home/rsm/src/amma-clock/docs/DB_Schema.md)
- [PRD Specification](file:///home/rsm/src/amma-clock/docs/prd_calendar.md)

---

## 1. Quick Start - Server Setup (Docker)

### Start the Server
```bash
docker compose up -d
```
The server will be reachable at `http://<server-ip>:8080` (e.g. `http://192.168.29.31:8080`).

### Check Logs & Status
```bash
docker compose logs -f
```

### Stop the Server
```bash
docker compose down
```

---

## 2. Managing Admin Users (CLI)

The database is initialized automatically with a default admin user:
- **Username**: `admin`
- **Password**: `admin123`

To create a new user or reset an existing password via CLI:
```bash
# Using python directly:
python3 server/manage_users.py create-user --username admin --password MySecretPassword

# Or inside the running Docker container:
docker exec -it amma_calendar_server python3 server/manage_users.py create-user --username admin --password MySecretPassword
```

---

## 3. Pre-Generating Images (Bulk / Cron Job)

To pre-generate images for the next 90 days:

### Running via CLI
```bash
# Generate 90 days starting from today:
python3 server/bulk_generate.py --days 90

# Force re-generation of existing images:
python3 server/bulk_generate.py --days 90 --force

# Re-fetch online panchanga (e.g. to refresh Shraddha Tithi) and update all existing DB records:
python3 server/bulk_generate.py --refetch-panchanga --all
```

### Setting Up a Nightly Cron Job
To automatically generate upcoming days and update panchanga data every night at 2:00 AM:

1. Open crontab:
   ```bash
   crontab -e
   ```
2. Add the following line:
   ```cron
   0 2 * * * cd /home/rsm/src/amma-clock && /usr/bin/python3 server/bulk_generate.py --days 90 >> /home/rsm/src/amma-clock/server/cron.log 2>&1
   ```

---

## 4. ESP32 Firmware Compilation & Upload

The ESP32 firmware is located in [`esp32/calendar/calendar.ino`](file:///home/rsm/src/amma-clock/esp32/calendar/calendar.ino).

### Pin Wiring (ESP32-C6 Super Mini to Waveshare 4.2" Display)
| Display Pin | Function | ESP32-C6 GPIO |
|---|---|---|
| **VCC** | 3.3V Power | 3V3 |
| **GND** | Ground | GND |
| **DIN** | SPI MOSI | GPIO 14 (or 5) |
| **CLK** | SPI SCK | GPIO 6 (or 7) |
| **CS** | Chip Select | GPIO 4 |
| **DC** | Data / Command | GPIO 3 |
| **RST** | Display Reset | GPIO 2 |
| **BUSY**| Busy Status | GPIO 1 |

### Compile Only
```bash
./esp32/run.sh
```

### Compile & Upload to ESP32
```bash
./esp32/run.sh --upload
```

### Compile, Upload & Open Serial Monitor
```bash
./esp32/run.sh --upload --monitor
```

---

## 5. Web Interface Walkthrough

1. Open `http://192.168.29.31:8080` in your web browser.
2. Sign in with your admin credentials.
3. **Dashboard (`/home`)**:
   - **Row 1, Column 1**: Date picker, navigation controls (Prev Day, Today, Next Day), and bulk generator button.
   - **Row 1, Column 2**: Real-time 400×300 pixel-accurate e-Paper display preview with MD5 checksum.
   - **Row 2**: Metadata table. You can edit any field (e.g. adjust Tithi, Nakshatra, Tamil date, or enter a custom birthday message). Click **Generate & Save Bitmap** to instantly regenerate the image.
4. **Display Config (`/config`)**:
   - Edit [`server/config.yaml`](file:///home/rsm/src/amma-clock/server/config.yaml) in the web editor to micro-configure font sizes, line positions, dividers, and icon offsets. Click **Save Configuration** to apply.
