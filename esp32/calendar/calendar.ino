#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>

#include "config.h"
#include "epd4in2_V2.h"
#include "epdpaint.h"

// --- Global Display & Cache Objects ---
Epd epd;

struct DaySlot {
  char date[12];
  char checksum[34];
  uint8_t bitmap[BITMAP_SIZE];
  bool valid;
};

DaySlot cache[CACHE_DAYS];

char currentDateStr[12] = "";
unsigned long pollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
unsigned long lastPollTime = 0;
unsigned long lastSuccessfulSync = 0;
bool serverErrorCondition = false;

// Buffer for error banner drawing
unsigned char errorBuffer[300]; 

// --- Function Prototypes ---
void connectWiFi();
bool syncDateFromServer();
bool pollCalendar();
bool downloadDayBitmap(const char* targetDate, uint8_t* buffer, const char* expectedChecksum);
void updateDisplay(const uint8_t* bitmap, bool showErrorBadge);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==========================================");
  Serial.println("   Amma Clock - ESP32-C6 Calendar Client  ");
  Serial.println("==========================================");

  // Initialize Cache
  for (int i = 0; i < CACHE_DAYS; i++) {
    cache[i].valid = false;
    cache[i].date[0] = '\0';
    cache[i].checksum[0] = '\0';
  }

  // Connect to WiFi
  connectWiFi();

  // Perform Initial Sync
  if (syncDateFromServer()) {
    lastSuccessfulSync = millis();
    pollCalendar();
  } else {
    Serial.println("[ERR] Initial date sync failed.");
  }

  lastPollTime = millis();
}

void loop() {
  // 1. Maintain WiFi Connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Reconnecting to WiFi...");
    connectWiFi();
  }

  unsigned long currentMillis = millis();

  // 2. Periodic Polling (frequency dynamically configured from server)
  if (currentMillis - lastPollTime >= pollIntervalMs || lastPollTime == 0) {
    lastPollTime = currentMillis;
    Serial.print("\n[POLL] Periodic poll starting (interval: ");
    Serial.print(pollIntervalMs / 60000UL);
    Serial.println(" min)...");

    if (syncDateFromServer()) {
      bool success = pollCalendar();
      if (success) {
        lastSuccessfulSync = millis();
        if (serverErrorCondition) {
          serverErrorCondition = false;
          Serial.println("[INFO] Server restored to healthy state.");
          // Re-render without error badge
          if (cache[0].valid) {
            updateDisplay(cache[0].bitmap, false);
          }
        }
      }
    }

    // 3. Check continuous error duration (> 24 hours)
    if (!serverErrorCondition && (millis() - lastSuccessfulSync >= ERROR_THRESHOLD_MS) && lastSuccessfulSync > 0) {
      Serial.println("[WARN] Continuous error reaching server for > 24 hours! Triggering ERROR banner.");
      serverErrorCondition = true;
      if (cache[0].valid) {
        updateDisplay(cache[0].bitmap, true);
      }
    }
  }

  delay(1000);
}

// --- WiFi Connection ---
void connectWiFi() {
  Serial.print("[WIFI] Connecting to SSID: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WIFI] Connected! IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WIFI] Connection failed. Will retry in loop.");
  }
}

// --- Sync Date from Server (GET /api/date) ---
bool syncDateFromServer() {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + API_DATE_PATH;
  Serial.print("[HTTP] Fetching Date from: ");
  Serial.println(url);

  http.begin(url);
  http.setTimeout(5000);
  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    http.end();

    StaticJsonDocument<384> doc;
    DeserializationError error = deserializeJson(doc, payload);
    if (!error) {
      const char* serverDate = doc["date"];
      if (doc.containsKey("poll_interval_minutes")) {
        int mins = doc["poll_interval_minutes"];
        if (mins > 0) {
          unsigned long newInterval = (unsigned long)mins * 60000UL;
          if (newInterval != pollIntervalMs) {
            pollIntervalMs = newInterval;
            Serial.print("[CONFIG] Server dynamic poll interval: ");
            Serial.print(mins);
            Serial.println(" minute(s).");
          }
        }
      }

      if (serverDate && strlen(serverDate) > 0) {
        Serial.print("[DATE] Server date: ");
        Serial.println(serverDate);

        // Check if date rolled over to next day
        if (strcmp(currentDateStr, serverDate) != 0) {
          Serial.println("[DATE] Day transition detected! Refreshing cache.");
          strncpy(currentDateStr, serverDate, sizeof(currentDateStr) - 1);
        }
        return true;
      }
    } else {
      Serial.print("[ERR] JSON parse error: ");
      Serial.println(error.c_str());
    }
  } else {
    Serial.print("[ERR] HTTP Date sync failed with code: ");
    Serial.println(httpCode);
    http.end();
  }
  return false;
}

