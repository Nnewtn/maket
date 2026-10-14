"""Telegram notification service — fully async, never blocks the booking flow.

Routing model:
  - one bot (token) per salon, created via @BotFather
  - MANAGER chat id lives in settings -> receives EVERY booking + cancellations
  - each STAFF member has their own telegram_chat_id -> personal mini-account,
    receives only bookings assigned to them (chosen or auto-assigned)
"""
import httpx

API_BASE = "https://api.telegram.org/bot{token}"


async def verify_bot_token(token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(API_BASE.format(token=token) + "/getMe")
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(data.get("description", "Invalid bot token"))
        return data["result"]


async def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Failures are swallowed — a broken Telegram config must never
    break the booking flow itself."""
    if not token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                API_BASE.format(token=token) + "/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            return resp.status_code == 200
    except Exception:
        return False


def format_booking_message(company: str, client_name: str, phone: str,
                           contact_method: str, contact_handle: str,
                           service_name: str, price: float, currency: str,
                           start, duration: int, staff_name: str) -> str:
    contact_line = f"📲 Preferred contact: {contact_method}"
    if contact_handle:
        contact_line += f" (<code>{contact_handle}</code>)"
    return (
        f"💈 <b>New booking — {company}</b>\n\n"
        f"👤 Client: <b>{client_name}</b>\n"
        f"📞 Phone: <code>{phone}</code>\n"
        f"{contact_line}\n"
        f"✂️ Service: {service_name} ({price:.0f} {currency}, {duration} min)\n"
        f"🧑‍🎨 Master: <b>{staff_name}</b>\n"
        f"🗓 When: <b>{start.strftime('%d %b %Y, %H:%M')}</b>\n\n"
        f"Open the CRM to confirm or cancel."
    )


def format_cancel_message(company: str, client_name: str, service_name: str,
                          start, staff_name: str, by_client: bool) -> str:
    who = "by the CLIENT (self-service)" if by_client else "by the salon"
    return (
        f"❌ <b>Booking cancelled — {company}</b>\n\n"
        f"👤 {client_name} · {service_name}\n"
        f"🧑‍🎨 Master: {staff_name}\n"
        f"🗓 Slot now free: <b>{start.strftime('%d %b %Y, %H:%M')}</b>\n"
        f"ℹ️ Cancelled {who}."
    )
