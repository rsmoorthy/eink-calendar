# Calendar server container.
#
# Debian slim (not python:*-slim) because the Tamil text needs Pillow built with
# Raqm: without it the vowel signs are placed by code point order and Tamil
# renders malformed, silently. Debian's python3-pil links against the system
# libraqm, which guarantees correct shaping.
#
# fonts-noto-core brings the NotoSans and NotoSansTamil faces used by the
# default layout config.
FROM debian:12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Kolkata \
    PORT=8080 \
    EINK_DB_PATH=/data/calendar.db \
    EINK_CONFIG_PATH=/data/config.yaml \
    EINK_ASSETS_DIR=/data/assets

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pil \
        python3-requests \
        python3-bs4 \
        python3-yaml \
        python3-flask \
        python3-gunicorn \
        python3-pip \
        tzdata \
        fonts-noto-core \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/ /app/

# Fail the build rather than shipping an image whose Tamil would be wrong.
RUN python3 -c "from PIL import features; assert features.check('raqm'), \
    'Pillow lacks Raqm: Tamil shaping would be incorrect'"

# Pre-fetch the fonts named in the config, so the first render needs no network.
# Fonts are downloaded rather than committed to keep the repository small, and
# they land in /app/fonts so a relative config path resolves the same way
# whether the container is built here or the app runs from a checkout.
RUN python3 fetch_fonts.py

# Sample day icons. These are placeholders until real artwork is provided; a
# missing icon is skipped by the renderer rather than failing the render.
RUN python3 make_placeholder_icons.py || true

# Run as an unprivileged user. The uid is 1000 to match the usual first host
# user, so a bind-mounted data directory stays writable without chown games.
# Without this the database and config files would be created as root and the
# host user could not manage them.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin calendar \
    && mkdir -p /data \
    && chown -R calendar:calendar /app /data

USER calendar

VOLUME ["/data"]

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"

# Single worker: SQLite is a single-writer store and the ESP polls on a timer,
# so concurrency buys nothing here. Threads handle the ESP and web requests
# together. create_app() is called through the factory so the app is built once
# per worker under gunicorn.
CMD ["sh", "-c", "exec python3 -m gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120 'app:create_app()'"]
