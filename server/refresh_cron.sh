#!/bin/bash
#
# Bulk-generate calendar images for the days ahead.
#
# Intended to be run from cron. Generating ahead of time means the ESP32 always
# finds an already-rendered image, so its hourly poll is fast and a temporary
# outage of the panchanga source does not blank the display.
#
# Suggested crontab entry (runs daily at 02:00, keeping 90 days ahead):
#
#   0 2 * * * /path/to/repo/server/refresh_cron.sh >> /var/log/eink-calendar.log 2>&1
#
# Install it with:  crontab -e
#
# Inside Docker, run it with:
#   docker exec eink-calendar /app/refresh_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAYS="${DAYS:-90}"
PYTHON="${PYTHON:-python3}"

cd "$SCRIPT_DIR"

echo "=== $(date -Is) starting refresh of $DAYS days ==="

# Fetch panchanga for the window. Failures here are expected to be partial: a
# day that cannot be scraped is stored with dashes and the run continues.
"$PYTHON" manage.py refresh --days "$DAYS" || echo "warn: some days failed to refresh"

# Render every day in the window, reusing whatever panchanga is now stored.
"$PYTHON" manage.py generate --days "$DAYS" --no-refresh || echo "warn: some images failed to render"

# Report the outcome so the cron log shows whether the run was healthy.
"$PYTHON" manage.py status

echo "=== $(date -Is) finished ==="
