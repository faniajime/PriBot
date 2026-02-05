# ai_controller.py
import os
import json
import re
from typing import Dict

ENABLE_AI = os.getenv("ENABLE_AI", "1").lower() in ("1", "true", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = """
Sos un clasificador de intención para un bot de WhatsApp.
Respondé con UN SOLO objeto JSON válido (sin markdown, sin texto extra).

Formato EXACTO:
{
  "intent": "reminder" | "memory_set" | "memory_get" | "memory_store" | "unknown",
  "reminder_text": "",
  "when": "",
  "key": "",
  "value": "",
  "text": ""
}

Reglas:
- reminder: "acuérdame", "recuérdame", "recuerdame", "recordar", "recordame"
  - reminder_text = tarea
  - when = tiempo o fecha (ej: "en 30 segundos", "mañana 7pm")
- memory_set: cuando haya una relación clave=valor (ej: "mi perro se llama Luna")
  - key = "perro"
  - value = "Luna"
- memory_store: cuando sea un dato amplio en forma de frase (ej: "la abuela de memen se llama Ocha")
  - text = frase completa sin "recuerda que"
- memory_get: preguntas para recuperar (ej: "cómo se llama la abuela de memen")
  - key = la entidad consultada (ej: "abuela de memen") o una versión corta
- Si no estás seguro: unknown

Ejemplos:
Usuario: "Recuérdame ir a la plaza en 30 segundos"
JSON: {"intent":"reminder","reminder_text":"ir a la plaza","when":"en 30 segundos","key":"","value":"","text":""}

Usuario: "Mi perro se llama Luna"
JSON: {"intent":"memory_set","reminder_text":"","when":"","key":"perro","value":"Luna","text":""}

Usuario: "Recuerda que la abuela de memen se llama Ocha"
JSON: {"intent":"memory_store","reminder_text":"","when":"","key":"","value":"","text":"la abuela de memen se llama Ocha"}

Usuario: "Cómo se llama la abuela de memen?"
JSON: {"intent":"memory_get","reminder_text":"","when":"","key":"abuela de memen","value":"","text":""}
"""

def _extract_json(text: str) -> Dict:
    # intenta extraer el primer {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"intent": "unknown"}
    block = m.group(0).strip()
    try:
        return json.loads(block)
    except Exception:
        return {"intent": "unknown"}

def _normalize(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return {"intent": "unknown"}

    data.setdefault("intent", "unknown")
    data.setdefault("reminder_text", "")
    data.setdefault("when", "")
    data.setdefault("key", "")
    data.setdefault("value", "")
    data.setdefault("text", "")

    # normalizar intent sinónimos
    intent = (data.get("intent") or "").strip().lower()
    if intent in ("memory_query", "query_memory", "memory_lookup"):
        intent = "memory_get"
    if intent in ("store_memory", "note", "remember"):
        intent = "memory_store"
    if intent in ("remind", "reminder_create"):
        intent = "reminder"
    data["intent"] = intent if intent else "unknown"

    # when: si viene "30 segundos" => "en 30 segundos"
    when = (data.get("when") or "").strip()
    if when and not when.lower().startswith("en "):
        if re.search(r"^\d+\s+(segundo|segundos|minuto|minutos|hora|horas)$", when.lower()):
            data["when"] = f"en {when}"

    # memory_store: a veces meten en "text" o en "value"
    if data["intent"] == "memory_store" and not data.get("text"):
        maybe = (data.get("value") or "").strip()
        if maybe:
            data["text"] = maybe

    return data

def ai_route(user_text: str) -> Dict:
    ENABLE_AI = os.getenv("ENABLE_AI", "1").lower() in ("1","true","yes")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    print("🔑 has_key?", bool(OPENAI_API_KEY), "model:", OPENAI_MODEL, "enable:", ENABLE_AI)


    if not ENABLE_AI or not OPENAI_API_KEY:
        return {"intent": "unknown"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0,
            max_tokens=220,
        )

        raw = (resp.choices[0].message.content or "").strip()
        print("🧠 AI raw:", raw)

        data = _extract_json(raw)
        return _normalize(data)

    except Exception as e:
        print("AI route error:", e)
        return {"intent": "unknown"}
