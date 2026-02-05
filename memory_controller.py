from typing import Tuple
from db import upsert_global_fact, get_global_fact, list_global_facts, delete_global_fact

def handle_memory_commands(user_phone: str, text_body: str) -> Tuple[bool, str]:
    """
    Retorna:
      (True, reply_text) si manejó el mensaje
      (False, "") si no era un comando de memoria
    """
    text = (text_body or "").strip()
    low = text.lower()

    # recuerda <clave> = <valor>
    if low.startswith("recuerda "):
        payload = text[len("recuerda "):].strip()
        if "=" not in payload:
            return True, "Usá: recuerda <clave> = <valor>\nEj: recuerda perro = Luna"

        key, value = payload.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if not key or not value:
            return True, "Usá: recuerda <clave> = <valor>\nEj: recuerda perro = Luna"

        upsert_global_fact(key, value)
        return True, f"✅ Listo. Voy a recordar:\n{key} = {value}"

    # dato <clave>
    if low.startswith("dato "):
        key = low[len("dato "):].strip()
        if not key:
            return True, "Usá: dato <clave>\nEj: dato perro"

        val = get_global_fact(key)
        if val:
            return True, f"📎 {key} = {val}"
        return True, f"No tengo guardado '{key}'.\nPodés hacer: recuerda {key} = ..."

    # mis datos
    if low == "mis datos":
        items = list_global_facts(limit=15)
        if not items:
            return True, "Aún no tengo datos guardados.\nEj: recuerda perro = Luna"

        lines = ["🧠 Tus datos guardados:"]
        for it in items:
            lines.append(f"• {it['key']} = {it['value']}")
        lines.append("\nPara borrar: olvida <clave>")
        return True, "\n".join(lines)

    # olvida <clave>
    if low.startswith("olvida "):
        key = low[len("olvida "):].strip()
        if not key:
            return True, "Usá: olvida <clave>\nEj: olvida perro"

        ok = delete_global_fact(key)
        return True, "✅ Olvidado." if ok else "No encontré ese dato."

    return False, ""
