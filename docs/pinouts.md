# Pinouts and wiring

Wiring between the **ESP32-C6 Super Mini** board and the **Waveshare 4.2" e-paper
module** (400x300, dual-colour) used by this project.

The pin numbers below are the ones the firmware actually uses. The source of
truth is `esp32/calendar/epdif.h` (and the identical copy in
`esp32/bringup/epdif.h`); this document only records them.

## Board: ESP32-C6 Super Mini

![ESP32-C6 Super Mini pinout diagram](ESP32-C6%20Super%20Mini%20pinout%20diagram.png)

## Display wiring

| ePaper pin | ESP32-C6 pin | Firmware define | Direction |
| --- | --- | --- | --- |
| VCC | **3V3 (OUT)** | — | power |
| GND | **GND** | — | ground |
| DIN (MOSI) | **GPIO 14** | `SPI_MOSI` | output |
| CLK (SCK) | **GPIO 6** | `SPI_SCK` | output |
| CS | **GPIO 4** | `CS_PIN` | output |
| DC | **GPIO 3** | `DC_PIN` | output |
| RST | **GPIO 2** | `RST_PIN` | output |
| BUSY | **GPIO 1** | `BUSY_PIN` | input, pull-up |

Eight wires in total.

## Notes

- **3.3 V only.** The panel is 3.3 V logic; connect VCC to `3V3 (OUT)`, never to
  the `5V` pin.
- **No MISO.** The display is write-only. `EpdIf::IfInit()` opens the bus with
  `SPI.begin(SPI_SCK, -1, SPI_MOSI, CS_PIN)`, so there is no data line back from
  the panel.
- **BUSY is active-high** on the Waveshare module: it should idle at **0**
  (`0 = idle, 1 = busy`). Both sketches print the idle level at boot; a stuck
  `1` means missing power, a loose wire, or RST not connected.
- **Avoid the on-board peripherals when re-mapping pins.** The Super Mini has an
  LED on `GPIO 15`, an addressable RGB LED on `GPIO 8`, the BOOT button on
  `GPIO 9`, and a reset button on `RST`. The pins chosen above avoid all of them.
- The board is flashed over its native USB CDC port; the firmware is built for
  `esp32:esp32:esp32c6:CDCOnBoot=cdc`.

## Verifying the wiring

Flash the standalone bring-up sketch, which needs no WiFi or server and
alternates two test frames:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc esp32/bringup
arduino-cli upload  -p /dev/ttyACM0 --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc esp32/bringup
```

Frame 1 shows `TEST 1` with a solid black box; frame 2 shows `TEST 2` with an
outlined box and Tamil text. If both alternate, the display side is healthy.
