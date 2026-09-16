#!/usr/bin/env python3
"""Capture ESP32 serial output robustly, surviving USB re-enumeration.

On the ESP32-C6 with CDCOnBoot=cdc, Serial goes over the native USB peripheral.
A reset makes the device disappear and reappear as /dev/ttyACM0, so a monitor
that opens the port once can silently read nothing at all. This script keeps
reopening the port and reports gaps, so a reboot loop is visible as repeated
boot banners rather than as silence.

It also does not touch DTR/RTS: those lines are the reset and boot-mode
controls, and toggling them here would reset the very output we want to see
(and can strand the chip in download mode).

Usage:
    python3 tools/watch_serial.py [seconds] [port]
"""

from __future__ import annotations

import sys
import time

import serial

DEFAULT_SECONDS = 90
DEFAULT_PORT = "/dev/ttyACM0"
BAUD = 115200

# Lines that mark a fresh boot, used to count restarts.
BOOT_MARKERS = ("ESP-ROM:", "rst:0x", "e-Ink calendar starting")


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SECONDS
    port_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PORT

    start = time.monotonic()
    port: serial.Serial | None = None
    total = 0
    boots = 0
    partial = b""

    print(f"# watching {port_name} for {seconds:.0f}s @ {BAUD}", flush=True)

    while time.monotonic() - start < seconds:
        if port is None:
            try:
                port = serial.Serial(port_name, BAUD, timeout=0.3)
                part = time.monotonic() - start
                print(f"[{part:7.3f}s] --- port opened ---", flush=True)
            except (serial.SerialException, OSError) as exc:
                # The device is re-enumerating; wait for it to come back.
                time.sleep(0.3)
                continue

        try:
            chunk = port.read(4096)
        except (serial.SerialException, OSError):
            print(f"[{time.monotonic()-start:7.3f}s] --- port dropped ---", flush=True)
            try:
                port.close()
            except Exception:
                pass
            port = None
            continue

        if not chunk:
            continue

        total += len(chunk)
        partial += chunk

        # Emit complete lines only, so a torn read does not look like corruption.
        while b"\n" in partial:
            line, partial = partial.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            if any(marker in text for marker in BOOT_MARKERS):
                if marker_start(text):
                    boots += 1
            print(f"[{time.monotonic()-start:7.3f}s] {text}", flush=True)

    if port is not None:
        port.close()

    print()
    print(f"# total bytes: {total}")
    if total == 0:
        print("# NOTHING RECEIVED.")
        print("# Either the firmware never reached its first print, or the USB")
        print("# console is not connected (check CDCOnBoot=cdc).")
    else:
        print(f"# boot banners seen: {boots}")
        if boots > 1:
            print("# Multiple boots => the device is resetting in a loop")
            print("# (typically a brownout when WiFi and the panel draw together).")
    return 0


def marker_start(text: str) -> bool:
    """True when a line looks like the start of a boot, not a mid-boot line."""
    return text.startswith("ESP-ROM:") or text.startswith("e-Ink calendar starting")


if __name__ == "__main__":
    raise SystemExit(main())
