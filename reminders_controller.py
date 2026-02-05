from typing import Tuple, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import dateparser
import re

from db import insert_reminder, list_reminders, mark_reminder_sent
from scheduler import schedule_job

TZ = ZoneInfo("America/Costa_Rica")


# =========================
# Time parsing helpers
# =========================

def parse_relative_time_fallback(text: str) -> Optional[datetime]:
    """
    Fallback manual para expresiones tipo:
    - en 1 minuto / en 5 minutos
    - en 30 segundos
    - en 2 horas
    """
    t = text.lower().strip()

    match = re.search(
        r"\ben\s+(\d+)\s+(segundo|segundos|minuto|minutos|hora|horas)\b",
        t,
    )
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    now = datetime.now(tz=TZ)

    if "segundo" in unit:
        return now + timedelta(seconds=amount)
    if "minuto" in unit:
        return now + timedelta(minutes=amount)
    if "hora" in unit:
        return now + timedelta(hours=amount)

    return None


def normalize_spanish_time(text: str) -> str:
    """
    Normaliza singular en español para ayudar a dateparser.
    """
    t = text.lower()

    patterns = [
        (r"\ben un minuto\b", "en 1 minutos"),
        (r"\ben una hora\b", "en 1 horas"),
        (r"\ben un segundo\b", "en 1 segundos"),
    ]

    for pattern, repl in patterns:
        t = re.sub(pattern, repl, t)

    return t


# =========================
# Core actions
# =========================

def create_reminder(
    user_phone: str,
    reminder_text: str,
    when_text: str,
    send_fn,
) -> Tuple[bool, str]:
    """
    Crea un recordatorio.
    La IA ya decidió intent=reminder y separó texto y tiempo.
    """

    if not reminder_text or not when_text:
        return True, "❌ Falta información para crear el recordatorio."

    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "America/Costa_Rica",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    normalized_when = normalize_spanish_time(when_text)

    # 1) dateparser
    dt_local = dateparser.parse(
        normalized_when,
        settings=settings,
        languages=["es", "en"],
    )

    # 2) fallback manual
    if not dt_local:
        dt_local = parse_relative_time_fallback(normalized_when)

    if not dt_local:
        return True, "No entendí cuándo 😅\nEj: en 10 minutos, mañana a las 7pm"

    # Guardar en UTC (sin tzinfo)
    dt_utc = dt_local.astimezone(timezone.utc)
    remind_at_utc_iso = dt_utc.replace(tzinfo=None).isoformat()

    rid = insert_reminder(user_phone, reminder_text, remind_at_utc_iso)

    def job():
        send_fn(f"⏰ Recordatorio: {reminder_text}")
        mark_reminder_sent(user_phone, rid)

    schedule_job(rid, dt_utc, job)

    return True, (
        f"✅ Recordatorio guardado #{rid}\n"
        f"🗓️ {dt_local.astimezone(TZ).strftime('%Y-%m-%d %H:%M')} (CR)\n"
        f"📝 {reminder_text}"
    )


def list_user_reminders(user_phone: str) -> Tuple[bool, str]:
    items = list_reminders(user_phone, limit=10)
    if not items:
        return True, "No tenés recordatorios activos."

    lines = ["⏰ Tus recordatorios:"]
    for r in items:
        dt_utc = datetime.fromisoformat(r["remind_at_utc"]).replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(TZ)
        lines.append(
            f"• #{r['id']} | {dt_local.strftime('%Y-%m-%d %H:%M')} | {r['reminder_text']} ({r['status']})"
        )

    return True, "\n".join(lines)
