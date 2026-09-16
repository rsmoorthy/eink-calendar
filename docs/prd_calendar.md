# PRD for calendar

This is a calendar that gets displayed on Waveshare 4.2" e-Ink display (BW, 400x300), connected to ESP32-C6. ESP32 is also connected to WiFi and to a HTTP server.

## Overview

Please see the initial example code at @main/main.ino and files at @epd4in2_V2/ folder. Subsequently, I made multiple modifications and created @epd4in2_V2/epd4in2_V2.ino prototype to check, if I can get the content as I wanted. This code included mechanisms to print Tamil fonts and any small image, as part of the whole image to be displayed on the 4.2inch display.

This prototype was built with the initial assumption that the entire image will be constructed at the ESP end. While going through the process, I realised it was too hard to install each and every font that I need (with diff sizes) as glyphs. The @edp4in2_V2/gly.py takes a Tamil font and convert it into a file glyph32.cpp for ex. And the file @epd4in2_V2/proto/pil.py takes any .png/.jpg file and convert into a bitmap array, which I (right now) manually save it to icons.cpp file. Again the initial idea was to get the actual text (in unicode) from a server, that provides contents for the calendar. With all the data, ESP will create a bitmap image and display that on a daily basis.

After seeing the complexity involved and restrictions in creating different output (for ex, adding few fonts / size) and also for customising output (where on a non-regular basis, add Happy Birthday for specific people manually), I have decided to change the route for developing this software.

All the image creation (for each day) will be done at the server side. The ESP will simply retrieve each day's image from the server on periodic basis, and keep a copy of 3 day's images in the RAM itself (in case internet connectivity is lost for 3 days). The server side will create the image using better tools like python PIL package and construct
the final bitmap (400x300). The server side also will provide a web interface for admin user to allow to add custom text or modify the contents on specific days. Any changes made for a particular day (within the 7 day window) will be synced back to ESP32, via regular polls from ESP.

## Modules

### ESP32 - WiFi

1. Connect to WiFi on startup (and keep connecting to WiFi even if it gets disconnected). 
2. WiFi credentials are stored as part of the header (.h) files.
3. Hardcode `Advaita` (SSID) and `NonduaLity` (password)

### ESP32 - Server connectivity via REST API

1. Server address is hardcoded in the ESP header files
2. ESP32 does a date sync on startup and daily.

### ESP32 - Downloading images via REST API

1. ESP32 downloads daily calendar images. Preloads for upto 3 days and keeps it in RAM.
2. ESP32 polls once every 1 hour with the server and checks if the daily image for today and the next 3 days have 
   changed. And downloads it. If it is for the current day (changed), it displays it immediately.
3. If there is continuous error in reaching the server for more than a day, it will display "ERROR" at the bottom-right
   corner.

### Server / Dev VM - infrastructure

1. I am happy with python PIL, so the whole backend can be on python. 
2. Since there will be few fonts and python packages to be installed, it is preferable to setup the entire server
   in a dockerized container, running python (debian minimal).
3. Even in initial dev environment, the same mechanism be followed.
4. Dev env VM is reachable on 192.168.29.31 IP. Dev env also has ESP32 connected via `/dev/ttyACM0`
5. Create the ino file for ESP32 in "esp32/calendar/calender.ino" and place all the required library files in 
   "esp32/lib/" folder. Current prototype files are there at "epd4in2_V2/". Use a run.sh similar to `epd4in2_V2/run` for compilation and upload.
6. Create the entire server files in "server/" folder. Dockerfile can be placed in the root directory itself. The 
   container can expose any port, preferably 8080.

### Server - APIs

The server will support the following APIs for ESP32 to connect.

1. GET /date -- Returns current date info in timezone IST (GMT+05:30)
2. GET /calendar -- Returns a list of images (date, checksum) including today + 3 days ahead
3. GET /calendar/:date -- Returns the bitmap of 400x300 along with date and checksum

The API for the Web interface to function is not listed here, they should be computed.

### Server - Image creation

Right now, the contents of the image to be displayed is not super clear. We will get more clarity as we go by.

The list of contents below. The reference to "Line" is not very strict at some cases.

Line 1:
1. Date of the month  - Largest font (64), Occupies about 100x100 size, Top left Position: 60x60
2. Month (like Jan/Feb) - Font size (32), right side of Date. Vertically positions center of Date
3. Day of Week (like Mon/Tue) - Font size (32), right side of Month. Vertically positions center of Date
4. 64x64 image depicting usually day of week (but on special days will be different) - Top left position: x=(400-64) 
   and y=2

Line 2:
1. Lunar Tithi name - Font size (24 if possible or 20)
2. An image indicating Moon's phase (right of Lunar tithi name). Since this is black on white (e-ink display), a gray outer ring indicates full moon (Purnima), a filled black circle indicates new moon (Amavasya), A waxing phase (shukla paksha) will show gray filled on the left side of the circle and white on the right side of the circle (chaturthi will have less white on the right and more black filled on the left side, dwadashi will be the reverse). A waning phase (krishna paksha) will be the opposite.
3. Lunar phase - "Shukla paksha|Lunar paksha"