// --- Poll Calendar (GET /api/calendar) ---
bool pollCalendar() {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + API_CALENDAR_PATH;
  Serial.print("[HTTP] Polling Calendar from: ");
  Serial.println(url);

  http.begin(url);
  http.setTimeout(8000);
  int httpCode = http.GET();

  if (httpCode != HTTP_CODE_OK) {
    Serial.print("[ERR] HTTP Calendar poll failed with code: ");
    Serial.println(httpCode);
    http.end();
    return false;
  }

  String payload = http.getString();
  http.end();

  StaticJsonDocument<1024> doc;
  DeserializationError error = deserializeJson(doc, payload);
  if (error) {
    Serial.print("[ERR] Calendar JSON parse failed: ");
    Serial.println(error.c_str());
    return false;
  }

  JsonArray arr = doc.as<JsonArray>();
  bool todayImageChanged = false;

  int idx = 0;
  for (JsonObject item : arr) {
    if (idx >= CACHE_DAYS) break;

    const char* itemDate = item["date"];
    const char* itemChecksum = item["checksum"];

    if (!itemDate || !itemChecksum) continue;

    // Check if cached slot matches
    bool match = (cache[idx].valid &&
                  strcmp(cache[idx].date, itemDate) == 0 &&
                  strcmp(cache[idx].checksum, itemChecksum) == 0);

    if (!match) {
      Serial.print("[SYNC] Slot ");
      Serial.print(idx);
      Serial.print(" (");
      Serial.print(itemDate);
      Serial.println(") needs download.");

      if (downloadDayBitmap(itemDate, cache[idx].bitmap, itemChecksum)) {
        strncpy(cache[idx].date, itemDate, sizeof(cache[idx].date) - 1);
        strncpy(cache[idx].checksum, itemChecksum, sizeof(cache[idx].checksum) - 1);
        cache[idx].valid = true;

        if (idx == 0) {
          todayImageChanged = true;
        }
      }
    } else {
      Serial.print("[SYNC] Slot ");
      Serial.print(idx);
      Serial.print(" (");
      Serial.print(itemDate);
      Serial.println(") is up to date.");
    }
    idx++;
  }

  // If today's image changed or was newly loaded, refresh display
  if (todayImageChanged && cache[0].valid) {
    Serial.println("[EPD] Today's image changed or updated. Refreshing display immediately!");
    updateDisplay(cache[0].bitmap, serverErrorCondition);
  }

  return true;
}

// --- Download Raw 1-Bit Bitmap (GET /api/calendar/:date?format=raw) ---
bool downloadDayBitmap(const char* targetDate, uint8_t* buffer, const char* expectedChecksum) {
  HTTPClient http;
  String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + API_IMAGE_PATH + targetDate + "?format=raw";
  Serial.print("[HTTP] Downloading raw bitmap: ");
  Serial.println(url);

  http.begin(url);
  http.setTimeout(15000);
  int httpCode = http.GET();

  if (httpCode != HTTP_CODE_OK) {
    Serial.print("[ERR] Image download failed with HTTP: ");
    Serial.println(httpCode);
    http.end();
    return false;
  }

  int len = http.getSize();
  if (len != BITMAP_SIZE && len != -1) {
    Serial.print("[WARN] Unexpected content length: ");
    Serial.println(len);
  }

  WiFiClient* stream = http.getStreamPtr();
  size_t bytesRead = 0;
  unsigned long startWait = millis();

  while (http.connected() && (bytesRead < BITMAP_SIZE) && (millis() - startWait < 15000)) {
    size_t availableBytes = stream->available();
    if (availableBytes) {
      size_t readChunk = stream->readBytes(buffer + bytesRead, min(availableBytes, (size_t)(BITMAP_SIZE - bytesRead)));
      bytesRead += readChunk;
      startWait = millis();
    }
    delay(1);
  }

  http.end();

  if (bytesRead == BITMAP_SIZE) {
    Serial.print("[HTTP] Successfully downloaded ");
    Serial.print(bytesRead);
    Serial.println(" bytes.");
    return true;
  } else {
    Serial.print("[ERR] Incomplete download. Received: ");
    Serial.print(bytesRead);
    Serial.println(" / 15000 bytes.");
    return false;
  }
}

// --- Push Bitmap to Waveshare 4.2" Display ---
void updateDisplay(const uint8_t* bitmap, bool showErrorBadge) {
  Serial.println("[EPD] Initializing e-Paper display (Fast Full Clean Refresh)...");

  if (epd.Init_Fast(Seconds_1_5S) != 0) {
    Serial.println("[ERR] e-Paper Init_Fast failed!");
    return;
  }

  Serial.println("[EPD] Writing bitmap and executing full display refresh...");
  epd.Display_Fast(bitmap);

  // If server has been down for >24 hours, draw "ERROR" at bottom-right corner
  if (showErrorBadge) {
    Serial.println("[EPD] Rendering ERROR badge at bottom-right corner...");
    // 80x24 area at (315, 272)
    Paint paint(errorBuffer, 80, 24);
    paint.Clear(0); // Black background
    paint.DrawStringAt(12, 4, "ERROR", &Font16, 1); // White text
    epd.Display_Partial(paint.GetImage(), 315, 272, 395, 296);
  }

  Serial.println("[EPD] Putting display to sleep...");
  epd.Sleep();
  Serial.println("[EPD] Display update completed.");
}
