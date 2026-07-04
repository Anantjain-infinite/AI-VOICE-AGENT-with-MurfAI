"""
Chat history persistence -- replaces the old CHAT_SESSIONS / CHAT_SESSIONS_REAL
in-memory dicts in main.py with SQLite-backed storage keyed by session_id.
"""
from services.db import get_conn
from config import CHAT_HISTORY_LIMIT


def append_message(session_id: str, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )


def get_history(session_id: str, limit: int = CHAT_HISTORY_LIMIT) -> list[dict]:
    """Returns the most recent `limit` messages, oldest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages
               WHERE session_id = ?
               ORDER BY id DESC LIMIT ?""",
            (session_id, limit)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_full_history(session_id: str) -> list[dict]:
    """Full history with row ids -- used by the memory extractor to track
    which messages have already been mined."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, role, content FROM messages
               WHERE session_id = ? ORDER BY id ASC""",
            (session_id,)
        ).fetchall()
    return [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in rows]


def clear_session(session_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
