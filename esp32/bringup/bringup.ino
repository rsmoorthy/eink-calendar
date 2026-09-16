/**
 * Display bring-up test - no WiFi, no server.
 *
 * Purpose: prove the panel, wiring and SPI work by drawing two different test
 * frames, five seconds apart, forever. Nothing here touches the network, so a
 * failure is unambiguously a hardware/driver problem rather than a WiFi or
 * server one.
 *
 * What to look for on the panel:
 *   Frame 1: "TEST 1", a SOLID BLACK box on the left, "frame one"
 *   Frame 2: "TEST 2", an OUTLINED box on the left, Tamil text at the bottom
 *
 * Every step prints with CR+LF and is prefixed by a millisecond timestamp, so
 * the log distinguishes "hung" from "quiet": if a line stops appearing the
 * device is stuck exactly there.
 */

#include <Arduino.h>
#include <SPI.h>

#include "epd4in2_V2.h"
#include "epdif.h"
#include "test_frames.h"

// The 5 second interval lets a human see both frames and confirm the second
// one replaced the first.
#define FRAME_INTERVAL_MS 5000

static Epd epd;
static unsigned long lastFrame = 0;
static uint8_t frameIndex = 0;

/// Print with CR+LF so a serial monitor renders each line on its own row.
#define LOGF(...)                     \
  do {                                \
    Serial.printf("[%8lu] ", millis()); \
    Serial.printf(__VA_ARGS__);       \
    Serial.print("\r\n");             \
  } while (0)

void setup() {
  Serial.begin(115200);
  delay(1500);  // let the host attach before the first line

  Serial.print("\r\n");
  LOGF("=== display bring-up test ===");
  LOGF("frames are %dx%d, %d bytes each",
       TEST_FRAME_WIDTH, TEST_FRAME_HEIGHT, TEST_FRAME_BYTES);
  LOGF("SPI pins: SCK=%d MOSI=%d CS=%d DC=%d RST=%d BUSY=%d",
       SPI_SCK, SPI_MOSI, CS_PIN, DC_PIN, RST_PIN, BUSY_PIN);

  // Report the BUSY pin level before touching anything. A stuck pin is the
  // most common cause of a dead panel and is invisible in the original driver.
  pinMode(BUSY_PIN, INPUT_PULLUP);
  delay(10);
  LOGF("BUSY pin idle level = %d (expect 0 = idle, 1 = busy)", digitalRead(BUSY_PIN));

  LOGF("calling epd.Init()...");
  unsigned long start = millis();
  int result = epd.Init();
  LOGF("epd.Init() returned %d after %lu ms", result, millis() - start);

  if (result != 0) {
    LOGF("FATAL: init failed, stopping. Check wiring and SPI pins.");
    while (true) {
      delay(1000);
    }
  }

  LOGF("init ok, starting frame loop every %d ms", FRAME_INTERVAL_MS);
}

void loop() {
  unsigned long now = millis();
  if (lastFrame != 0 && now - lastFrame < FRAME_INTERVAL_MS) {
    return;
  }
  lastFrame = now;

  const uint8_t *frame = (frameIndex == 0) ? FRAME1 : FRAME2;
  LOGF("drawing frame %d (first byte 0x%02X)...", frameIndex + 1, frame[0]);

  unsigned long start = millis();
  epd.Display(frame);
  LOGF("frame %d displayed in %lu ms", frameIndex + 1, millis() - start);

  frameIndex = (frameIndex + 1) % 2;
}
