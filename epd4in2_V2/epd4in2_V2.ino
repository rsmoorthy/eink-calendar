/**
 *  @filename   :   epd4in2_V2-demo.ino
 *  @brief      :   4.2inch e-paper V2 display demo
 *  @author     :   Yehui from Waveshare
 *
 *  Copyright (C) Waveshare     August 4 2017
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documnetation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to  whom the Software is
 * furished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include <SPI.h>
#include "epd4in2_V2.h"
#include "imagedata.h"
#include "epdpaint.h"
#include "icons.h"

#define COLORED 0
#define UNCOLORED 1

void print_busy(void) {
  for (int i = 0; i < 5; i++) {
    Serial.print("busy = ");
    Serial.println(digitalRead(BUSY_PIN));
    delay(10);
  }
}

void setup() {
  // put your setup code here, to run once:
  delay(1000);
  Serial.begin(115200);
  Serial.println("Setup started!");

#if 0
  print_busy();

  pinMode(RST_PIN, OUTPUT);
  delay(10);
  digitalWrite(RST_PIN, HIGH);
  delay(100);
  print_busy();
  digitalWrite(RST_PIN, LOW);
  delay(10);
  digitalWrite(RST_PIN, HIGH);
  print_busy();
  delay(100);
  print_busy();
#endif

  Epd epd;

  if (epd.Init() != 0) {
    Serial.print("e-Paper init failed");
    return;
  }
  Serial.println("Init completed");
  //Serial.print(UNCOLORED);
  /* This clears the SRAM of the e-paper display */
  epd.Clear();
  Serial.println("Clear completed");


#if 0

  /**
    * Due to RAM not enough in Arduino UNO, a frame buffer is not allowed.
    * In this case, a smaller image buffer is allocated and you have to 
    * update a partial display several times.
    * 1 byte = 8 pixels, therefore you have to set 8*N pixels at a time.
    */
  unsigned char image[1500];
  Paint paint(image, 400, 28);  //width should be the multiple of 8

  paint.Clear(UNCOLORED);
  paint.DrawStringAt(20, 5, "e-Paper Demo", &Font16, COLORED);
  epd.Display_Partial_Not_refresh(paint.GetImage(), 0, 32, 0 + paint.GetWidth(), 32 + paint.GetHeight());
  Serial.println("e-Paper demo completed");

  paint.Clear(COLORED);
  paint.DrawStringAt(20, 5, "Hello world!", &Font16, UNCOLORED);
  epd.Display_Partial_Not_refresh(paint.GetImage(), 0, 64, 0 + paint.GetWidth(), 64 + paint.GetHeight());
  Serial.println("Hello world completed");

  paint.SetWidth(64);
  paint.SetHeight(64);

  paint.Clear(UNCOLORED);
  paint.DrawRectangle(0, 0, 40, 50, COLORED);
  paint.DrawLine(0, 0, 40, 50, COLORED);
  paint.DrawLine(40, 0, 0, 50, COLORED);
  epd.Display_Partial_Not_refresh(paint.GetImage(), 10, 130, 10 + paint.GetWidth(), 130 + paint.GetHeight());
  Serial.println("Rectangle Line completed");

  paint.Clear(UNCOLORED);
  paint.DrawCircle(32, 32, 30, COLORED);
  epd.Display_Partial_Not_refresh(paint.GetImage(), 90, 120, 90 + paint.GetWidth(), 120 + paint.GetHeight());
  Serial.println("Circle completed");

  paint.Clear(UNCOLORED);
  paint.DrawFilledRectangle(0, 0, 40, 50, COLORED);
  epd.Display_Partial_Not_refresh(paint.GetImage(), 10, 200, 10 + paint.GetWidth(), 200 + paint.GetHeight());
  Serial.println("filled rect completed");

  paint.Clear(UNCOLORED);
  paint.DrawCircle(32, 32, 30, COLORED);
  // paint.DrawFilledCircle(32, 32, 30, COLORED);
  epd.Display_Partial(paint.GetImage(), 90, 190, 90 + paint.GetWidth(), 190 + paint.GetHeight());
  Serial.println(paint.GetWidth());
  Serial.println(paint.GetHeight());
  Serial.println("filled circle completed");
  delay(5000);
#endif

#if 1

  /* This displays an image */
  // epd.Init();
  Serial.println("show 2-gray image\r\n");
  // epd.Display(IMAGE_BUTTERFLY);
  // epd.Display(VINAYAKA);
  // epd.Display_Partial_Not_refresh((unsigned char *)adiyogi_64_48, 100, 100, 164, 148);
  int x = 100;
  int y = 140;
  epd.Display_Partial_Not_refresh((unsigned char *)adiyogi_128_96, x, y, x + 128, y + 96);
  // epd.Display_Partial_Not_refresh((unsigned char *)hanuman_64_64, 0, 100, 64, 164);
  // epd.Display_Partial_Not_refresh((unsigned char *)hanuman_128_128, 0, 0, 128, 128);

  x = 0;
  y = 0;
  epd.Display_Partial_Not_refresh((unsigned char *)hanuman_12_128_128, x, y, x + 128, y + 128);
  x = 128;
  y = 0;
  epd.Display_Partial_Not_refresh((unsigned char *)hanuman_12_64_64, x, y, x + 64, y + 64);
  // epd.Display_Partial_Not_refresh((unsigned char *)lakshmi_48_64, 100, 100, 148, 164);
  // epd.Display_Partial_Not_refresh((unsigned char *)glyph_ku, 200, 200, 240, 234);
  unsigned char image[4800];
  Paint paint(image, 400, 90);  //width should be the multiple of 8

  paint.Clear(UNCOLORED);
  paint.DrawStringAt(20, 5, "26 May", &Font24, COLORED);
  paint.DrawStringAt2(200, 5, "குறள்", glyphs_f32, glyphs_f32_count, COLORED);
  paint.DrawVerticalLine(150, 5, 5 + 80, COLORED);
  Serial.print("Paints width and height");
  Serial.print(paint.GetWidth());
  Serial.print(" ");
  Serial.println(paint.GetHeight());
  // epd.Display_Partial_Not_refresh(paint.GetImage(), 0, 10, 0 + paint.GetWidth(), 10 + paint.GetHeight());


  Paint paint2(image, 200, 90);  //width should be the multiple of 8
  paint2.Clear(UNCOLORED);
  paint2.DrawStringAt2(0, 5, "29 5", glyphs_f64, glyphs_f64_count, COLORED);
  epd.Display_Partial(paint2.GetImage(), 200, 100, 200 + paint2.GetWidth(), 100 + paint.GetHeight());
  Serial.println("e-Paper demo completed");
  Serial.println("Done");
#endif

#if 0

  Serial.print("show 4-gray image\r\n");
  epd.Init_4Gray();
  // epd.Set_4GrayDisplay(gImage_4in2_4Gray1, 100, 100, 200, 150);

#endif

  /* Deep sleep */
  epd.Sleep();
}

void loop() {
  // put your main code here, to run repeatedly:
}
