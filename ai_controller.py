import json
from gpt4all import GPT4All

# Carga del modelo (una sola vez)
model = GPT4All("mistral-7b-instruct-v0.1.Q4_0.gguf")

SYSTEM_PROMPT = """
Sos un clasificador de intención para un bot de WhatsApp.
Respondé SIEMPRE con un JSON válido, sin texto extra.

Formato EXACTO:

{
  "intent": "reminder" | "memory_set" | "memory_get" | "unknown",
  "reminder_text": "",
  "when": "",
  "key": "",
  "value": ""
}

Reglas:
- Recordatorios: "acuérdame", "recuérdame", "recordar"
- memory_set: "guardá", "recordá que", "mi X es Y"
- memory_get: "qué es X", "cómo se llama X"
- Si no estás seguro: intent = unknown
"""

def ai_route(text: str) -> dict:
    try:
        prompt = f"""
{SYSTEM_PROMPT}

Usuario:
{text}

JSON:
"""
        with model.chat_session():
            response = model.generate(
                prompt,
                max_tokens=300,
                temp=0.1
            )

        # Limpieza básica
        response = response.strip()
        start = response.find("{")
        end = response.rfind("}") + 1
        json_text = response[start:end]

        data = json.loads(json_text)
        return data if "intent" in data else {"intent": "unknown"}

    except Exception as e:
        print("AI parse error:", e)
        return {"intent": "unknown"}
