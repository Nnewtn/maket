"""
Glamour Studio — Booking Mini-CRM v4 for beauty salons & barbershops.
v4 adds: per-visitor brand preview via URL params, logo color analysis
for automatic theme matching, and one-click sample data for sales demos.
Run:  uvicorn main:app --reload
"""
import io
import logging
import os
import re
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
from fastapi import (BackgroundTasks, Depends, FastAPI, HTTPException,
                     Request, UploadFile, File)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import (BASE_DIR, Booking, Service, SessionLocal, Staff,
                      Waitlist, get_setting, init_db, seed_fake_data,
                      set_setting)
from schemas import (BookingCreate, BookingOut, CancelIn, LoginIn,
                     PasswordChange, ServiceIn, ServiceOut,
                     SiteSettingsUpdate, StaffIn, StaffOut, StatusUpdate,
                     TelegramSettings, WaitlistIn, WaitlistOut)
from services.fx import get_rates
from services.logo_colors import analyze_logo
from services.telegram import (format_booking_message, format_cancel_message,
                               send_telegram_message, verify_bot_token)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("salon")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Salon Booking Mini-CRM", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """Safety net: ANY unexpected error becomes a clean JSON 500."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "Internal server error. Please try again."})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth — in-memory admin sessions
# ---------------------------------------------------------------------------

SESSIONS: dict[str, float] = {}
SESSION_TTL = 60 * 60 * 12


def require_admin(request: Request):
    token = request.headers.get("X-Admin-Token", "")
    if token not in SESSIONS or SESSIONS[token] < time.time():
        SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="Unauthorized")
    SESSIONS[token] = time.time() + SESSION_TTL
    return True


# ---------------------------------------------------------------------------
# Rate limiting for public write endpoints
# ---------------------------------------------------------------------------

_rate: dict[str, list] = defaultdict(list)
RATE_LIMIT, RATE_WINDOW = 8, 300


def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    _rate[ip] = [t for t in _rate[ip] if now - t < RATE_WINDOW]
    if len(_rate[ip]) >= RATE_LIMIT:
        raise HTTPException(429, "Too many requests. Try again in a few minutes.")
    _rate[ip].append(now)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def all_settings(db: Session) -> dict:
    keys = ("company_name", "description", "opening_hours", "slot_step",
            "logo_url", "currency")
    return {k: get_setting(db, k) for k in keys}


def parse_hours(db: Session):
    raw = get_setting(db, "opening_hours", "09:00-20:00")
    try:
        start_s, end_s = raw.split("-")
        sh, sm = map(int, start_s.split(":"))
        eh, em = map(int, end_s.split(":"))
        return (sh * 60 + sm, eh * 60 + em)
    except Exception:
        return (9 * 60, 20 * 60)


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def phones_match(a: str, b: str) -> bool:
    da, db_ = digits(a), digits(b)
    if not da or not db_:
        return False
    tail = min(len(da), len(db_), 9)
    return da[-tail:] == db_[-tail:]


def staff_is_free(db: Session, staff_id: int, start, end) -> bool:
    return db.query(Booking).filter(
        Booking.staff_id == staff_id,
        Booking.start_time < end,
        Booking.end_time > start,
        Booking.status.in_(["New", "Confirmed"]),
    ).first() is None


def pick_free_staff(db: Session, start, end):
    """'Any available master': free master with the lightest schedule today."""
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    candidates = []
    for s in db.query(Staff).filter(Staff.active.is_(True)).all():
        if staff_is_free(db, s.id, start, end):
            load = db.query(Booking).filter(
                Booking.staff_id == s.id,
                Booking.start_time >= day_start,
                Booking.start_time < day_end,
                Booking.status.in_(["New", "Confirmed"])).count()
            candidates.append((load, s.id, s))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def booking_out(b: Booking) -> BookingOut:
    return BookingOut(
        id=b.id, client_name=b.client_name, phone=b.phone,
        contact_method=b.contact_method or "Call",
        contact_handle=b.contact_handle or "",
        service_id=b.service_id,
        service_name=b.service.name if b.service else "—",
        staff_id=b.staff_id,
        staff_name=b.staff.name if b.staff else "Any",
        start_time=b.start_time, end_time=b.end_time,
        status=b.status, created_at=b.created_at)


