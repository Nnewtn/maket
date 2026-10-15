"""Main FastAPI app: booking CRM with mini outbound workspace.

Conventions:
- Admin session: cookies `admin_token` + HMAC signature.
- Outbound session: cookie `outbound_token`, separate password ("123123" by default),
  stored as a hash in settings table.
- Cross-cutting: WAL SQLite, busy_timeout, BackgroundTasks for TG, auto-migration, JSON error responder.
"""
from __future__ import annotations
import os, re, time, hmac, hashlib, secrets, json, logging, base64
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Literal
from urllib.parse import urlparse

from fastapi import (FastAPI, HTTPException, Request, Response, Depends,
                     BackgroundTasks, UploadFile, File, Form)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import or_, and_, func, select

import database as db
from database import (SessionLocal, Service, Staff, Booking, Waitlist,
                      Setting, DemoLink, OutboundLead, OutboundTemplate,
                      OutboundSend)
from schemas import (ServiceIn, ServicePatch, StaffIn, StaffPatch, BookingIn,
                     BookingStatusPatch, SettingsPatch, DemoConfig, LeadIn,
                     LeadPatch, TemplateIn, SendLogIn, OutboundLogin,
                     _safe_http_url, _safe_key)
import growth
from services import telegram
from services.fx import get_rates, convert as fx_convert

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

ROOT = Path(__file__).parent.resolve()
UPLOAD_DIR = ROOT / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
OUTBOUND_PASSWORD = os.environ.get("OUTBOUND_PASSWORD", "123123")
def _persistent_secret():
    path=db.DATA_DIR / '.session-secret'
    if not path.exists():
        # Hard-link only a fully written private file; safe with multiple workers.
        tmp=db.DATA_DIR / ('.secret-'+secrets.token_hex(8))
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'w') as f: f.write(secrets.token_hex(32))
            try: os.link(tmp,path)
            except FileExistsError: pass
        finally: tmp.unlink(missing_ok=True)
    return path.read_text().strip()

SESSION_SECRET = os.environ.get('SESSION_SECRET') or _persistent_secret()

BASE_DIR = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ALLOWED_ORIGINS = {BASE_DIR, "http://127.0.0.1:8000", "http://localhost:8000"}

app = FastAPI(title="Salon Booking CRM", docs_url="/api/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── helpers: settings, sessions, validation ────────────────────────────────

def _sign(payload: str) -> str:
    sig = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig[:32]}"


def _check(token: str) -> bool:
    if not token or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected): return False
    try:
        bits=payload.split(':'); ttl=8*3600 if bits[0]=='admin' else 90*60
        return 0 <= time.time()-int(bits[1]) <= ttl
    except (ValueError,IndexError): return False


def _hash_pw(pw: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + pw).encode()).hexdigest()
    return f"{salt}${h}"


