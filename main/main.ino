#include <GxEPD2_BW.h>

// --- Corrected Pin Definitions for Waveshare 4.2" Display ---
// Using hardware SPI pins on ESP32-C6 Super Mini
#define EPD_CS 4    // Hardware CS pin
#define EPD_DC 3    // Data/Command (GPIO 3)
#define EPD_RST 2   // Reset (GPIO 2)
#define EPD_BUSY 1  // Busy status (GPIO 1) \
                    //
#define SPI_SCK 7
#define SPI_MOSI 5

// The SPI hardware pins are fixed:
// MOSI (DIN) = GPIO 5
// SCK (CLK)  = GPIO 7
// You don't need to define these - GxEPD2 will use them automatically

// Initialize the display with the 4.2" 400x300 driver
// GxEPD2_BW<GxEPD2_420, GxEPD2_420::HEIGHT> display( GxEPD2_420(/*cs=*/ EPD_CS, /*dc=*/ EPD_DC, /*rst=*/ EPD_RST, /*busy=*/ EPD_BUSY));

GxEPD2_BW<GxEPD2_420_GDEY042T81, GxEPD2_420_GDEY042T81::HEIGHT> display(
  GxEPD2_420_GDEY042T81(/*cs=*/EPD_CS, /*dc=*/EPD_DC, /*rst=*/EPD_RST, /*busy=*/EPD_BUSY));

// GxEPD2_BW<GxEPD2_420, GxEPD2_420::HEIGHT> display( GxEPD2_420(/*cs=*/ EPD_CS, /*dc=*/ EPD_DC, /*rst=*/ EPD_RST, /*busy=*/ EPD_BUSY));
void setup() {
  delay(5000);
  Serial.begin(115200);
  SPI.begin(SPI_SCK, -1, SPI_MOSI, EPD_CS);
  Serial.println("Starting E-Ink Display...");

  // Initialize display - library automatically uses GPIO5(MOSI) and GPIO7(SCK)
  Serial.println("Step 1");
  display.init(115200, true, 2, false);
  delay(1000);
  Serial.println("Step 2");
  display.setRotation(1);  // Adjust as needed
  display.setFullWindow();
  display.firstPage();
  display.fillScreen(GxEPD_BLACK);
  display.display(true);
  Serial.println("Step 3");
  delay(2000);

  display.fillScreen(GxEPD_WHITE);
  display.setTextColor(GxEPD_BLACK);
  display.setFont(NULL);

  // Draw large, simple shapes first to verify display works
  display.fillRect(50, 50, 100, 80, GxEPD_BLACK);
  display.fillRect(200, 150, 80, 100, GxEPD_BLACK);

  // Test text
  display.setCursor(20, 60);
  display.print("Display Connected!");
  display.setCursor(20, 120);
  display.print("Hello Waveshare!");
  Serial.println("Step 4");

  // Send to screen
  display.display(true);

  Serial.println("Display updated successfully");
}

void loop() {
  // Your calendar code here
  delay(5000);
  Serial.println("Just ...");
}