def notify_booking(db: Session, booking: Booking, master):
    """Collect targets (manager + master) for background sending."""
    token = get_setting(db, "telegram_token")
    if not token:
        return []
    company = get_setting(db, "company_name", "Salon")
    currency = get_setting(db, "currency", "PLN")
    service = booking.service
    msg = format_booking_message(
        company, booking.client_name, booking.phone,
        booking.contact_method, booking.contact_handle,
        service.name if service else "—", service.price if service else 0,
        currency, booking.start_time,
        service.duration_min if service else 0, master.name)
    return [(token, chat, msg) for chat in
            {c for c in (get_setting(db, "telegram_chat_id"),
                         master.telegram_chat_id) if c}]


PHONE_RE = re.compile(r"^[+\d][\d\s()\-]{5,23}$")


def save_image_square(data: bytes, prefix: str) -> str:
    """Decode ANY image Pillow understands, normalize to square PNG ≤512px.
    Never trusts the browser MIME header (the old 400 bug)."""
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 5 MB)")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise HTTPException(400, "File is not a valid image (PNG/JPEG/WebP/GIF)")
    if img.mode not in ("RGBA", "LA"):
        img = img.convert("RGBA")
    img.thumbnail((512, 512), Image.LANCZOS)
    os.makedirs(os.path.join(BASE_DIR, "static", "uploads"), exist_ok=True)
    fname = f"{prefix}_{secrets.token_hex(6)}.png"
    img.save(os.path.join(BASE_DIR, "static", "uploads", fname), "PNG", optimize=True)
    return f"/static/uploads/{fname}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@app.get("/api/settings/public")
def public_settings(db: Session = Depends(get_db)):
    return all_settings(db)


@app.get("/api/fx")
async def fx_rates(db: Session = Depends(get_db)):
    return await get_rates(get_setting(db, "currency", "PLN"))