Line 3:
1. Lunar month name (Masa) - Font size (24 possible or 20)
2. Lunar Tithi name (Tithi) - next to Lunar month. Same font
3. Nakshatra - next to Tithi
4. Tamil Month name  (in tamil font)
5. Tamil Month date

Line 4:

Custom text added by admin user in the web interface

### Server - Create images in bulk

Typically it is a good idea to create all the images for the next 90 days. A cron job should be setup that runs a script that creates the images for the next 90 (X) days. Setting up the cron job will be done by admin manually, steps should be provided in README.md

The images are possibly stored as bitmap (400x300 array), so it is easy to send to ESP as is when needed. The bitmap also needs to be displayed on web interface as jpeg/png, so appropriately it may be converted at runtime (either front-end or backend).

### Server - Web interface

1. A very simple Web app, with Sqlite datatabase. Username/Password to login will be set by CLI (add the steps in 
   README.md)
2. After login, the default web page is /home, which shows a calendar. Clicking on a date in the calendar will show the 
   corresponding image (converted from the bitmap of 400x300) next to the calendar. If there is no bitmap already created, it will show a Generate button.
3. On a wider display size, row 1 -> col 1 will be calendar,  col 2 will be the image. Otherwise one component in one 
   row.
4. The next row will contain the different values (like date, lunar month, etc listed above) as fields (in a two 
   column table or similar, with column name and value as editable field). Including Custom text field - Most usually this value will be filled by the Admin to indicate some special day. A Generate button at the end will create a new bitmap which will show the image on row 2 -> col 2.

### Server - Config web interface

1. We also need another web page `/config` that allows the Web admin to do micro configurations.
2. What are these configurations? The image is constructed based on certain configuration options. Like the y position 
   of each Line, Line height, distance between two lines, font name and size of each component, position and size of each image placed, margin/padding between two components. These configurations can be adjusted so that I can get the actual image exactly to my liking. Please choose these configurations based on what you think could be helpful. We will add more configurations, in the future, if needed.
3. The config can be edited via the webpage and preferably stored as an yaml file (so it is easy to edit via editor). 
   The software should provide a default config yaml.

## Appendix A - Lunar Tithi names

Prathama: 1st lunar day
Dwitiya: 2nd lunar day
Tritiya: 3rd lunar day
Chaturthi: 4th lunar day
Panchami: 5th lunar day
Shashthi: 6th lunar day
Saptami: 7th lunar day
Ashtami: 8th lunar day
Navami: 9th lunar day
Dashami: 10th lunar day
Ekadashi: 11th lunar day
Dwadashi: 12th lunar day
Trayodashi: 13th lunar day
Chaturdashi: 14th lunar day

Purnima or Amavasya: 15 day

## Appendix B - Getting Lunar Month and Tithi

Running @epd4in2_V2/panchanga.py <yyyy-mm-dd> returns Masa (month) / Tithi (lunar day) / Nakshatra

## Appendix C - Getting Tamil month name and date

For now, please use @epd4in2_V2/proto/tamilcal.py, which gives guidance only until 2027. Please also explore the following (but this is optional for now and we can relook at this after one year):
```
you can scrape directly from portals such as Tamil Daily Calendar using requests and BeautifulSoup:URL Structure: https://www.tamildailycalendar.com/tamil_monthly_calendar.php?month={MM}&year={YYYY}Target Elements: Each day tile in the table contains day_number for the Gregorian date and secondary text indicating the corresponding Tamil month date.
```


## Appendix D - Review comments (Response)

1.  Tamil Calendar Calculation is Undefined -- Is resolved now. We need only tamil month name (in tamil) and date.
2.  Reliance on Web Scraping for Bulk Image Generation -- This is OK, we can rely on this method. Perhaps we could 
    run this only for 3 days ahead, to avoid any rate limits. But I will go with your recommendation of scraped data into SQLite.
3.  Display Bit Depth: Grayscale vs. 1-bit Monochrome Dithering -- You are right, there is no gray mode. This is BW 
    display, does not have 4 gray option. I have corrected from gray to black in the PRD now.
    While I know that this module does not have "4Gray" option, now I understand what is "1-bit Monochrome dithering" let us go ahead with that for Moon image.
4. REST API Schema & Wire Format -- I am fine either with binary body or JSON response. ESP32 wastage of RAM and CPU 
   cycles is okay. I suppose RAM wastage is only temporary. Unless the CPU wastage is so much that it woule extra-ordinarily higher RAM and CPU (that is noticeable to human time), JSON is okay.
5. Line 1 Coordinate Notation & Day-of-Week Icon Assets -- It is meant as x=336 y=2 (I inverted x and y, sorry). 
   Corrected now. Right now, copy `adiyogi.png` into `sun.png`, `mon.png` and so on until `sat.png`. I will update with proper images later.
6. ESP32 Display Driver Selection -- Please use epd4in2_V2.cpp (waveshare native driver, I have added few functions in 
   epdpaint.cpp, functions ending with 2 to draw glyphs of my own, perhaps it is not needed now)

Additional notes: If you chose to use `tamilcal.py` and `panchanga.py` -- please do not use those files as is. Grasp that code and imbibe it in your own code in the server side code.
