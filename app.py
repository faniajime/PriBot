import os
import requests
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, request
from dotenv import load_dotenv

from memory_controller import handle_memory_commands
from scheduler import start_scheduler
from reminders_controller import handle_reminders_commands
from db import init_db
from ai_controller import ai_route


load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "pribot_verify_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


# =========================
# WhatsApp sender
# =========================
def send_whatsapp_text(to: str, text: str) -> int:
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print("📤 Send status:", r.status_code, r.text)
    return r.status_code


# =========================
# Webhook parsing helpers
# =========================
def extract_value(data: Dict[str, Any]) -> Dict[str, Any]:
    entry = (data.get("entry") or [None])[0] or {}
    change = (entry.get("changes") or [None])[0] or {}
    value = change.get("value") or {}
    return value


def extract_messages(value: Dict[str, Any]) -> List[Dict[str, Any]]:
    return value.get("messages") or []


def extract_statuses(value: Dict[str, Any]) -> List[Dict[str, Any]]:
    return value.get("statuses") or []


def get_text_message_fields(msg: Dict[str, Any]) -> Tuple[Optional[str], str]:
    from_number = msg.get("from")
    text_body = (msg.get("text") or {}).get("body", "")
    text_body = (text_body or "").strip()
    return from_number, text_body


# =========================
# AI normalization
# =========================
def normalize_ai_routing(routed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Corrige outputs típicos de GPT4All/Mistral:
    - key "reminder\\_text" en vez de "reminder_text"
    - when: "30 segundos" -> "en 30 segundos"
    """
    if not routed:
        return {"intent": "unknown"}

    # Normalizar reminder_text
    if "reminder_text" not in routed and "reminder\\_text" in routed:
        routed["reminder_text"] = routed.get("reminder\\_text")

    # Normalizar when
    when = (routed.get("when") or "").strip()
    if when and not when.lower().startswith("en "):
        # si parece duración (seg/min/hora), agregamos "en "
        # ej: "30 segundos" -> "en 30 segundos"
        routed["when"] = f"en {when}"

    return routed


# =========================
# Message handlers
# =========================
def handle_reminders(from_number: str, text_body: str) -> bool:
    handled, reply = handle_reminders_commands(
        from_number,
        text_body,
        send_fn=lambda m: send_whatsapp_text(from_number, m),
    )
    if handled:
        send_whatsapp_text(from_number, reply)
    return handled


def handle_memory(from_number: str, text_body: str) -> bool:
    handled, reply = handle_memory_commands(from_number, text_body)
    if handled:
        send_whatsapp_text(from_number, reply)
    return handled


def handle_ai_intents(from_number: str, text_body: str) -> bool:
    routed = ai_route(text_body)
    routed = normalize_ai_routing(routed)

    print("🧭 AI routed:", routed)

    intent = (routed.get("intent") or "").strip()

    if intent == "reminder":
        reminder_text = (routed.get("reminder_text") or "").strip()
        when = (routed.get("when") or "").strip()

        if reminder_text and when:
            synthetic = f"recordar {reminder_text} {when}"
            return handle_reminders(from_number, synthetic)

        return False

    if intent == "memory_set":
        key = (routed.get("key") or "").strip()
        value_ = (routed.get("value") or "").strip()

        if key and value_:
            synthetic = f"recuerda {key} = {value_}"
            return handle_memory(from_number, synthetic)

        return False

    if intent == "memory_get":
        key = (routed.get("key") or "").strip()
        if key:
            synthetic = f"dato {key}"
            return handle_memory(from_number, synthetic)

        return False

    return False


def handle_default(from_number: str, text_body: str) -> None:
    low = text_body.lower().strip()
    if low in ("hola", "hi", "hello"):
        send_whatsapp_text(from_number, "¡Hola! 🤖 Soy PriBot. Escribí 'ayuda' para ver comandos.")
    else:
        send_whatsapp_text(from_number, f"Te leí: “{text_body}” ✅")


# =========================
# Routes
# =========================
@app.get("/")
def health():
    return "PriBot está vivo 🤖"


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.post("/webhook")
def receive_webhook():
    data = request.get_json(silent=True) or {}
    print("📩 Webhook event:", data)

    try:
        value = extract_value(data)

        # 0) Status updates (sent/delivered/read)
        statuses = extract_statuses(value)
        if statuses:
            s = statuses[0]
            print(f"📦 Status update: {s.get('status')} -> {s.get('recipient_id')}")
            return "OK", 200

        # 1) Incoming messages
        messages = extract_messages(value)
        if not messages:
            return "OK", 200

        # Procesar todos por si vienen en batch
        for msg in messages:
            from_number, text_body = get_text_message_fields(msg)
            if not from_number or not text_body:
                continue

            print("📨 Incoming text from", from_number, ":", text_body)

            # 2) Primero: comandos directos
            if handle_reminders(from_number, text_body):
                continue

            if handle_memory(from_number, text_body):
                continue

            # 3) Luego: IA light (traduce a comandos)
            if handle_ai_intents(from_number, text_body):
                continue

            # 4) Default
            handle_default(from_number, text_body)

    except Exception as e:
        print("Webhook parse error:", e)

    return "OK", 200


# =========================
# Main
# =========================
if __name__ == "__main__":
    init_db()
    start_scheduler()
    app.run(host="0.0.0.0", port=5005, debug=True, use_reloader=False)
