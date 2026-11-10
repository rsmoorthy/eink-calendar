# e-Ink Calendar

A daily calendar rendered on a Waveshare 4.2" e-ink display (400×300, black and
white) driven by an ESP32-C6.

All image construction happens on the server, using Python and PIL. The ESP32
only downloads finished images over HTTP and displays them, which keeps the
firmware small and lets the layout change without reflashing the device. The
device keeps four days of images in RAM, so the display keeps working through a
short network outage.

```
  [ browser ]  --admin-->  [ calendar server ]  <--HTTP poll--  [ ESP32-C6 ] --> [ e-ink panel ]
   /home, /config              Flask + SQLite
                                    |
                            vyasaraja matha panchanga
```

## Contents

| Path | Purpose |
| --- | --- |
| `server/` | Flask application, renderer, database, CLI |
| `server/config.default.yaml` | Shipped layout defaults |
| `esp32/calendar/` | Firmware sketch (flat layout: `.ino` plus its `.cpp`/`.h`) |
| `esp32/run` | Compile, upload and monitor helper |
| `Dockerfile` | Server container |
| `epd4in2_V2/`, `main/` | Original prototype, kept for reference |

## Quick start

```bash
# 1. Build and start the server
docker build -t eink-calendar .
docker run -d --name eink-calendar -p 8080:8080 -v eink-data:/data eink-calendar

# 2. Create the admin login (prompts for a password)
docker exec -it eink-calendar python3 manage.py create-admin admin

# 3. Load the Tamil month table
docker exec -it eink-calendar python3 manage.py seed-tamil-months

# 4. Generate the next 90 days
docker exec -it eink-calendar /app/refresh_cron.sh
```

Then open <http://localhost:8080/home> and sign in.

## Creating the admin user

The web interface has no self-registration: accounts are created from the
command line, so an exposed instance cannot be claimed by a stranger.

```bash
docker exec -it eink-calendar python3 manage.py create-admin <username>
```

You are prompted for a password (minimum 8 characters). Re-running the command
with the same username resets that user's password. To list or remove users:

```bash
docker exec -it eink-calendar python3 manage.py list-admins
docker exec -it eink-calendar python3 manage.py delete-admin <username>
```

## Scheduled image generation

Images should be rendered ahead of time so the ESP32 always finds one ready and
a temporary failure of the panchanga source does not blank the display.

The script generates a configurable number of days ahead, defaulting to 90:

```bash
# On the host, pointing at the repo (adjust the path):
0 2 * * * /path/to/repo/server/refresh_cron.sh >> /var/log/eink-calendar.log 2>&1
```

Install it with `crontab -e`. A `docker exec` line works just as well:

```bash
0 2 * * * docker exec eink-calendar /app/refresh_cron.sh >> /var/log/eink-calendar.log 2>&1
```

Set `DAYS=30` to change the horizon, either in the crontab line or in the
environment. Note that each run makes one scrape request per day, so a 90-day
horizon is about 90 requests per day.

## The web interface

- **`/home`** — a month calendar. Selecting a date shows that day's image beside
  it, with the editable fields below (Masa, Paksha, Tithi, Nakshatra, Festival,
  Next Ekadashi, Tamil month, Tamil date, and Custom text). Saving re-renders the
  image.
  - **Generate image** renders a day that has no image yet.
  - **Re-fetch panchanga** re-scrapes that day.
  - **Refresh whole month** re-scrapes every day in the displayed month.
- **`/upload`** — the image library: upload, preview (thumbnail), see each file's
  real pixel resolution, and delete. The weekday defaults (`sun.png` … `sat.png`
  and `special.png`) cannot be deleted because the layout falls back to them by
  name, but they can be replaced by uploading a file with the same name.

  Uploads are written to `/data/assets/day` inside the container (set by
  `EINK_ASSETS_DIR`), not to the copy of `server/assets` baked into the image.
  Only `/data` is a volume, so storing them anywhere else would lose every
  upload the moment the container is recreated. The shipped placeholder icons
  are copied into that directory on first start, and an existing file is never
  overwritten by the seeding.
- **`/config`** — the layout YAML: positions, font sizes, dividers, and image
  placement.
