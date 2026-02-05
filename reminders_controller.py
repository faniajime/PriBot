from typing import Tuple, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import dateparser
import re

from db import insert_reminder, list_reminders, mark_reminder_sent
from scheduler import schedule_job

TZ = ZoneInfo("America/Costa_Rica")


def parse_relative_time_fallback(text: str) -> Optional[datetime]:
    """
    Fallback manual para expresiones tipo:
    - en 1 minuto / en 5 minutos
    - en 1 segundo / en 30 segundos
    - en 1 hora / en 2 horas
    """
    t = text.lower().strip()

    match = re.search(r"\ben\s+(\d+)\s+(minuto|minutos|segundo|segundos|hora|horas)\b", t)
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
    Normaliza singular en español (un minuto/una hora) para ayudar a parseo.
    """
    t = text.lower()

    patterns = [
        (r"\ben un minuto\b", "en 1 minutos"),
        (r"\ben una minuto\b", "en 1 minutos"),
        (r"\ben 1 minuto\b", "en 1 minutos"),
        (r"\ben un segundo\b", "en 1 segundos"),
        (r"\ben 1 segundo\b", "en 1 segundos"),
        (r"\ben una hora\b", "en 1 horas"),
        (r"\ben un hora\b", "en 1 horas"),
        (r"\ben 1 hora\b", "en 1 horas"),
    ]

    for pattern, repl in patterns:
        t = re.sub(pattern, repl, t)

    return t


def handle_reminders_commands(user_phone: str, text_body: str, send_fn) -> Tuple[bool, str]:
    text = (text_body or "").strip()
    low = text.lower()

    # LISTAR
    if low == "mis recordatorios":
        items = list_reminders(user_phone, limit=10)
        if not items:
            return True, "No tenés recordatorios. Ej: recordar pagar luz mañana 7pm"

        lines = ["⏰ Tus recordatorios:"]
        for r in items:
            dt_utc = datetime.fromisoformat(r["remind_at_utc"]).replace(tzinfo=timezone.utc)
            dt_local = dt_utc.astimezone(TZ)
            lines.append(
                f"• #{r['id']} | {dt_local.strftime('%Y-%m-%d %H:%M')} | {r['reminder_text']} ({r['status']})"
            )
        return True, "\n".join(lines)

    # CREAR
    if low.startswith("recordar "):
        content = text[len("recordar "):].strip()
        if not content:
            return True, "Usá: recordar <tarea> <fecha/hora>\nEj: recordar pagar luz mañana 7pm"

        settings = {
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "America/Costa_Rica",
            "RETURN_AS_TIMEZONE_AWARE": True,
        }

        normalized = normalize_spanish_time(content)

        # 1) Intento con dateparser
        dt_local = dateparser.parse(normalized, settings=settings, languages=["es", "en"])

        # 2) Fallback manual si dateparser falla
        if not dt_local:
            dt_local = parse_relative_time_fallback(normalized)

        if not dt_local:
            return True, "No entendí la fecha/hora 😅\nEj: recordar tomar agua en 10 minutos"

        # Guardar en UTC en la DB como ISO sin tzinfo
        dt_utc = dt_local.astimezone(timezone.utc)
        remind_at_utc_iso = dt_utc.replace(tzinfo=None).isoformat()

        rid = insert_reminder(user_phone, content, remind_at_utc_iso)

        def job():
            send_fn(f"⏰ Recordatorio: {content}")
            mark_reminder_sent(user_phone, rid)

        schedule_job(rid, dt_utc, job)

        return True, (
            f"✅ Guardado #{rid}\n"
            f"🗓️ {dt_local.astimezone(TZ).strftime('%Y-%m-%d %H:%M')} (CR)\n"
            f"📝 {content}"
        )

    return False, ""
