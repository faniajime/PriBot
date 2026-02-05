# ai_controller.py
import json
import re
import ast
import threading
from typing import Dict

from gpt4all import GPT4All

MODEL_NAME = "mistral-7b-instruct-v0.1.Q4_0.gguf"

# IMPORTANTE: si tenés model_path, ponelo para evitar re-descargas raras
# model = GPT4All(MODEL_NAME, model_path="./models", allow_download=False, device="cpu")
model = GPT4All(MODEL_NAME)

_model_lock = threading.Lock()

SYSTEM_PROMPT = r"""
Sos un clasificador de intención para un bot de WhatsApp.
Respondé con UN SOLO objeto JSON. No agregues texto extra.

Formato:
{
  "intent": "reminder" | "memory_set" | "memory_store" | "memory_get" | "unknown",
  "reminder_text": "",
  "when": "",
  "key": "",
  "value": "",
  "text": ""
}

Reglas:
- reminder: "acuérdame", "recuérdame", "recordar", "recuerdame", "recuerdame"
- memory_store: si el usuario dice "recuerda que <frase>" y NO es fácil convertir a key/value -> usá "text"
- memory_set: si podés extraer par claro key/value (ej: "mi perro se llama Luna" -> key="perro", value="Luna")
- memory_get: preguntas tipo "cómo se llama X", "qué es X", "quién es X"

Ejemplos:
Usuario: "Recuerda que la abuela de memen se llama Ocha"
JSON: {"intent":"memory_store","text":"la abuela de memen se llama Ocha","key":"","value":"","reminder_text":"","when":""}

Usuario: "Mi perro se llama Luna"
JSON: {"intent":"memory_set","key":"perro","value":"Luna","text":"","reminder_text":"","when":""}

Usuario: "Cómo se llama la abuela de memen?"
JSON: {"intent":"memory_get","text":"como se llama la abuela de memen","key":"","value":"","reminder_text":"","when":""}

Usuario: "Recuérdame ir a comer con Pri en 30 seg"
JSON: {"intent":"reminder","reminder_text":"ir a comer con Pri","when":"30 seg","key":"","value":"","text":""}
"""

def _extract_object_block(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else ""

def _repair_json_string(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", s)
    return s

def safe_parse_to_dict(raw_text: str) -> Dict:
    block = _extract_object_block(raw_text)
    if not block:
        return {"intent": "unknown"}

    block = _repair_json_string(block)

    try:
        data = json.loads(block)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    try:
        data = ast.literal_eval(block)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    return {"intent": "unknown"}

def normalize_ai_fields(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return {"intent": "unknown"}

    # arreglar reminder\_text
    if "reminder\\_text" in data and "reminder_text" not in data:
        data["reminder_text"] = data.pop("reminder\\_text")

    # normalizar intent variantes
    intent = (data.get("intent") or "").strip().lower()
    if intent in ("memory_query", "query_memory", "memory_lookup"):
        intent = "memory_get"
    if intent in ("memory_store", "store_memory", "note"):
        intent = "memory_store"
    if intent in ("remember", "memory_set"):
        intent = "memory_set"
    if intent in ("remind", "reminder_create"):
        intent = "reminder"

    if intent not in ("reminder", "memory_set", "memory_store", "memory_get"):
        intent = "unknown"
    data["intent"] = intent

    # normalizar when relativo
    when = (data.get("when") or "").strip()
    if when and not when.lower().startswith("en "):
        if re.search(r"^\d+\s*(seg|segs|segundo|segundos|min|minuto|minutos|hora|horas)$", when.lower()):
            data["when"] = f"en {when}"

    return data

def ai_route(user_text: str) -> Dict:
    prompt = f"""{SYSTEM_PROMPT}

Usuario:
{user_text}

JSON:
"""
    # ✅ Lock: evita que 2 threads entren al modelo a la vez
    with _model_lock:
        try:
            with model.chat_session():
                response = model.generate(prompt, max_tokens=220, temp=0.0)
        except Exception as e:
            print("AI route error:", e)
            return {"intent": "unknown"}

    response = (response or "").strip()
    print("🧠 AI raw:", response[:800])

    # si viene puro <unk>, tratamos como unknown (suele indicar corrupción)
    if "<unk>" in response and "{" not in response:
        return {"intent": "unknown"}

    data = safe_parse_to_dict(response)
    return normalize_ai_fields(data)
