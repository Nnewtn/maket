"""
Database layer: SQLite via SQLAlchemy 2.0
Models: Service, Staff, Booking, Waitlist, Setting.
Hardened: WAL journal mode + busy_timeout, automatic column migration,
plus a one-click sample-data generator for sales demos.
"""
import os
import random
from datetime import datetime, timedelta

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        String, Text, create_engine, event, text)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", BASE_DIR))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "salon.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _sqlite_tuning(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(String(300), default="")
    price = Column(Float, nullable=False, default=0.0)
    duration_min = Column(Integer, nullable=False, default=60)
    active = Column(Boolean, default=True)

    bookings = relationship("Booking", back_populates="service")


class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    role = Column(String(80), default="")
    avatar_url = Column(String(200), default="")
    telegram_chat_id = Column(String(40), default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="staff")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    client_name = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)
    contact_method = Column(String(20), default="Call")
    contact_handle = Column(String(80), default="")
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(20), default="New")
    created_at = Column(DateTime, default=datetime.utcnow)

    service = relationship("Service", back_populates="bookings")
    staff = relationship("Staff", back_populates="bookings")


class Waitlist(Base):
    __tablename__ = "waitlist"

    id = Column(Integer, primary_key=True)
    client_name = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)
    contact_method = Column(String(20), default="Call")
    contact_handle = Column(String(80), default="")
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    date_pref = Column(String(10), default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    service = relationship("Service")
    staff = relationship("Staff")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(60), primary_key=True)
    value = Column(Text, default="")


DEFAULT_SETTINGS = {
    "company_name": "Glamour Studio",
    "description": "Premium beauty & barber services. Book online in 30 seconds — no phone calls, no waiting.",
    "opening_hours": "09:00-20:00",
    "slot_step": "30",
    "admin_password": "admin123",
    "telegram_token": "",
    "telegram_chat_id": "",
    "logo_url": "",
    "currency": "PLN",
}

SEED_SERVICES = [
    ("Men's Haircut", "Classic cut, wash & styling", 120.0, 45),
    ("Beard Trim & Shape", "Hot towel, razor finish", 80.0, 30),
    ("Women's Cut & Blowout", "Cut, wash & professional blowout", 180.0, 60),
    ("Full Coloring", "Premium dye, toner & treatment", 350.0, 120),
    ("Manicure", "Shape, cuticle care & polish", 140.0, 60),
]

SEED_STAFF = [
    ("Alex Kowalski", "Master Barber"),
    ("Marta Nowak", "Colorist & Stylist"),
]

FAKE_CLIENTS = [
    ("Kuba Wojciechowski", "+48 512 340 901"),
    ("Anna Zielińska", "+48 601 442 780"),
    ("Piotr Lewandowski", "+48 733 118 205"),
    ("Ewa Kamińska", "+48 509 227 114"),
    ("Michał Dąbrowski", "+48 665 903 441"),
    ("Ola Wiśniewska", "+48 788 410 662"),
    ("Tomasz Nowak", "+48 534 871 209"),
    ("Kasia Mazur", "+48 692 115 348"),
    ("Bartek Krawczyk", "+48 517 664 930"),
    ("Magda Piotrowska", "+48 785 209 416"),
]
CONTACTS = [("Call", ""), ("WhatsApp", ""), ("Telegram", "@client_tg")]


def seed_fake_data(db) -> dict:
    """Populate realistic demo data: bookings across past 14 days + next 7,
    a couple of waitlist entries. Idempotent-ish: skips if already seeded."""
    if db.query(Booking).count() >= 10:
        return {"ok": False, "detail": "Sample data already loaded"}

    services = db.query(Service).filter(Service.active.is_(True)).all()
    staff = db.query(Staff).filter(Staff.active.is_(True)).all()
    if not services or not staff:
        return {"ok": False, "detail": "No services or staff to attach bookings to"}

    rng = random.Random(42)
    now = datetime.now()
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count = 0
    for i in range(40):
        day_off = i - 28                      # -28 … +11 days
        day = today0 + timedelta(days=day_off)
        for slot_h in rng.sample(range(9, 19), rng.choice([1, 1, 2])):
            svc = rng.choice(services)
            master = rng.choice(staff)
            start = day.replace(hour=slot_h, minute=rng.choice([0, 30]))
            name, phone = rng.choice(FAKE_CLIENTS)
            method, handle = rng.choice(CONTACTS)
            if day_off < 0:
                status = rng.choice(["Completed", "Completed", "Completed", "Cancelled"])
            elif day_off == 0:
                status = rng.choice(["New", "Confirmed", "Confirmed"])
            else:
                status = rng.choice(["New", "Confirmed"])
            db.add(Booking(
                client_name=name, phone=phone,
                contact_method=method, contact_handle=handle,
                service_id=svc.id, staff_id=master.id,
                start_time=start, end_time=start + timedelta(minutes=svc.duration_min),
                status=status,
                created_at=start - timedelta(days=rng.randint(1, 6)),
            ))
            count += 1

    for name, phone in FAKE_CLIENTS[:3]:
        db.add(Waitlist(client_name=name, phone=phone,
                        contact_method="WhatsApp",
                        service_id=services[0].id, staff_id=None,
                        date_pref=(today0 + timedelta(days=2)).strftime("%Y-%m-%d")))
    db.commit()
    return {"ok": True, "bookings": count}


def get_setting(db, key: str, default: str = "") -> str:
    try:
        row = db.query(Setting).filter(Setting.key == key).first()
        return row.value if row else DEFAULT_SETTINGS.get(key, default)
    except Exception:
        return DEFAULT_SETTINGS.get(key, default)


def set_setting(db, key: str, value: str):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def _ensure_columns():
    wanted = {
        "bookings": {
            "staff_id": "INTEGER",
            "contact_method": "VARCHAR(20) DEFAULT 'Call'",
            "contact_handle": "VARCHAR(80) DEFAULT ''",
        },
        "staff": {
            "avatar_url": "VARCHAR(200) DEFAULT ''",
        },
    }
    with engine.connect() as conn:
        for table, cols in wanted.items():
            try:
                existing = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
                for col, ddl in cols.items():
                    if col not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            except Exception:
                pass
        conn.commit()


def init_db():
    Base.metadata.create_all(engine)
    _ensure_columns()
    db = SessionLocal()
    try:
        for k, v in DEFAULT_SETTINGS.items():
            if not db.query(Setting).filter(Setting.key == k).first():
                db.add(Setting(key=k, value=v))
        if db.query(Service).count() == 0:
            for name, desc, price, dur in SEED_SERVICES:
                db.add(Service(name=name, description=desc, price=price, duration_min=dur))
        if db.query(Staff).count() == 0:
            for name, role in SEED_STAFF:
                db.add(Staff(name=name, role=role))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
