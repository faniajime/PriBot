import os
import requests
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, request
from dotenv import load_dotenv

from memory_controller import store_memory, query_memory
from reminders_controller import create_reminder, list_user_reminders
from scheduler import start_scheduler
from db import init_db
from ai_controller import ai_route

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "pribot_verify_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


# ==================================================
# WhatsApp sender
# ==================================================
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


# ==================================================
# Webhook parsing helpers
# ==================================================
def extract_value(data: Dict[str, Any]) -> Dict[str, Any]:
    entry = (data.get("entry") or [{}])[0]
    change = (entry.get("changes") or [{}])[0]
    return change.get("value") or {}


def extract_messages(value: Dict[str, Any]) -> List[Dict[str, Any]]:
    return value.get("messages") or []


def extract_statuses(value: Dict[str, Any]) -> List[Dict[str, Any]]:
    return value.get("statuses") or []


def get_text_message_fields(msg: Dict[str, Any]) -> Tuple[Optional[str], str]:
    from_number = msg.get("from")
    text_body = (msg.get("text") or {}).get("body", "")
    return from_number, (text_body or "").strip()


# ==================================================
# AI normalization
# ==================================================
def normalize_ai_routing(routed: Dict[str, Any]) -> Dict[str, Any]:
    if not routed:
        return {"intent": "unknown"}

    # corregir reminder\_text
    if "reminder_text" not in routed and "reminder\\_text" in routed:
        routed["reminder_text"] = routed.get("reminder\\_text")

    # ✅ NORMALIZAR INTENTS (sinónimos del modelo)
    intent = (routed.get("intent") or "").strip().lower()

    if intent in ("memory_store", "store_memory", "note", "remember"):
        routed["intent"] = "memory_store"

    if intent in ("memory_query", "memory_get", "query_memory", "ask_memory", "memory_lookup"):
        routed["intent"] = "memory_get"

    if intent in ("remind", "reminder_create"):
        routed["intent"] = "reminder"

    # normalizar tiempo relativo
    when = (routed.get("when") or "").strip()
    if when and not when.lower().startswith("en "):
        routed["when"] = f"en {when}"

    # a veces el modelo usa "text" en vez de "key" para queries
    if routed.get("intent") == "memory_get":
        if not routed.get("key") and routed.get("text"):
            routed["key"] = routed.get("text")

    return routed


def handle_ai_intents(from_number: str, text_body: str) -> bool:
    routed = normalize_ai_routing(ai_route(text_body))
    print("🧭 AI routed:", routed)

    intent = routed.get("intent")

    # =======================
    # RECORDATORIOS
    # =======================
    if intent == "reminder":
        reminder_text = (routed.get("reminder_text") or "").strip()
        when = (routed.get("when") or "").strip()

        handled, reply = create_reminder(
            user_phone=from_number,
            reminder_text=reminder_text,
            when_text=when,
            send_fn=lambda m: send_whatsapp_text(from_number, m),
        )
        send_whatsapp_text(from_number, reply)
        return True

    # =======================
    # MEMORIA
    # =======================
    if intent == "memory_set":
        key = (routed.get("key") or "").strip()
        value = (routed.get("value") or "").strip()

        if key and value:
            store_memory(key, value)
            send_whatsapp_text(
                from_number,
                f"🧠 Listo, voy a recordar:\n{key} = {value}",
            )
            return True
        
    if intent == "memory_store":
        note = (routed.get("text") or "").strip()
        if note:
            # Guardar nota completa (memoria amplia)
            store_memory(note)  # <- ver nota abajo
            send_whatsapp_text(from_number, f"🧠 Anotado: {note}")
            return True
        return False

    if intent == "memory_get":
        key = (routed.get("key") or "").strip()
        if not key:
            key = (routed.get("text") or "").strip()

        if key:
            answer = query_memory(key)
            send_whatsapp_text(from_number, answer)
            return True


    return False


def handle_default(from_number: str, text_body: str) -> None:
    low = text_body.lower()
    if low in ("hola", "hi", "hello"):
        send_whatsapp_text(
            from_number,
            "¡Hola! 🤖 Soy PriBot.\n"
            "Puedo guardar recuerdos y crear recordatorios."
        )
    else:
        send_whatsapp_text(from_number, f"Te leí: “{text_body}” ✅")


# ==================================================
# Routes
# ==================================================
@app.get("/")
def health():
    return "PriBot está vivo 🤖"


@app.get("/webhook")
def verify_webhook():
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == VERIFY_TOKEN
    ):
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403


@app.post("/webhook")
def receive_webhook():
    data = request.get_json(silent=True) or {}
    print("📩 Webhook event:", data)

    try:
        value = extract_value(data)

        # 0) Status updates
        if extract_statuses(value):
            return "OK", 200

        # 1) Mensajes
        for msg in extract_messages(value):
            from_number, text_body = get_text_message_fields(msg)
            if not from_number or not text_body:
                continue

            print("📨 Incoming:", from_number, text_body)

            # 1) atajo: listar recordatorios (sin IA)
            if text_body.lower().strip() == "mis recordatorios":
                _, reply = list_user_reminders(from_number)
                send_whatsapp_text(from_number, reply)
                continue

            # 2) IA decide intent y ejecuta
            if handle_ai_intents(from_number, text_body):
                continue

            # 3) fallback
            handle_default(from_number, text_body)


    except Exception as e:
        print("Webhook error:", e)

    return "OK", 200


# ==================================================
# Main
# ==================================================
if __name__ == "__main__":
    init_db()
    start_scheduler()
    app.run(host="0.0.0.0", port=5005, debug=True, use_reloader=False)