- **`/tamil-months`** — the manual Tamil month start dates.

The day image and the additional image are chosen per day in the Contents
section of `/home`, where both fields offer the uploaded file names as
suggestions. Leaving **Day Image** blank uses the weekday default
(`mon.png`, `tue.png`, …); leaving **Addl image** blank draws nothing.

On screens narrower than 820px the calendar and image stack vertically.

### Custom text and festivals

The last line of the image shows the day's **Custom text**, and when that is
empty it falls back to the day's **Festival** scraped from the source. A day with
a festival and no custom text is therefore labelled with the festival
automatically, and your own custom text overrides it for that day.

The two stay separate in the database: the festival is not copied into Custom
text, so clearing your custom text brings the festival back rather than losing
it.

Festival strings are long — the current 90-day window reaches 55 characters, for
example `SHRIKAMBALURU RAMACHANDRATIRTHARA ARADHANE (RAYAVELURU)` — so line 4
wraps them and steps the font size down until the block fits. On the longest
names it settles at 14px over two lines.

`python3 check_layout.py` measures that wrapped block rather than the raw string,
so it reports the space line 4 really uses.

### Next Ekadashi

Each day carries a **Next Ekadashi** field, shown under Contents on `/home` and
drawn on the image by the `line3.next_ekadashi` element. Its text is
`N.Eka: <Mon> <date>` naming the Gregorian date of the next Ekadashi, for example
`N.Eka: Oct 21`, and `N.Eka: —` when no Ekadashi is known ahead of the day. On a
day that is itself an Ekadashi it names the following one, so it always tells you
something the Tithi line does not.

Whether a day is an Ekadashi is decided solely by its **Festivals/Events** text:
the day counts when that text contains the letters `EKADASHI` anywhere,
case-insensitively (so `SARVESHAMEKADASHI(PASHANKUSHA)` counts). The tithi is not
consulted.

This field describes a day in terms of a later one, so it cannot be filled in the
same pass that scrapes the day: the date it names is only known once that later
day has been scraped. Generation therefore runs in two passes —

1. **Scrape** every day in the range, storing each day's own panchanga.
2. **Derive** the fields that depend on the range: for each day, look ahead at
   most 16 days for the first stored day whose festival names an Ekadashi and
   write the annotation.

`manage.py refresh`, `manage.py generate` and **Refresh whole month** on `/home`
all run both passes. `manage.py refresh-derived` runs only the second, which is
what to use after extending the stored range. The horizon is 16 days because
consecutive Ekadashis are never more than 15 days apart, so a 90-day run leaves
only the days after the last Ekadashi in the range showing the dash. A later run
that covers the following fortnight fills those in.

The element ships switched off (`x: -1, y: -1` in `config.default.yaml`), so it
does not appear on the image until you give it a position on `/config`.

### Manually edited fields are preserved

When you change a field by hand it is recorded as an override for that date. The
daily refresh job will not overwrite it, so a correction you make (for example
setting a festival name) survives later scraping. Clear an override by editing
the field to match the scraped value.

## Configuration

`server/config.default.yaml` holds the defaults and is the reference for what
each setting does. The `/config` page edits a separate copy at `/data/config.yaml`
inside the container, so the defaults are never lost; **Reset to defaults**
deletes that copy.

The page is a plain YAML editor: delete a key, or comment it out with `#`, and it
stays deleted. Your text is saved verbatim, so comments and key order survive
between edits.

An edit made directly to `/data/config.yaml` — or deleting it to reset — takes
effect without a restart. That copy is combined with the defaults **one section
at a time**: a top-level section you define replaces that whole section, and a
section you leave out comes from the defaults. So removing `height` from
`line1.day_image` removes it for good, while a document that only mentions
`line1` still gets the shipped `line2`, `line3` and `fonts`.

Coordinates are pixels on the 400×300 canvas with the origin at the top-left.

### Fonts

`fonts` maps a name of your choosing to a font file. Every text element selects a
face with its own `font` key, and an element with no `font` key uses `latin`:

```yaml
fonts:
  latin: fonts/NotoSans-Regular.ttf
  latin_bold: fonts/NotoSans-Bold.ttf
  tamil: fonts/NotoSansTamil-Regular.ttf

line3:
  tithi:
    font: latin_bold
```

