import os
import requests
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


def send_whatsapp_text(to: str, text: str):
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
        entry = (data.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        value = change.get("value") or {}

        # 0) Status updates (sent/delivered/read)
        statuses = value.get("statuses") or []
        if statuses:
            s = statuses[0]
            print(f"📦 Status update: {s.get('status')} -> {s.get('recipient_id')}")
            return "OK", 200

        # 1) Incoming messages
        messages = value.get("messages") or []
        if not messages:
            return "OK", 200

        # Procesar todos por si vienen en batch
        for msg in messages:
            from_number = msg.get("from")
            if not from_number:
                continue

            text_body = (msg.get("text") or {}).get("body", "")
            text_body = (text_body or "").strip()
            if not text_body:
                continue

            low = text_body.lower()

            # 2) Recordatorios (por usuario)
            handled, reply = handle_reminders_commands(
                from_number,
                text_body,
                send_fn=lambda m: send_whatsapp_text(from_number, m),
            )
            if handled:
                send_whatsapp_text(from_number, reply)
                continue

            # 3) Memoria (global)
            handled, reply = handle_memory_commands(from_number, text_body)
            if handled:
                send_whatsapp_text(from_number, reply)
                continue

            # 4) IA light (solo si no matcheó comandos)
            routed = ai_route(text_body)  # dict: intent + campos
            intent = (routed.get("intent") or "").strip()

            if intent == "reminder":
                reminder_text = (routed.get("reminder_text") or "").strip()
                when = (routed.get("when") or "").strip()

                # Convertimos a tu comando actual
                if reminder_text and when:
                    synthetic = f"recordar {reminder_text} {when}"
                    handled, reply = handle_reminders_commands(
                        from_number,
                        synthetic,
                        send_fn=lambda m: send_whatsapp_text(from_number, m),
                    )
                    if handled:
                        send_whatsapp_text(from_number, reply)
                        continue

            elif intent == "memory_set":
                key = (routed.get("key") or "").strip()
                value_ = (routed.get("value") or "").strip()

                if key and value_:
                    synthetic = f"recuerda {key} = {value_}"
                    handled, reply = handle_memory_commands(from_number, synthetic)
                    if handled:
                        send_whatsapp_text(from_number, reply)
                        continue

            elif intent == "memory_get":
                key = (routed.get("key") or "").strip()

                if key:
                    synthetic = f"dato {key}"
                    handled, reply = handle_memory_commands(from_number, synthetic)
                    if handled:
                        send_whatsapp_text(from_number, reply)
                        continue

            # 5) Default
            if low in ("hola", "hi", "hello"):
                send_whatsapp_text(from_number, "¡Hola! 🤖 Soy PriBot. Escribí 'ayuda' para ver comandos.")
            else:
                send_whatsapp_text(from_number, f"Te leí: “{text_body}” ✅")

    except Exception as e:
        print("Webhook parse error:", e)

    return "OK", 200



if __name__ == "__main__":
    init_db()
    start_scheduler()
    app.run(host="0.0.0.0", port=5005, debug=True, use_reloader=False)

