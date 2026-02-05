import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from datetime import datetime

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