Paths resolve relative to `server/` unless they are absolute. A name with no
entry, or an entry whose file is missing, stops the render with an error rather
than falling back to another face, so a typo cannot quietly draw the wrong font.

Tamil is not detected from the text: an element holding Tamil has to name a Tamil
face (`font: tamil`, as the shipped `tamil_month` and `tamil_date` do). Without
one the glyphs render as boxes — the font is never chosen for you.

The faces themselves are downloaded by `server/fetch_fonts.py` into
`server/fonts/` — automatically during the image build, or by hand for a source
checkout. They are not committed, which keeps the repository small.

#### Adding a font

1. Put the `.ttf` in `server/fonts/`.
2. Add a name for it to the `fonts` block of `server/config.default.yaml` (for
   the running instance, edit `/config` instead — it writes to `/data/config.yaml`).
3. Set `font: <name>` on the elements that should use it.
4. Rebuild and recreate the container so the file is baked into the image:

   ```bash
   docker build -t eink-calendar .
   docker rm -f eink-calendar
   docker run -d --name eink-calendar -p 8080:8080 -v eink-data:/data eink-calendar
   ```

   Recreating the container keeps `/data`, so the database, the live config and
   the uploaded images all survive. Only the image contents change.

5. Run `python3 check_layout.py` from `server/` (or
   `docker exec -w /app eink-calendar python3 check_layout.py`) if the new face is
   wider than the one it replaces. A heavier or wider face changes how much room
   each string needs, and the script reports anything that would collide or leave
   the canvas. For example, `latin_bold` is registered but no default element uses
   it: applying it to the 18–22px body text collides with the moon and nakshatra
   elements. It is safe on short, large fields such as `line1.weekday`.

Without Docker, the same thing is a file copy into `server/fonts/` plus the two
config edits; `python3 fetch_fonts.py` will not download a font you supply
yourself, so nothing overwrites it.

### Hiding parts of the layout

Any element can be switched off without deleting the rest of its settings, by
setting `font_size: 0`, or setting its `x` or `y` to `-1`. This applies to the
text fields, the moon, the images and the scrape-failure marker.

### Dividers

`dividers` is a list, so any number of horizontal rules can be drawn. Each entry
takes a `y` position, an optional `thickness`, and optional `x_start`/`x_end` to
limit how far the line runs. A divider with `y: -1` is skipped, so entries can be
parked in the config without deleting them.

```yaml
dividers:
  - y: 140
    thickness: 1
  - y: -1          # parked, not drawn
```

### Image sizing

Both `line1.day_image` and `addl_image` take `x`, `y`, `width` and `height`. Give
both sides to force an exact size, or give only one and the other is derived from
the source file's own aspect ratio (a 200×50 logo drawn at `width: 64` becomes
64×16). A side that is absent, `0` or `-1` means "derive this one", so a value
can be parked or commented out instead of deleted. Leaving out both sides draws
the file at its own pixel size, which for the placeholder icons overflows the
canvas — give at least one.

## REST API

Used by the ESP32. All responses are JSON except the image itself.

| Endpoint | Description |
| --- | --- |
| `GET /date` | Current date in IST, its epoch, and the 4 dates in the window |
| `GET /calendar` | Manifest of today + 3 days: `date`, `checksum`, `has_bitmap` |
| `GET /calendar/<date>` | The raw 400×300 1-bit bitmap, 15000 bytes |
| `GET /calendar/<date>/meta` | The content fields for a date |
| `GET /healthz` | Liveness probe |

The bitmap is `application/octet-stream`, MSB-first with a set bit meaning
white, which is what the display driver expects. Responses carry an
`X-Checksum` header. Send it back as `If-None-Match` (or as a `?checksum=`
query parameter) and the server answers `304 Not Modified` when the image has
not changed, which is the common case and avoids transferring 15 KB per poll.

A date with no rendered image reports `checksum: null`; fetching that date
renders it on demand.

## The device

Network settings are compiled into `esp32/calendar/config.h`:

