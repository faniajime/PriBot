# ai_controller.py
import json
import re
import ast
from typing import Dict

from gpt4all import GPT4All

MODEL_NAME = "mistral-7b-instruct-v0.1.Q4_0.gguf"
model = GPT4All(MODEL_NAME)

SYSTEM_PROMPT = r"""
Sos un clasificador de intención para un bot de WhatsApp.
Respondé SOLO un objeto JSON válido. No agregues texto extra.

Formato:
{
  "intent": "reminder" | "memory_store" | "memory_query" | "unknown",
  "reminder_text": "",
  "when": "",
  "text": ""
}

"intent": "reminder" | "memory_store" | "memory_get" | "unknown"
Nunca uses otros valores.

Reglas:

INTENT = reminder
- El usuario quiere que le recuerden algo en el futuro
- Palabras clave: recuerda, recuérdame, acuérdame, recordar
Ej:
Usuario: "Recuérdame ir a la plaza en 30 segundos"
JSON: {
  "intent":"reminder",
  "reminder_text":"ir a la plaza",
  "when":"30 segundos",
  "text":""
}

INTENT = memory_store
- El usuario está afirmando información para guardar
- Ejemplos:
  - "Recuerda que la abuela de memen se llama Ocha"
  - "Mi perro se llama Luna"
  - "James es profesor de biología"
JSON:
{
  "intent":"memory_store",
  "text":"la abuela de memen se llama Ocha",
  "reminder_text":"",
  "when":""
}

INTENT = memory_query
- El usuario está preguntando algo que podría estar en memoria
- Ejemplos:
  - "¿Cómo se llama la abuela de memen?"
  - "¿A qué se dedica James?"
JSON:
{
  "intent":"memory_query",
  "text":"como se llama la abuela de memen",
  "reminder_text":"",
  "when":""
}

INTENT = unknown
- Si no estás seguro

Respondé siempre JSON válido.
"""

def _extract_object_block(text: str) -> str:
    # agarra el primer {...} grande que encuentre
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else ""

def _repair_json_string(s: str) -> str:
    """
    Arregla problemas típicos:
    - saltos de línea dentro del JSON
    - backslashes sueltos \ que rompen json.loads
    """
    s = s.strip()
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")

    # Si el modelo mete backslashes raros, escaparlos para que JSON no explote:
    # Convierte \x (invalido) -> \\x (valido como string)
    s = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)

    return s

def safe_parse_to_dict(raw_text: str) -> Dict:
    """
    Nunca tira excepción. Devuelve dict con 'intent' o unknown.
    """
    block = _extract_object_block(raw_text)
    if not block:
        return {"intent": "unknown"}

    block = _repair_json_string(block)

    # 1) Intento JSON estricto
    try:
        data = json.loads(block)
        if isinstance(data, dict) and "intent" in data:
            return data
    except Exception:
        pass

    # 2) Fallback: algunos modelos devuelven "JSON" con comillas simples
    # ast.literal_eval puede parsear dict python-style de forma segura
    try:
        data = ast.literal_eval(block)
        if isinstance(data, dict):
            if "intent" not in data:
                data["intent"] = "unknown"
            return data
    except Exception:
        pass

    return {"intent": "unknown"}

def normalize_ai_fields(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return {"intent": "unknown"}

    # normalizar reminder_text mal escapado
    if "reminder\\_text" in data and "reminder_text" not in data:
        data["reminder_text"] = data.pop("reminder\\_text")

    # normalizar when
    when = (data.get("when") or "").strip()
    if when and not when.lower().startswith("en "):
        if re.search(r"\d+\s+(segundo|segundos|minuto|minutos|hora|horas)", when.lower()):
            data["when"] = f"en {when}"

    return data



def ai_route(user_text: str) -> Dict:
    """
    Router IA: devuelve intención + campos.
    """
    try:
        prompt = f"""{SYSTEM_PROMPT}

Usuario:
{user_text}

JSON:
"""

        with model.chat_session():
            response = model.generate(
                prompt,
                max_tokens=300,
                temp=0.0,   # más determinista para JSON
            )

        response = (response or "").strip()

        # Debug útil (opcional): ver qué responde el modelo
        print("🧠 AI raw:", response)

        data = safe_parse_to_dict(response)
        return normalize_ai_fields(data)


    except Exception as e:
        print("AI route error:", e)
        return {"intent": "unknown"}
