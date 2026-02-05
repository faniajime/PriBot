import re
from typing import Tuple

from db import upsert_global_fact, get_global_fact, delete_global_fact


HELP = (
    "Usá:\n"
    "• recuerda <clave> = <valor>\n"
    "• dato <clave>\n"
    "• olvida <clave>\n"
    "Ej: recuerda perro = Luna"
)


def _normalize_key(key: str) -> str:
    key = (key or "").strip()
    key = re.sub(r"\s+", " ", key)
    return key


def _try_natural_language_set(text: str) -> Tuple[bool, str, str]:
    """
    Intenta parsear frases tipo:
    - "recuerda que mi perro se llama Luna"
    - "mi perro se llama Luna"
    - "mi perro es Luna"
    Retorna: (matched, key, value)
    """
    t = (text or "").strip()

    patterns = [
        # recuerda que X es Y  (sin "mi")
        r"^recuerda\s+que\s+(?P<key>.+?)\s+es\s+(?P<value>.+)$",

        # recuerda que X se llama Y (sin "mi")
        r"^recuerda\s+que\s+(?P<key>.+?)\s+se\s+llama\s+(?P<value>.+)$",

        # recuerda que mi X se llama Y
        r"^recuerda\s+que\s+mi\s+(?P<key>.+?)\s+se\s+llama\s+(?P<value>.+)$",

        # mi X se llama Y
        r"^mi\s+(?P<key>.+?)\s+se\s+llama\s+(?P<value>.+)$",

        # recuerda que mi X es Y
        r"^recuerda\s+que\s+mi\s+(?P<key>.+?)\s+es\s+(?P<value>.+)$",

        # mi X es Y
        r"^mi\s+(?P<key>.+?)\s+es\s+(?P<value>.+)$",
    ]

    for p in patterns:
        m = re.match(p, t, flags=re.IGNORECASE)
        if m:
            key = _normalize_key(m.group("key"))
            value = (m.group("value") or "").strip()
            return True, key, value

    return False, "", ""


def _try_natural_language_get(text: str) -> Tuple[bool, str]:
    """
    Intenta parsear:
    - "cómo se llama mi perro"
    - "como se llama mi perro"
    - "cuál es mi perro"
    - "cual es mi perro"
    Retorna: (matched, key)
    """
    t = (text or "").strip()

    patterns = [
        r"^(c[oó]mo|como)\s+se\s+llama\s+mi\s+(?P<key>.+)\??$",
        r"^(cu[aá]l|cual)\s+es\s+mi\s+(?P<key>.+)\??$",
    ]

    for p in patterns:
        m = re.match(p, t, flags=re.IGNORECASE)
        if m:
            key = _normalize_key(m.group("key").rstrip("?").strip())
            return True, key

    return False, ""


def handle_memory_commands(user_phone: str, text_body: str) -> Tuple[bool, str]:
    """
    Memoria global (no depende del usuario).
    Comandos:
      - recuerda <clave> = <valor>
      - dato <clave>
      - olvida <clave>

    + lenguaje natural:
      - "recuerda que mi perro se llama Luna"
      - "mi perro se llama Luna"
      - "cómo se llama mi perro?"
    """
    text = (text_body or "").strip()
    low = text.lower().strip()

    # 1) borrar
    if low.startswith("olvida "):
        key = _normalize_key(text[len("olvida "):])
        if not key:
            return True, HELP
        delete_global_fact(key)
        return True, f"🧹 Olvidado: {key}"

    # 2) obtener (command)
    if low.startswith("dato "):
        key = _normalize_key(text[len("dato "):])
        if not key:
            return True, HELP
        val = get_global_fact(key)
        if val is None:
            return True, f"🤷 No tengo guardado: {key}"
        return True, f"📌 {key} = {val}"

    # 3) set (command) recuerda key = value
    if low.startswith("recuerda "):
        rest = text[len("recuerda "):].strip()
        if "=" not in rest:
            # permite también "recuerda que mi perro se llama Luna"
            matched, key, value = _try_natural_language_set(text)
            if matched and key and value:
                upsert_global_fact(key, value)
                return True, f"✅ Listo. Voy a recordar:\n{key} = {value}"
            return True, HELP

        key, value = rest.split("=", 1)
        key = _normalize_key(key)
        value = value.strip()
        if not key or not value:
            return True, HELP

        upsert_global_fact(key, value)
        return True, f"✅ Listo. Voy a recordar:\n{key} = {value}"

    # 4) natural language set (sin 'recuerda')
    matched, key, value = _try_natural_language_set(text)
    if matched and key and value:
        upsert_global_fact(key, value)
        return True, f"✅ Listo. Voy a recordar:\n{key} = {value}"

    # 5) natural language get
    matched, key = _try_natural_language_get(text)
    if matched and key:
        val = get_global_fact(key)
        if val is None:
            return True, f"🤷 No tengo guardado: {key}"
        return True, f"📌 {key} = {val}"

    return False, ""
