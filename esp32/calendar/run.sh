#!/bin/bash

PORT=${PORT:-/dev/ttyACM0}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

set -e

echo "Compiling ESP32 Calendar..."
arduino-cli compile -p "$PORT" --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc --library "$ROOT_DIR/esp32/lib" "$ROOT_DIR/esp32/calendar"

if [ "$1" == "--upload" ] || [ "$1" == "-u" ]; then
    echo "Uploading to $PORT..."
    arduino-cli upload -p "$PORT" --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc "$ROOT_DIR/esp32/calendar"
    if [ "$2" == "--monitor" ] || [ "$2" == "-m" ]; then
        echo "Opening serial monitor..."
        minicom -D "$PORT" -b 115200
    fi
fi
