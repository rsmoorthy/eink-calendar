#!/usr/bin/env python3
"""Reset the ESP32 and capture its serial output with timestamps.

Used to tell the difference between "the firmware is stuck" and "the firmware
is running but quiet". Ordinary serial monitors show nothing in both cases.

The board is reset in-process via the USB-Serial/JTAG DTR/RTS sequence, so boot
messages are not missed.

Usage:
    python3 tools/serial_monitor.py [seconds] [port]
"""

from __future__ import annotations

import sys
import time

import serial

DEFAULT_SECONDS = 20
DEFAULT_PORT = "/dev/ttyACM0"
BAUD = 115200


def reset_board(port: serial.Serial) -> None:
    """Reset a chip using its USB-Serial/JTAG peripheral.

    This is esptool's USBJTAGSerialReset sequence, reproduced exactly. Getting
    it wrong strands the chip in download mode ("waiting for download") instead
    of booting the application, which is easy to mistake for a firmware fault.
    """
    port.setRTS(False)
    port.setDTR(False)  # idle
    time.sleep(0.1)
    port.setDTR(True)  # set IO0
    port.setRTS(False)
    time.sleep(0.1)
    port.setRTS(True)  # reset; steps through (1,1) rather than (0,0)
    port.setDTR(False)
    port.setRTS(True)  # RTS set as Windows only propagates DTR on RTS setting
    time.sleep(0.1)
    port.setDTR(False)
    port.setRTS(False)  # chip out of reset


def open_with_retry(port_name: str, attempts: int = 20) -> serial.Serial | None:
    """Open the port, retrying while the device re-enumerates after a reset."""
    for _ in range(attempts):
        try:
            return serial.Serial(port_name, BAUD, timeout=0.3)
        except (serial.SerialException, OSError):
            time.sleep(0.25)
    return None


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SECONDS
    port_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PORT

    port = open_with_retry(port_name)
    if port is None:
        print(f"# could not open {port_name}", file=sys.stderr)
        return 1

    print(f"# capturing {seconds:.0f}s from {port_name} @ {BAUD}", flush=True)
    reset_board(port)
    # Closing forces the re-enumeration to finish before we reopen. Holding the
    # old handle would read a dead file descriptor forever and report silence.
    port.close()
    time.sleep(1.5)

    start = time.monotonic()
    buffer = bytearray()
    partial = b""
    port = None

    while time.monotonic() - start < seconds:
        if port is None:
            port = open_with_retry(port_name)
            if port is None:
                time.sleep(0.25)
                continue
            print(f"[{time.monotonic()-start:7.3f}s] --- port open ---", flush=True)

        try:
            chunk = port.read(4096)
        except (serial.SerialException, OSError):
            # Re-enumeration mid-capture: reopen and keep going.
            print(f"[{time.monotonic()-start:7.3f}s] --- port dropped ---", flush=True)
            try:
                port.close()
            except Exception:
                pass
            port = None
            time.sleep(0.25)
            continue

        if not chunk:
            continue

        buffer.extend(chunk)
        partial += chunk
        # Only emit whole lines so a torn USB read is not shown as corruption.
        while b"\n" in partial:
            line, partial = partial.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                elapsed = time.monotonic() - start
                print(f"[{elapsed:7.3f}s] {text}", flush=True)

    if port is not None:
        try:
            port.close()
        except Exception:
            pass

    print()
    print(f"# total bytes: {len(buffer)}")
    if not buffer:
        print("# NOTHING RECEIVED - firmware hung before its first print, or the")
        print("# USB console is not connected (check CDCOnBoot=cdc).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
