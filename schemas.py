"""Pydantic schemas — strict input validation at the API boundary."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

CONTACT_METHODS = "^(Call|WhatsApp|Telegram)$"
CURRENCIES = "^(PLN|USD|EUR)$"


class BookingCreate(BaseModel):
    client_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=25)
    service_id: int = Field(gt=0)
    staff_id: int = Field(default=0, ge=0)          # 0 = "any available master"
    start_time: datetime
    contact_method: str = Field(default="Call", pattern=CONTACT_METHODS)
    contact_handle: str = Field(default="", max_length=80)


class BookingOut(BaseModel):
    id: int
    client_name: str
    phone: str
    contact_method: str
    contact_handle: str
    service_id: int
    service_name: str
    staff_id: Optional[int]
    staff_name: str
    start_time: datetime
    end_time: datetime
    status: str
    created_at: datetime


class WaitlistIn(BaseModel):
    client_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=25)
    contact_method: str = Field(default="Call", pattern=CONTACT_METHODS)
    contact_handle: str = Field(default="", max_length=80)
    service_id: int = Field(default=0, ge=0)
    staff_id: int = Field(default=0, ge=0)
    date_pref: str = Field(default="", max_length=10)


class WaitlistOut(BaseModel):
    id: int
    client_name: str
    phone: str
    contact_method: str
    contact_handle: str
    service_name: str
    staff_name: str
    date_pref: str
    created_at: datetime


class CancelIn(BaseModel):
    phone: str = Field(min_length=7, max_length=25)


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=300)
    price: float = Field(ge=0)
    duration_min: int = Field(ge=10, le=480)


class ServiceOut(BaseModel):
    id: int
    name: str
    description: str
    price: float
    duration_min: int
    active: bool


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(default="", max_length=80)
    telegram_chat_id: str = Field(default="", max_length=40)


class StaffOut(BaseModel):
    id: int
    name: str
    role: str
    avatar_url: str = ""
    telegram_chat_id: str
    active: bool


class SiteSettingsUpdate(BaseModel):
    company_name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    opening_hours: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}-\d{2}:\d{2}$")
    slot_step: Optional[int] = Field(default=None, ge=10, le=120)
    currency: Optional[str] = Field(default=None, pattern=CURRENCIES)


class TelegramSettings(BaseModel):
    telegram_token: str = Field(default="", max_length=100)
    telegram_chat_id: str = Field(default="", max_length=40)


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=100)


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=100)
    new_password: str = Field(min_length=6, max_length=100)


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(New|Confirmed|Completed|Cancelled)$")
