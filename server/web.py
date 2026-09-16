"""Admin web interface: login, calendar editing, and layout configuration."""

from __future__ import annotations

import calendar as calmod
import functools
import io
import re
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from assets_store import MAX_DIMENSION, PROTECTED as PROTECTED_ICONS, AssetError, AssetStore
from calendar_db import CONTENT_FIELDS
from panchanga import DASH, TamilMonthOutOfRange, tamil_month_for, tithi_number_for, today_ist
from renderer import DAY_IMAGE_DIR

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Fields the admin can edit on /home. Order controls the form layout.
EDITABLE_FIELDS = (
    "masa",
    "paksha",
    "tithi",
    "nakshatra",
    "tamil_month",
    "tamil_date",
    "custom_text",
    "addl_image",
    "day_image",
)

FIELD_LABELS = {
    "masa": "Lunar month (Masa)",
    "paksha": "Paksha",
    "tithi": "Tithi",
    "nakshatra": "Nakshatra",
    "tamil_month": "Tamil month",
    "tamil_date": "Tamil date",
    "custom_text": "Custom text",
    "addl_image": "Addl image",
    "day_image": "Day Image",
}


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def register(app, service, db, config_store) -> None:
    app.secret_key = _secret_key(db)

    # ------------------------------------------------------------------ auth
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            row = db.get_admin(username)
            if row is None or not check_password_hash(row["password_hash"], password):
                flash("Invalid username or password.", "error")
                return render_template("login.html"), 401
            session["user"] = username
            target = request.args.get("next") or url_for("home")
            if not target.startswith("/"):
                target = url_for("home")
            return redirect(target)
        return render_template("login.html")

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return redirect(url_for("home"))

    # ------------------------------------------------------------------ home
    @app.get("/home")
    @login_required
    def home():
        selected = _selected_date(request.args.get("date"))
        month = _month_grid(selected.year, selected.month)

        content = db.get_content(selected)
        if content is None:
            # First visit to a date: fetch metadata so the form is populated.
            service.refresh_date(selected)
            content = db.get_content(selected)

        return render_template(
            "home.html",
            selected=selected,
            month=month,
            content=content,
            fields=EDITABLE_FIELDS,
            labels=FIELD_LABELS,
            month_names=_MONTH_NAMES,
            today=today_ist(),
            prev_month=_shift_month(selected, -1),
            next_month=_shift_month(selected, 1),
            image_names=[asset.name for asset in _asset_store(service).list()],
        )

    @app.get("/image/<day>.png")
    @login_required
    def image(day: str):
        """Serve the stored bitmap as a PNG for browser display.

        The wire format to the ESP is 1-bit raw; browsers cannot render that, so
        the same buffer is wrapped in a PNG container here.
        """
        parsed = _parse(day)
        bitmap = db.get_bitmap(parsed)
        if bitmap is None:
            abort(404)

        from PIL import Image

        width, height = _canvas_size(config_store)
        image = Image.frombytes("1", (width, height), bitmap)
        buffer = io.BytesIO()
        image.convert("L").save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png")

    @app.post("/image/<day>/generate")
    @login_required
    def generate(day: str):
        parsed = _parse(day)
        try:
            _, checksum = service.generate(parsed)
        except Exception as exc:  # noqa: BLE001 - show the reason in the UI
            app.logger.exception("generate failed for %s", day)
            if request.accept_mimetypes.best == "application/json":
                return jsonify({"ok": False, "error": str(exc)}), 500
            flash(f"Could not generate image: {exc}", "error")
            return redirect(url_for("home", date=parsed.isoformat()))

        if request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": True, "date": parsed.isoformat(), "checksum": checksum})
        flash("Image generated.", "ok")
        return redirect(url_for("home", date=parsed.isoformat()))

    @app.post("/content/<day>")
    @login_required
    def save_content(day: str):
        """Save admin edits for a date and re-render.

        A manually edited field is recorded as an override so the periodic
        panchanga refresh will not overwrite it.
        """
        parsed = _parse(day)
        row = db.get_day(parsed)
        previous = db.get_content(parsed) or {}

        values: dict[str, object] = {}
        for field in EDITABLE_FIELDS:
            if field not in request.form:
                continue
            raw = request.form.get(field, "").strip()
            if field == "tamil_date":
                values[field] = int(raw) if raw.isdigit() else None
            else:
                values[field] = raw

        changed = [
            field
            for field, value in values.items()
            if _normalise(previous.get(field)) != _normalise(value)
        ]
        if not changed:
            flash("No changes to save.", "info")
            return redirect(url_for("home", date=parsed.isoformat()))

        # Editing the tithi text changes which moon phase should be drawn, so
        # re-derive the number from the new name.
        if "tithi" in changed:
            values["tithi_number"] = tithi_number_for(values["tithi"])

        db.upsert_content(parsed, values)
        for field in changed:
            db.mark_override(parsed, field)

        regenerate = request.form.get("regenerate", "1") == "1"
        message = "Saved."
        if regenerate:
            try:
                service.generate(parsed)
                message = "Saved and image regenerated."
            except Exception as exc:  # noqa: BLE001 - keep the saved edits
                app.logger.exception("regenerate failed for %s", day)
                message = f"Saved, but regenerating failed: {exc}"

        flash(message, "ok")
        return redirect(url_for("home", date=parsed.isoformat()))

    @app.post("/refresh/<day>")
    @login_required
    def refresh(day: str):
        """Re-scrape panchanga for a date, honouring any manual overrides."""
        parsed = _parse(day)
        if not service.refresh_date(parsed):
            flash("Panchanga fetch failed; values fall back to dashes.", "error")
        else:
            flash("Panchanga refreshed.", "ok")
        return redirect(url_for("home", date=parsed.isoformat()))

    @app.post("/refresh-month")
    @login_required
    def refresh_month():
        """Refresh panchanga for every day of the selected month.

        Scraped once per day, so this is intentionally explicit rather than
        automatic: a full month is ~30 requests to the source.
        """
        selected = _selected_date(request.form.get("date"))
        start = Date(selected.year, selected.month, 1)
        days_in_month = calmod.monthrange(selected.year, selected.month)[1]
        results = service.refresh_range(start, days_in_month)
        failures = sum(1 for ok in results.values() if not ok)
        if failures:
            flash(
                f"Refreshed {len(results)} days; {failures} could not be fetched.",
                "error",
            )
        else:
            flash(f"Refreshed all {len(results)} days.", "ok")
        return redirect(url_for("home", date=selected.isoformat()))

    # ---------------------------------------------------------------- config
    @app.route("/config", methods=["GET", "POST"])
    @login_required
    def config():
        if request.method == "POST":
            action = request.form.get("action", "save")
            if action == "reset":
                config_store.reset()
                flash("Configuration reset to defaults.", "ok")
                return redirect(url_for("config"))

            # The form posts the whole YAML document as text. Parsing it back
            # (rather than mapping dozens of individual inputs) keeps the page in
            # step with whatever keys the config gains later.
            try:
                document = yaml.safe_load(request.form.get("config_yaml") or "")
            except Exception as exc:  # noqa: BLE001 - report parse errors inline                flash(f"Could not parse YAML: {exc}", "error")
                return render_template(
                    "config.html",
                    config_yaml=request.form.get("config_yaml", ""),
                    error=str(exc),
                )

            if not isinstance(document, dict):
                flash("Configuration must be a YAML mapping.", "error")
                return render_template(
                    "config.html",
                    config_yaml=request.form.get("config_yaml", ""),
                    error="Top level must be a mapping",
                )

            # Keep the admin's own text, so comments and key order survive.
            config_store.save(document, text=request.form.get("config_yaml", ""))
            flash("Configuration saved.", "ok")
            return redirect(url_for("config"))

        return render_template(
            "config.html",
            # Show the file itself, not a re-serialised form: comments and the
            # admin's key order are part of what they are editing.
            config_yaml=config_store.text(),
            config_path=config_store.path,
            defaults_yaml=yaml.safe_dump(
                config_store.defaults(), sort_keys=False, default_flow_style=False
            ),
            error=None,
        )

    # -------------------------------------------------------------- uploads
    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload():
        """Manage the image files used by the layout.

        Uploads are validated by opening the file, not by trusting the browser's
        content type, and the weekday defaults cannot be deleted because the
        layout falls back to them by name.
        """
        store = _asset_store(service)

        if request.method == "POST":
            action = request.form.get("action", "upload")
            try:
                if action == "delete":
                    store.delete(request.form.get("name", ""))
                    flash(f"Deleted {request.form.get('name', '')}.", "ok")
                else:
                    file_storage = request.files.get("image")
                    if file_storage is None or not file_storage.filename:
                        raise AssetError("Choose a file to upload.")
                    # Prefer an explicit name field so an upload can be given a
                    # stable name (for example to replace sun.png).
                    supplied = (request.form.get("name") or "").strip()
                    name = supplied or Path(file_storage.filename).name
                    info = store.save(
                        name,
                        file_storage.read(),
                        overwrite=request.form.get("overwrite", "1") == "1",
                    )
                    flash(
                        f"Uploaded {info.name} ({info.resolution}).", "ok"
                    )
            except AssetError as exc:
                flash(str(exc), "error")
            except Exception as exc:  # noqa: BLE001 - report any read failure inline
                app.logger.exception("upload failed")
                flash(f"Upload failed: {exc}", "error")
            return redirect(url_for("upload"))

        assets = store.list()
        return render_template(
            "upload.html",
            assets=assets,
            protected=PROTECTED_ICONS,
            max_dimension=MAX_DIMENSION,
        )

    @app.get("/upload/thumb/<path:name>")
    @login_required
    def upload_thumb(name: str):
        """Serve a downscaled preview of a stored image.

        Thumbnails are generated per request rather than cached: the set is
        small and this avoids another store to keep in step with the files.
        """
        store = _asset_store(service)
        path = store.path_for(name)
        if not path.exists():
            abort(404)

        from PIL import Image

        with Image.open(path) as handle:
            preview = handle.convert("L")
            preview.thumbnail((120, 120), Image.LANCZOS)
            buffer = io.BytesIO()
            preview.save(buffer, format="PNG")
        buffer.seek(0)
        response = send_file(buffer, mimetype="image/png")
        response.headers["Cache-Control"] = "no-cache"
        return response

    # ------------------------------------------------------------- tamil data
    @app.route("/tamil-months", methods=["GET", "POST"])
    @login_required
    def tamil_months():
        """Maintain the manual Tamil month start dates.

        Tamil months begin at solar ingress and drift year to year, so these are
        entered by hand rather than computed.
        """
        if request.method == "POST":
            raw = request.form.get("tamil_months") or ""
            rows = []
            errors = []
            for line_number, line in enumerate(raw.splitlines(), start=1):
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                parts = [part.strip() for part in text.split(",")]
                if len(parts) != 3:
                    errors.append(f"line {line_number}: expected 'date,english,tamil'")
                    continue
                try:
                    start = Date.fromisoformat(parts[0])
                except ValueError:
                    errors.append(f"line {line_number}: bad date {parts[0]!r}")
                    continue
                rows.append((start, parts[1], parts[2]))

            if errors:
                for message in errors:
                    flash(message, "error")
            elif rows:
                db.seed_tamil_months(rows)
                flash(f"Saved {len(rows)} Tamil month entries.", "ok")
            return redirect(url_for("tamil_months"))

        stored = db.list_tamil_months()
        lines = "\n".join(
            f"{row['start_date']},{row['month_en']},{row['month_ta']}" for row in stored
        )
        return render_template("tamil_months.html", tamil_months=lines)