```c
#define WIFI_SSID "Advaita"
#define WIFI_PASSWORD "NonduaLity"
#define SERVER_HOST "192.168.29.31"
#define SERVER_PORT 8080
```

Changing them requires a reflash, by design — the device has no configuration UI.

`POLL_INTERVAL_MS` defaults to **2 minutes** during development so an admin edit
appears on the display quickly. Polling is cheap: in the common case it is a few
hundred bytes of JSON, and the e-ink panel is only redrawn when a checksum
actually changes. That matters because a full refresh visibly blinks the panel.
Raise it to an hour or more for long-term use.

The device keeps its own clock once it has synced, and checks the local date on
every loop, so the displayed day turns over at IST midnight rather than at
whenever it last talked to the server. Re-syncing with the server is drift
correction only.

An **ERROR** badge appears in the bottom-right corner in two situations, both
governed by constants in `config.h`:

- **The server has been unreachable for a while** (`SERVER_ERROR_AFTER_MS`,
  default 24 h). The cached day stays on screen with the badge over it, so the
  calendar keeps working through an outage.
- **The device rebooted and cannot reach the server** (`BOOT_ERROR_AFTER_MS`,
  default 90 s). A reboot empties the RAM image cache, so there is no image to
  draw; without this the panel would sit blank white, which looks identical to
  broken hardware. The badge is drawn on its own so the fault is stated.

Once the server answers again the badge is cleared and the day is drawn.

### Refresh strategy

The 4.2" V2 controller does not tolerate repeated full `Init()`/`Display()`
sequences back to back: the second refresh can hang the panel. The
vendor-supported way to update it repeatedly is the fast path, so the firmware
uses `Init_Fast()` + `Display_Fast()` for normal updates.

Fast refresh does not fully clear the panel, so old ink lingers. Every
`FULL_REFRESH_EVERY` refreshes (default 10) it performs one full
`Init()`/`Display()` pass to clear it. The first refresh after boot is always
full, so the panel starts from a clean state. Both are configurable in
`config.h`.

### Diagnostics

Two scripts help when the device misbehaves. Both reset the board using the
correct USB-Serial/JTAG sequence and survive the USB re-enumeration that
follows, which a plain `minicom` session does not.

```bash
python3 tools/serial_monitor.py 60      # reset and capture 60s with timestamps
python3 tools/watch_serial.py 120       # keep reading; reports reboots
```

The firmware prints a timestamped status line every 30 seconds (and immediately
whenever its state changes), so **silence in the log means the device is stuck**,
not merely idle. It also prints a stage marker at each step of start-up
(`stage=1 alloc` through `stage=6 polling`), which pinpoints where a failure
occurred:

```
[    4354] drawing today's image
[    6435]   refresh: done in 1873 ms
[    6872] alive up=6s wifi=3(192.168.29.136) date=20711 cached=4/4 today=ready heap=262044
```

`Serial` runs over the native USB peripheral (`CDCOnBoot=cdc`), so a reset
briefly disconnects the port. A serial monitor that opens the port once can
therefore read nothing at all; the scripts above handle that.

### Bring-up test

`esp32/bringup/` is a standalone sketch that draws two test frames (including
Tamil text) five seconds apart, with **no WiFi and no server**. Use it to prove
the panel, wiring and SPI independently of the network:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc esp32/bringup
arduino-cli upload  -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc esp32/bringup
```

Frame 1 shows `TEST 1` with a solid black box; frame 2 shows `TEST 2` with an
outlined box and Tamil text. If both alternate on the panel, the display side is
healthy and any remaining problem is in the network path.

### Building and uploading

```bash
./esp32/run              # compile, upload, then open the serial monitor
./esp32/run compile      # compile only
./esp32/run upload       # upload only
./esp32/run monitor      # serial monitor only