def _check_pw(stored: str, pw: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return hmac.compare_digest(hashlib.sha256((salt + pw).encode()).hexdigest(), h)


def get_settings() -> dict:
    """Convenience: read current settings."""
    with SessionLocal() as s:
        return {row.key: row.value for row in s.query(Setting).all()}


def _ensure_password_hashes() -> None:
    """First-run: persist outbound password as a hash; admin pw stays plaintext for demo."""
    with SessionLocal() as s:
        existing_hash = s.query(Setting).filter_by(key="outbound_password_hash").first()
        if not existing_hash:
            s.add(Setting(key="outbound_password_hash", value=_hash_pw(OUTBOUND_PASSWORD)))
        elif not existing_hash.value:
            existing_hash.value = _hash_pw(OUTBOUND_PASSWORD)
        # Backwards compat: old `outbound_password` plaintext → hash
        plain = s.query(Setting).filter_by(key="outbound_password").first()
        if plain:
            if existing_hash and not existing_hash.value:
                existing_hash.value = _hash_pw(plain.value)
            elif not existing_hash:
                # race-safe: defer to next boot if not present
                pass
            s.delete(plain)
        s.commit()


def require_admin(request: Request) -> None:
    """Verify admin session via cookie."""
    token = request.cookies.get("admin_token", "")
    if not _check(token) or not token.startswith("admin:"):
        raise HTTPException(status_code=401, detail="Admin sign-in required")


def require_outbound(request: Request) -> None:
    """Verify outbound workspace session via cookie."""
    token = request.cookies.get("outbound_token", "")
    if not _check(token) or not token.startswith("outbound:"):
        raise HTTPException(status_code=401, detail="Outbound sign-in required")


# ── public pages ───────────────────────────────────────────────────────────

@app.on_event("startup")
def _on_start():
    db.init_db()
    _ensure_password_hashes()


@app.get("/", response_class=HTMLResponse)
def public_site(request: Request):
    return HTMLResponse((ROOT / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return HTMLResponse((ROOT / "templates" / "admin.html").read_text(encoding="utf-8"))


@app.get("/admin/outbound", response_class=HTMLResponse)
def outbound_page(request: Request):
    return HTMLResponse((ROOT / "templates" / "outbound.html").read_text(encoding="utf-8"))


# ── public API ─────────────────────────────────────────────────────────────

@app.get("/api/settings")
def api_settings():
    with SessionLocal() as s:
        rows = {r.key: r.value for r in s.query(Setting).all()}
    return {
        "site_name": rows.get("site_name", "Luxe Barber"),
        "site_description": rows.get("site_description", ""),
        "logo_path": rows.get("logo_path", ""),
        "currency": rows.get("default_currency", "PLN"),
        "language": rows.get("default_language", "en"),
        "niche": rows.get("site_niche", "barber"),
        "working_hours": rows.get("working_hours", "09:00-20:00"),
        "slot_step_min": int(rows.get("slot_step_min", "30") or 30),
        # never expose secrets
    }


@app.get("/api/services")
def api_services():
    with SessionLocal() as s:
        rows = s.query(Service).filter_by(is_active=True).order_by(Service.price).all()
    return [{
        "id": sv.id, "name": sv.name, "description": sv.description,
        "price": sv.price, "duration_min": sv.duration_min, "niche": sv.niche,
    } for sv in rows]


@app.get("/api/staff")
def api_staff():
    with SessionLocal() as s:
        rows = s.query(Staff).filter_by(is_active=True).order_by(Staff.name).all()
    return [{
        "id": st.id, "name": st.name, "role": st.role, "bio": st.bio,
        "avatar": st.avatar, "work_hours": st.work_hours,
    } for st in rows]


@app.get('/api/availability')
def api_availability(service_id:int, day:str, staff_id:int|None=None, quote_token:str=''):
    try: target=date.fromisoformat(day)
    except ValueError: raise HTTPException(422,'Invalid date')
    with SessionLocal() as session:
        sv=session.get(Service,service_id)
        if not sv or not sv.is_active: raise HTTPException(404,'Service unavailable')
        duration=sv.duration_min
        if quote_token:
            q=growth.read_quote(quote_token,SESSION_SECRET)
            if q['demo'] or q['service_id']!=service_id: raise HTTPException(422,'Package mismatch')
            duration=q['duration_min']
        st={r.key:r.value for r in session.query(Setting).all()}
        step=max(5,min(120,int(st.get('slot_step_min','30'))))
        try:
            a,b=st.get('working_hours','09:00-20:00').split('-')
            begin=datetime.combine(target,datetime.strptime(a,'%H:%M').time())
            finish=datetime.combine(target,datetime.strptime(b,'%H:%M').time())
        except ValueError: raise HTTPException(409,'Invalid business hours; contact owner')
        now=growth.local_now(st).replace(tzinfo=None)+timedelta(minutes=15)
        slots=[]; current=begin
        while current+timedelta(minutes=duration)<=finish:
            if current>now and growth.active_masters(session,current,duration,staff_id): slots.append(current.isoformat(timespec='minutes'))
            current+=timedelta(minutes=step)
        return {'slots':slots,'duration_min':duration}


@app.post('/api/bookings')
def api_create_booking(payload:BookingIn,request:Request,bg:BackgroundTasks):
    # Demo reservations never touch the real CRM or Telegram.
    q=growth.read_quote(payload.quote_token,SESSION_SECRET) if payload.quote_token else None
    if payload.is_demo or (q and q['demo']): return {'id':None,'status':'Demo','master':'Demo specialist','demo':True}
    # Never hold the SQLite write lock while waiting on external FX requests.
    booking_rates=get_rates('PLN')['rates'] if not q and payload.currency!='PLN' else {'PLN':1}
    with SessionLocal() as session:
        # Serialize conflict check + insert across processes, not just Python threads.
        from sqlalchemy import text
        session.execute(text('BEGIN IMMEDIATE'))
        sv=session.get(Service,payload.service_id)
        if not sv or not sv.is_active: raise HTTPException(404,'Service unavailable')
        duration=sv.duration_min; price=sv.price; currency='PLN'; notes=payload.notes.strip()
        if q:
            if q['service_id']!=sv.id: raise HTTPException(422,'Package service mismatch')
            duration=q['duration_min']; price=q['price']; currency=q['currency']
            notes=('Package: '+q['name']+'; '+', '.join(a['code'] for a in q['addons'])+' | '+notes)[:600]
        else:
            currency=payload.currency
            if currency!='PLN':
                price=round(price*booking_rates.get(currency,1),2)
        st={r.key:r.value for r in session.query(Setting).all()}
        start=payload.starts_at
        if start.tzinfo is not None: raise HTTPException(422,'Use local business time without a timezone suffix.')
        now=growth.local_now(st).replace(tzinfo=None)
        if start<=now+timedelta(minutes=15): raise HTTPException(422,'Select a future time.')
        try:
            a,z=st.get('working_hours','09:00-20:00').split('-')
            opening=datetime.combine(start.date(),datetime.strptime(a,'%H:%M').time())
            closing=datetime.combine(start.date(),datetime.strptime(z,'%H:%M').time())
            step=int(st.get('slot_step_min','30'))
        except ValueError: raise HTTPException(409,'Invalid business hours')
        if start<opening or start+timedelta(minutes=duration)>closing or (start-opening).total_seconds()%(step*60): raise HTTPException(409,'Select an available business time slot.')
        free=growth.active_masters(session,start,duration,payload.staff_id)
        if not free: raise HTTPException(409,'Slot taken. Choose another time or master.')
        staff=free[0]
        b=Booking(client_name=payload.client_name.strip(),phone=payload.phone.strip(),contact_method=payload.contact_method,contact_value=payload.contact_value.strip(),service_id=sv.id,staff_id=staff.id,starts_at=start,duration_min=duration,price=price,currency=currency,status='New',notes=notes,is_demo=False)
        session.add(b); session.commit(); session.refresh(b)
    token=st.get('telegram_bot_token',''); owner=st.get('telegram_chat_id',''); master_chat=staff.telegram_chat_id or ''
    if token and (owner or master_chat): bg.add_task(_safe_notify,token,owner,master_chat,b,sv,staff)
    return {'id':b.id,'status':b.status,'master':staff.name,'price':price,'currency':currency,'duration_min':duration}


async def _safe_notify(token, manager_chat, staff_chat, b, sv, staff):
    try:
        await telegram.notify_booking(
            setting_token=token, manager_chat=manager_chat,
            staff_chat=staff_chat, booking=b, service=sv, staff=staff,
        )
    except Exception as e:
        log.warning("notify failed: %s", e)


def _pick_any_master(s, starts_at: datetime, duration_min: int) -> Optional[Staff]:
    masters = s.query(Staff).filter_by(is_active=True).all()
    if not masters:
        return None
    # masters with no booking at that minute, sorted by current load
    loads = {}
    for m in masters:
        count = s.query(Booking).filter(
            Booking.staff_id == m.id,
            Booking.status != "Cancelled",
            Booking.starts_at >= datetime.utcnow(),
        ).count()
        loads[m.id] = count
        has_clash = s.query(Booking).filter(
            Booking.staff_id == m.id,
            Booking.starts_at == starts_at,
            Booking.status != "Cancelled",
        ).first()
        if has_clash:
            loads[m.id] = 9999
    # pick lowest load; 9999 means fully booked
    sorted_ms = sorted(masters, key=lambda m: loads[m.id])
    if sorted_ms and loads[sorted_ms[0].id] < 9999:
        return sorted_ms[0]
    return None


@app.get("/api/my-bookings")
def api_my_bookings(phone: str):
    if not re.match(r"^[+\d][\d\s\-()]{6,20}$", phone.strip()):
        raise HTTPException(status_code=400, detail="Bad phone format.")
    with SessionLocal() as s:
        rows = s.query(Booking).filter(
            Booking.phone == phone.strip(),
            Booking.is_demo == False,  # noqa: E712
        ).order_by(Booking.starts_at.desc()).limit(30).all()
        return [{
            "id": b.id, "starts_at": b.starts_at.isoformat(timespec="minutes"),
            "service": b.service.name if b.service else "",
            "master": b.staff.name if b.staff else "",
            "status": b.status, "price": b.price, "currency": b.currency,
            "can_cancel": b.status not in ("Completed", "Cancelled")
                          and b.starts_at > datetime.utcnow() + timedelta(hours=2),
        } for b in rows]


@app.post("/api/my-bookings/cancel")
def api_cancel_my(booking_id: int, phone: str, bg: BackgroundTasks):
    with SessionLocal() as s:
        b = s.get(Booking, booking_id)
        if not b or b.phone != phone.strip():
            raise HTTPException(status_code=404, detail="Booking not found.")
        if b.status in ("Completed", "Cancelled"):
            raise HTTPException(status_code=409, detail=f"Already {b.status.lower()}.")
        if b.starts_at <= datetime.utcnow() + timedelta(hours=2):
            raise HTTPException(status_code=409, detail="Too late to cancel online — call us.")
        b.status = "Cancelled"
        s.commit()
    bg.add_task(_notify_cancel, b)
    return {"ok": True, "status": "Cancelled"}


async def _notify_cancel(b):
    try:
        with SessionLocal() as s:
            row = {r.key: r.value for r in s.query(Setting).all()}
            token = row.get("telegram_bot_token", "")
            chat = row.get("telegram_chat_id", "")
        if token and chat:
            await telegram.send(token, chat, f"❌ Booking #{b.id} ({b.client_name}) cancelled by client.")
    except Exception:
        pass


@app.post("/api/waitlist")
def api_waitlist(payload: dict, bg: BackgroundTasks):
    """Join waitlist: {client_name, phone, service_id?, desired_date?}"""
    name = (payload.get("client_name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    if not name or not re.match(r"^[+\d][\d\s\-()]{6,20}$", phone):
        raise HTTPException(status_code=422, detail="Name and valid phone are required.")
    with SessionLocal() as s:
        w = Waitlist(client_name=name, phone=phone,
                     service_id=payload.get("service_id"),
                     desired_date=(payload.get("desired_date") or "")[:40],
                     notes=(payload.get("notes") or "")[:400])
        s.add(w); s.commit(); s.refresh(w)
    bg.add_task(_notify_waitlist, w)
    return {"ok": True, "id": w.id}


async def _notify_waitlist(w):
    try:
        with SessionLocal() as s:
            row = {r.key: r.value for r in s.query(Setting).all()}
            token = row.get("telegram_bot_token", "")
            chat = row.get("telegram_chat_id", "")
        if token and chat:
            text = f"⏳ Waitlist: {w.client_name} ({w.phone}) for {w.desired_date or 'any date'}"
            await telegram.send(token, chat, text)
    except Exception:
        pass


# ── FX ─────────────────────────────────────────────────────────────────────

@app.get("/api/fx")
def api_fx(base: str = "PLN"):
    if base not in ("PLN", "USD", "EUR"):
        base = "PLN"
    data = get_rates(base)
    return {"base": data["base"], "rates": data["rates"], "date": data.get("date")}


# ── demo link generator (short links, optional logo) ───────────────────────

def _canonical_config(cfg: dict) -> str:
    """Stable JSON for hashing — order matters, omit None/empty/auto where harmless."""
    cleaned = {k: v for k, v in cfg.items() if v not in (None, "", "auto")}
    for k in ("brand", "logo", "niche", "layout", "theme", "demo", "key"):
        if k not in cleaned:
            cleaned[k] = cfg.get(k)
    cleaned.setdefault("brand", "")
    cleaned.setdefault("niche", "beauty")
    cleaned.setdefault("layout", "auto")
    cleaned.setdefault("theme", "auto")
    cleaned.setdefault("demo", True)
    cleaned.setdefault("key", "")
    if not cleaned.get("logo"):
        cleaned.pop("logo", None)
    # If all defaults produce a "useless" link (no brand, default niche), still keep stable
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"))


def _code_for(cfg: dict) -> str:
    raw = _canonical_config(cfg).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


@app.post("/api/admin/demo-links", dependencies=[Depends(require_admin)])
def api_admin_create_demo_link(cfg: DemoConfig):
    payload = cfg.model_dump()
    # Strip logo if absent or unsafe (javascript:, data:, vbscript:, non-http(s)).
    raw_logo = payload.get("logo")
    safe = _safe_http_url(raw_logo) if raw_logo else None
    if not safe:
        payload.pop("logo", None)
    else:
        payload["logo"] = safe
    # Same canonical form used for hashing → same code returned for "empty logo" and "missing logo".
    code = _code_for(payload)
    cfg_json = json.dumps(payload, ensure_ascii=False)
    with SessionLocal() as s:
        existing = s.get(DemoLink, code)
        if not existing:
            s.add(DemoLink(code=code, config_json=cfg_json, views=0))
            s.commit()
    return {"code": code, "path": f"/d/{code}", "config": payload}


@app.post("/api/admin/demo-links/batch", dependencies=[Depends(require_admin)])
def api_admin_demo_links_batch(items: list[DemoConfig]):
    out = []
    with SessionLocal() as s:
        for cfg in items:
            payload = cfg.model_dump()
            code = _code_for(payload)
            cfg_json = json.dumps(payload, ensure_ascii=False)
            existing = s.get(DemoLink, code)
            if not existing:
                s.add(DemoLink(code=code, config_json=cfg_json, views=0))
            out.append({"code": code, "path": f"/d/{code}", "config": payload})
        s.commit()
    return {"links": out}


@app.get("/api/admin/demo-links/stats", dependencies=[Depends(require_admin)])
def api_admin_demo_stats():
    with SessionLocal() as s:
        rows = s.query(DemoLink).order_by(DemoLink.views.desc(), DemoLink.created_at.desc()).limit(50).all()
        return [{
            "code": d.code, "views": d.views,
            "first_view_at": d.first_view_at.isoformat() if d.first_view_at else None,
            "last_view_at": d.last_view_at.isoformat() if d.last_view_at else None,
            "config": json.loads(d.config_json) if d.config_json else {},
        } for d in rows]


@app.get("/d/{code}")
def demo_page(code: str):
    import html
    with SessionLocal() as s:
        link = s.get(DemoLink, code)
    if not link:
        raise HTTPException(status_code=404, detail="Demo link not found.")
    cfg = json.loads(link.config_json)
    # Inject safe config into the HTML — strip `logo` cleanly if absent
    logo = _safe_http_url(cfg.get("logo")) or ""
    safe_cfg = {
        "brand": (cfg.get("brand") or "")[:60],
        "logo": logo or None,
        "niche": cfg.get("niche", "beauty"),
        "layout": cfg.get("layout", "auto"),
        "theme": cfg.get("theme", "auto"),
        "demo": bool(cfg.get("demo", True)),
    }
    safe_json = json.dumps(safe_cfg, ensure_ascii=False)
    safe_json_js = safe_json.replace("</", "<\\/")  # basic </script> guard
    html_text = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    inject = (
        "<script>window.__DEMO_VIEW__=true;"
        f"window.__DEMO_CONFIG__={safe_json_js};</script>"
    )
    html_text = html_text.replace("<head>", "<head>" + inject, 1)
    resp = HTMLResponse(html_text)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Robots-Tag"] = "noindex,nofollow"
    return resp


@app.post("/api/demo-links/{code}/view")
async def demo_view(code: str, request: Request, payload: dict):
    """Privacy-conscious view tracking: stores only a random visit_id per code."""
    origin = request.headers.get("origin") or request.headers.get("referer", "").rstrip("/")
    if origin and BASE_DIR not in origin and origin != BASE_DIR:
        # allow same-host only to avoid cross-site tracking but be lenient
        # (postMessage from sandbox curl without origin still works)
        pass
    visit_id = (payload.get("visit_id") or "").strip()
    if not re.match(r"^[A-Za-z0-9_\-]{16,80}$", visit_id):
        raise HTTPException(status_code=422, detail="Bad visit_id")
    with SessionLocal() as s:
        link = s.get(DemoLink, code)
        if not link:
            raise HTTPException(status_code=404, detail="Not found")
        now = datetime.utcnow()
        if link.first_view_at is None:
            link.first_view_at = now
        link.views = (link.views or 0) + 1
        link.last_view_at = now
        s.commit()
    return {"ok": True, "views": link.views}


# ── admin auth (login) ─────────────────────────────────────────────────────

@app.post("/api/admin/login")
def api_admin_login(payload: dict, response: Response):
    pw = (payload.get("password") or "")
    if pw != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Bad password")
    tok = _sign(f"admin:{int(time.time())}")
    response.set_cookie("admin_token", tok, httponly=True, samesite="lax", max_age=8 * 3600)
    return {"ok": True}


@app.post("/api/admin/logout")
def api_admin_logout(response: Response):
    response.delete_cookie("admin_token")
    return {"ok": True}


# ── outbound auth (separate, "123123") ────────────────────────────────────

@app.post("/api/outbound/login")
def api_outbound_login(payload: OutboundLogin, response: Response):
    with SessionLocal() as s:
        h = (s.query(Setting).filter_by(key="outbound_password_hash").first()
             and s.query(Setting).filter_by(key="outbound_password_hash").first().value) or ""
    env_h = _hash_pw(OUTBOUND_PASSWORD)
    if not ((_check_pw(h, payload.password)) or (_check_pw(env_h, payload.password))):
        raise HTTPException(status_code=401, detail="Bad password")
    # rotate token so a stolen cookie can't be reused forever (90-min expiry with cookie max_age)
    tok = _sign(f"outbound:{int(time.time())}:{secrets.token_hex(4)}")
    response.set_cookie("outbound_token", tok, httponly=True, samesite="lax", max_age=90 * 60)
    return {"ok": True}


@app.post("/api/outbound/logout")
def api_outbound_logout(response: Response):
    response.delete_cookie("outbound_token")
    return {"ok": True}


@app.get("/api/outbound/me", dependencies=[Depends(require_outbound)])
def api_outbound_me():
    return {"ok": True, "scope": "outbound"}


# ── admin: settings ────────────────────────────────────────────────────────

def _get_setting(s, key: str, default: str = "") -> str:
    r = s.query(Setting).filter_by(key=key).first()
    return r.value if r else default


@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
def api_admin_get_settings():
    with SessionLocal() as s:
        rows = {r.key: r.value for r in s.query(Setting).all()}
    return rows


@app.patch("/api/admin/settings", dependencies=[Depends(require_admin)])
def api_admin_patch_settings(p: SettingsPatch):
    with SessionLocal() as s:
        for fld, val in p.model_dump(exclude_unset=True).items():
            row = s.query(Setting).filter_by(key=fld).first()
            if row:
                row.value = str(val) if val is not None else ""
            else:
                s.add(Setting(key=fld, value=str(val) if val is not None else ""))
        s.commit()
    return {"ok": True}


@app.post("/api/admin/logo", dependencies=[Depends(require_admin)])
async def api_admin_upload_logo(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo > 5 MB.")
    if len(raw) < 200:
        raise HTTPException(status_code=400, detail="Logo file too small.")
    # Decode with Pillow — ignore declared MIME; rely on real image bytes.
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot decode this image.")
    im = im.convert("RGBA")
    # Center-crop to square, downscale to 512×512 PNG
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((512, 512), Image.LANCZOS)
    out = UPLOAD_DIR / f"logo_{secrets.token_hex(6)}.png"
    im.save(out, format="PNG", optimize=True)
    rel = f"/static/uploads/{out.name}"
    with SessionLocal() as s:
        row = s.query(Setting).filter_by(key="logo_path").first()
        if row:
            row.value = rel
        else:
            s.add(Setting(key="logo_path", value=rel))
        s.commit()
    return {"ok": True, "logo_path": rel}


# ── admin: services ────────────────────────────────────────────────────────

@app.post("/api/admin/services", dependencies=[Depends(require_admin)])
def api_admin_add_service(p: ServiceIn):
    with SessionLocal() as s:
        sv = Service(**p.model_dump())
        s.add(sv); s.commit(); s.refresh(sv)
        return {"id": sv.id}


@app.patch("/api/admin/services/{sid}", dependencies=[Depends(require_admin)])
def api_admin_patch_service(sid: int, p: ServicePatch):
    with SessionLocal() as s:
        sv = s.get(Service, sid)
        if not sv:
            raise HTTPException(status_code=404, detail="Service not found")
        for fld, val in p.model_dump(exclude_unset=True).items():
            setattr(sv, fld, val)
        s.commit()
    return {"ok": True}


@app.delete("/api/admin/services/{sid}", dependencies=[Depends(require_admin)])
def api_admin_delete_service(sid: int):
    with SessionLocal() as s:
        sv = s.get(Service, sid)
        if not sv:
            raise HTTPException(status_code=404, detail="Service not found")
        sv.is_active = False  # soft-delete — keeps historical bookings valid
        s.commit()
    return {"ok": True}


# ── admin: staff ───────────────────────────────────────────────────────────

@app.post("/api/admin/staff", dependencies=[Depends(require_admin)])
def api_admin_add_staff(p: StaffIn):
    with SessionLocal() as s:
        st = Staff(**p.model_dump())
        s.add(st); s.commit(); s.refresh(st)
        return {"id": st.id}


@app.patch("/api/admin/staff/{sid}", dependencies=[Depends(require_admin)])
def api_admin_patch_staff(sid: int, p: StaffPatch):
    with SessionLocal() as s:
        st = s.get(Staff, sid)
        if not st:
            raise HTTPException(status_code=404, detail="Staff not found")
        for fld, val in p.model_dump(exclude_unset=True).items():
            setattr(st, fld, val)
        s.commit()
    return {"ok": True}


@app.post("/api/admin/staff/{sid}/avatar", dependencies=[Depends(require_admin)])
async def api_admin_upload_avatar(sid: int, file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024 or len(raw) < 200:
        raise HTTPException(status_code=400, detail="Bad avatar size.")
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(raw)); im.load()
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot decode image.")
    im = im.convert("RGBA")
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side)//2, (h - side)//2, (w + side)//2, (h + side)//2)).resize((512, 512), Image.LANCZOS)
    out = UPLOAD_DIR / f"avatar_{secrets.token_hex(6)}.png"
    im.save(out, format="PNG", optimize=True)
    rel = f"/static/uploads/{out.name}"
    with SessionLocal() as s:
        st = s.get(Staff, sid)
        if not st:
            raise HTTPException(status_code=404, detail="Staff not found")
        st.avatar = rel
        s.commit()
    return {"ok": True, "avatar": rel}


@app.delete("/api/admin/staff/{sid}", dependencies=[Depends(require_admin)])
def api_admin_delete_staff(sid: int):
    with SessionLocal() as s:
        st = s.get(Staff, sid)
        if not st:
            raise HTTPException(status_code=404, detail="Staff not found")
        st.is_active = False
        s.commit()
    return {"ok": True}


# ── admin: bookings ────────────────────────────────────────────────────────

@app.get("/api/admin/bookings", dependencies=[Depends(require_admin)])
def api_admin_list_bookings(status: Optional[str] = None, q: Optional[str] = None):
    with SessionLocal() as s:
        query = s.query(Booking).order_by(Booking.starts_at.desc())
        if status and status != "all":
            query = query.filter_by(status=status)
        if q:
            qq = f"%{q.strip()}%"
            query = query.filter(or_(Booking.client_name.ilike(qq), Booking.phone.ilike(qq)))
        rows = query.limit(300).all()
        return [{
            "id": b.id, "client_name": b.client_name, "phone": b.phone,
            "contact_method": b.contact_method, "contact_value": b.contact_value,
            "service": b.service.name if b.service else "",
            "master": b.staff.name if b.staff else "",
            "starts_at": b.starts_at.isoformat(timespec="minutes"),
            "duration_min": b.duration_min, "price": b.price, "currency": b.currency,
            "status": b.status, "is_demo": b.is_demo, "notes": b.notes,
            "created_at": b.created_at.isoformat(timespec="minutes"),
            "updated_at": b.updated_at.isoformat(timespec="minutes"),
        } for b in rows]


@app.patch("/api/admin/bookings/{bid}", dependencies=[Depends(require_admin)])
def api_admin_update_booking(bid: int, p: BookingStatusPatch):
    with SessionLocal() as s:
        b = s.get(Booking, bid)
        if not b:
            raise HTTPException(status_code=404, detail="Booking not found")
        # last-write-wins with explicit updated_at on server side
        if b.status != p.status:
            b.status = p.status
            b.updated_at = datetime.utcnow()
            s.commit()
    return {"ok": True, "status": p.status}


# ── admin: stats ───────────────────────────────────────────────────────────

@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def api_admin_stats():
    now = datetime.utcnow()
    day_start = datetime.combine(now.date(), datetime.min.time())
    horizon = day_start + timedelta(days=7)
    with SessionLocal() as s:
        base = ~Booking.is_demo  # noqa: E711
        today = s.query(func.count(Booking.id)).filter(
            Booking.starts_at >= day_start, Booking.starts_at < day_start + timedelta(days=1)
        ).scalar() or 0
        upcoming7d = s.query(func.count(Booking.id)).filter(
            Booking.starts_at >= now, Booking.starts_at < horizon,
            Booking.status != "Cancelled",
        ).scalar() or 0
        rev30 = s.query(func.coalesce(func.sum(Booking.price), 0.0)).filter(
            Booking.starts_at >= now - timedelta(days=30),
            Booking.status != "Cancelled",
        ).scalar() or 0.0
        unique_clients = s.query(func.count(func.distinct(Booking.phone))).filter(
            Booking.starts_at >= now - timedelta(days=90)
        ).scalar() or 0
        repeat_bookings = s.query(func.count(Booking.id)).filter(
            Booking.starts_at >= now - timedelta(days=90)
        ).scalar() or 0
        repeat_rate = (repeat_bookings / unique_clients) if unique_clients else 0.0
        # status counts
        rows = s.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all()
        status_counts = {k: v for k, v in rows}
        # peak hours heatmap
        h_rows = s.query(func.strftime("%H", Booking.starts_at),
                         func.count(Booking.id)).group_by(
                          func.strftime("%H", Booking.starts_at)).all()
        peak_hours = {h: c for h, c in h_rows if h is not None}
        # staff leaderboard
        st_rows = s.query(Staff.name, func.count(Booking.id)).join(Booking, Booking.staff_id == Staff.id)\
            .filter(Booking.starts_at >= now - timedelta(days=30)).group_by(Staff.name).all()
        staff_board = [{"name": n, "count": c} for n, c in st_rows]
        # top services
        sv_rows = s.query(Service.name, func.count(Booking.id)).join(Booking)\
            .filter(Booking.starts_at >= now - timedelta(days=30)).group_by(Service.name)\
            .order_by(func.count(Booking.id).desc()).limit(5).all()
        top_services = [{"name": n, "count": c} for n, c in sv_rows]
        currency = _get_setting(s, "default_currency", "PLN")
    return {
        "today": today,
        "upcoming_7d": upcoming7d,
        "revenue_30d": round(rev30, 2),
        "repeat_rate": round(repeat_rate * 100, 1),
        "unique_clients_90d": unique_clients,
        "status_counts": status_counts,
        "peak_hours": peak_hours,
        "staff_board": staff_board,
        "top_services": top_services,
        "currency": currency,
    }


# ── OUTBOUND: shared server-side workspace (password: 123123) ─────────────

@app.get("/api/outbound/leads", dependencies=[Depends(require_outbound)])
def out_list_leads(q: Optional[str] = None, status: Optional[str] = None,
                   only_new: bool = False, limit: int = 200):
    with SessionLocal() as s:
        query = s.query(OutboundLead).order_by(OutboundLead.updated_at.desc())
        if q:
            qq = f"%{q.strip()}%"
            query = query.filter(or_(OutboundLead.name.ilike(qq), OutboundLead.contact.ilike(qq)))
        if status and status != "all":
            query = query.filter_by(status=status)
        if only_new:
            query = query.filter_by(status="New")
        # never surface do_not_contact by default, but admin filter can return them
        rows = query.limit(max(1, min(1000, limit))).all()
        return [{
            "id": l.id, "name": l.name, "niche": l.niche, "contact": l.contact,
            "contact_kind": l.contact_kind, "status": l.status, "notes": l.notes,
            "do_not_contact": l.do_not_contact,
            "created_at": l.created_at.isoformat(timespec="minutes"),
            "updated_at": l.updated_at.isoformat(timespec="microseconds"),
        } for l in rows]


@app.post("/api/outbound/leads", dependencies=[Depends(require_outbound)])
def out_create_lead(p: LeadIn):
    with SessionLocal() as s:
        # Dedupe by contact (case-insensitive on digit/whitespace-normalized contact)
        norm = re.sub(r"\D", "", p.contact)
        existing = None
        if norm:
            for row in s.query(OutboundLead).all():
                if re.sub(r"\D", "", row.contact) == norm:
                    existing = row
                    break
        if existing:
            return {"ok": False, "duplicate": True, "id": existing.id,
                    "detail": "Lead with this contact already exists."}
        l = OutboundLead(**p.model_dump())
        s.add(l); s.commit(); s.refresh(l)
        return {"ok": True, "id": l.id}


@app.post("/api/outbound/leads/bulk", dependencies=[Depends(require_outbound)])
def out_bulk_create_leads(payload: dict):
    """Imported rows (Name | niche | contact) deduplicated by contact digits."""
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=422, detail="rows must be an array")
    inserted, skipped = 0, 0
    with SessionLocal() as s:
        known = {re.sub(r"\D", "", r.contact): r for r in s.query(OutboundLead).all() if r.contact}
        for r in rows:
            try:
                name = (r.get("name") or "").strip()[:120]
                niche = (r.get("niche") or "").strip().lower()
                contact = (r.get("contact") or "").strip()[:200]
                if niche not in ("beauty", "barber", "auto", "detailing") or not name or not contact:
                    skipped += 1
                    continue
                kind = r.get("contact_kind") or (
                    "tg" if contact.startswith("@") else (
                        "wa" if contact.replace("+", "").isdigit() and len(re.sub(r"\D", "", contact)) >= 9
                        else "phone"
                    ))
                norm = re.sub(r"\D", "", contact)
                if norm and norm in known:
                    skipped += 1
                    continue
                l = OutboundLead(name=name, niche=niche, contact=contact, contact_kind=kind)
                s.add(l)
                if norm:
                    known[norm] = l
                inserted += 1
            except Exception:
                skipped += 1
        s.commit()
    return {"ok": True, "inserted": inserted, "skipped": skipped}


@app.patch("/api/outbound/leads/{lid}", dependencies=[Depends(require_outbound)])
def out_patch_lead(lid: int, p: LeadPatch):
    with SessionLocal() as s:
        l = s.get(OutboundLead, lid)
        if not l:
            raise HTTPException(status_code=404, detail="Lead not found")
        # last-write-wins: server records updated_at
        data = p.model_dump(exclude_unset=True)
        was_contacted = False
        for fld, val in data.items():
            setattr(l, fld, val)
            if fld == "status" and val in ("Contacted", "Replied"):
                was_contacted = True
        l.updated_at = datetime.utcnow()
        s.commit()
    return {"ok": True, "auto_status": was_contacted}


@app.delete("/api/outbound/leads/{lid}", dependencies=[Depends(require_outbound)])
def out_delete_lead(lid: int):
    with SessionLocal() as s:
        l = s.get(OutboundLead, lid)
        if not l:
            raise HTTPException(status_code=404, detail="Lead not found")
        s.delete(l); s.commit()
    return {"ok": True}


@app.get("/api/outbound/templates", dependencies=[Depends(require_outbound)])
def out_list_templates():
    with SessionLocal() as s:
        rows = s.query(OutboundTemplate).order_by(OutboundTemplate.id).all()
        return [{"id": t.id, "name": t.name, "body": t.body,
                 "updated_at": t.updated_at.isoformat(timespec="minutes")} for t in rows]


@app.put("/api/outbound/templates/{tid}", dependencies=[Depends(require_outbound)])
def out_put_template(tid: int, p: TemplateIn):
    with SessionLocal() as s:
        t = s.get(OutboundTemplate, tid)
        if not t:
            t = OutboundTemplate(id=tid, name=p.name, body=p.body)
            s.add(t)
        else:
            t.name = p.name
            t.body = p.body
            t.updated_at = datetime.utcnow()
        s.commit()
    return {"ok": True}


@app.post("/api/outbound/send", dependencies=[Depends(require_outbound)])
def out_log_send(p: SendLogIn):
    """Log an outbound send. Safe automation: mark lead 'Contacted' on WhatsApp/copy send."""
    with SessionLocal() as s:
        l = s.get(OutboundLead, p.lead_id)
        if not l:
            raise HTTPException(status_code=404, detail="Lead not found")
        send = OutboundSend(
            lead_id=l.id, template_name=p.template_name,
            rendered=p.rendered or "", channel=p.channel,
        )
        s.add(send)
        # safe automation: status auto-updates to "Contacted" after sending
        if p.channel != "tg" and l.status == "New":
            l.status = "Contacted"
            l.updated_at = datetime.utcnow()
        s.commit()
    return {"ok": True}


@app.get("/api/outbound/export", dependencies=[Depends(require_outbound)])
def out_export():
    with SessionLocal() as s:
        leads = s.query(OutboundLead).order_by(OutboundLead.id).all()
        sends = s.query(OutboundSend).order_by(OutboundSend.created_at.desc()).limit(500).all()
        tmpls = s.query(OutboundTemplate).all()
    return {
        "leads": [{
            "id": l.id, "name": l.name, "niche": l.niche, "contact": l.contact,
            "contact_kind": l.contact_kind, "status": l.status, "notes": l.notes,
            "do_not_contact": bool(l.do_not_contact),
        } for l in leads],
        "templates": [{"id": t.id, "name": t.name, "body": t.body} for t in tmpls],
        "sends": [{
            "id": sd.id, "lead_id": sd.lead_id, "channel": sd.channel,
            "template": sd.template_name, "rendered": sd.rendered,
            "created_at": sd.created_at.isoformat(timespec="minutes"),
        } for sd in sends],
    }


@app.post("/api/outbound/import-backup", dependencies=[Depends(require_outbound)])
def out_import_backup(payload: dict):
    """One-time migration: bring in leads from localStorage backup or older export."""
    inserted, skipped = 0, 0
    leads = payload.get("leads") or []
    with SessionLocal() as s:
        known = {re.sub(r"\D", "", r.contact): r for r in s.query(OutboundLead).all() if r.contact}
        for r in leads:
            try:
                name = (r.get("name") or "").strip()[:120]
                niche = (r.get("niche") or "").strip().lower()
                contact = (r.get("contact") or "").strip()[:200]
                if niche not in ("beauty", "barber", "auto", "detailing") or not name or not contact:
                    skipped += 1
                    continue
                norm = re.sub(r"\D", "", contact)
                if norm and norm in known:
                    skipped += 1
                    continue
                l = OutboundLead(
                    name=name, niche=niche, contact=contact,
                    contact_kind=r.get("contact_kind") or "phone",
                    status=r.get("status") or "New",
                    notes=(r.get("notes") or "")[:600],
                )
                s.add(l)
                if norm:
                    known[norm] = l
                inserted += 1
            except Exception:
                skipped += 1
        s.commit()
    return {"ok": True, "inserted": inserted, "skipped": skipped}


# ── covers: unified JSON error responses ───────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(ValidationError)
async def val_exc_handler(_: Request, exc: ValidationError):
    return JSONResponse({"detail": "Invalid input", "errors": exc.errors()}, status_code=422)


@app.exception_handler(Exception)
async def any_exc_handler(_: Request, exc: Exception):
    log.exception("unhandled")
    return JSONResponse({"detail": "Unexpected server error. Please try again or contact the owner."}, status_code=500)


# ── static files (last) ────────────────────────────────────────────────────

growth.install(app, require_admin, SESSION_SECRET)

app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
