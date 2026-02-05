import os
from dotenv import load_dotenv

load_dotenv()  # ✅ ANTES de importar módulos que leen env vars

import requests
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, request

from memory_controller import store_memory, query_memory
from reminders_controller import create_reminder, list_user_reminders
from scheduler import start_scheduler
from db import init_db
from ai_controller import ai_route



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
    if not routed or not isinstance(routed, dict):
        return {"intent": "unknown"}

    # 1) Fix reminder_text key variants
    if "reminder_text" not in routed:
        if "reminder\\_text" in routed:
            routed["reminder_text"] = routed.get("reminder\\_text")
        elif "reminder_text " in routed:
            routed["reminder_text"] = routed.get("reminder_text ")

    # 2) Normalize intent synonyms from GPT4All/Mistral
    intent = (routed.get("intent") or "").strip().lower()

    # memory
    if intent in ("memory_store", "store_memory", "note", "remember", "memory_save"):
        intent = "memory_store"
    if intent in ("memory_query", "memory_get", "query_memory", "ask_memory", "memory_lookup"):
        intent = "memory_get"

    # reminder
    if intent in ("remind", "reminder_create", "create_reminder"):
        intent = "reminder"

    # canonical intents for your app
    if intent not in ("reminder", "memory_set", "memory_store", "memory_get"):
        intent = "unknown"

    routed["intent"] = intent

    # 3) Normalize relative time string: "30 segundos" -> "en 30 segundos"
    when = (routed.get("when") or "").strip()
    if when and not when.lower().startswith("en "):
        if re.search(r"^\d+\s+(segundo|segundos|minuto|minutos|hora|horas)$", when.lower()):
            routed["when"] = f"en {when}"

    # 4) IMPORTANT: do NOT set key to the whole question.
    # Use "query" for memory_get if model returns "text"
    if routed["intent"] == "memory_get":
        if not routed.get("query"):
            if routed.get("text"):
                routed["query"] = routed.get("text")
            elif routed.get("key"):
                routed["query"] = routed.get("key")

    return routed


# ==================================================
# AI action router
# ==================================================
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
    # MEMORIA (facts key/value)
    # =======================
    if intent == "memory_set":
        key = (routed.get("key") or "").strip()
        value = (routed.get("value") or "").strip()

        if key and value:
            store_memory(key=key, value=value)  # facts
            send_whatsapp_text(from_number, f"🧠 Listo. Recordaré:\n{key} = {value}")
            return True

        return False

    # =======================
    # MEMORIA (notes free-form)
    # =======================
    if intent == "memory_store":
        note = (routed.get("text") or "").strip()
        if note:
            store_memory(note=note)  # notes
            send_whatsapp_text(from_number, f"🧠 Anotado: {note}")
            return True
        return False

    # =======================
    # MEMORIA (query)
    # =======================
    if intent == "memory_get":
        q = (routed.get("query") or "").strip()
        if q:
            answer = query_memory(q)
            send_whatsapp_text(from_number, answer)
            return True
        return False

    return False


def handle_default(from_number: str, text_body: str) -> None:
    low = text_body.lower().strip()
    if low in ("hola", "hi", "hello"):
        send_whatsapp_text(
            from_number,
            "¡Hola! 🤖 Soy PriBot.\n"
            "Decime algo como:\n"
            "• 'Recuérdame tomar agua en 10 minutos'\n"
            "• 'Recuerda que la abuela de memen se llama Ocha'\n"
            "• 'Cómo se llama la abuela de memen?'"
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

        # 1) Incoming messages
        for msg in extract_messages(value):
            from_number, text_body = get_text_message_fields(msg)
            if not from_number or not text_body:
                continue

            print("📨 Incoming:", from_number, text_body)

            # Atajo: listar recordatorios sin IA
            if text_body.lower().strip() == "mis recordatorios":
                _, reply = list_user_reminders(from_number)
                send_whatsapp_text(from_number, reply)
                continue

            # IA decide intent y ejecuta
            if handle_ai_intents(from_number, text_body):
                continue

            # Fallback
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
