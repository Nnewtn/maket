"""Short-link storage and privacy-conscious page-view telemetry. No message sending."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, update, func
from sqlalchemy.dialects.sqlite import insert

from database import Base, BASE_DIR, SessionLocal

class DemoLink(Base):
    __tablename__ = "demo_links"
    code = Column(String(24), primary_key=True)
    config_json = Column(Text, nullable=False)
    views = Column(Integer, nullable=False, default=0)
    first_view_at = Column(DateTime)
    last_view_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)

class DemoVisit(Base):
    __tablename__ = "demo_visits"
    id = Column(Integer, primary_key=True)
    code = Column(String(24), ForeignKey("demo_links.code"), nullable=False)
    visit_id = Column(String(80), nullable=False)
    __table_args__ = (UniqueConstraint("code", "visit_id"),)

class DemoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: str = Field(default="", max_length=120)
    logo: str = Field(default="", max_length=2048)
    niche: Literal["beauty", "barber", "auto", "detailing"] = "beauty"
    layout: Literal["", "classic", "split", "bold", "minimal", "glass", "poster", "cards"] = ""
    theme: Literal["", "light", "dark", "gold", "rose"] = ""
    demo: bool = True
    key: str = Field(default="", max_length=120, pattern=r"^[a-zA-Z0-9_-]*$")

    @field_validator("logo")
    @classmethod
    def safe_logo(cls, value):
        if not value:
            return value
        if re.fullmatch(r"/static/uploads/[A-Za-z0-9_-]+\.png", value):
            return value  # logo pasted/uploaded through the admin (same origin)
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Logo must be a public http(s) image URL without credentials")
        return value

class DemoBatch(BaseModel):
    items: list[DemoConfig] = Field(min_length=1, max_length=500)

class Codes(BaseModel):
    codes: list[str] = Field(max_length=500)

class Visit(BaseModel):
    visit_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")

def code_for(config):
    canonical = json.dumps(config.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:24], canonical

def link_result(row):
    return {"code": row.code, "path": f"/d/{row.code}", "views": row.views,
            "first_view_at": row.first_view_at, "last_view_at": row.last_view_at}

def build_router(require_admin):
    router = APIRouter()

    @router.post("/api/admin/demo-links", dependencies=[Depends(require_admin)])
    def create_link(payload: DemoConfig):
        code, canonical = code_for(payload)
        with SessionLocal.begin() as db:
            db.execute(insert(DemoLink).values(code=code, config_json=canonical, views=0,
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None)).on_conflict_do_nothing(index_elements=["code"]))
            return link_result(db.get(DemoLink, code))

    @router.post("/api/admin/demo-links/batch", dependencies=[Depends(require_admin)])
    def create_batch(payload: DemoBatch):
        with SessionLocal.begin() as db:
            result = []
            for item in payload.items:
                code, canonical = code_for(item)
                db.execute(insert(DemoLink).values(code=code, config_json=canonical, views=0,
                            created_at=datetime.now(timezone.utc).replace(tzinfo=None)).on_conflict_do_nothing(index_elements=["code"]))
                result.append(link_result(db.get(DemoLink, code)))
            return {"items": result}

    @router.post("/api/admin/demo-links/stats", dependencies=[Depends(require_admin)])
    def link_stats(payload: Codes):
        with SessionLocal() as db:
            rows = db.scalars(select(DemoLink).where(DemoLink.code.in_(payload.codes))).all()
            return {"items": [link_result(r) for r in rows]}

    @router.get("/d/{code}", response_class=HTMLResponse, include_in_schema=False)
    def demo_page(code: str):
        with SessionLocal() as db:
            row = db.get(DemoLink, code)
            if row is None:
                raise HTTPException(404, "Demo link not found")
            config = json.loads(row.config_json)
        config.pop("key", None)  # never publish the sender's correlation key
        config["code"] = code
        data = json.dumps(config, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        html = Path(BASE_DIR, "templates", "index.html").read_text()
        html = html.replace("<head>", '<head><meta name="robots" content="noindex,nofollow"><script>window.__DEMO_CONFIG__=' + data + ';</script>', 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                         "X-Robots-Tag": "noindex, nofollow"})

    @router.post("/api/demo-links/{code}/view", status_code=204)
    def track_view(code: str, payload: Visit, request: Request):
        # Only visible JS-loaded pages are counted. GET, HEAD, image previews and admin
        # iframe previews do not count. No IP addresses, user agents or cookies stored.
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
            raise HTTPException(403, "Cross-origin tracking rejected")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with SessionLocal.begin() as db:
            if db.get(DemoLink, code) is None:
                raise HTTPException(404, "Demo link not found")
            result = db.execute(insert(DemoVisit).values(code=code, visit_id=payload.visit_id)
                       .on_conflict_do_nothing(index_elements=["code", "visit_id"]))
            if result.rowcount:
                db.execute(update(DemoLink).where(DemoLink.code == code).values(
                    views=DemoLink.views + 1,
                    first_view_at=func.coalesce(DemoLink.first_view_at, now),
                    last_view_at=now))
        return None

    @router.get("/admin/outbound", include_in_schema=False)
    def outbound_page():
        return HTMLResponse(Path(BASE_DIR, "templates", "outbound.html").read_text(),
                            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

    return router
