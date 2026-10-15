"""Telegram notifications: manager gets every booking, masters get only their own."""
from __future__ import annotations
import logging
from html import escape
import asyncio
import httpx

log = logging.getLogger("telegram")


async def send(bot_token: str, chat_id: str, text: str) -> tuple[bool, str]:
    if not bot_token or not chat_id:
        return False, "missing bot_token or chat_id"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as cx:
            r = await cx.post(url, json=payload)
        if r.status_code == 200:
            return True, "ok"
        return False, f"{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)[:200]


def format_booking(*, booking, service, staff, sign: str = "") -> str:
    """Render booking into a beautiful HTML Telegram message."""
    parts = [
        f"<b>{sign or 'New booking'}</b>",
        f"<b>Client:</b> {escape(booking.client_name)}",
        f"<b>Phone:</b> <code>{escape(booking.phone)}</code>",
    ]
    if booking.contact_method and booking.contact_value:
        kind = {"call": "Phone", "wa": "WhatsApp", "tg": "Telegram"}[booking.contact_method]
        parts.append(f"<b>{kind}:</b> {escape(booking.contact_value)}")
    parts.append(f"<b>Service:</b> {escape(service.name) if service else '—'}")
    if staff:
        parts.append(f"<b>Master:</b> {escape(staff.name)}")
    parts.append(f"<b>Date:</b> {booking.starts_at:%Y-%m-%d %H:%M}")
    if booking.price:
        parts.append(f"<b>Price:</b> {booking.price} {booking.currency}")
    if booking.notes:
        parts.append(f"<b>Notes:</b> {escape(booking.notes)}")
    return "\n".join(parts)


async def notify_booking(setting_token: str, manager_chat: str, staff_chat: str | None,
                        booking, service, staff) -> None:
    msg = format_booking(booking=booking, service=service, staff=staff, sign="New booking")
    ok1, e1 = await send(setting_token, manager_chat, msg)
    if not ok1:
        log.warning("manager TG failed: %s", e1)
    if staff_chat and staff_chat != manager_chat:
        msg2 = format_booking(booking=booking, service=service, staff=staff, sign="Your booking")
        ok2, e2 = await send(setting_token, staff_chat, msg2)
        if not ok2:
            log.warning("staff TG failed: %s", e2)


def schedule_notify(background_tasks, **kw) -> None:
    """Schedule a Telegram notification on FastAPI BackgroundTasks."""
    background_tasks.add_task(asyncio.run, _run_notify(**kw))


async def _run_notify(**kw) -> None:
    try:
        await notify_booking(**kw)
    except Exception as e:  # never let a worker die
        log.warning("notify task crashed: %s", e)
