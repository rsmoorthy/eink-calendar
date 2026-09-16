"""Application factory and entry point for the calendar server."""

from __future__ import annotations

import logging
import os

from flask import Flask

from assets_store import prepare_assets_dir
from calendar_config import ConfigStore
from calendar_db import Database
from calendar_service import CalendarService


def create_app(
    db: Database | None = None,
    config_store: ConfigStore | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

    database = db or Database()
    store = config_store or ConfigStore()
    # Uploads have to outlive the container, so the renderer reads images from
    # the seeded data volume rather than the read-only copy baked into the image.
    service = CalendarService(database, store, assets_dir=prepare_assets_dir())

    import api
    import web

    api.register(app, service, database)
    web.register(app, service, database, store)

    app.extensions["calendar"] = {"service": service, "db": database, "config": store}

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


app = create_app()


if __name__ == "__main__":
    _configure_logging()
    port = int(os.environ.get("PORT", "8080"))
    # Host 0.0.0.0 so the ESP32 on the LAN can reach it, not just localhost.
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
