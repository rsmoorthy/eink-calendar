#ifndef CALENDAR_CONFIG_H
#define CALENDAR_CONFIG_H

// --- WiFi Credentials ---
#define WIFI_SSID       "Advaita"
#define WIFI_PASSWORD   "NonduaLity"

// --- Server Configuration ---
#define SERVER_HOST     "192.168.29.31"
#define SERVER_PORT     8080

// --- API Endpoints ---
#define API_DATE_PATH       "/api/date"
#define API_CALENDAR_PATH   "/api/calendar"
#define API_IMAGE_PATH      "/api/calendar/"

// --- Polling Intervals ---
#define DEFAULT_POLL_INTERVAL_MS   (300000UL)        // 5 minutes default (overridden dynamically by server)
#define ERROR_THRESHOLD_MS         (86400000UL)      // 24 hours in ms

// --- Cache Settings ---
#define CACHE_DAYS              4                  // Today + 3 days ahead
#define BITMAP_SIZE             15000              // 400x300 / 8 bytes

#endif // CALENDAR_CONFIG_H
