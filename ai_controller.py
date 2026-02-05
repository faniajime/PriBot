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
Respondé con UN SOLO objeto JSON. No agregues texto extra.

Formato:
{
  "intent": "reminder" | "memory_set" | "memory_get" | "unknown",
  "reminder_text": "",
  "when": "",
  "key": "",
  "value": ""
}

Reglas:
- reminder: "acuérdame", "recuérdame", "recordar", "recuerdame"
- memory_set: "guardá", "recordá que", "mi X es Y", "recuerda X = Y"
- memory_get: "qué es X", "cómo se llama X", "dato X"
- Si el usuario dice “mi X se llama Y” → memory_set con key=X y value=Y
- Si dice “recuerda que mi X es Y” → memory_set
- Si pregunta “cómo se llama mi X” o “cuál es mi X” → memory_get con key=X
- Si no estás seguro: "unknown"

Ejemplos:
Usuario: "Recuerda que mi perro se llama Luna"
JSON: {"intent":"memory_set","key":"perro","value":"Luna","reminder_text":"","when":""}

Usuario: "Mi gata se llama Moka"
JSON: {"intent":"memory_set","key":"gata","value":"Moka","reminder_text":"","when":""}

Usuario: "Cómo se llama mi perro?"
JSON: {"intent":"memory_get","key":"perro","value":"","reminder_text":"","when":""}
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
    # Arreglar keys raras como "reminder\_text"
    if "reminder\\_text" in data and "reminder_text" not in data:
        data["reminder_text"] = data.pop("reminder\\_text")

    # Normalizar when: si viene "30 segundos" lo convertimos a "en 30 segundos"
    when = (data.get("when") or "").strip()
    if when:
        # si ya empieza con "en " lo dejamos
        if not when.lower().startswith("en "):
            # y si parece duración corta, agregamos "en "
            if re.search(r"^\d+\s+(segundo|segundos|minuto|minutos|hora|horas)$", when.lower()):
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
