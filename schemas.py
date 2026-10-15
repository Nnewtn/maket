"""Pydantic schemas for API validation."""
from __future__ import annotations
import re
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{6,20}$")
HTTP_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
DANGEROUS_RE = re.compile(r"javascript:|data:|vbscript:", re.IGNORECASE)


def _safe_http_url(v: Optional[str]) -> Optional[str]:
    """Allow only http/https; reject javascript:, data:, vbscript:."""
    if not v:
        return v
    v = v.strip()
    if DANGEROUS_RE.search(v):
        return None
    if not HTTP_URL_RE.match(v):
        return None
    return v[:500]


def _safe_key(v: Optional[str]) -> str:
    if not v:
        return ""
    return re.sub(r"[^a-zA-Z0-9_\-]", "", v)[:60]


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=400)
    price: float = Field(ge=0)
    duration_min: int = Field(ge=5, le=600)
    niche: Literal["all", "beauty", "barber", "auto", "detailing"] = "all"


class ServicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    duration_min: Optional[int] = Field(default=None, ge=5, le=600)
    niche: Optional[Literal["all", "beauty", "barber", "auto", "detailing"]] = None
    is_active: Optional[bool] = None


class StaffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="Master", max_length=120)
    bio: str = Field(default="", max_length=400)
    avatar: str = Field(default="", max_length=400)
    work_hours: str = Field(default="09:00-20:00", max_length=120)
    telegram_chat_id: str = Field(default="", max_length=120)
    telegram_handle: str = Field(default="", max_length=120)

    @field_validator("avatar")
    @classmethod
    def check_avatar(cls, v: str) -> str:
        return _safe_http_url(v) or ""


class StaffPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[str] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None
    work_hours: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_handle: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("avatar")
    @classmethod
    def check_avatar(cls, v):
        return _safe_http_url(v) or "" if v is not None else v


class BookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_name: str = Field(min_length=1, max_length=120)
    phone: str
    contact_method: Literal["call", "wa", "tg"] = "call"
    contact_value: str = Field(default="", max_length=120)
    service_id: int
    staff_id: Optional[int] = None
    starts_at: datetime
    currency: Literal["PLN", "EUR", "USD"] = "PLN"
    quote_token: str = Field(default="", max_length=8000)
    notes: str = Field(default="", max_length=600)
    is_demo: bool = False

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        if not PHONE_RE.match(v.strip()):
            raise ValueError("Phone must be 7–20 digits, may start with + and contain spaces/dashes.")
        return v.strip()

    @field_validator("contact_value")
    @classmethod
    def check_contact(cls, v: str) -> str:
        if not v:
            return ""
        # For telegram, accept either @handle or full URL
        if v.startswith("@"):
            return _safe_key(v[1:]) and ("@" + _safe_key(v[1:])) or v[:120]
        return _safe_http_url(v) or v[:120]


class BookingStatusPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["New", "Confirmed", "Completed", "Cancelled", "NoShow"]


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_name: Optional[str] = Field(default=None, max_length=120)
    site_description: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    default_currency: Optional[Literal["PLN", "EUR", "USD"]] = None
    default_language: Optional[Literal["en", "pl"]] = None
    working_hours: Optional[str] = None
    slot_step_min: Optional[int] = Field(default=None, ge=5, le=120)

    google_maps_url: str | None = Field(default=None, max_length=500)
    daily_summary_enabled: Literal['0','1'] | None = None
    daily_summary_time: str | None = None
    business_timezone: str | None = None
    site_niche: Literal['beauty','barber','auto','detailing'] | None = None

    @field_validator('google_maps_url')
    @classmethod
    def check_google(cls,v):
        if v:
            from urllib.parse import urlparse
            u=urlparse(v)
            hosts={'google.com','www.google.com','maps.google.com','maps.app.goo.gl','g.page','goo.gl','www.google.pl','google.pl'}
            if u.scheme!='https' or u.hostname not in hosts or u.username or u.password: raise ValueError('Use an HTTPS Google Maps / g.page review link.')
        return v

    @field_validator('daily_summary_time')
    @classmethod
    def check_time(cls,v):
        if v is not None and not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',v): raise ValueError('Use HH:MM')
        return v

    @field_validator('business_timezone')
    @classmethod
    def check_zone(cls,v):
        if v:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try: ZoneInfo(v)
            except ZoneInfoNotFoundError: raise ValueError('Unknown timezone')
        return v


class DemoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: str = Field(default="", max_length=60)
    logo: Optional[str] = Field(default=None, max_length=500)
    niche: Literal["beauty", "barber", "auto", "detailing"] = "beauty"
    layout: Literal["auto", "classic", "split", "bold", "minimal", "glass", "poster", "cards"] = "auto"
    theme: Literal["auto", "light", "dark", "gold", "rose"] = "auto"
    demo: bool = True

    @field_validator("logo")
    @classmethod
    def safe_logo(cls, v):
        if v is None or v == "":
            return None
        return _safe_http_url(v)


class LeadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    niche: Literal["beauty", "barber", "auto", "detailing"]
    contact: str = Field(min_length=3, max_length=200)
    contact_kind: Optional[Literal["phone", "wa", "tg", "other"]] = "phone"
    notes: str = Field(default="", max_length=600)


class LeadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    niche: Optional[Literal["beauty", "barber", "auto", "detailing"]] = None
    contact: Optional[str] = None
    contact_kind: Optional[Literal["phone", "wa", "tg", "other"]] = None
    status: Optional[Literal["New", "Contacted", "Replied", "Converted", "Lost"]] = None
    notes: Optional[str] = None
    do_not_contact: Optional[bool] = None


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Default", max_length=120)
    body: str = Field(min_length=1, max_length=2000)


class SendLogIn(BaseModel):
    rendered: str = Field(default="", max_length=5000)
    model_config = ConfigDict(extra="forbid")
    lead_id: int
    template_name: str = Field(default="Default", max_length=120)
    channel: Literal["wa", "tg", "copy"] = "wa"


class OutboundLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=4, max_length=120)


class ImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[dict] = Field(default_factory=list)
