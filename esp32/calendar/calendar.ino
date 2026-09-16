/**
 * e-Ink calendar display firmware.
 *
 * The ESP32 keeps a rolling window of pre-rendered day images in RAM and shows
 * today's. All image construction happens on the server; this device only
 * downloads and displays, which keeps it small and lets the layout change
 * without reflashing.
 *
 * Behaviour:
 *   - joins WiFi, reconnecting if the connection drops
 *   - syncs the clock from the server at boot, then follows the local date, so
 *     the displayed day changes at local midnight rather than at the next sync
 *   - polls the server for changed images; downloads only what changed
 *   - keeps DAY_SLOTS days in RAM so the display survives an outage
 *   - shows an "ERROR" badge once the server has been unreachable for a day;
 *     after a reboot, which empties that cache, it shows ERROR on its own if the
 *     server cannot be reached soon after starting
 *
 * A full refresh is always used. Partial refresh is not safe here: the
 * controller's previous-image plane is not reloaded between days, so a partial
 * update would XOR the new image against yesterday's content.
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <WiFi.h>
#include <time.h>

#include <ArduinoJson.h>
#include <esp_task_wdt.h>

#include "config.h"
#include "epd4in2_V2.h"
#include "epdif.h"
#include "error_badge.h"

// 400x300 monochrome, one bit per pixel, MSB first. 15000 bytes.
#define IMAGE_STRIDE (EPD_WIDTH / 8)
#define IMAGE_BYTES (IMAGE_STRIDE * EPD_HEIGHT)

// Print with CR+LF and a timestamp. The prototype's bare "\n" output looked
// truncated in every serial monitor and made a running device look hung.
#define LOGF(...)                          \
  do {                                     \
    Serial.printf("[%8lu] ", millis());    \
    Serial.printf(__VA_ARGS__);            \
    Serial.print("\r\n");                 \
  } while (0)

/// One cached day: its date string plus the rendered bitmap.
struct DaySlot {
  char date[11];  // "YYYY-MM-DD" plus terminator
  char checksum[33];
  bool valid;
  bool hasChecksum;
  uint8_t *bitmap;
};

static DaySlot slots[DAY_SLOTS];
static Epd epd;

// Date tracking. Kept as days since epoch so comparisons are simple arithmetic
// rather than parsing on every loop.
static long currentDayNumber = -1;
static time_t lastDateSync = 0;
static time_t lastSuccessfulContact = 0;
static bool wdtArmed = true;

static void feedWatchdog();
static void displayBuffer(const uint8_t *bitmap);

// --------------------------------------------------------------------- helpers

/// Days since 1970-01-01 for a civil date, so dates compare with plain < and ==.
/// Algorithm from Howard Hinnant's days_from_civil.
static long daysFromCivil(int year, unsigned month, unsigned day) {
  year -= month <= 2;
  const long era = (year >= 0 ? year : year - 399) / 400;
  const unsigned yoe = (unsigned)(year - era * 400);
  const unsigned doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097L + (long)doe - 719468L;
}

/// Inverse of daysFromCivil, used to build a "YYYY-MM-DD" string.
static void civilFromDays(long days, int *year, unsigned *month, unsigned *day) {
  long z = days + 719468L;
  const long era = (z >= 0 ? z : z - 146096) / 146097L;
  const unsigned doe = (unsigned)(z - era * 146097L);
  const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const long y = (long)yoe + era * 400;
  const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const unsigned mp = (5 * doy + 2) / 153;
  *day = doy - (153 * mp + 2) / 5 + 1;
  *month = mp + (mp < 10 ? 3 : -9);
  *year = (int)(y + (*month <= 2));
}

static void formatDate(long dayNumber, char *out) {
  int year;
  unsigned month, day;
  civilFromDays(dayNumber, &year, &month, &day);
  snprintf(out, 11, "%04d-%02d-%02d", year, month, day);
}

/// Parse "YYYY-MM-DD" into a day number. Returns -1 on malformed input.
static long parseDate(const char *text) {
  int year, month, day;
  if (sscanf(text, "%4d-%2d-%2d", &year, &month, &day) != 3) {
    return -1;
  }
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    return -1;
  }
  return daysFromCivil(year, (unsigned)month, (unsigned)day);
}

/// Index of a day number within the window, or -1 when outside it.
static int slotForDay(long dayNumber) {
  if (currentDayNumber < 0) {
    return -1;
  }
  long offset = dayNumber - currentDayNumber;
  if (offset < 0 || offset >= DAY_SLOTS) {
    return -1;
  }
  return (int)offset;
}

static DaySlot *slotForDate(const char *date) {
  long number = parseDate(date);
  if (number < 0) {
    return nullptr;
  }
  int index = slotForDay(number);
  return index < 0 ? nullptr : &slots[index];
}

/// The local (IST) calendar day an epoch falls on, as a day number.
///
/// Split out from localDayNumber() so it can be exercised with any instant on a
/// host, where the system clock cannot be set.
static long dayNumberForEpoch(time_t epoch) {
  time_t local = epoch + IST_OFFSET_SECONDS;
  struct tm parts;
  gmtime_r(&local, &parts);
  return daysFromCivil(parts.tm_year + 1900, (unsigned)parts.tm_mon + 1,
                       (unsigned)parts.tm_mday);
}

/// Today's day number according to the local clock, or -1 when the clock has
/// never been set.
///
/// The clock is set from the server's epoch at boot, so it advances on its own.
/// Deriving the date from it makes the window roll over at midnight instead of
/// whenever the next date sync happens to fall. With the sync on a 24h timer the
/// lag after midnight was up to a full day, and the display sat on yesterday's
/// image for all of it.
static long localDayNumber() {
  time_t now = time(nullptr);
  // No battery-backed clock: before the first sync this reads 1970.
  if (now < 1600000000L) {
    return -1;
  }
  return dayNumberForEpoch(now);
}

/// Slide the cached window so it starts at ``newDayNumber``.
///
/// The entries are moved rather than discarded. A rollover normally shifts the
/// window by one day, so three of the four images are still days we want and only
/// the new one needs downloading. Invalidating every slot instead threw away the
/// whole cache, leaving the display with nothing to show until all four images
/// had been fetched again.
static void shiftWindow(long newDayNumber) {
  long delta = newDayNumber - currentDayNumber;

  if (delta <= 0 || delta >= DAY_SLOTS) {
    // A jump that cannot be lined up: a cold boot, a large clock correction, or
    // a clock that moved backwards. Start over rather than pair an image with
    // the wrong date. Buffers are kept for reuse.
    for (int i = 0; i < DAY_SLOTS; i++) {
      slots[i].valid = false;
      slots[i].hasChecksum = false;
      slots[i].date[0] = '\0';
    }
    return;
  }

  // Each slot owns a fixed buffer, and moving a slot wholesale would copy its
  // bitmap pointer too, leaving two slots pointing at one buffer. Rotate the
  // buffers alongside the day data so the pairings stay one-to-one.
  uint8_t *rotated[DAY_SLOTS];
  for (int i = 0; i < DAY_SLOTS; i++) {
    rotated[i] = slots[(i + delta) % DAY_SLOTS].bitmap;
  }

  for (int i = 0; i + delta < DAY_SLOTS; i++) {
    slots[i] = slots[i + delta];
  }
  for (int i = DAY_SLOTS - delta; i < DAY_SLOTS; i++) {
    slots[i].valid = false;
    slots[i].hasChecksum = false;
    slots[i].date[0] = '\0';
  }
  for (int i = 0; i < DAY_SLOTS; i++) {
    slots[i].bitmap = rotated[i];
  }
}

/// Make ``dayNumber`` the day the window starts at, sliding the cache when it
/// changes. Returns true when the day actually changed.
static bool applyDayNumber(long dayNumber) {
  if (dayNumber < 0 || dayNumber == currentDayNumber) {
    return false;
  }

  if (currentDayNumber >= 0) {
    shiftWindow(dayNumber);
  }
  currentDayNumber = dayNumber;

  char formatted[11];
  formatDate(dayNumber, formatted);
  LOGF("date is now %s (day number %ld)", formatted, dayNumber);
  return true;
}

/// GET a URL into a String. Returns the HTTP status, or a negative value when
/// the request could not be completed at all.
static int httpGet(const String &url, String *body) {
  HTTPClient http;
  http.setTimeout(20000);
  if (!http.begin(url)) {
    return -1;
  }
  int status = http.GET();
  if (status > 0 && body != nullptr) {
    *body = http.getString();
  }
  http.end();
  return status;
}

/// GET a URL into a caller-supplied buffer. Returns the HTTP status, or a
/// negative value on transport failure.
static int httpGetBinary(const String &url, uint8_t *buffer, size_t capacity) {
  HTTPClient http;
  http.setTimeout(30000);
  if (!http.begin(url)) {
    return -1;
  }
  int status = http.GET();
  if (status == 200) {
    WiFiClient *stream = http.getStreamPtr();
    size_t read = 0;
    unsigned long deadline = millis() + 30000;
    while (read < capacity && millis() < deadline) {
      feedWatchdog();
      size_t available = stream->available();
      if (available > 0) {
        int got = stream->readBytes(buffer + read, min(available, capacity - read));
        if (got <= 0) {
          break;
        }
        read += (size_t)got;
      } else if (!http.connected()) {
        break;
      } else {
        delay(10);
      }
    }
    http.end();
    if (read != capacity) {
      LOGF("image read %u of %u bytes (truncated)", (unsigned)read, (unsigned)capacity);
      // A short read means a truncated image; treat it as a failure so we never
      // display a half-written frame.
      return -2;
    }
    return 200;
  }
  http.end();
  return status;
}

// ----------------------------------------------------------------------- WiFi

static void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  LOGF("connecting to WiFi \"%s\"...", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  // Bounded wait: the main loop keeps running so the panel retains its content
  // and the error badge can appear on schedule.
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");  // progress dots, no newline
    if (wdtArmed) {
      esp_task_wdt_reset();  // WiFi association can outlast the WDT period
    }
  }
  Serial.print("\r\n");
  if (WiFi.status() == WL_CONNECTED) {
    LOGF("WiFi connected, IP %s, RSSI %d dBm, channel %d",
         WiFi.localIP().toString().c_str(), WiFi.RSSI(), WiFi.channel());
  } else {
    LOGF("WiFi FAILED after %lu ms (status=%d). Will retry.",
         millis() - start, (int)WiFi.status());
  }
}

// ------------------------------------------------------------------ date sync

/// Ask the server for today's date. Returns true when the date is known.
static bool syncDate() {
  String body;
  int status = httpGet(String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/date", &body);
  if (status != 200) {
    LOGF("date sync FAILED: GET /date -> %d", status);
    return false;
  }

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, body);
  if (error) {
    LOGF("date sync FAILED: bad JSON (%s)", error.c_str());
    return false;
  }

  // Prefer the server's epoch over the local clock: the ESP has no RTC and
  // would otherwise drift or boot at 1970.
  long epoch = doc["epoch"] | 0L;
  const char *date = doc["date"] | (const char *)nullptr;

  long dayNumber = -1;
  if (epoch > 0) {
    // Set the clock; the day is then derived from it, so it keeps advancing
    // between syncs and the window rolls over at local midnight. Deriving the
    // day from the epoch we were just given also keeps the date authoritative
    // even if settimeofday() is refused.
    struct timeval tv = {(time_t)epoch, 0};
    settimeofday(&tv, nullptr);
    dayNumber = dayNumberForEpoch((time_t)epoch);
  } else if (date != nullptr) {
    dayNumber = parseDate(date);
  }

  if (dayNumber < 0) {
    LOGF("date sync FAILED: no usable date in response");
    return false;
  }
  LOGF("date sync ok (server said %s)", date != nullptr ? date : "?");

  applyDayNumber(dayNumber);
  lastDateSync = time(nullptr);
  return true;
}

// ------------------------------------------------------------- image download

/// Fetch the checksum manifest and record which cached days changed.
/// Returns true when the manifest was retrieved.
static bool refreshManifest() {
  String body;
  int status = httpGet(String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/calendar", &body);
  if (status != 200) {
    LOGF("manifest FAILED: GET /calendar -> %d", status);
    return false;
  }

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, body);
  if (error) {
    LOGF("manifest FAILED: bad JSON (%s)", error.c_str());
    return false;
  }

  JsonArray days = doc["days"].as<JsonArray>();
  LOGF("manifest: %u day(s) listed", (unsigned)days.size());
  for (JsonObject entry : days) {
    const char *date = entry["date"] | "";
    const char *checksum = entry["checksum"] | (const char *)nullptr;

    DaySlot *slot = slotForDate(date);
    if (slot == nullptr) {
      continue;
    }

    bool matches = checksum != nullptr && slot->hasChecksum &&
                   strncmp(slot->checksum, checksum, sizeof(slot->checksum)) == 0;
    if (matches && slot->valid) {
      continue;
    }

    // Only fetch when the server actually has an image. A null checksum means
    // the server has not rendered that day yet.
    if (checksum == nullptr) {
      LOGF("%s: server has no image yet (checksum null)", date);
      continue;
    }

    LOGF("%s: checksum changed -> downloading", date);
    String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/calendar/" + date;
    int imageStatus = httpGetBinary(url, slot->bitmap, IMAGE_BYTES);
    if (imageStatus != 200) {
      LOGF("%s: download FAILED (status %d)", date, imageStatus);
      continue;
    }

    strncpy(slot->date, date, sizeof(slot->date) - 1);
    slot->date[sizeof(slot->date) - 1] = '\0';
    strncpy(slot->checksum, checksum, sizeof(slot->checksum) - 1);
    slot->checksum[sizeof(slot->checksum) - 1] = '\0';
    slot->hasChecksum = true;
    slot->valid = true;
    LOGF("%s: cached ok (checksum %s)", date, slot->checksum);
  }
  return true;
}

/// Invalidate slots that no longer fall inside the current window so their
/// memory is not mistaken for a valid day after midnight.
static void expireStaleSlots() {
  for (int i = 0; i < DAY_SLOTS; i++) {
    if (!slots[i].valid) {
      continue;
    }
    long number = parseDate(slots[i].date);
    if (number < 0 || slotForDay(number) != i) {
      LOGF("expired cached day %s (left the window)", slots[i].date);
      slots[i].valid = false;
      slots[i].hasChecksum = false;
      slots[i].date[0] = '\0';
    }
  }
}

// -------------------------------------------------------------------- display

/// Number of refreshes performed since boot, used to schedule periodic full
/// clears. Fast refresh leaves residual ink, so a full refresh is interleaved.
static unsigned int refreshCount = 0;

static void displaySlot(const DaySlot *slot) {
  LOGF("  refresh: free heap %u bytes", (unsigned)ESP.getFreeHeap());

  // Full refresh every FULL_REFRESH_EVERY frames to clear accumulated ghosting.
  // refreshCount starts at 0, so the first refresh after boot is always full,
  // which also gives a clean starting state.
  bool full = (refreshCount % FULL_REFRESH_EVERY) == 0;

  unsigned long t0 = millis();
  if (full) {
    LOGF("  refresh: full (Init + Display), frame %u", refreshCount);
    epd.Init();
    feedWatchdog();
    epd.Display(slot->bitmap);
  } else {
    LOGF("  refresh: fast (Init_Fast + Display_Fast), frame %u", refreshCount);
    epd.Init_Fast(FAST_REFRESH_MODE);
    feedWatchdog();
    epd.Display_Fast(slot->bitmap);
  }
  refreshCount++;
  LOGF("  refresh: done in %lu ms", millis() - t0);
}

/// Draw a frame with the ERROR badge overlaid in the bottom-right corner.
///
/// ``bitmap`` may be null, in which case the badge is stamped on a blank white
/// panel. That is the cold-boot case: the device has no cached image to put
/// behind the badge, and a panel that is merely blank looks the same as dead
/// hardware, so the fault has to be stated explicitly.
static void displayWithErrorBitmap(const uint8_t *bitmap) {
  static uint8_t scratch[IMAGE_BYTES];
  LOGF("  display(error): free heap %u bytes before", (unsigned)ESP.getFreeHeap());
  if (bitmap != nullptr) {
    memcpy(scratch, bitmap, IMAGE_BYTES);
  } else {
    memset(scratch, 0xFF, IMAGE_BYTES);
  }

  const int badgeX = EPD_WIDTH - ERROR_BADGE_W - 2;
  const int badgeY = EPD_HEIGHT - ERROR_BADGE_H - 2;

  for (int row = 0; row < ERROR_BADGE_H; row++) {
    int y = badgeY + row;
    if (y < 0 || y >= EPD_HEIGHT) {
      continue;
    }
    for (int col = 0; col < ERROR_BADGE_W; col++) {
      int x = badgeX + col;
      if (x < 0 || x >= EPD_WIDTH) {
        continue;
      }
      uint8_t source = ERROR_BADGE[row * ERROR_BADGE_STRIDE + (col >> 3)];
      bool white = (source >> (7 - (col & 7))) & 0x01;

      // White background behind the text, black glyph pixels on top, so the
      // badge stays legible over whatever the server drew there.
      size_t index = (size_t)y * IMAGE_STRIDE + (x >> 3);
      uint8_t mask = (uint8_t)(0x80 >> (x & 7));
      if (white) {
        scratch[index] |= mask;
      } else {
        scratch[index] &= (uint8_t)~mask;
      }
    }
  }

  displayBuffer(scratch);
}

/// Draw ERROR over a cached day, or on a blank panel when there is none.
static void displayWithError(const DaySlot *slot) {
  displayWithErrorBitmap((slot != nullptr && slot->valid) ? slot->bitmap : nullptr);
}

/// Refresh the panel from a buffer, choosing full or fast per the schedule.
static void displayBuffer(const uint8_t *bitmap) {
  bool full = (refreshCount % FULL_REFRESH_EVERY) == 0;
  if (full) {
    epd.Init();
    feedWatchdog();
    epd.Display(bitmap);
  } else {
    epd.Init_Fast(FAST_REFRESH_MODE);
    feedWatchdog();
    epd.Display_Fast(bitmap);
  }
  refreshCount++;
}

/// Render an all-white frame, used before the first image is available.
static void displayBlank() {
  static uint8_t blank[IMAGE_BYTES];
  memset(blank, 0xFF, sizeof(blank));
  // Always a full refresh: this is the first frame after reset, and the panel
  // must start from a clean state.
  epd.Init();
  epd.Display(blank);
  refreshCount++;
}

// ----------------------------------------------------------------------- setup

void setup() {
  // Print immediately. Any delay here means a firmware that is actually
  // running looks dead, because the host sees nothing for seconds.
  Serial.begin(SERIAL_BAUD);
  Serial.println();
  LOGF("e-Ink calendar starting (build %s %s)", __DATE__, __TIME__);

  // Verify the task watchdog is usable, not merely present.
  //
  // The Arduino core already initialises the TWDT and subscribes loopTask with
  // a 5 second timeout, so esp_task_wdt_init() fails with "TWDT already
  // initialized". Touching it at all without reconfiguring means any call that
  // blocks longer than 5 seconds - the WiFi association wait below allows 20 -
  // trips the watchdog and reboots the board mid-render. That produced a reset
  // loop where every third pass happened to reach the display.
  //
  // Reconfigure to a limit comfortably longer than the slowest blocking call,
  // and confirm it took effect.
  esp_task_wdt_config_t wdtConfig = {
      .timeout_ms = 60000,
      .idle_core_mask = 0,
      .trigger_panic = false,
  };
  esp_err_t wdtResult = esp_task_wdt_reconfigure(&wdtConfig);
  if (wdtResult == ESP_OK) {
    // Reconfiguring clears the subscription list, so the loop task has to be
    // added back; without this every esp_task_wdt_reset() fails with
    // "task not found" and the board is left unprotected.
    esp_err_t addResult = esp_task_wdt_add(NULL);
    wdtArmed = (addResult == ESP_OK);
    LOGF("watchdog: 60s limit, loopTask %s", wdtArmed ? "armed" : "NOT armed");
  } else {
    wdtArmed = false;
    LOGF("watchdog: reconfigure failed (%s); leaving core default alone",
         esp_err_to_name(wdtResult));
  }

  LOGF("boot: baseline shown, starting bring-up sequence");
  LOGF("stages: alloc=1 panel=2 wifi=3 date=4 manifest=5 polling=6");
  LOGF("allocating %d image slots (%u bytes each)", DAY_SLOTS, (unsigned)IMAGE_BYTES);

  for (int i = 0; i < DAY_SLOTS; i++) {
    slots[i].bitmap = (uint8_t *)malloc(IMAGE_BYTES);
    slots[i].valid = false;
    slots[i].hasChecksum = false;
    slots[i].date[0] = '\0';
    slots[i].checksum[0] = '\0';
    if (slots[i].bitmap == nullptr) {
      // The panel still works without cached images, so keep going rather than
      // spinning forever where nothing can be diagnosed.
      LOGF("ERROR slot %d allocation failed; continuing with fewer slots", i);
    }
  }
  LOGF("stage=1 alloc done, %d slots usable", countValidSlotsTotal());

  // SPI is initialised by the driver's IfInit() during epd.Init().
  pinMode(BUSY_PIN, INPUT_PULLUP);
  delay(10);
  LOGF("BUSY pin idle level = %d (0 = idle, 1 = busy)", digitalRead(BUSY_PIN));
  LOGF("stage=2 clearing panel...");
  unsigned long clearStart = millis();
  displayBlank();
  LOGF("stage=2 panel cleared in %lu ms", millis() - clearStart);

  LOGF("stage=3 server target http://%s:%d", SERVER_HOST, SERVER_PORT);
  connectWiFi();

  LOGF("stage=4 syncing date...");
  if (syncDate()) {
    lastSuccessfulContact = time(nullptr);
    LOGF("stage=5 fetching manifest...");
    refreshManifest();
  }
  LOGF("setup complete; entering poll loop");
}

// ------------------------------------------------------------------------ loop

void loop() {
  static time_t lastPoll = 0;
  time_t now = time(nullptr);

  connectWiFi();

  // Follow the local date on every pass. The clock is set from the server at
  // boot, so this is what makes the window turn over at midnight rather than at
  // whatever hour the last sync happened to fall on.
  applyDayNumber(localDayNumber());

  // Correct the clock against the server on schedule. The date follows the local
  // clock between syncs, so this is drift correction, not what flips the day.
  if (lastDateSync == 0 ||
      now - lastDateSync >= (time_t)(DATE_RESYNC_INTERVAL_MS / 1000UL)) {
    syncDate();
  }

  expireStaleSlots();

  int todayIndex = slotForDay(currentDayNumber);
  DaySlot *today = (todayIndex >= 0) ? &slots[todayIndex] : nullptr;

  if (WiFi.status() == WL_CONNECTED &&
      (lastPoll == 0 || now - lastPoll >= (time_t)(POLL_INTERVAL_MS / 1000UL))) {
    lastPoll = now;
    bool manifestOk = refreshManifest();
    if (manifestOk) {
      lastSuccessfulContact = now;
    }
  }

  // Decide what the panel should be showing.
  //
  // A reboot loses the RAM image cache and the wall clock comes from the server,
  // so "server unreachable" cannot be judged by elapsed server time alone: on a
  // cold boot there is no image to put behind the badge and no clock to measure a
  // 24h outage against. Key the decision off whether there is an image to show.
  //
  // With an image, keep the day up and only flag a long outage. With nothing
  // cached, the blank panel is itself the problem - it looks the same as dead
  // hardware - so say so promptly, measured against the boot clock.
  bool haveImage = (today != nullptr && today->valid);
  bool serverLongGone =
      lastSuccessfulContact > 0 &&
      (now - lastSuccessfulContact) >= (time_t)(SERVER_ERROR_AFTER_MS / 1000UL);
  bool wantError = haveImage ? serverLongGone : millis() >= BOOT_ERROR_AFTER_MS;

  // Repaint only on a real change of what should be on screen, so a healthy
  // device never blinks the panel and the log stays quiet.
  static char shownChecksum[33] = {0};
  static char lastShownDate[11] = {0};
  static bool shownError = false;

  bool contentChanged = haveImage &&
      (strncmp(shownChecksum, today->checksum, sizeof(shownChecksum)) != 0 ||
       strncmp(lastShownDate, today->date, sizeof(lastShownDate)) != 0);

  if (wantError != shownError || (!wantError && contentChanged)) {
    if (wantError && haveImage) {
      LOGF("server gone beyond the outage limit; drawing today WITH error badge");
      displayWithError(today);
    } else if (wantError) {
      if (lastSuccessfulContact > 0) {
        LOGF("server reachable but no image for today; drawing ERROR on a blank panel");
      } else {
        LOGF("nothing cached and server unreachable; drawing ERROR on a blank panel");
      }
      displayWithErrorBitmap(nullptr);
    } else if (haveImage) {
      LOGF("drawing today's image");
      displaySlot(today);
    } else {
      // Recovered, but the manifest had no image for today yet.
      LOGF("server reachable again; clearing ERROR badge");
      displayBlank();
    }
    shownError = wantError;
    if (haveImage) {
      strncpy(shownChecksum, today->checksum, sizeof(shownChecksum) - 1);
      shownChecksum[sizeof(shownChecksum) - 1] = '\0';
      strncpy(lastShownDate, today->date, sizeof(lastShownDate) - 1);
      lastShownDate[sizeof(lastShownDate) - 1] = '\0';
    } else {
      shownChecksum[0] = '\0';
      lastShownDate[0] = '\0';
    }
  }

  // Status line: proof the loop is alive. Printed every 30s and immediately
  // whenever something changes, so the log stays readable but silence is still
  // meaningful. Driven by millis(); the wall clock jumps when the date syncs.
  static unsigned long lastStatusMs = 0;
  static char lastState[48] = "";
  char state[48];
  snprintf(state, sizeof(state), "%d/%d/%s", (int)WiFi.status(),
           countValidSlots(), (today != nullptr && today->valid) ? "ready" : "none");
  bool changedState = strcmp(state, lastState) != 0;
  if (changedState || millis() - lastStatusMs >= 30000UL) {
    lastStatusMs = millis();
    snprintf(lastState, sizeof(lastState), "%s", state);
    LOGF("alive up=%lus wifi=%d(%s) date=%ld cached=%d/%d today=%s heap=%u",
         (unsigned long)(millis() / 1000), (int)WiFi.status(),
         (WiFi.status() == WL_CONNECTED) ? WiFi.localIP().toString().c_str() : "down",
         currentDayNumber, countValidSlots(), DAY_SLOTS,
         (today != nullptr && today->valid) ? "ready" : "none",
         (unsigned)ESP.getFreeHeap());
  }

  feedWatchdog();

  // Sleep in short slices so the loop stays responsive and the log keeps
  // flowing; the status line must appear at a human-visible rate during
  // bring-up.
  delay(LOOP_TICK_MS);
}

/// Feed the watchdog during slow network work.
///
/// A generous timeout is not enough on its own: an HTTP GET allows 30 seconds,
/// which still exceeds it, so every blocking call feeds the WDT as it goes.
static void feedWatchdog() {
  if (wdtArmed) {
    esp_task_wdt_reset();
  }
}

/// Total slots that were allocated successfully.
static int countValidSlotsTotal() {
  int count = 0;
  for (int i = 0; i < DAY_SLOTS; i++) {
    if (slots[i].bitmap != nullptr) {
      count++;
    }
  }
  return count;
}

/// How many day slots currently hold a usable bitmap.
static int countValidSlots() {
  int count = 0;
  for (int i = 0; i < DAY_SLOTS; i++) {
    if (slots[i].valid) {
      count++;
    }
  }
  return count;
}
