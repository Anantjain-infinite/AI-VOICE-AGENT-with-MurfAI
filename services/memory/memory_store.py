"""
Long-term user memory: durable facts extracted from past conversations,
keyed by user_id (stable across sessions -- see static/js/app.js for how
the frontend generates/persists a user_id separately from session_id).
"""
from services.db import get_conn
from config import MEMORY_FACT_LIMIT


def add_fact(user_id: str, fact: str, category: str = "general"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO memories (user_id, fact, category) VALUES (?, ?, ?)",
            (user_id, fact, category)
        )


def get_facts(user_id: str, limit: int = MEMORY_FACT_LIMIT) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, fact, category, created_at FROM memories
               WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_fact(user_id: str, fact_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM memories WHERE id = ? AND user_id = ?",
            (fact_id, user_id)
        )
    return cur.rowcount > 0


def clear_facts(user_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