@app.get("/api/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(Service).filter(Service.active.is_(True)).all()


@app.get("/api/staff", response_model=list[StaffOut])
def list_staff(db: Session = Depends(get_db)):
    return db.query(Staff).filter(Staff.active.is_(True)).all()


@app.post("/api/brand-preview")
async def brand_preview(payload: dict):
    """Compatibility endpoint. v5 samples remote logos in browser canvas.
    Deliberately does not fetch arbitrary URLs on the application server.
    """
    return {"method": "browser", "fallback": "niche_palette"}


@app.get("/api/availability")
def availability(date: str, staff_id: int = 0, db: Session = Depends(get_db)):
    """Free slots for a day. staff_id=0 → slot offered if ANY master is free."""
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(400, "Bad date format, expected YYYY-MM-DD")

    open_m, close_m = parse_hours(db)
    step = max(10, int(get_setting(db, "slot_step", "30") or 30))
    day_start = datetime(day.year, day.month, day.day)
    day_end = day_start + timedelta(days=1)

    active_staff = db.query(Staff).filter(Staff.active.is_(True)).all()
    if staff_id:
        active_staff = [s for s in active_staff if s.id == staff_id]
    if not active_staff:
        return {"date": date, "slots": []}

    existing = db.query(Booking).filter(
        Booking.start_time >= day_start, Booking.start_time < day_end,
        Booking.status.in_(["New", "Confirmed"])).all()

    slots, t, now = [], open_m, datetime.now()
    while t < close_m:
        slot_start = day_start + timedelta(minutes=t)
        slot_end = slot_start + timedelta(minutes=step)
        if slot_start > now:
            for s in active_staff:
                busy = any(b.staff_id == s.id and
                           overlaps(slot_start, slot_end, b.start_time, b.end_time)
                           for b in existing)
                if not busy:
                    slots.append(slot_start.strftime("%H:%M"))
                    break
        t += step
    return {"date": date, "slots": slots}


@app.post("/api/bookings")
def create_booking(payload: BookingCreate, request: Request,
                   background: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(request)

    name = payload.client_name.strip()
    phone = payload.phone.strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(400, "Invalid phone number format")
    if len(digits(phone)) < 7:
        raise HTTPException(400, "Invalid phone number format")

    handle = payload.contact_handle.strip()
    if payload.contact_method == "Telegram" and handle and not handle.startswith("@"):
        handle = "@" + handle

    service = db.query(Service).filter(Service.id == payload.service_id,
                                       Service.active.is_(True)).first()
    if not service:
        raise HTTPException(404, "Service not found")

    start = payload.start_time.replace(tzinfo=None)
    end = start + timedelta(minutes=service.duration_min)
    if start <= datetime.now():
        raise HTTPException(400, "Cannot book a time in the past")

    open_m, close_m = parse_hours(db)
    if start.hour * 60 + start.minute < open_m or end.hour * 60 + end.minute > close_m:
        raise HTTPException(400, "Selected time is outside opening hours")

    if payload.staff_id:
        master = db.query(Staff).filter(Staff.id == payload.staff_id,
                                        Staff.active.is_(True)).first()
        if not master:
            raise HTTPException(404, "Master not found")
        if not staff_is_free(db, master.id, start, end):
            raise HTTPException(409, "This master is already booked at that time")
    else:
        master = pick_free_staff(db, start, end)
        if master is None:
            raise HTTPException(409, "No master is free at that time — pick another slot")

    booking = Booking(client_name=name, phone=phone,
                      contact_method=payload.contact_method, contact_handle=handle,
                      service_id=service.id, staff_id=master.id,
                      start_time=start, end_time=end, status="New")
    db.add(booking)
    try:
        db.commit()
        db.refresh(booking)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This time slot was just taken — pick another one")
    except SQLAlchemyError:
        db.rollback()
        log.exception("DB error while creating booking")
        raise HTTPException(500, "Could not save the booking. Please try again.")

    for token, chat, msg in notify_booking(db, booking, master):
        background.add_task(send_telegram_message, token, chat, msg)

    return {"id": booking.id, "status": "ok", "staff_name": master.name}


# --- client self-service (no account, just a phone number) ------------------

@app.post("/api/my-bookings", response_model=list[BookingOut])
def my_bookings(payload: CancelIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    if len(digits(payload.phone)) < 7:
        raise HTTPException(400, "Invalid phone number format")
    rows = db.query(Booking).filter(
        Booking.start_time >= datetime.now() - timedelta(days=1)
    ).order_by(Booking.start_time).all()
    return [booking_out(b) for b in rows if phones_match(b.phone, payload.phone)]


@app.post("/api/bookings/{booking_id}/cancel")
def client_cancel(booking_id: int, payload: CancelIn, request: Request,
                  background: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(request)
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b or not phones_match(b.phone, payload.phone):
        raise HTTPException(404, "Booking not found")
    if b.status not in ("New", "Confirmed"):
        raise HTTPException(400, "This booking can no longer be cancelled")
    if b.start_time <= datetime.now():
        raise HTTPException(400, "Cannot cancel a past visit")
    b.status = "Cancelled"
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not cancel. Please call the salon.")

    token = get_setting(db, "telegram_token")
    if token:
        msg = format_cancel_message(get_setting(db, "company_name", "Salon"),
                                    b.client_name,
                                    b.service.name if b.service else "—",
                                    b.start_time,
                                    b.staff.name if b.staff else "Any", True)
        targets = {get_setting(db, "telegram_chat_id"),
                   b.staff.telegram_chat_id if b.staff else ""}
        for chat in {c for c in targets if c}:
            background.add_task(send_telegram_message, token, chat, msg)
    return {"ok": True}


# --- waitlist ---------------------------------------------------------------

@app.post("/api/waitlist")
def join_waitlist(payload: WaitlistIn, request: Request,
                  background: BackgroundTasks, db: Session = Depends(get_db)):
    rate_limit(request)
    if not PHONE_RE.match(payload.phone.strip()):
        raise HTTPException(400, "Invalid phone number format")
    handle = payload.contact_handle.strip()
    if payload.contact_method == "Telegram" and handle and not handle.startswith("@"):
        handle = "@" + handle
    w = Waitlist(client_name=payload.client_name.strip(), phone=payload.phone.strip(),
                 contact_method=payload.contact_method, contact_handle=handle,
                 service_id=payload.service_id or None,
                 staff_id=payload.staff_id or None,
                 date_pref=payload.date_pref)
    db.add(w)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Could not join the waitlist. Please try again.")

    token = get_setting(db, "telegram_token")
    chat = get_setting(db, "telegram_chat_id")
    if token and chat:
        msg = (f"⏳ <b>Waitlist — {get_setting(db, 'company_name', 'Salon')}</b>\n\n"
               f"👤 {w.client_name} · <code>{w.phone}</code>\n"
               f"📅 Wants: {w.date_pref or 'any day'}\n"
               f"Open the CRM to call them back when a slot frees up.")
        background.add_task(send_telegram_message, token, chat, msg)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

@app.post("/api/admin/login")
def admin_login(payload: LoginIn, db: Session = Depends(get_db)):
    if payload.password != get_setting(db, "admin_password", "admin123"):
        raise HTTPException(401, "Wrong password")
    token = secrets.token_hex(24)
    SESSIONS[token] = time.time() + SESSION_TTL
    return {"token": token}


@app.get("/api/admin/verify")
def admin_verify(_: bool = Depends(require_admin)):
    return {"ok": True}


@app.post("/api/admin/password")
def change_password(payload: PasswordChange, db: Session = Depends(get_db),
                    _: bool = Depends(require_admin)):
    if payload.old_password != get_setting(db, "admin_password"):
        raise HTTPException(400, "Current password is incorrect")
    set_setting(db, "admin_password", payload.new_password)
    return {"ok": True}


@app.get("/api/admin/settings")
def admin_settings(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    s = all_settings(db)
    s["telegram_token"] = get_setting(db, "telegram_token")
    s["telegram_chat_id"] = get_setting(db, "telegram_chat_id")
    return s


@app.patch("/api/admin/settings")
def update_settings(payload: SiteSettingsUpdate, db: Session = Depends(get_db),
                    _: bool = Depends(require_admin)):
    for k, v in payload.model_dump(exclude_none=True).items():
        set_setting(db, k, str(v))
    return all_settings(db)


@app.post("/api/admin/logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db),
                      _: bool = Depends(require_admin)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    url = save_image_square(data, "logo")
    set_setting(db, "logo_url", url)
    return {"logo_url": url}


@app.post("/api/admin/seed-sample")
def seed_sample(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    """Load realistic demo bookings/waitlist for sales presentations."""
    return seed_fake_data(db)


@app.post("/api/admin/telegram")
async def save_telegram(payload: TelegramSettings, db: Session = Depends(get_db),
                        _: bool = Depends(require_admin)):
    token = payload.telegram_token.strip()
    chat_id = payload.telegram_chat_id.strip()
    if token:
        try:
            bot = await verify_bot_token(token)
        except (ValueError, httpx.HTTPError) as e:
            raise HTTPException(400, f"Telegram rejected the token: {e}")
        set_setting(db, "telegram_token", token)
        set_setting(db, "telegram_chat_id", chat_id)
        if chat_id:
            ok = await send_telegram_message(
                token, chat_id,
                f"✅ <b>{get_setting(db, 'company_name')}</b> manager account connected!\n"
                f"Every new booking will arrive here. Masters get their own alerts "
                f"once you add their personal chat ID in the Team section.")
            if not ok:
                raise HTTPException(400, "Token is valid but could not message the chat. "
                                         "Open a chat with your bot first and press /start.")
        return {"ok": True, "bot": bot.get("username", "")}
    set_setting(db, "telegram_token", "")
    set_setting(db, "telegram_chat_id", "")
    return {"ok": True, "bot": ""}


# --- services CRUD ----------------------------------------------------------

@app.get("/api/admin/services", response_model=list[ServiceOut])
def admin_services(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    return db.query(Service).order_by(Service.id).all()


@app.post("/api/admin/services", response_model=ServiceOut)
def add_service(payload: ServiceIn, db: Session = Depends(get_db),
                _: bool = Depends(require_admin)):
    svc = Service(**payload.model_dump())
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return svc


@app.delete("/api/admin/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db),
                   _: bool = Depends(require_admin)):
    svc = db.query(Service).filter(Service.id == service_id).first()
    if not svc:
        raise HTTPException(404, "Service not found")
    svc.active = False
    db.commit()
    return {"ok": True}


# --- staff CRUD + avatars -----------------------------------------------------

@app.get("/api/admin/staff", response_model=list[StaffOut])
def admin_staff(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    return db.query(Staff).order_by(Staff.id).all()


@app.post("/api/admin/staff", response_model=StaffOut)
def add_staff(payload: StaffIn, db: Session = Depends(get_db),
              _: bool = Depends(require_admin)):
    member = Staff(**payload.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@app.patch("/api/admin/staff/{staff_id}", response_model=StaffOut)
def update_staff(staff_id: int, payload: StaffIn, db: Session = Depends(get_db),
                 _: bool = Depends(require_admin)):
    member = db.query(Staff).filter(Staff.id == staff_id).first()
    if not member:
        raise HTTPException(404, "Master not found")
    for k, v in payload.model_dump().items():
        setattr(member, k, v)
    db.commit()
    db.refresh(member)
    return member


@app.post("/api/admin/staff/{staff_id}/avatar")
async def staff_avatar(staff_id: int, file: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       _: bool = Depends(require_admin)):
    member = db.query(Staff).filter(Staff.id == staff_id).first()
    if not member:
        raise HTTPException(404, "Master not found")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    url = save_image_square(data, "avatar")
    member.avatar_url = url
    db.commit()
    return {"avatar_url": url}


@app.delete("/api/admin/staff/{staff_id}")
def delete_staff(staff_id: int, db: Session = Depends(get_db),
                 _: bool = Depends(require_admin)):
    member = db.query(Staff).filter(Staff.id == staff_id).first()
    if not member:
        raise HTTPException(404, "Master not found")
    member.active = False
    db.commit()
    return {"ok": True}


# --- bookings management -----------------------------------------------------

@app.get("/api/admin/bookings", response_model=list[BookingOut])
def admin_bookings(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    rows = db.query(Booking).order_by(Booking.start_time.desc()).limit(500).all()
    return [booking_out(b) for b in rows]


@app.patch("/api/admin/bookings/{booking_id}/status")
def update_status(booking_id: int, payload: StatusUpdate,
                  background: BackgroundTasks,
                  db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise HTTPException(404, "Booking not found")
    b.status = payload.status
    db.commit()
    if payload.status == "Cancelled":
        token = get_setting(db, "telegram_token")
        if token:
            msg = format_cancel_message(get_setting(db, "company_name", "Salon"),
                                        b.client_name,
                                        b.service.name if b.service else "—",
                                        b.start_time,
                                        b.staff.name if b.staff else "Any", False)
            targets = {get_setting(db, "telegram_chat_id"),
                       b.staff.telegram_chat_id if b.staff else ""}
            for chat in {c for c in targets if c}:
                background.add_task(send_telegram_message, token, chat, msg)
    return {"ok": True, "status": b.status}


# --- waitlist admin -----------------------------------------------------------

@app.get("/api/admin/waitlist", response_model=list[WaitlistOut])
def admin_waitlist(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    rows = db.query(Waitlist).filter(Waitlist.active.is_(True)) \
             .order_by(Waitlist.created_at.desc()).limit(200).all()
    return [WaitlistOut(
        id=w.id, client_name=w.client_name, phone=w.phone,
        contact_method=w.contact_method, contact_handle=w.contact_handle or "",
        service_name=w.service.name if w.service else "Any",
        staff_name=w.staff.name if w.staff else "Any",
        date_pref=w.date_pref or "", created_at=w.created_at) for w in rows]


@app.delete("/api/admin/waitlist/{entry_id}")
def resolve_waitlist(entry_id: int, db: Session = Depends(get_db),
                     _: bool = Depends(require_admin)):
    w = db.query(Waitlist).filter(Waitlist.id == entry_id).first()
    if not w:
        raise HTTPException(404, "Entry not found")
    w.active = False
    db.commit()
    return {"ok": True}


# --- statistics ---------------------------------------------------------------

@app.get("/api/admin/stats")
def admin_stats(db: Session = Depends(get_db), _: bool = Depends(require_admin)):
    now = datetime.now()
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d30, d7 = now - timedelta(days=30), now - timedelta(days=7)
    currency = get_setting(db, "currency", "PLN")

    rows = db.query(Booking).all()
    price_of = {s.id: s.price for s in db.query(Service).all()}
    name_of = {s.id: s.name for s in db.query(Service).all()}
    staff_of = {s.id: s.name for s in db.query(Staff).all()}

    active = [b for b in rows if b.status in ("New", "Confirmed")]
    done = [b for b in rows if b.status == "Completed"]
    rev = lambda bs: round(sum(price_of.get(b.service_id, 0) for b in bs), 2)

    status_counts = {"New": 0, "Confirmed": 0, "Completed": 0, "Cancelled": 0}
    for b in rows:
        status_counts[b.status] = status_counts.get(b.status, 0) + 1

    daily = []
    for i in range(13, -1, -1):
        d0 = today0 - timedelta(days=i)
        d1 = d0 + timedelta(days=1)
        day_b = [b for b in rows if d0 <= b.start_time < d1 and b.status != "Cancelled"]
        daily.append({"date": d0.strftime("%d %b"), "count": len(day_b),
                      "revenue": rev(day_b)})

    svc_agg = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    for b in rows:
        if b.status == "Cancelled":
            continue
        a = svc_agg[name_of.get(b.service_id, "—")]
        a["count"] += 1
        a["revenue"] += price_of.get(b.service_id, 0)
    top_services = sorted(({"name": k, **v} for k, v in svc_agg.items()),
                          key=lambda x: -x["count"])[:5]
    for t in top_services:
        t["revenue"] = round(t["revenue"], 2)

    staff_agg = defaultdict(lambda: {"count": 0, "revenue": 0.0})
    for b in rows:
        if b.status == "Cancelled" or not b.staff_id:
            continue
        a = staff_agg[staff_of.get(b.staff_id, "—")]
        if b.start_time >= d30:
            a["count"] += 1
        if b.status == "Completed" and b.start_time >= d30:
            a["revenue"] += price_of.get(b.service_id, 0)
    staff_board = sorted(({"name": k, "count": v["count"],
                           "revenue": round(v["revenue"], 2)}
                          for k, v in staff_agg.items()), key=lambda x: -x["count"])

    hours = defaultdict(int)
    for b in rows:
        if b.status != "Cancelled":
            hours[b.start_time.hour] += 1
    peak_hours = [{"hour": h, "count": hours.get(h, 0)} for h in range(24)]

    phones = defaultdict(int)
    for b in rows:
        if b.status != "Cancelled":
            phones[digits(b.phone)] += 1
    total_clients = len(phones)
    repeat = round(100 * sum(1 for c in phones.values() if c > 1) / total_clients) if total_clients else 0

    return {
        "currency": currency,
        "today_count": sum(1 for b in active if today0 <= b.start_time < today0 + timedelta(days=1)),
        "upcoming_7d": sum(1 for b in active if now <= b.start_time <= now + timedelta(days=7)),
        "revenue_7d": rev([b for b in done if b.start_time >= d7]),
        "revenue_30d": rev([b for b in done if b.start_time >= d30]),
        "total_clients": total_clients,
        "repeat_rate": repeat,
        "new_waiting": status_counts.get("New", 0),
        "status_counts": status_counts,
        "daily": daily,
        "top_services": top_services,
        "staff_board": staff_board,
        "peak_hours": peak_hours,
    }


# ---------------------------------------------------------------------------
# Frontend routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))


@app.get("/admin", include_in_schema=False)
def admin():
    return FileResponse(os.path.join(BASE_DIR, "templates", "admin.html"))


# v5: imports register models before lifespan calls create_all.
from outreach import build_router
app.include_router(build_router(require_admin))
