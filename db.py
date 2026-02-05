import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

DB_PATH = "pribot.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS facts_global (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        value TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_phone TEXT NOT NULL,
        reminder_text TEXT NOT NULL,
        remind_at_utc TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'scheduled'
    );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
        );
    """)
    

    conn.commit()
    conn.close()

def upsert_global_fact(key: str, value: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    cur.execute("""
    INSERT INTO facts_global (key, value, created_at_utc, updated_at_utc)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET
        value=excluded.value,
        updated_at_utc=excluded.updated_at_utc;
    """, (key, value, now, now))

    conn.commit()
    conn.close()

def get_global_fact(key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM facts_global WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else None

def list_global_facts(limit: int = 15):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT key, value FROM facts_global
        ORDER BY updated_at_utc DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_global_fact(key: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM facts_global WHERE key=?", (key,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok

def insert_reminder(user_phone: str, reminder_text: str, remind_at_utc_iso: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("""
        INSERT INTO reminders (user_phone, reminder_text, remind_at_utc, created_at_utc, status)
        VALUES (?, ?, ?, ?, 'scheduled')
    """, (user_phone, reminder_text, remind_at_utc_iso, now))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def list_reminders(user_phone: str, limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, reminder_text, remind_at_utc, status
        FROM reminders
        WHERE user_phone=?
        ORDER BY remind_at_utc ASC
        LIMIT ?
    """, (user_phone, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_reminder_sent(user_phone: str, reminder_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE reminders
        SET status='sent'
        WHERE id=? AND user_phone=?
    """, (reminder_id, user_phone))
    conn.commit()
    conn.close()

def insert_note(text: str) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notes (text, created_at_utc) VALUES (?, ?)",
            (text, datetime.now(timezone.utc).replace(tzinfo=None).isoformat())
        )
        conn.commit()
        return cur.lastrowid

def search_notes(query: str, limit: int = 5):
    """
    Búsqueda mejorada:
    - quita stopwords comunes (como/qué/cuál/etc.)
    - usa OR en vez de AND
    - ordena por "cantidad de matches" (ranking simple)
    """
    stopwords = {
        "como", "cómo", "que", "qué", "cual", "cuál", "quien", "quién",
        "se", "llama", "es", "la", "el", "los", "las", "un", "una",
        "de", "del", "al", "a", "mi", "mis", "tu", "tus", "su", "sus",
        "por", "para", "sobre", "esto", "eso"
    }

    # tokens limpios
    raw_terms = [t.strip("¿?¡!.,:;()\"'").lower() for t in query.split()]
    terms = [t for t in raw_terms if len(t) >= 3 and t not in stopwords]
    if not terms:
        return []

    like_clauses = ["LOWER(text) LIKE ?"] * len(terms)
    where_or = " OR ".join(like_clauses)
    params = [f"%{t}%" for t in terms]

    # ranking: suma 1 por cada término que matchee
    score_expr = " + ".join([f"(CASE WHEN LOWER(text) LIKE ? THEN 1 ELSE 0 END)" for _ in terms])
    score_params = [f"%{t}%" for t in terms]

    sql = f"""
        SELECT id, text, created_at_utc,
               ({score_expr}) AS score
        FROM notes
        WHERE ({where_or})
        ORDER BY score DESC, id DESC
        LIMIT ?
    """

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (*score_params, *params, limit))
        rows = cur.fetchall()
        return [{"id": r[0], "text": r[1], "created_at_utc": r[2]} for r in rows]