# --------------------------------------------------------------------- helpers

_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _secret_key(db) -> str:
    """Persistent session key, stored in the database.

    A random key per process would invalidate logins on every restart.
    """
    existing = db.get_setting("flask_secret_key")
    if existing:
        return existing
    import secrets

    generated = secrets.token_hex(32)
    db.set_setting("flask_secret_key", generated)
    return generated


def _selected_date(raw: str | None) -> Date:
    if raw and DATE_RE.match(raw):
        try:
            return Date.fromisoformat(raw)
        except ValueError:
            pass
    return today_ist()


def _parse(raw: str) -> Date:
    if not DATE_RE.match(raw):
        abort(404)
    try:
        return Date.fromisoformat(raw)
    except ValueError:
        abort(404)


def _month_grid(year: int, month: int) -> dict:
    """Weeks of the month for the calendar widget, Monday-first.

    Each cell is ``None`` for padding days, otherwise the date.
    """
    first = Date(year, month, 1)
    days_in_month = calmod.monthrange(year, month)[1]
    leading = first.weekday()  # Monday == 0
    cells: list[Date | None] = [None] * leading
    cells.extend(Date(year, month, day) for day in range(1, days_in_month + 1))
    while len(cells) % 7:
        cells.append(None)
    weeks = [cells[index : index + 7] for index in range(0, len(cells), 7)]
    return {"year": year, "month": month, "weeks": weeks}


def _normalise(value: object) -> object:
    """Compare form strings against stored Python values consistently."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value).strip()


def _asset_store(service) -> AssetStore:
    """Asset store for the directory the renderer reads images from."""
    return AssetStore(service.assets_dir / DAY_IMAGE_DIR)


def _canvas_size(config_store) -> tuple[int, int]:
    """Canvas dimensions from the active layout config."""
    canvas = config_store.load().get("canvas", {})
    return int(canvas.get("width", 400)), int(canvas.get("height", 300))


def _shift_month(day: Date, delta: int) -> Date:
    """Return the first day of the month ``delta`` months away from ``day``."""
    month_index = day.year * 12 + (day.month - 1) + delta
    year, month = divmod(month_index, 12)
    return Date(year, month + 1, 1)