PORT=/dev/ttyUSB0 ./esp32/run   # non-default port
```

Requirements: `arduino-cli` with the `esp32` core (3.0.x) and the `ArduinoJson`
library. The target board is `esp32:esp32:esp32c6:CDCOnBoot=cdc`.

The sketch uses a flat layout: `calendar.ino` and all of its `.cpp`/`.h` files
live together in `esp32/calendar/`. `arduino-cli` does not search a sibling
folder for libraries, so the driver files are compiled as part of the sketch
rather than kept in a separate `lib/` directory.

### Pins

From `esp32/calendar/epdif.h`, matching the prototype wiring (see
[`docs/pinouts.md`](docs/pinouts.md) for the board diagram and notes):

| Display | ESP32-C6 |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| DIN | GPIO 14 |
| CLK | GPIO 6 |
| CS | GPIO 4 |
| DC | GPIO 3 |
| RST | GPIO 2 |
| BUSY | GPIO 1 |

## Data sources and known limits

- **Panchanga** is scraped from the Vyasaraja Matha panchanga endpoint. Their
  reckoning is treated as authoritative because panchangas differ slightly
  between sources.
- **Tithi** is taken from the **Shraddha Tithi** element, which governs the day's
  observances. Two cases fall back to the plain **Tithi** element instead,
  because the Shraddha Tithi does not name a single tithi: **SHRADDHABHAVA** (a
  shraddha observance, not a tithi) and a compound such as **EKADASHI/DVADASHI**
  (the tithi changes during the day, so Tithi carries the day's name). The page
  records which element was used, under *Panchanga source* on `/home`.
- **Festivals/Events** is stored in its own `Festival` column. When a day has no
  **Custom text**, the festival is drawn as the image's last line instead (see
  *Contents* below).
- **Next Ekadashi** is derived from the festivals already stored, not from the
  day's own scrape, so it is filled by a second pass and the days past the last
  Ekadashi in a range show a dash until a later run covers them.
- **When scraping fails**, the affected values are shown as em dashes and a
  small "no panchanga" marker is drawn, so a failed fetch is distinguishable
  from genuinely empty data. Nothing is computed as a fallback.
- **Tamil months** are a maintained table, not a calculation: Tamil months begin
  at solar ingress, which drifts by a day or two year to year. Edit `/tamil-months`
  to extend the table. The table currently ends in April 2028; dates beyond it
  render a dash. **Extend it before then.**
- **Icons** under `server/assets/day/` are placeholders. Replace them with real
  64×64 PNGs of the same names (`mon.png` … `sun.png`, plus `special.png` for
  days with custom text) — no code change is needed. A missing icon is skipped
  rather than failing the render.

## Development without Docker

```bash
python3 -m venv .venv
.venv/bin/pip install pillow flask requests beautifulsoup4 pyyaml

# Pillow must have Raqm, or Tamil renders malformed without any error.
# On Debian/Ubuntu: apt-get install libraqm0
.venv/bin/python -c "from PIL import features; print(features.check('raqm'))"

cd server
python3 fetch_fonts.py
python3 manage.py create-admin admin
python3 manage.py seed-tamil-months
python3 manage.py generate --days 4
PORT=8080 python3 app.py
```

`manage.py status` prints a summary of stored state, which is the quickest way
to see whether generation is healthy.

After editing the layout, check it for overlaps before regenerating. The script
measures the longest values the panchanga source actually produces and reports
anything that would collide or run off the canvas:

```bash
python3 check_layout.py
```

It exits non-zero on a problem, so it is safe to use as a commit gate.

## Layout

The image follows the PRD:

- **Line 1** — day number (largest), month, weekday, and a 64×64 day icon
- **Line 2** — tithi name and a moon-phase disc, plus the paksha
- **Line 3** — Masa, tithi, nakshatra, and Tamil month with Tamil date
- **Line 4** — custom text entered in the web interface

The moon is dithered since the panel is strictly 1-bit: solid black is new moon,
a white disc with a gray ring is full moon, and a partly-filled disc shows the
waxing or waning phase.

### How text is rasterised

Text is not drawn straight onto the 1-bit canvas. PIL rasterises directly to
1-bit without anti-aliasing, and at the 18–22px body sizes the thin strokes of
the default faces come out broken. Instead all text goes onto a full-canvas
greyscale layer, which is thresholded once at the end (`TEXT_THRESHOLD`, 170 in
`renderer.py`) and pasted through the resulting mask. Lowering the threshold
thickens every glyph; raising it erodes thin strokes until they break up. The
images and dividers are still drawn directly, since they are already strictly
black or white.
