import os
import sys
import io
import base64
import yaml
from datetime import date, datetime, timedelta
import zoneinfo

# Ensure current directory is in sys.path for local module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, Response, Form, Depends, HTTPException, status, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from PIL import Image
import re

import db
import panchanga
import tamil_calendar
import image_generator

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Amma Calendar")

def get_icons_dir() -> str:
    cfg = image_generator.load_layout_config()
    icons_dir = cfg.get("icons_dir", "server/icons")
    for base in [os.path.join(BASE_DIR, "..", icons_dir), os.path.join(BASE_DIR, icons_dir), icons_dir]:
        if os.path.exists(base):
            return os.path.abspath(base)
    fallback = os.path.join(BASE_DIR, "icons")
    os.makedirs(fallback, exist_ok=True)
    return os.path.abspath(fallback)

# Mount static files, icons, & templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/icons", StaticFiles(directory=get_icons_dir()), name="icons")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

DAY_ICONS = ["mon.png", "tue.png", "wed.png", "thu.png", "fri.png", "sat.png", "sun.png"]

def get_icon_metadata(filename: str, icons_dir: str):
    path = os.path.join(icons_dir, filename)
    if not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as img:
            w, h = img.size
        size_kb = round(os.path.getsize(path) / 1024, 1)
        return {
            "name": filename,
            "url": f"/icons/{filename}",
            "width": w,
            "height": h,
            "resolution": f"{w} × {h}",
            "size_kb": size_kb,
        }
    except Exception:
        return None

# Session cookie name
SESSION_COOKIE = "cal_session"


def get_current_user(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    # For lightweight simplicity, token is username if user exists
    user = db.get_user_by_username(token)
    return user["username"] if user else None


def require_login(request: Request) -> str:
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return user


@app.on_event("startup")
def on_startup():
    db.init_db()
    # Create default admin if no user exists
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    if count == 0:
        db.create_or_update_user("admin", "admin123")
        print("Initialized default admin user (username: 'admin', password: 'admin123')")


# -------------------------------------------------------------
# Web Administration Routes
# -------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/home")
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, response: Response, username: str = Form(...), password: str = Form(...)):
    user = db.get_user_by_username(username)
    if user and db.verify_password(password, user["password_hash"], user["salt"]):
        resp = RedirectResponse(url="/home", status_code=status.HTTP_303_SEE_OTHER)
        resp.set_cookie(key=SESSION_COOKIE, value=username, httponly=True, max_age=86400 * 7)
        return resp
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password."})


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login")
    resp.delete_cookie(key=SESSION_COOKIE)
    return resp


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return RedirectResponse(url="/home")


@app.get("/home", response_class=HTMLResponse)
def home_page(request: Request, user: str = Depends(require_login)):
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    return templates.TemplateResponse(request=request, name="home.html", context={
        "user": user,
        "current_date": today_str,
    })


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, user: str = Depends(require_login)):
    config_path = os.path.join(BASE_DIR, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_content = f.read()
    else:
        yaml_content = ""

    return templates.TemplateResponse(request=request, name="config.html", context={
        "user": user,
        "config_yaml": yaml_content,
    })


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request, user: str = Depends(require_login)):
    icons_dir = get_icons_dir()
    day_icons = []
    for fname in DAY_ICONS:
        meta = get_icon_metadata(fname, icons_dir)
        if meta:
            day_icons.append(meta)

    other_icons = []
    if os.path.exists(icons_dir):
        for fname in sorted(os.listdir(icons_dir)):
            if fname.lower() in DAY_ICONS or fname.startswith("."):
                continue
            meta = get_icon_metadata(fname, icons_dir)
            if meta:
                other_icons.append(meta)

    return templates.TemplateResponse(request=request, name="upload.html", context={
        "user": user,
        "day_icons": day_icons,
        "other_icons": other_icons,
    })


