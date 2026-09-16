#pragma once

// ---------------------------------------------------------------------------
// Network and server configuration.
//
// WiFi credentials and the server address are compiled in, per the project
// design: the device has no configuration UI, so changing them means a
// reflash.
// ---------------------------------------------------------------------------

#define WIFI_SSID "Advaita"
#define WIFI_PASSWORD "NonduaLity"

// Address of the calendar server (see server/ in this repository). The ESP32
// and the server must be on the same network.
#define SERVER_HOST "192.168.29.31"
#define SERVER_PORT 8080

// How often to poll the server for changed images. Short by design so that an
// admin edit on the web page shows up on the display quickly. The panel is only
// refreshed when a checksum actually changes, so polling often is cheap: it is
// a few hundred bytes of JSON in the common case.
#define POLL_INTERVAL_MS (2UL * 60UL * 1000UL)

// Re-sync the clock with the server this often. The device now follows its own
// clock for the date, so this only corrects drift rather than being what makes
// the day change; the interval therefore trades update traffic against drift.
// Each sync also re-checks which images the window needs, so it doubles as a
// safety net if a day change was somehow missed.
#define DATE_RESYNC_INTERVAL_MS (6UL * 60UL * 60UL * 1000UL)

// How long the server may be unreachable before "ERROR" is drawn on screen.
// This applies once the device has talked to the server at least once: it is the
// "server has been gone a long while" threshold, and the cached days behind the
// badge stay displayed meanwhile.
#define SERVER_ERROR_AFTER_MS (24UL * 60UL * 60UL * 1000UL)

// How long after boot to wait for the server before showing ERROR when the
// device has never managed to reach it.
//
// A reboot loses the RAM image cache, so there is nothing to put behind the
// badge and the panel would otherwise stay blank white - indistinguishable from
// dead hardware. The wall clock is also unset at that point (it comes from the
// server), so this one is measured against the monotonic boot clock instead.
// Kept short so a network fault is visible quickly, but long enough that a
// normal slow boot does not flash an error on a healthy device.
#define BOOT_ERROR_AFTER_MS (90UL * 1000UL)

// Number of days held in RAM, so the display keeps working through an outage.
// "today" plus three days ahead.
#define DAY_SLOTS 4

// Refresh strategy.
//
// 1 = always use the full Init()/Display() sequence; 2 or more = use the fast
// path (Init_Fast/Display_Fast) for the interim refreshes and a full one every
// Nth frame.
//
// Full refresh is the default because the panel updates at most a few times a
// day, so the extra second is irrelevant, and a full refresh is the sequence
// that fully clears the panel. The SPI bus is configured once per boot, which
// is what previously made a repeated Init() deadlock.
#define FULL_REFRESH_EVERY 1

// Fast refresh mode, only used when FULL_REFRESH_EVERY > 1.
// Seconds_1_5S (0) or Seconds_2S (1), as defined by the vendor driver.
#define FAST_REFRESH_MODE Seconds_1_5S

// Serial console speed.
#define SERIAL_BAUD 115200

// Main loop tick. The loop prints a status line every pass, so this also sets
// how often the device reports it is alive. Kept short during bring-up so
// silence is quickly distinguishable from a hang. Raise it for long-term use
// (the poll interval below still governs how often the server is contacted).
#define LOOP_TICK_MS 1000

// Timezone: the calendar is rendered for IST. This offset is only used to turn
// the server-supplied epoch into a local date.
#define IST_OFFSET_SECONDS (5 * 3600 + 30 * 60)
