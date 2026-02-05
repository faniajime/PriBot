from typing import Tuple
from db import (
    upsert_global_fact,
    get_global_fact,
    delete_global_fact,
    insert_note,
    search_notes,
)

HELP = (
    "Podés decir cosas como:\n"
    "• Recuerda que la abuela de memen se llama Ocha\n"
    "• ¿Cómo se llama la abuela de memen?\n"
    "• Olvida perro\n"
)


# =========================
# Actions
# =========================

def store_memory(text: str) -> Tuple[bool, str]:
    """
    Guarda memoria como nota libre.
    (La IA ya decidió que esto es memory_store)
    """
    if not text:
        return True, HELP

    rid = insert_note(text)
    return True, f"🧠 Anotado #{rid}: {text}"


def query_memory(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "Decime qué querés buscar 🙂"

    results = search_notes(question, limit=3)
    if not results:
        return "🤷 No encontré nada en mis notas sobre eso."

    best = results[0]["text"]
    return f"🧠 Recuerdo esto:\n{best}"


def forget_memory(key: str) -> Tuple[bool, str]:
    if not key:
        return True, HELP

    delete_global_fact(key)
    return True, f"🧹 Olvidado: {key}"
