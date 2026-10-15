"""SQLite/SQLAlchemy 2.0 layer with WAL, busy_timeout, auto-migration."""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, Index, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy import event

DATA_DIR = Path(os.environ.get("DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "salon.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
    pool_pre_ping=True,
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(String(400), default="")
    price = Column(Float, nullable=False, default=0.0)
    duration_min = Column(Integer, nullable=False, default=30)
    niche = Column(String(40), default="all")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Staff(Base):
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    role = Column(String(120), default="Master")
    bio = Column(String(400), default="")
    avatar = Column(String(400), default="")
    work_hours = Column(String(120), default="09:00-20:00")
    telegram_chat_id = Column(String(120), default="")
    telegram_handle = Column(String(120), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    client_name = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False, index=True)
    contact_method = Column(String(20), default="call")  # call/wa/tg
    contact_value = Column(String(120), default="")
    service_id = Column(Integer, ForeignKey("services.id"))
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    duration_min = Column(Integer, nullable=False)
    price = Column(Float, default=0.0)
    currency = Column(String(8), default="PLN")
    status = Column(String(20), default="New", index=True)  # New/Confirmed/Completed/Cancelled
    notes = Column(String(600), default="")
    is_demo = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    service = relationship("Service")
    staff = relationship("Staff")


class Waitlist(Base):
    __tablename__ = "waitlist"
    id = Column(Integer, primary_key=True)
    client_name = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    desired_date = Column(String(40), default="")
    status = Column(String(20), default="Open")
    notes = Column(String(400), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(80), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DemoLink(Base):
    __tablename__ = "demo_links"
    code = Column(String(40), primary_key=True)
    config_json = Column(Text, nullable=False)
    views = Column(Integer, default=0)
    first_view_at = Column(DateTime, nullable=True)
    last_view_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OutboundLead(Base):
    __tablename__ = "outbound_leads"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    niche = Column(String(40), nullable=False)
    contact = Column(String(200), nullable=False)
    contact_kind = Column(String(20), default="phone")
    status = Column(String(20), default="New", index=True)
    notes = Column(String(600), default="")
    do_not_contact = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class OutboundTemplate(Base):
    __tablename__ = "outbound_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), default="Default")
    body = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OutboundSend(Base):
    __tablename__ = "outbound_sends"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("outbound_leads.id", ondelete="CASCADE"), index=True)
    template_name = Column(String(120), default="")
    rendered = Column(Text, default="")
    channel = Column(String(20), default="wa")
    created_at = Column(DateTime, default=datetime.utcnow)


DEFAULT_SETTINGS = {
    "site_name": "Luxe Barber",
    "site_description": "Premium grooming studio in the heart of the city. Walk in, look sharp.",
    "logo_path": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "default_currency": "PLN",
    "default_language": "en",
    "working_hours": "09:00-20:00",
    "slot_step_min": 30,
    "outbound_password_hash": "",  # set on first run
}

SEED_SERVICES = [
    ("Men's Haircut", "Classic or modern cut, wash, and style.", 80.0, 45, "barber"),
    ("Beard Trim & Shape", "Precision beard sculpt with hot towel.", 50.0, 30, "barber"),
    ("Hot Shave", "Traditional straight-razor shave ritual.", 70.0, 45, "barber"),
    ("Kids Cut", "Friendly trim for ages 5–12.", 40.0, 30, "barber"),
    ("Hair Wash & Style", "Wash, blow-dry and finish.", 35.0, 20, "beauty"),
]

SEED_STAFF = [
    ("Alex Kowalski", "Senior Barber", "10 years of experience, classic techniques.", "09:00-20:00"),
    ("Marta Nowak", "Top Stylist", "Color specialist and modern cuts.", "10:00-19:00"),
    ("Piotr Wiśniewski", "Beard Master", "Beard shaping and hot shaves.", "11:00-20:00"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    _ensure_columns()
    with SessionLocal() as s:
        if not s.query(Setting).count():
            for k, v in DEFAULT_SETTINGS.items():
                s.add(Setting(key=k, value=v))
        if not s.query(Service).count():
            for n, d, p, dur, niche in SEED_SERVICES:
                s.add(Service(name=n, description=d, price=p, duration_min=dur, niche=niche))
        if not s.query(Staff).count():
            for n, role, bio, hours in SEED_STAFF:
                s.add(Staff(name=n, role=role, bio=bio, work_hours=hours))
        if not s.query(OutboundTemplate).count():
            s.add(OutboundTemplate(
                name="Default",
                body="Hi {name}! I built a quick personalized preview for your {niche} business: {link}",
            ))
        s.commit()


def _ensure_columns() -> None:
    """Add columns when migrating from older DBs (idempotent)."""
    expected = {
        "bookings": {
            "contact_method": "VARCHAR(20) DEFAULT 'call'",
            "contact_value": "VARCHAR(120) DEFAULT ''",
            "currency": "VARCHAR(8) DEFAULT 'PLN'",
            "is_demo": "BOOLEAN DEFAULT 0",
            "updated_at": "TIMESTAMP",
        },
        "settings": {"updated_at": "TIMESTAMP"},
        "outbound_leads": {
            "do_not_contact": "BOOLEAN DEFAULT 0",
            "updated_at": "TIMESTAMP",
            "contact_kind": "VARCHAR(20) DEFAULT 'phone'",
        },
        "outbound_templates": {"updated_at": "TIMESTAMP"},
    }
    with engine.begin() as conn:
        for table, cols in expected.items():
            try:
                res = conn.exec_driver_sql(f"PRAGMA table_info({table})")
                existing = {row[1] for row in res.fetchall()}
            except Exception:
                continue
            for col, decl in cols.items():
                if col not in existing:
                    try:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                    except Exception:
                        pass