@app.post("/api/upload")
async def upload_icon_api(
    file: UploadFile = File(...),
    custom_name: str = Form(None),
    user: str = Depends(require_login)
):
    icons_dir = get_icons_dir()
    raw_name = (custom_name or file.filename or "").strip()
    raw_name = os.path.basename(raw_name)
    if not raw_name:
        return JSONResponse({"status": "error", "message": "No file name provided."}, status_code=400)

    base_part, ext = os.path.splitext(raw_name)
    if not ext:
        ext = ".png"
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", base_part).strip("_")
    if not safe_base:
        safe_base = "icon"
    final_filename = f"{safe_base}{ext.lower()}"

    contents = await file.read()
    try:
        with Image.open(io.BytesIO(contents)) as test_img:
            test_img.verify()
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Invalid image file: {e}"}, status_code=400)

    target_path = os.path.join(icons_dir, final_filename)
    with open(target_path, "wb") as f:
        f.write(contents)

    return {"status": "ok", "filename": final_filename}


@app.post("/api/icons/{filename}/delete")
@app.delete("/api/icons/{filename}")
def delete_icon_api(filename: str, user: str = Depends(require_login)):
    clean_name = os.path.basename(filename)
    if clean_name.lower() in DAY_ICONS:
        return JSONResponse({"status": "error", "message": f"Day of week icon '{clean_name}' cannot be deleted."}, status_code=400)

    icons_dir = get_icons_dir()
    target = os.path.join(icons_dir, clean_name)
    if not os.path.isfile(target):
        return JSONResponse({"status": "error", "message": f"Icon '{clean_name}' not found."}, status_code=404)

    try:
        os.remove(target)
        return {"status": "ok", "message": f"Deleted '{clean_name}'"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# -------------------------------------------------------------
# REST APIs for Web UI & Admin Actions
# -------------------------------------------------------------

@app.get("/api/day/{target_date}")
def get_day_api(target_date: str, user: str = Depends(require_login)):
    day = db.get_calendar_day(target_date)
    d_obj = date.fromisoformat(target_date)

    if not day:
        # Generate initial data for this day
        panch = panchanga.fetch_online_panchanga(d_obj)
        tamil = tamil_calendar.get_tamil_date(d_obj)
        return {
            "date": target_date,
            "day_of_week": d_obj.strftime("%A"),
            "gregorian_day": d_obj.day,
            "gregorian_month": d_obj.strftime("%b"),
            "lunar_masa": panch.get("lunar_masa", ""),
            "lunar_paksha": panch.get("lunar_paksha", "Shukla"),
            "lunar_tithi": panch.get("lunar_tithi", "Prathama"),
            "nakshatra": panch.get("nakshatra", ""),
            "tamil_month": tamil.get("tamil_month", ""),
            "tamil_month_ta": tamil.get("tamil_month_ta", ""),
            "tamil_date": tamil.get("tamil_date", 0),
            "custom_text": "",
            "icon_name": "",
            "addl_icon_name": "",
            "day_icon_file": "",
            "addl_icon_file": "",
            "has_image": False,
            "checksum": "",
        }

    icon_val = day["icon_name"] if "icon_name" in day.keys() and day["icon_name"] else ""
    addl_icon_val = day["addl_icon_name"] if "addl_icon_name" in day.keys() and day["addl_icon_name"] else ""

    return {
        "date": day["date"],
        "day_of_week": day["day_of_week"],
        "gregorian_day": day["gregorian_day"],
        "gregorian_month": day["gregorian_month"],
        "lunar_masa": day["lunar_masa"],
        "lunar_paksha": day["lunar_paksha"],
        "lunar_tithi": day["lunar_tithi"],
        "nakshatra": day["nakshatra"],
        "tamil_month": day["tamil_month"],
        "tamil_month_ta": day["tamil_month_ta"],
        "tamil_date": day["tamil_date"],
        "custom_text": day["custom_text"],
        "icon_name": icon_val,
        "addl_icon_name": addl_icon_val,
        "day_icon_file": icon_val,
        "addl_icon_file": addl_icon_val,
        "has_image": bool(day["bitmap"]),
        "checksum": day["checksum"],
    }


class UpdateDayRequest(BaseModel):
    day_of_week: str = ""
    lunar_masa: str = ""
    lunar_tithi: str = ""
    lunar_paksha: str = "Shukla"
    nakshatra: str = ""
    tamil_month_ta: str = ""
    tamil_date: int = 0
    custom_text: str = ""
    icon_name: str | None = ""
    addl_icon_name: str | None = ""
    day_icon_file: str | None = ""
    addl_icon_file: str | None = ""


@app.post("/api/day/{target_date}")
def update_day_api(target_date: str, req: UpdateDayRequest, user: str = Depends(require_login)):
    d_obj = date.fromisoformat(target_date)
    existing = db.get_calendar_day(target_date)

    day_icon = (req.day_icon_file or req.icon_name or "").strip()
    addl_icon = (req.addl_icon_file or req.addl_icon_name or "").strip()

    day_data = {
        "date": target_date,
        "day_of_week": req.day_of_week or d_obj.strftime("%A"),
        "gregorian_day": d_obj.day,
        "gregorian_month": d_obj.strftime("%b"),
        "lunar_masa": req.lunar_masa,
        "lunar_paksha": req.lunar_paksha,
        "lunar_tithi": req.lunar_tithi,
        "nakshatra": req.nakshatra,
        "tamil_month": existing["tamil_month"] if existing and existing["tamil_month"] else "",
        "tamil_month_ta": req.tamil_month_ta,
        "tamil_date": req.tamil_date,
        "custom_text": req.custom_text,
        "icon_name": day_icon,
        "addl_icon_name": addl_icon,
    }

    # Render Image & Bitmap (reads config.yaml automatically)
    pil_img = image_generator.generate_calendar_image(day_data)
    bitmap_bytes = image_generator.image_to_bitmap_bytes(pil_img)
    checksum = image_generator.compute_checksum(bitmap_bytes)

    day_data["bitmap"] = bitmap_bytes
    day_data["checksum"] = checksum

    db.save_calendar_day(day_data)
    return {"status": "ok", "checksum": checksum}


@app.get("/api/preview/{target_date}.png")
def preview_image_png(target_date: str):
    day = db.get_calendar_day(target_date)
    if day and day["bitmap"]:
        pil_img = image_generator.bitmap_bytes_to_image(day["bitmap"])
    else:
        # Generate on the fly
        d_obj = date.fromisoformat(target_date)
        panch = panchanga.fetch_online_panchanga(d_obj)
        tamil = tamil_calendar.get_tamil_date(d_obj)
        day_data = {
            "date": target_date,
            "day_of_week": d_obj.strftime("%A"),
            "gregorian_day": d_obj.day,
            "gregorian_month": d_obj.strftime("%b"),
            "lunar_masa": panch.get("lunar_masa", ""),
            "lunar_paksha": panch.get("lunar_paksha", "Shukla"),
            "lunar_tithi": panch.get("lunar_tithi", "Prathama"),
            "nakshatra": panch.get("nakshatra", ""),
            "tamil_month_ta": tamil.get("tamil_month_ta", ""),
            "tamil_date": tamil.get("tamil_date", 0),
            "custom_text": "",
            "icon_name": "",
            "addl_icon_name": "",
        }
        pil_img = image_generator.generate_calendar_image(day_data)

    # Save to PNG in memory
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


class ConfigRequest(BaseModel):
    config_yaml: str


@app.get("/api/config")
def get_config_api(reset: bool = False, user: str = Depends(require_login)):
    config_path = os.path.join(BASE_DIR, "config.yaml")
    content = ""
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
    return {"config_yaml": content}


@app.post("/api/config")
def save_config_api(req: ConfigRequest, user: str = Depends(require_login)):
    try:
        yaml.safe_load(req.config_yaml)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Invalid YAML: {e}"}, status_code=400)

    config_path = os.path.join(BASE_DIR, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(req.config_yaml)
    return {"status": "ok"}


class BulkRequest(BaseModel):
    start_date: str | None = None
    days: int = 90
    force: bool = False
    refetch_panchanga: bool = False


@app.post("/api/generate")
def bulk_generate_api(req: BulkRequest, user: str = Depends(require_login)):
    import bulk_generate
    s_date = date.fromisoformat(req.start_date) if req.start_date else datetime.now(IST).date()
    gen_cnt = 0
    skip_cnt = 0
    for i in range(req.days):
        d = s_date + timedelta(days=i)
        _, generated = bulk_generate.generate_day(d, force=req.force, refetch_panchanga=req.refetch_panchanga)
        if generated:
            gen_cnt += 1
        else:
            skip_cnt += 1

    return {"status": "ok", "generated_count": gen_cnt, "skipped_count": skip_cnt}


# -------------------------------------------------------------
# ESP32 REST API Client Endpoints
# -------------------------------------------------------------

@app.get("/date")
@app.get("/api/date")
def get_current_date():
    now_ist = datetime.now(IST)
    cfg = image_generator.load_layout_config()
    poll_mins = cfg.get("system", {}).get("poll_interval_minutes", 60)
    return {
        "date": now_ist.strftime("%Y-%m-%d"),
        "day_of_week": now_ist.strftime("%A"),
        "day_abbr": now_ist.strftime("%a"),
        "time": now_ist.strftime("%H:%M:%S"),
        "timestamp": int(now_ist.timestamp()),
        "poll_interval_minutes": poll_mins,
    }


@app.get("/calendar")
@app.get("/api/calendar")
def get_calendar_list(response: Response):
    now_ist = datetime.now(IST)
    start_date_str = now_ist.strftime("%Y-%m-%d")

    cfg = image_generator.load_layout_config()
    poll_mins = cfg.get("system", {}).get("poll_interval_minutes", 60)
    response.headers["X-Poll-Interval-Minutes"] = str(poll_mins)

    # Fetch 4 days (today + 3 days ahead)
    rows = db.get_calendar_range(start_date_str, count=4)
    result = []

    # Map existing rows by date
    row_map = {r["date"]: r for r in rows}

    import bulk_generate
    for i in range(4):
        d = now_ist.date() + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        if d_str in row_map and row_map[d_str]["checksum"]:
            result.append({"date": d_str, "checksum": row_map[d_str]["checksum"]})
        else:
            # Generate on demand
            chk, _ = bulk_generate.generate_day(d)
            result.append({"date": d_str, "checksum": chk})

    return result


@app.get("/calendar/{target_date}")
@app.get("/api/calendar/{target_date}")
def get_calendar_image_data(target_date: str, request: Request, format: str | None = None):
    day = db.get_calendar_day(target_date)
    if not day or not day["bitmap"]:
        import bulk_generate
        d_obj = date.fromisoformat(target_date)
        chk, _ = bulk_generate.generate_day(d_obj)
        day = db.get_calendar_day(target_date)

    if not day or not day["bitmap"]:
        raise HTTPException(status_code=404, detail="Date image not found")

    bitmap_bytes = bytes(day["bitmap"])
    checksum = day["checksum"]

    # Check if client requested raw binary stream
    accept = request.headers.get("accept", "")
    if format == "raw" or "application/octet-stream" in accept:
        return Response(
            content=bitmap_bytes,
            media_type="application/octet-stream",
            headers={
                "X-Calendar-Date": target_date,
                "X-Calendar-Checksum": checksum,
                "Content-Length": str(len(bitmap_bytes)),
            }
        )

    # Default JSON response
    b64_str = base64.b64encode(bitmap_bytes).decode("ascii")
    return {
        "date": target_date,
        "checksum": checksum,
        "width": 400,
        "height": 300,
        "size_bytes": len(bitmap_bytes),
        "bitmap": b64_str,
    }
